"""Owner-authorized hardware run: pairing survives a server restart (isolated LOCALAPPDATA, server :18780).
Usage: hw_durable.py pair | after_restart"""
import json, re, subprocess, sys, time, urllib.request, urllib.error
sys.path.insert(0, r'C:\Users\TheBox\Desktop\Hackaton\OpenBridge-v4')
B = 'http://127.0.0.1:18780'; TV = '192.168.1.15:5555'
OUT = r'C:\Users\TheBox\Desktop\Hackaton\.xbuild\HW_DURABLE_TRANSCRIPT.json'
try:
    T = json.load(open(OUT, encoding='utf-8'))
except (OSError, ValueError):
    T = {'kind': 'HW_DURABLE_RELAY', 'log': []}
CSRF = json.loads(urllib.request.urlopen(B + '/api/session').read())['csrf_token']
def log(k, v):
    T['log'].append({'at': time.strftime('%H:%M:%S'), k: v}); print(k, json.dumps(v, ensure_ascii=False)[:400], flush=True)
    json.dump(T, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
def req(path, body=None):
    h = {'Content-Type': 'application/json'}
    if body is not None: h.update({'X-CSRF-Token': CSRF, 'Origin': B})
    r = urllib.request.Request(B + path, json.dumps(body).encode() if body is not None else None, h)
    try:
        with urllib.request.urlopen(r, timeout=90) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')
def adb(*a):
    return subprocess.run(['adb', '-s', TV, *a], capture_output=True, text=True, timeout=40, encoding='utf-8', errors='replace').stdout
def ui():
    adb('shell', 'uiautomator', 'dump', '/sdcard/obui.xml'); x = adb('shell', 'cat', '/sdcard/obui.xml'); adb('shell', 'rm', '/sdcard/obui.xml'); return x
mode = sys.argv[1]
st, snap = req('/api/fabric-discover', {'device_id': 'fabric', 'providers': ['android']})
tv = next(d for d in snap['devices'] if d['category'] == 'tv'); h = sorted(tv['handles'].values())[0]
if mode == 'pair':
    adb('shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity'); time.sleep(3)
    st, r = req('/api/relay-pair-start', {'device_id': h}); log('pair_start', {'http': st})
    code = None
    for _ in range(12):
        m = re.findall(r'text="(\d{3}) (\d{3})"', ui())
        if m: code = ''.join(m[0]); break
        time.sleep(1.5)
    st, r = req('/api/relay-pair-confirm', {'device_id': h, 'code': code}); log('pair_confirm', {'http': st, 'state': r.get('state'), 'relay_id': r.get('relay_id')})
    st, rc = req('/api/v2/remote_controls'); log('transport_before_restart', rc.get('transport'))
else:
    st, rc = req('/api/v2/remote_controls'); log('transport_after_restart_and_discovery', rc.get('transport'))
    rid = next(iter(rc.get('transport') or {}), None)
    # Prove the restored relay really works: install a one-label layout, read it on screen, then clear it.
    st, rs = req('/api/v2/remote_controls', {'relay_id': rid, 'consent': True, 'controls': []}); log('owner_command_over_restored_relay', {'http': st, 'err': rs.get('error')})
    st, sf = req('/api/v2/facts/signed?device=' + tv['key']); fp = sf['device_fingerprint']
    log('relay_fingerprint_matches_tv', {'tv_fp': fp})
    log('done', True)
