"""Hardware proof for V4-07: with OpenBridge running (--local-meta --glimmer) and the TV/phone discovered over ADB,
run one consent-gated visual read-back and print the sanitized receipt (verdict, classes, frame hash; no image).
    python -m dev.visual_readback_tv --device <device_key from /api/v2/graph>
"""
import argparse
import json
import urllib.request

BASE = 'http://127.0.0.1:18765'


def call(path, body=None, token=''):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), method='GET' if body is None else 'POST',
                                 headers={'Content-Type': 'application/json', 'Origin': BASE, 'X-CSRF-Token': token})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=400) as r:
        return json.loads(r.read())


if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--device', required=True); a = a.parse_args()
    tok = call('/api/session')['csrf_token']
    r = call('/api/v2/execute', {'primitive_id': 'visual_readback', 'device_key': a.device, 'params': {}, 'consent': True}, tok)
    print(json.dumps({k: r[k] for k in ('transaction_id', 'state', 'after', 'verified', 'errors')} | {'result': r['result']}, indent=1))
