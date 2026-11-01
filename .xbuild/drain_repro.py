"""Repro: enroll the physical phone manually, call poll_once in-process."""
import json
import subprocess
import sys
import tempfile
import time
import types
import urllib.request

sys.path.insert(0, r'C:\users\TheBox\Desktop\Hackaton\OpenBridge')
from src.fabric import relay as R

ADB = r'E:\Android\sdk\platform-tools\adb.exe'
SERIAL = 'BV9300PEEA0004883'
PORT = 18794
BASE = 'http://127.0.0.1:%d' % PORT


def sh(*a, timeout=60):
    r = subprocess.run(list(a), capture_output=True, text=True, timeout=timeout,
                       encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '') + (r.stderr or '')


tmp = tempfile.mkdtemp(prefix='ob-repro-')
import os
env = dict(os.environ, LOCALAPPDATA=tmp, XDG_DATA_HOME=tmp)
srv = subprocess.Popen([sys.executable, '-m', 'src.cli', 'serve', '--port', str(PORT)],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       cwd=r'C:\users\TheBox\Desktop\Hackaton\OpenBridge')
try:
    tok = None
    for _ in range(30):
        try:
            with urllib.request.urlopen(BASE + '/api/session', timeout=5) as r:
                tok = json.loads(r.read().decode())['csrf_token']
                break
        except OSError:
            time.sleep(1)

    def post(path, body, timeout=90):
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json', 'Origin': BASE,
                                              'X-CSRF-Token': tok}, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())

    st, snap = post('/api/fabric-discover', {'device_id': 'fabric', 'providers': ['android']}, timeout=120)
    handle = None
    for d in snap.get('devices', []):
        if d.get('label') == 'BV9300 Pro':
            handle = list(d['handles'].values())[0]
    print('handle:', handle)
    sh(ADB, '-s', SERIAL, 'shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
    time.sleep(5)
    st, hello = post('/api/relay-pair-start', {'device_id': handle})
    print('pair-start:', st, hello.get('state'))
    import re
    sh(ADB, '-s', SERIAL, 'shell', 'uiautomator', 'dump', '/sdcard/repro.xml')
    rc, xml = sh(ADB, '-s', SERIAL, 'shell', 'cat', '/sdcard/repro.xml')
    code = re.search(r'Pairing code (\d{6})', xml).group(1)
    print('code:', code)
    st, conf = post('/api/relay-pair-confirm', {'device_id': handle, 'code': code})
    print('confirm:', st, (conf or {}).get('state'))
    # Now the drain runs in THAT server process, not here. Check flows growth:
    time.sleep(16)
    sh(ADB, '-s', SERIAL, 'shell', 'uiautomator', 'dump', '/sdcard/repro2.xml')
    rc, xml2 = sh(ADB, '-s', SERIAL, 'shell', 'cat', '/sdcard/repro2.xml')
    m = re.findall(r'OUT\s+(\d+) msgs|IN\s+(\d+) msgs', xml2)
    print('flows after 16 s:', m)
finally:
    srv.terminate()
    srv.wait(timeout=15)
