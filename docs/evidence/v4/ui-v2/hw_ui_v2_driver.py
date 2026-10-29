"""Owner-authorized hardware run of UI layout v2 on the Android TV Companion (0.8.0), isolated server :18780.
Presses are driven by adb (owner-authorized automation), labeled as such in the transcript."""
import json, re, subprocess, sys, time, urllib.request, urllib.error
sys.path.insert(0, r'C:\Users\TheBox\Desktop\Hackaton\OpenBridge-v4')
from src.substrate.kernel import manifest_hash
B = 'http://127.0.0.1:18780'; TV = '192.168.1.15:5555'
OUT = r'C:\Users\TheBox\Desktop\Hackaton\.xbuild\HW_UI_V2_TRANSCRIPT.json'
CSRF = json.loads(urllib.request.urlopen(B + '/api/session').read())['csrf_token']
T = {'kind': 'HW_UI_LAYOUT_V2', 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
     'press_method': 'adb-injected long-press + dialog tap (owner-authorized automation)', 'log': []}
t0 = time.time()
def log(k, v):
    T['log'].append({'t': round(time.time() - t0, 1), k: v}); print(k, json.dumps(v, ensure_ascii=False)[:400], flush=True)
    json.dump(T, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
def req(path, body=None):
    h = {'Content-Type': 'application/json'}
    if body is not None: h.update({'X-CSRF-Token': CSRF, 'Origin': B})
    r = urllib.request.Request(B + path, json.dumps(body).encode() if body is not None else None, h)
    try:
        with urllib.request.urlopen(r, timeout=90) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')
def adb(*a):
    try: return subprocess.run(['adb', '-s', TV, *a], capture_output=True, text=True, timeout=40, encoding='utf-8', errors='replace').stdout
    except subprocess.TimeoutExpired: return ''
def ui():
    adb('shell', 'uiautomator', 'dump', '/sdcard/obui.xml'); x = adb('shell', 'cat', '/sdcard/obui.xml'); adb('shell', 'rm', '/sdcard/obui.xml'); return x
def texts(x): return [t for t in re.findall(r'text="([^"]+)"', x)]
def center(x, pattern):
    m = re.search(r'text="' + pattern + r'"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', x)
    return ((int(m[1]) + int(m[3])) // 2, (int(m[2]) + int(m[4])) // 2) if m else None
def open_app(): adb('shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity'); time.sleep(3)
def oracle():
    st, r = req('/api/v2/execute', {'primitive_id': 'device_action', 'device_key': S['key'], 'params': {'action': 'audio_state'}, 'consent': True})
    return (r.get('result') or {}).get('muted'), (r.get('result') or {}).get('volume_index')
def press_confirm(tag):
    x = ui(); c = center(x, 'Mute toggle')
    if not c: log(tag, {'error': 'Mute toggle not on screen', 'texts': texts(x)[:30]}); return False
    adb('shell', 'input', 'swipe', str(c[0]), str(c[1]), str(c[0]), str(c[1]), '900'); time.sleep(1.5)
    x = ui(); r = center(x, '(?i:run)')
    if not r: log(tag, {'error': 'confirm dialog not shown', 'texts': texts(x)[:30]}); return False
    log(tag + '_dialog', {'texts': [t for t in texts(x) if t in ('Confirm', 'Cancel', 'Run', 'RUN', 'CANCEL') or 'Run "' in t]})
    adb('shell', 'input', 'tap', str(r[0]), str(r[1])); return True
def wait_result(n_before, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        st, rc = req('/api/v2/remote_controls')
        if len(rc.get('history', [])) > n_before: return rc
        time.sleep(1)
    return req('/api/v2/remote_controls')[1]

S = {}
# 1. Pair the TV Companion with this isolated server
st, snap = req('/api/fabric-discover', {'device_id': 'fabric', 'providers': ['android']})
tv = next(d for d in snap['devices'] if d['category'] == 'tv'); S['key'] = tv['key']; h = sorted(tv['handles'].values())[0]
open_app()
st, r = req('/api/relay-pair-start', {'device_id': h}); log('pair_start', {'http': st, 'err': r.get('error')})
code = None
for _ in range(12):
    m = re.findall(r'text="(\d{3}) (\d{3})"', ui())
    if m: code = ''.join(m[0]); break
    time.sleep(1.5)
st, r = req('/api/relay-pair-confirm', {'device_id': h, 'code': code}); rid = r.get('relay_id')
log('pair_confirm', {'http': st, 'state': r.get('state'), 'err': r.get('error'), 'relay_id': rid})
if st != 200: sys.exit(2)
# 2. Manifest from the G3 Meta run (steps unchanged), grant, v2 plan
st, sf = req('/api/v2/facts/signed?device=' + S['key']); fp, facts = sf['device_fingerprint'], sf['facts']
cat = next(f for f in facts if f['name'] == 'category')
g4 = json.load(open(r'C:\Users\TheBox\Desktop\Hackaton\OpenBridge-v4\docs\evidence\v4\g3-smoke\attempt4_SUCCESS.json', encoding='utf-8'))
m = dict(g4['manifest']); m['target'] = {'category': 'tv', 'device_fingerprint': fp}
m['facts_required'] = [cat['fact_id']]; m['evidence_refs'] = [cat['fact_id']]
m['expires_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 3600))
log('manifest', {'model_run': m['model_run'], 'steps': [(s['primitive_id'], s['args']) for s in m['steps']],
                 'host_rebinding': 'target fingerprint, required fact and expiry refreshed; Meta steps unchanged'})
st, g = req('/api/v2/manifests/grant', {'manifest': m, 'facts': facts, 'consent': True, 'max_uses': 6, 'ttl_s': 1800})
grant = g.get('grant'); log('grant', {'http': st, 'grant_id': (grant or {}).get('grant_id'), 'err': g.get('error')})
hsh = manifest_hash(m)
plan = {'target_device': fp, 'profile_id': 'tv.audio', 'layout_version': 7, 'origin_model_run_id': m['model_run']['run_id'],
        'evidence_refs': [cat['fact_id']],
        'widgets': [{'widget_id': 'title', 'kind': 'label', 'label': 'Living room TV', 'binding': None, 'permission_label': ''},
                    {'widget_id': 'mute', 'kind': 'confirm', 'label': 'Mute toggle', 'binding': {'manifest_hash': hsh, 'inputs': {}}, 'permission_label': 'press the TV mute key'},
                    {'widget_id': 'last', 'kind': 'status', 'label': 'Last result', 'source': 'mute', 'binding': None, 'permission_label': ''}]}
plan['plan_hash'] = manifest_hash(plan)
st, inst = req('/api/v2/manifests/ui_install', {'relay_id': rid, 'plan': plan, 'consent': True,
                                               'bindings': {hsh: {'manifest': m, 'grant': grant, 'facts': facts}}})
log('ui_install', {'http': st, 'installed': inst.get('installed'), 'err': inst.get('error'), 'code': inst.get('code')})
time.sleep(4)
x = ui(); log('screen_after_install', {'texts': [t for t in texts(x) if t in ('Living room TV', 'Mute toggle') or t.startswith('Last result')]})
st, rc = req('/api/v2/remote_controls'); log('layout_ack', rc.get('layouts', {}).get(rid))
# 3. Confirmed press -> mute; status; second press -> unmute
pre = oracle(); log('oracle_pre', pre)
n = len(rc.get('history', []))
if press_confirm('press1'):
    rc = wait_result(n); log('result1', rc['history'][-1] if rc.get('history') else None)
time.sleep(1.5); log('oracle_after_press1', oracle())
x = ui(); log('status_on_screen1', [t for t in texts(x) if t.startswith('Last result')])
n = len(rc.get('history', []))
time.sleep(2)
if press_confirm('press2'):
    rc = wait_result(n); log('result2', rc['history'][-1] if rc.get('history') else None)
time.sleep(1.5); log('oracle_after_press2', oracle())
# 4. Restart the Companion: layout restored from device storage
adb('shell', 'am', 'force-stop', 'fr.openbridge.companion'); time.sleep(1); open_app()
x = ui(); log('screen_after_restart', {'texts': [t for t in texts(x) if t in ('Living room TV', 'Mute toggle') or t.startswith('Last result')]})
st, rc = req('/api/v2/remote_controls'); time.sleep(4); st, rc = req('/api/v2/remote_controls'); log('layout_ack_after_restart', rc.get('layouts', {}).get(rid))
# 5. Revoke: the control no longer executes
st, rv = req('/api/v2/manifests/revoke', {'grant_id': grant['grant_id']}); log('revoke', {'http': st})
n = len(rc.get('history', [])); before = oracle()
time.sleep(2)
if press_confirm('press_after_revoke'):
    rc = wait_result(n); log('result_after_revoke', rc['history'][-1] if rc.get('history') else None)
time.sleep(1.5); log('oracle_after_revoked_press', {'before': before, 'after': oracle()})
x = ui(); log('status_on_screen_after_revoke', [t for t in texts(x) if t.startswith('Last result')])
# 6. Cleanup: remove the layout from the TV
st, cl = req('/api/v2/remote_controls', {'relay_id': rid, 'consent': True, 'controls': []}); log('cleanup', {'http': st})
time.sleep(3); x = ui(); log('screen_after_cleanup', {'has_mute': 'Mute toggle' in texts(x)})
T['finished'] = time.strftime('%Y-%m-%dT%H:%M:%S%z'); json.dump(T, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print('DONE')
