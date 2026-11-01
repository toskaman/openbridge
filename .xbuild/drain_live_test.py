"""Live drain test on the physical phone (isolated test server, port 18795).

Pair -> type a command -> drain parses -> caption shows the outcome.
Then voice: record 3 s of room tone -> drain fetches clip -> honest STT report.
Evidence under E:/shots/drain-live/.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

SERIAL = 'BV9300PEEA0004883'
PORT = 18795
BASE = 'http://127.0.0.1:%d' % PORT
OUT = r'E:\shots\drain-live'
ADB = r'E:\Android\sdk\platform-tools\adb.exe'
os.makedirs(OUT, exist_ok=True)


def sh(*args, timeout=90):
    r = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout,
                       encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def adb(*args, timeout=90):
    return sh(ADB, '-s', SERIAL, *args, timeout=timeout)


token = None


def post(path, body, timeout=90):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'Origin': BASE, 'X-CSRF-Token': token},
                                 method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except ValueError:
            return e.code, {'error': 'non-json'}


def awake():
    adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
    time.sleep(1)
    adb('shell', 'input', 'swipe', '540', '1800', '540', '600')
    time.sleep(1)


def dump(name, scroll_top=False):
    awake()
    if scroll_top:
        adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')  # dismiss Gboard (shrinks the dump window)
        time.sleep(1)
        adb('shell', 'input', 'swipe', '540', '500', '540', '1600')  # caption back into the window
        time.sleep(1)
    adb('shell', 'uiautomator', 'dump', '/sdcard/%s.xml' % name)
    adb('pull', '/sdcard/%s.xml' % name, os.path.join(OUT, '%s.xml' % name))
    with open(os.path.join(OUT, '%s.xml' % name), encoding='utf-8') as f:
        return f.read()


def tap(x, y):
    adb('shell', 'input', 'tap', str(x), str(y))


verdict = {'steps': {}, 'status': 'FAIL'}


def record(name, ok, detail=''):
    verdict['steps'][name] = {'ok': bool(ok), 'detail': str(detail)[:300]}
    print(('PASS ' if ok else 'FAIL ') + name + (' — ' + str(detail)[:160] if detail and not ok else ''))
    return ok


tmp = tempfile.mkdtemp(prefix='ob-drain-')
env = dict(os.environ, LOCALAPPDATA=tmp, XDG_DATA_HOME=tmp)
try:
    urllib.request.urlopen(BASE + '/api/session', timeout=3)
    print('REFUSING: something already answers on port %d (zombie server?). Kill it first.' % PORT)
    raise SystemExit(2)
except (OSError, urllib.error.URLError):
    pass
srvlog = open(os.path.join(OUT, 'server.log'), 'w', encoding='utf-8')
srv = subprocess.Popen([sys.executable, '-m', 'src.cli', 'serve', '--port', str(PORT)],
                       env=env, stdout=srvlog, stderr=subprocess.STDOUT, text=True,
                       cwd=r'C:\users\TheBox\Desktop\Hackaton\OpenBridge')
try:
    ok = False
    for _ in range(60):
        try:
            with urllib.request.urlopen(BASE + '/api/session', timeout=5) as r:
                token = json.loads(r.read().decode())['csrf_token']
                ok = True
                break
        except OSError:
            time.sleep(1)
    if not record('server starts', ok):
        raise SystemExit(1)
    st, snap = post('/api/fabric-discover', {'device_id': 'fabric', 'providers': ['android']}, timeout=120)
    handle = None
    if st == 200:
        for d in snap.get('devices', []):
            if d.get('label') == 'BV9300 Pro':
                hs = list((d.get('handles') or {}).values())
                handle = hs[0] if hs else None
    if not record('phone discovered', bool(handle), 'st=%s' % st):
        raise SystemExit(1)
    for perm in ('android.permission.BLUETOOTH_SCAN', 'android.permission.BLUETOOTH_CONNECT',
                 'android.permission.RECORD_AUDIO'):
        adb('shell', 'pm', 'grant', 'fr.openbridge.companion', perm)
    adb('shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
    time.sleep(6)
    for _ in range(3):
        rc, win = adb('shell', 'dumpsys', 'window')
        f = [ln for ln in win.splitlines() if 'mCurrentFocus' in ln]
        if f and 'fr.openbridge.companion' in f[0]:
            break
        adb('shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
        time.sleep(3)
    st, hello = post('/api/relay-pair-start', {'device_id': handle})
    if not record('pair-start', st == 200 and hello.get('state') == 'CODE_SHOWN_ON_DEVICE', 'st=%s' % st):
        raise SystemExit(1)
    rid = hello['relay_id']
    code = None
    for _ in range(4):
        adb('shell', 'input', 'swipe', '540', '1600', '540', '500')  # code card into the dump window
        time.sleep(1)
        xml = dump('drain-pair')
        rc, top = adb('shell', 'dumpsys', 'activity', 'top')
        blob = xml + '\n' + top
        m = re.search(r'Pairing code (\d{6})', blob)
        if not m:
            m2 = re.search(r'(?i)(?:pair\w*|code)\W{0,60}(\d{3})\s(\d{3})', blob)
            if m2:
                code = m2.group(1) + m2.group(2)
                break
        if m:
            code = m.group(1)
            break
        time.sleep(3)
    if not record('code shown (get fix holds)', bool(code)):
        raise SystemExit(1)
    st, conf = post('/api/relay-pair-confirm', {'device_id': handle, 'code': code})
    if not record('paired', st == 200 and (conf or {}).get('state') == 'PAIRED', 'st=%s' % st):
        raise SystemExit(1)
    # Fresh activity: the post-confirm UI state confuses uiautomator (84-node dump
    # without the ask bar). Pairing persists (key on device + enrolled relay).
    adb('shell', 'am', 'force-stop', 'fr.openbridge.companion')
    time.sleep(2)
    adb('shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
    time.sleep(5)
    # Typed command via the real UI (coords re-located after pairing).
    xml = dump('drain-layout')
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml.encode('utf-8', 'replace'))

    def center(b):
        m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', b)
        x1, y1, x2, y2 = map(int, m.groups())
        return (x1 + x2) // 2, (y1 + y2) // 2

    edit = send = speak = None
    for n in root.iter('node'):
        if n.get('class') == 'android.widget.EditText' and edit is None:
            edit = center(n.get('bounds'))
        if n.get('content-desc') == 'Send':
            send = center(n.get('bounds'))
        if n.get('content-desc') == 'Speak':
            speak = center(n.get('bounds'))
    if not record('input nodes located', edit and send and speak, '%s %s %s' % (edit, send, speak)):
        raise SystemExit(1)
    tap(*edit)
    time.sleep(1)
    adb('shell', 'input', 'text', 'allume%slampe%sdu%ssalon')
    time.sleep(1)
    tap(*send)
    time.sleep(2)
    xml0 = dump('drain-echo', scroll_top=True)
    echo = set(re.findall(r'text="([^"]{4,200})"', xml0))
    srvlog.flush()
    logmark = os.path.getsize(os.path.join(OUT, 'server.log'))
    caption, drainline = '', ''
    IDLE = ('Hi. Ask me anything', 'Open OpenBridge on your PC to pair')
    for i in range(30):
        time.sleep(5)
        xml = dump('drain-typed%d' % i, scroll_top=True)
        texts = re.findall(r'text="([^"]{4,200})"', xml)
        new = [t for t in texts if t not in echo and not any(k in t for k in IDLE)
               and 'msgs' not in t and 'OUT' not in t and 'IN ' not in t]
        with open(os.path.join(OUT, 'server.log'), encoding='utf-8', errors='replace') as f:
            f.seek(logmark)
            tail = f.read()
        m = re.search(r'\[drain\] \S+ \S+ -> (\S+): (.*)', tail)
        if m:
            drainline = m.group(0)
            if new:
                caption = new[0]
            break
        if new:
            caption = new[0]
    ok = bool(drainline)
    if not record('typed order reported', ok, (drainline + ' / ' + caption)[:160] or caption[:160]):
        raise SystemExit(1)
    # Voice: 3 s of room tone through the real mic path.
    tap(*speak)
    time.sleep(3)
    tap(*speak)
    time.sleep(2)
    srvlog.flush()
    vmark = os.path.getsize(os.path.join(OUT, 'server.log'))
    vcap, vdrain = '', ''
    for i in range(30):
        time.sleep(5)
        xml = dump('drain-voice%d' % i, scroll_top=True)
        texts = re.findall(r'text="([^"]{4,200})"', xml)
        cands = [t for t in texts if 'Heard' in t or 'transcription' in t.lower()
                 or 'silence' in t.lower()]
        if cands:
            vcap = cands[0]
        with open(os.path.join(OUT, 'server.log'), encoding='utf-8', errors='replace') as f:
            f.seek(vmark)
            tail = f.read()
        m = re.search(r'\[drain\] \S+ \S+ -> (\S+): (.*)', tail)
        if m:
            vdrain = m.group(0)
            break
    if not record('voice order reported', bool(vdrain), (vdrain + ' / ' + vcap)[:160]):
        raise SystemExit(1)
    verdict['status'] = 'PASS'
finally:
    with open(os.path.join(OUT, 'verdict.json'), 'w', encoding='utf-8') as f:
        json.dump(verdict, f, indent=1)
    srv.terminate()
    try:
        srv.wait(timeout=15)
    except subprocess.TimeoutExpired:
        srv.kill()
print('DRAIN LIVE RESULT: ' + verdict['status'])
