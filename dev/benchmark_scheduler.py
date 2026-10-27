"""V4-12 benchmark: same synthetic prompt on every ready worker (this PC, and the owner-declared LAN PC).
Measures probe latency and generation tokens/s, then shows which worker the scheduler would choose.
Synthetic data only. Writes artifacts/scheduler/<date>.json.  Run: python -m dev.benchmark_scheduler"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

from src.ai import scheduler

PROMPT = [{'role': 'user', 'content': 'SIMULATED facts: battery 72%, storage 3.1 GB free. In one sentence, name one read-only check.'}]


def http(ep, path, body=None, timeout=300):
    req = Request(ep + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'},
                  method='GET' if body is None else 'POST')
    with build_opener(ProxyHandler({})).open(req, timeout=timeout) as r:
        return json.loads(r.read(1 << 20))


def main():
    rows = []
    workers = scheduler.default_workers()
    for w in workers:
        w.probe(lambda ep: http(ep, '/api/tags', timeout=3))
        if not w.ready:
            rows.append(w.row()); continue
        t = time.monotonic()
        r = http(w.endpoint, '/api/chat', {'model': w.model_id, 'stream': False, 'messages': PROMPT, 'options': {'temperature': 0, 'num_predict': 120}})
        dt = time.monotonic() - t
        if r.get('eval_count') and r.get('eval_duration'):
            w.tokens_per_s = round(r['eval_count'] / (r['eval_duration'] / 1e9), 2)
        rows.append(dict(w.row(), wall_s=round(dt, 2)))
    out = {'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'workers': rows}
    for model in {w.model_id for w in workers}:
        try:
            _, why = scheduler.choose(workers, model, 'redacted')
            out.setdefault('choice', {})[model] = why
        except scheduler.SchedulerBlocked as e:
            out.setdefault('choice', {})[model] = str(e)
    p = Path('artifacts/scheduler'); p.mkdir(parents=True, exist_ok=True)
    f = p / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json'); f.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1)); print('saved', f)


if __name__ == '__main__':
    main()
