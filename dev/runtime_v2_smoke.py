"""Owner-run smoke of /api/v2 on the real LAN: bounded discovery, capabilities, Freebox read_facts, diagnosis.
Read-only. Prints counts and finding names/kinds only (no labels, addresses or identifiers)."""
import json
import threading
import urllib.request
from collections import Counter

from src.server import create_server


def main():
    s = create_server(0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{s.server_port}'
    get = lambda p: json.loads(urllib.request.urlopen(base + p, timeout=120).read())
    csrf = get('/api/session')['csrf_token']
    def ex(pid, key, params=None, consent=False):
        req = urllib.request.Request(base + '/api/v2/execute', json.dumps({'primitive_id': pid, 'device_key': key, 'params': params or {}, 'consent': consent}).encode(),
                                     {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Origin': base})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())
    out = {}
    r = ex('bounded_discovery', 'fabric', {'providers': ['mdns', 'ssdp', 'android', 'freebox', 'ble']})
    out['discovery'] = {'state': r['state'], 'verified': r['verified'], 'providers': {k: v.get('status') for k, v in r['result'].get('providers', {}).items()}}
    graph = get('/api/v2/graph')
    out['graph'] = dict(Counter(d['category'] for d in graph['devices']))
    caps = get('/api/v2/capabilities')['capabilities']
    out['capabilities'] = {'total': len(caps), 'readable': sum(c['readable'] for c in caps), 'controllable': sum(c['controllable'] for c in caps),
                           'verified_states': dict(Counter(c['verified'] for c in caps))}
    router = next((d['device_key'] for d in graph['devices'] if d['category'] == 'router'), None)
    if router:
        f = ex('read_facts', router)
        out['freebox_read_facts'] = {'state': f['state'], 'verified': f['verified'], 'errors': f['errors'],
                                     'findings': sorted(f'{x["name"]}:{x["kind"]}' for x in f['result'].get('facts', []) if not x['name'].startswith(('temperature_', 'fan_', 'wifi_')))}
    out['refusals'] = {'free_form': ex('adb_shell', router or 'x', {'cmd': 'reboot'})['errors'][0][:40],
                       'write_without_consent': ex('android_optional_app_state', router or 'x', {'plan_id': 'p'})['errors'][0][:40]}
    out['diagnosis'] = [f'{x["name"]}={x["value"]} ({x["kind"]})' for x in get('/api/v2/diagnosis')['findings']]
    out['recovery'] = get('/api/v2/recovery')
    print(json.dumps(out, indent=1, ensure_ascii=False))
    s.shutdown()


if __name__ == '__main__':
    main()
