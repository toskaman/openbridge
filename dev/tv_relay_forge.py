# Requires the Capability Forge package (src/forge) next to this tree: run from a merged copy.
"""Owner-authorized: real Android TV relay over the LAN (Wi-Fi ADB) through product paths, consumed by Forge.
Every environment change is journaled for Finish session. Prints sanitized results only."""
import json, os, re, subprocess, time
os.environ['OPENBRIDGE_COMPANION_APK'] = r'C:\Users\TheBox\Desktop\Hackaton\OpenBridge\artifacts\companion\openbridge-companion.apk'
from src.server import create_server
from src.runtime import api_v2
from src.forge.runtime_bridge import RuntimeV1Provider

out = {}
s = create_server(0)
ex = api_v2.executor(s)
out['discovery'] = ex.execute('bounded_discovery', 'fabric', {'providers': ['android']})['state']
tv = next(k for k, d in s.fabric_registry.devices.items() if d['category'] == 'tv' and any(i.strong for i in d['identifiers']))
handle = next(iter(s.fabric_registry.devices[tv]['handles'].values()))
serial = next(k for k, v in s.android._handles.items() if v == handle)
adb = lambda *a: subprocess.run(['adb', '-s', serial, *a], capture_output=True, text=True, encoding='utf-8', timeout=60).stdout
if 'com.android.bluetooth' in adb('shell', 'pm', 'list', 'packages', '-d'):
    adb('shell', 'pm', 'enable', 'com.android.bluetooth')
    s.session_journal.record('system_package_enabled', 'Android TV', {'serial': serial, 'package': 'com.android.bluetooth'}, 3, 1)
    time.sleep(3)
out['bt_app_enabled'] = 'com.android.bluetooth' not in adb('shell', 'pm', 'list', 'packages', '-d')
s.start_companion_install(handle, attempts=3, delay=5)
for _ in range(90):
    if s.companion_install.get('state') != 'RETRYING':
        break
    time.sleep(1)
out['install'] = s.companion_install.get('state')
adb('shell', 'pm', 'grant', 'fr.openbridge.companion', 'android.permission.ACCESS_FINE_LOCATION')
adb('shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
time.sleep(5)
pair = s.relay_action('/api/relay-pair-start', {'device_id': handle})
rid = pair['relay_id']
time.sleep(2)
adb('shell', 'uiautomator', 'dump', '/sdcard/ob_ui.xml'); xml = adb('shell', 'cat', '/sdcard/ob_ui.xml'); adb('shell', 'rm', '/sdcard/ob_ui.xml')
m = re.search(r'Pairing code (\d{6})', xml)
out['code_read_from_screen'] = bool(m)
conf = s.relay_action('/api/relay-pair-confirm', {'device_id': handle, 'code': m.group(1)})
out['paired'] = conf['state']; out['eligible'] = conf['eligible_for_ble']
r = ex.execute('relay_ble_scan', tv, {'relay_id': rid, 'seconds': 10}, consent=True)
out['scan'] = {'state': r['state'], 'verified': r['verified'], 'advertisers': r['result'].get('advertisers'), 'errors': r['errors']}
read = api_v2.reader(s)
targets = [l['child'] for l in read('/api/v2/graph')['links'] if l['source'] == 'RELAY:' + rid]
res = []
for t in targets:
    try:
        p = RuntimeV1Provider(read, tv + ':ble_relay', t, rid); m2 = p.snapshot(p.capability_id); res.append(('OK', m2['status']))
    except Exception as e:
        res.append(('REFUSED', str(e)))
out['forge'] = {'targets': len(targets), 'accepted': sum(x[0] == 'OK' for x in res), 'statuses': sorted({x[1] for x in res})}
if targets:
    out['source_filtered_facts'] = [f['name'] for f in read(f'/api/v2/facts?device={targets[0]}&source=RELAY%3A{rid}')['facts']]
ex.execute('relay_revoke', tv, {'relay_id': rid}, consent=True)
try:
    p = RuntimeV1Provider(read, tv + ':ble_relay', targets[0], rid); p.snapshot(p.capability_id); out['after_revoke'] = 'NOT BLOCKED'
except Exception as e:
    out['after_revoke'] = str(e)
out['open_session_changes'] = [c['title'] for c in s.session_journal.open_changes()]
s.server_close()
print(json.dumps(out, indent=1))
