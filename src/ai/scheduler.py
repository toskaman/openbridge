"""Cost-aware Meta inference scheduler (V4-12), narrow by design.

The second PC is a client device like the others. For Meta inference it is used as an Ollama endpoint on the LAN
serving the same pinned weights (this module). Arbitrary owner jobs go through the separate, consent-gated
`pc_job` primitive (BridgeWindows exec.run), not through this scheduler.

A LAN worker must be declared by the owner in a local file (never committed):
    %LOCALAPPDATA%/OpenBridge/workers.json  ->  {"workers": [{"endpoint": "http://192.168.1.20:11438", "model_id": "...", "label": "PC 2"}]}
and is used only if: private address, model is a pinned Meta model, its /api/tags digest equals the pinned digest,
and the request's data class is allowed off-box ('redacted' or 'synthetic'; never 'raw').
Policy: among ready workers allowed for the data class, pick the lowest expected latency; cost is 0 for local/LAN
(own hardware), and the hosted model is never chosen by the scheduler (it has its own consent flow)."""
import ipaddress
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

from src.ai.glimmer import GLIMMER_ID, GLIMMER_DIGEST, GLIMMER_ENDPOINT
from src.ai.local_meta import MODEL_ID as LLAMA_ID, MODEL_DIGEST as LLAMA_DIGEST, LOCAL_ENDPOINT as LLAMA_ENDPOINT

PINNED = {GLIMMER_ID: GLIMMER_DIGEST, LLAMA_ID: LLAMA_DIGEST}
DATA_CLASSES = {'raw': ('local',), 'redacted': ('local', 'lan'), 'synthetic': ('local', 'lan')}


class SchedulerBlocked(ValueError):
    pass


def owner_workers(path=None):
    p = Path(path or Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'workers.json')
    try:
        rows = json.loads(p.read_text(encoding='utf-8')).get('workers', [])
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for r in rows[:4]:
        try:
            out.append(Worker(r['endpoint'], r['model_id'], 'lan', str(r.get('label', 'LAN worker'))[:40]))
        except (KeyError, SchedulerBlocked):
            continue
    return out


class Worker:
    def __init__(self, endpoint, model_id, kind, label=''):
        u = urlsplit(endpoint)
        if model_id not in PINNED:
            raise SchedulerBlocked('not a pinned Meta model')
        if u.scheme != 'http' or not u.hostname or u.path not in ('', '/') or u.query:
            raise SchedulerBlocked('endpoint must be http://host:port')
        ip = ipaddress.ip_address(u.hostname)
        if kind == 'local' and not ip.is_loopback:
            raise SchedulerBlocked('local worker must be loopback')
        if kind == 'lan' and (not ip.is_private or ip.is_loopback or ip.is_link_local):
            raise SchedulerBlocked('LAN worker must be a private, non-loopback address')
        self.endpoint, self.model_id, self.kind, self.label = endpoint.rstrip('/'), model_id, kind, label or kind
        self.digest = PINNED[model_id]
        self.ready, self.latency_ms, self.tokens_per_s = False, None, None

    def probe(self, tags):
        """tags: callable(endpoint) -> /api/tags JSON. Readiness = pinned digest present."""
        t = time.monotonic()
        try:
            rows = tags(self.endpoint).get('models', [])
            self.ready = any(r.get('name') == self.model_id and r.get('digest', '').removeprefix('sha256:') == self.digest for r in rows)
        except Exception:
            self.ready = False
        self.latency_ms = round((time.monotonic() - t) * 1000)
        return self.ready

    def row(self):
        return {'label': self.label, 'kind': self.kind, 'model_id': self.model_id, 'ready': self.ready,
                'probe_ms': self.latency_ms, 'tokens_per_s': self.tokens_per_s, 'cost_usd': 0.0}


def default_workers():
    return [Worker(GLIMMER_ENDPOINT, GLIMMER_ID, 'local', 'this PC (Glimmer)'), Worker(LLAMA_ENDPOINT, LLAMA_ID, 'local', 'this PC (Llama 3B)')] + owner_workers()


def choose(workers, model_id, data_class, expected_tokens=400):
    if data_class not in DATA_CLASSES:
        raise SchedulerBlocked('unknown data class')
    allowed = [w for w in workers if w.model_id == model_id and w.kind in DATA_CLASSES[data_class] and w.ready]
    trace = [dict(w.row(), eligible=w in allowed,
                  why=('ready' if w.ready else 'not ready / digest mismatch') if w.kind in DATA_CLASSES[data_class] else f'{data_class} data never leaves this PC')
             for w in workers if w.model_id == model_id]
    if not allowed:
        raise SchedulerBlocked('no ready worker for this model and data class')
    def expected_ms(w):
        tps = w.tokens_per_s or (8.0 if w.kind == 'local' else 8.0)
        return (w.latency_ms or 0) + expected_tokens / tps * 1000
    best = min(allowed, key=lambda w: (expected_ms(w), w.kind != 'local'))
    return best, {'chosen': best.label, 'expected_ms': round(expected_ms(best)), 'candidates': trace,
                  'policy': 'lowest expected latency among ready, digest-verified workers allowed for this data class; cost 0 on own hardware'}
