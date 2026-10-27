"""Privacy-Preserving Cloud Escalation (V4-05). Never called "zero-knowledge": Meta receives the reviewed subset.

Flow (no silent transfer, no fallback to cloud):
1. preview(analysis, rows): build a coarse local projection of the timeline hypotheses (device aliases, times
   relative to the first symptom and rounded to 10 s, no labels), run it through src/runtime/redact.prepare
   (fails closed), and keep the EXACT outgoing bytes. Returns the original projection, the outgoing payload, the
   field diff, the categories shared and the payload SHA-256.
2. confirm(preview_id, sha256, consent=True): only then are those same bytes sent to `muse-spark-1.3` through the
   supervised RuntimeModelBroker reservation ($0.10 per call, $1 total, unchanged). No retry.
3. The answer is untrusted: it may only rank hypothesis ids that were sent, must contain no identifier-like string,
   and may not propose any action other than a read-only check. Aliases are mapped back locally only.
4. The receipt stores model id, policy hash, payload hash, decision, latency — never the payload itself.
Without a broker (no key / no fresh credit permit) the state is UNAVAILABLE; a recorded call is never shown as live.
"""
import hashlib
import json
import secrets
import threading
import time

from src.ai.broker import MODEL_ID, ModelBlocked
from src.runtime import redact

PREVIEW_TTL_S = 300
POLICY = ('V4-05 policy v1: aliases per request; times relative and rounded to 10 s; labels, names, serials, MACs, '
          'IPs, SSIDs, hostnames, URLs, e-mails, phone numbers dropped or aliased; fail closed on any leak; '
          'one explicit consent per payload; answer limited to ranking sent hypothesis ids + a read-only check.')
POLICY_SHA = hashlib.sha256(POLICY.encode()).hexdigest()[:16]
CATEGORIES = ('device categories (tv, phone, router, ...)', 'fact names and values from read-only diagnostics',
              'relative timing of changes (10 s resolution)', 'the local hypotheses and their counts')
TERMS_URL = 'https://dev.meta.ai/docs'
SYSTEM = ('You review a home-network timeline that was minimised before leaving the device. Devices are aliases. '
          'Return ONLY a JSON object: {"ranking": [hypothesis ids from the input, best first], "summary": string, '
          '"uncertainty": string, "next_read_only_check": string}. Say "consistent with", never "caused by". '
          'Do not invent devices, identifiers, commands or write actions.')


def projection(analysis, rows):
    cited = {c for h in analysis.get('hypotheses', []) for c in h['cites']}
    by_id = {r['id']: r for r in rows}
    sym = [by_id[s] for s in analysis.get('symptoms', []) if s in by_id]
    t0 = min((s['t'] for s in sym), default=0)
    devices = {}
    def dev(k):
        return devices.setdefault(k, f'device_{len(devices) + 1}')
    dev(analysis.get('target', ''))
    events = []
    for i in sorted(cited, key=lambda x: int(x[1:])):
        r = by_id.get(i)
        if r is None:
            continue
        v = r['value'] if isinstance(r['value'], (int, float, bool, str)) or r['value'] is None else 'structured'
        events.append({'ref': i, 'device': dev(r['device_key']), 'category': r['category'], 'fact': r['name'],
                       'value': v, 'unit': r.get('unit', ''), 'relative_s': int(round((r['t'] - t0) / 10.0) * 10)})
    return {'question': 'Which hypothesis best fits these observations, and what single read-only check would discriminate?',
            'target': 'device_1', 'window_s': analysis.get('window_s'),
            'hypotheses': [{'id': h['id'], 'statement': h['statement'], 'confidence': h['confidence'], 'support': h['support'],
                            'counterexamples': h['counterexamples']} for h in analysis.get('hypotheses', [])],
            'events': events}, {v: k for k, v in devices.items()}


class CloudEscalation:
    def __init__(self, broker=None, clock=time.monotonic):
        self.broker = broker
        self.clock = clock
        self._pending = {}
        self._lock = threading.Lock()
        self.receipts = []

    def available(self):
        return self.broker is not None and getattr(self.broker, 'transport', None) is not None

    def preview(self, analysis, rows):
        if analysis.get('verdict') != 'HYPOTHESES':
            raise ModelBlocked('Nothing to escalate: no symptom in the timeline')
        local, aliases = projection(analysis, rows)
        prepared = redact.prepare(local)                     # raises LeakDetected -> nothing leaves
        body = prepared['payload'].decode()
        sha = hashlib.sha256(prepared['payload']).hexdigest()
        pid = 'pv-' + secrets.token_hex(8)
        with self._lock:
            self._pending = {k: v for k, v in self._pending.items() if self.clock() - v['at'] < PREVIEW_TTL_S}
            self._pending[pid] = {'at': self.clock(), 'body': body, 'sha': sha, 'aliases': aliases,
                                  'ids': [h['id'] for h in analysis['hypotheses']]}
        return {'preview_id': pid, 'model': MODEL_ID, 'live_available': self.available(), 'categories_shared': list(CATEGORIES),
                'local_projection': local, 'outgoing_payload': body, 'diff': prepared['diff'], 'sha256': sha,
                'bytes': prepared['stats']['bytes'], 'policy_sha': POLICY_SHA, 'expires_in_s': PREVIEW_TTL_S,
                'terms_url': TERMS_URL, 'disclosure': 'Data minimisation, not anonymity: categories and timing can still be informative.'}

    def confirm(self, preview_id, sha256, consent):
        if consent is not True:
            raise ModelBlocked('Explicit consent is required for each payload')
        with self._lock:
            p = self._pending.pop(preview_id, None)
        if p is None or self.clock() - p['at'] >= PREVIEW_TTL_S:
            raise ModelBlocked('Unknown or expired preview; build a new one')
        if sha256 != p['sha']:
            raise ModelBlocked('Payload hash differs from the reviewed preview')
        if not self.available():
            self._receipt(p, 'UNAVAILABLE', None, 0)
            raise ModelBlocked('Meta cloud unavailable (no key or no fresh credit permit); local analysis remains')
        payload = {'model': MODEL_ID, 'max_completion_tokens': 4000,
                   'messages': [{'role': 'developer', 'content': SYSTEM}, {'role': 'user', 'content': p['body']}]}
        assert payload['messages'][1]['content'] == p['body']          # exactly the reviewed bytes
        self.broker._reserve()                                         # committed before network I/O
        started = time.monotonic()
        try:
            resp = self.broker.transport(payload)
        except Exception:
            self._receipt(p, 'FAILED', None, time.monotonic() - started)
            raise ModelBlocked('Meta call failed; reservation retained; no automatic retry') from None
        try:
            out = self.validate(resp, p['ids'])
        except ModelBlocked:
            self._receipt(p, 'REJECTED', resp.get('id') if isinstance(resp, dict) else None, time.monotonic() - started)
            raise
        rec = self._receipt(p, 'ACCEPTED', resp.get('id'), time.monotonic() - started, resp.get('usage'))
        return {'state': 'LIVE', 'model': MODEL_ID, 'answer': out, 'receipt': rec,
                'note': 'Untrusted model output: ranking only, validated locally; nothing was executed.'}

    @staticmethod
    def validate(resp, ids):
        if not isinstance(resp, dict) or resp.get('model') != MODEL_ID:
            raise ModelBlocked('Returned model identity is not approved')
        try:
            content = resp['choices'][0]['message'].get('content')
            ans = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelBlocked('Invalid model answer') from None
        if not isinstance(ans, dict) or set(ans) != {'ranking', 'summary', 'uncertainty', 'next_read_only_check'}:
            raise ModelBlocked('Invalid answer schema')
        if not isinstance(ans['ranking'], list) or not ans['ranking'] or any(r not in ids for r in ans['ranking']) \
                or len(set(ans['ranking'])) != len(ans['ranking']):
            raise ModelBlocked('Ranking cites unknown hypotheses')
        for k in ('summary', 'uncertainty', 'next_read_only_check'):
            if not isinstance(ans[k], str) or not 1 <= len(ans[k]) <= 1500:
                raise ModelBlocked('Malformed answer')
        text = ' '.join(ans[k] for k in ('summary', 'uncertainty', 'next_read_only_check'))
        if redact.scan(text):
            raise ModelBlocked('Answer introduced identifier-like values')
        low = text.lower()
        if any(w in low for w in ('caused by', 'adb shell', 'reboot', 'factory reset', 'rm -', 'disable ', 'uninstall')):
            raise ModelBlocked('Answer claims a cause or proposes an action')
        return ans

    def _receipt(self, p, decision, request_id, latency_s, usage=None):
        r = {'model': MODEL_ID, 'policy_sha': POLICY_SHA, 'payload_sha256': p['sha'], 'decision': decision,
             'request_id': request_id, 'latency_ms': round(latency_s * 1000), 'usage': usage,
             'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        self.receipts.append(r)
        return r
