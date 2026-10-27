# Requires the Capability Forge package (src/forge) next to this tree: run from a merged copy, not from the runtime branch alone.
"""Owner-authorized: real Companion relay on the USB phone through the product server paths, then Forge's
unmodified RuntimeV1Provider reads the result through the trusted v2 reader. Prints sanitized results only."""
import json, os, re, subprocess, time
os.environ['OPENBRIDGE_COMPANION_APK'] = r'C:\Users\TheBox\Desktop\Hackaton\OpenBridge\artifacts\companion\openbridge-companion.apk'
from src.server import create_server
from src.runtime import api_v2
from src.runtime.primitives import Executor
from src.forge.runtime_bridge import RuntimeV1Provider

out = {}
s = create_server(0)
ex = api_v2.executor(s)
out['discovery'] = ex.execute('bounded_discovery', 'fabric', {'providers': ['android']})['state']
phone_key = next(k for k, d in s.fabric_registry.devices.items() if d['category'] == 'phone')
handle = s.fabric_registry.devices[phone_key]['handles']['USB']
serial = next(k for k, v in s.android._handles.items() if v == handle)
code, st = s.start_companion_install(handle, attempts=3, delay=5)
for _ in range(60):
    if s.companion_install.get('state') not in ('RETRYING',):
        break
    time.sleep(1)
out['install'] = s.companion_install.get('state')
adb = lambda *a: subprocess.run(['adb', '-s', serial, *a], capture_output=True, text=True, encoding='utf-8', timeout=30).stdout
for p in ('BLUETOOTH_SCAN', 'BLUETOOTH_CONNECT'):
    adb('shell', 'pm', 'grant', 'fr.openbridge.companion', 'android.permission.' + p)
adb('shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
time.sleep(4)
pair = s.relay_action('/api/relay-pair-start', {'device_id': handle})
rid = pair['relay_id']
time.sleep(1.5)
adb('shell', 'uiautomator', 'dump', '/sdcard/ob_ui.xml'); xml = adb('shell', 'cat', '/sdcard/ob_ui.xml'); adb('shell', 'rm', '/sdcard/ob_ui.xml')
m = re.search(r'Pairing code (\d{6})', xml)
out['code_read_from_screen'] = bool(m)
conf = s.relay_action('/api/relay-pair-confirm', {'device_id': handle, 'code': m.group(1)})
out['paired'] = conf['state']; out['eligible'] = conf['eligible_for_ble']
r = ex.execute('relay_ble_scan', phone_key, {'relay_id': rid, 'seconds': 8}, consent=True)
out['scan'] = {'state': r['state'], 'verified': r['verified'], 'advertisers': r['result'].get('advertisers'), 'errors': r['errors']}
read = api_v2.reader(s)
caps = [c for c in read('/api/v2/capabilities')['capabilities'] if c['name'] == 'ble_relay']
out['ble_relay_capability'] = [{k: c[k] for k in ('readable', 'controllable', 'verified', 'reversibility')} for c in caps]
out['route'] = [{k: x[k] for k in ('permission_granted', 'owner_enabled', 'online', 'status')} for x in read('/api/v2/routes')['routes']]
targets = [l['child'] for l in read('/api/v2/graph')['links'] if l['source'] == 'RELAY:' + rid]
results = []
for t in targets:
    try:
        p = RuntimeV1Provider(read, phone_key + ':ble_relay', t, rid)
        m = p.snapshot(p.capability_id)
        results.append(('OK', m['status'], round(time.time() - m['observed_at'], 1)))
    except Exception as e:
        results.append(('REFUSED', str(e)))
out['forge_snapshots'] = {'targets': len(targets), 'accepted': sum(1 for x in results if x[0] == 'OK'),
                          'refusal_reasons': sorted({x[1] for x in results if x[0] == 'REFUSED'}),
                          'example_ok': next((x for x in results if x[0] == 'OK'), None)}
import urllib.request
from src.forge.demo_host import create_forge_server
import threading
ok_target = next(t for t, x in zip(targets, results) if x[0] == 'OK')
prov = RuntimeV1Provider(read, phone_key + ':ble_relay', ok_target, rid)
fs = create_forge_server(0, provider=prov, capability_id=prov.capability_id)
threading.Thread(target=fs.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{fs.server_port}'
tok = json.loads(urllib.request.urlopen(base + '/api/session').read())['token']
def call(path, body=None):
    h = {'Authorization': 'Bearer ' + tok}
    if body is not None:
        h.update({'Content-Type': 'application/json', 'Origin': base})
    req = urllib.request.Request(base + path, json.dumps(body).encode() if body is not None else None, h)
    try:
        r = urllib.request.urlopen(req); return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
http = {}
c = call('/api/catalog')[1]; http['catalog_mode'] = c['mode']; http['available'] = c['available']
http['publish'] = call('/api/publish', {'consent': True})
st, obs = call(fs.observation_path)
http['read'] = (st, {'simulation': obs.get('simulation'), 'observations': len(obs.get('observations', [])), 'source_is_relay': str(obs.get('source', '')).startswith('RELAY:')})
st, docs = call('/api/documents'); http['documents'] = (st, sorted(docs)[:6] if st == 200 else docs)
ex.execute('relay_revoke', phone_key, {'relay_id': rid}, consent=True)
http['read_after_revoke'] = call(fs.observation_path)
http['remove'] = call('/api/remove', {})
http['read_after_remove'] = call(fs.observation_path)
out['forge_http_physical'] = http
fs.shutdown(); fs.server_close()
out['open_session_changes'] = [c['title'] for c in s.session_journal.open_changes()]
print(json.dumps(out, indent=1, default=str))
