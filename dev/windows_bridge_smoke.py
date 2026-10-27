"""Owner-run: accept the owner's BridgeWindows agent (read-only allowlist), discover it, read diagnostics.
Prints sanitized results only (no hostname, IP, GUID or process names)."""
import json, time
from src.runtime import api_v2
from src.server import create_server, start_windows_bridge

s = create_server(0)
s.windows_bridge = start_windows_bridge()
out = {'listening_on_lan_only': s.windows_bridge.bind_ip not in ('0.0.0.0', '127.0.0.1')}
for _ in range(60):
    if s.windows_bridge.connected():
        break
    time.sleep(1)
out['agent_connected'] = s.windows_bridge.connected()
out['agent'] = s.windows_bridge.hello
if out['agent_connected']:
    ex = api_v2.executor(s)
    d = ex.execute('bounded_discovery', 'fabric', {'providers': ['windows']})
    out['discovery'] = (d['state'], d['result'].get('providers', {}).get('windows'))
    key = next((k for k, v in s.fabric_registry.devices.items() if v['category'] == 'computer'), None)
    if key:
        r = ex.execute('read_facts', key, {})
        out['read_facts'] = {'state': r['state'], 'verified': r['verified'], 'errors': r['errors'],
                             'findings': [f'{f["name"]}={f["value"]}{f["unit"]} ({f["kind"]})' for f in r['result'].get('facts', [])]}
        caps = api_v2.reader(s)('/api/v2/capabilities?device=' + key)['capabilities']
        out['capabilities'] = sorted(f"{c['name']}:{c['verified']}:{'ctl' if c['controllable'] else 'ro'}" for c in caps)
        try:
            s.windows_bridge.call('exec.run', {'cmd': 'whoami'})
            out['forbidden_call'] = 'SENT (BUG)'
        except ValueError as e:
            out['forbidden_call'] = 'refused before sending: ' + str(e)
s.server_close()
print(json.dumps(out, indent=1, ensure_ascii=False))
