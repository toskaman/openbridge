"""Cloud end-to-end (§10 NET-01..20 subset): real server on Linux -> real Companion
APK on an official emulator -> signed pairing -> signed command -> independent
adb oracle -> relay-side revoke (pm clear) -> command denied.

Runs inside the android.yml `e2e` job (emulator already booted, adb attached).
Exit 0 with e2e-evidence/verdict.json on PASS, 1 otherwise.

Usage: python scripts/verify/cloud_e2e.py --apk <path> --out <dir> [--port 18795]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request


def sh(*args, timeout=90):
    r = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout,
                       encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apk', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--port', type=int, default=18795)
    args = ap.parse_args()
    base = 'http://127.0.0.1:%d' % args.port
    outdir = args.out
    os.makedirs(outdir, exist_ok=True)
    verdict = {'steps': {}, 'status': 'FAIL'}
    tmp = tempfile.mkdtemp(prefix='ob-e2e-')

    def record(name, ok, detail=''):
        verdict['steps'][name] = {'ok': bool(ok), 'detail': str(detail)[:300]}
        print(('PASS ' if ok else 'FAIL ') + name + (' — ' + str(detail)[:160] if detail and not ok else ''))
        return ok

    def post(path, body, timeout=90):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json',
                                              'Origin': base, 'X-CSRF-Token': token},
                                     method='POST')
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode())
            except ValueError:
                return e.code, {'error': 'non-json'}

    # NET-01: server starts (isolated store, nothing shared with any other server).
    env = dict(os.environ, LOCALAPPDATA=tmp, XDG_DATA_HOME=tmp)
    srvlog = open(os.path.join(outdir, 'server.log'), 'w', encoding='utf-8')
    srv = subprocess.Popen([sys.executable, '-m', 'src.cli', 'serve', '--port', str(args.port)],
                           env=env, stdout=srvlog, stderr=subprocess.STDOUT, text=True)
    try:
        ok = False
        for _ in range(60):
            try:
                with urllib.request.urlopen(base + '/api/session', timeout=5) as r:
                    token = json.loads(r.read().decode())['csrf_token']
                    ok = True
                    break
            except OSError:
                time.sleep(1)
        if not record('NET-01 server starts', ok):
            raise SystemExit(1)
        # NET-02..06: discovery finds the emulator; handshake material ready.
        st, snap = post('/api/fabric-discover', {'device_id': 'fabric', 'providers': ['android']}, timeout=120)
        handles = []
        if st == 200:
            for d in snap.get('devices', []):
                for h in (d.get('handles') or {}).values():
                    handles.append(h)
        if not record('NET-02..06 emulator discovered', bool(handles), 'st=%s' % st):
            raise SystemExit(1)
        handle = handles[0]
        rc, outp = sh('adb', 'install', '--no-incremental', args.apk, timeout=180)
        if not record('APK installed', rc == 0 and 'Success' in outp, outp[-200:]):
            raise SystemExit(1)
        for perm in ('android.permission.BLUETOOTH_SCAN', 'android.permission.BLUETOOTH_CONNECT',
                     'android.permission.RECORD_AUDIO'):
            sh('adb', 'shell', 'pm', 'grant', 'fr.openbridge.companion', perm)
        sh('adb', 'shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
        time.sleep(8)
        # NET-04/07/08: pairing handshake (code shown on the emulator screen).
        st, hello = post('/api/relay-pair-start', {'device_id': handle})
        if not record('NET-04 pair-start', st == 200 and hello.get('state') == 'CODE_SHOWN_ON_DEVICE',
                      'st=%s %s' % (st, json.dumps(hello)[:200])):
            raise SystemExit(1)
        rid = hello['relay_id']
        code = None
        pat = re.compile(r'\b(\d{3})\s?(\d{3})\b')
        for _ in range(6):
            sh('adb', 'shell', 'uiautomator', 'dump', '/sdcard/ob-e2e.xml', timeout=60)
            rc, dump = sh('adb', 'shell', 'cat', '/sdcard/ob-e2e.xml', timeout=60)
            m = pat.search(dump) if rc == 0 else None
            if m:
                code = m.group(1) + m.group(2)
                break
            rc, top = sh('adb', 'shell', 'dumpsys', 'activity', 'top', timeout=60)
            m = pat.search(top) if rc == 0 else None
            if m:
                code = m.group(1) + m.group(2)
                break
            time.sleep(5)
        if not record('code read from screen', bool(code)):
            raise SystemExit(1)
        st, conf = post('/api/relay-pair-confirm', {'device_id': handle, 'code': code})
        if not record('NET-05..08 PAIRED', st == 200 and conf.get('state') == 'PAIRED',
                      'st=%s %s' % (st, json.dumps(conf)[:200])):
            raise SystemExit(1)
        # NET-09..11: signed command reaches the target; independent adb oracle agrees.
        st, res = post('/api/relay-scan', {'device_id': handle, 'relay_id': rid, 'seconds': 4}, timeout=120)
        scan_ok = st == 200 or (st == 409 and 'Relay refused' in json.dumps(res))
        advertisers = None
        if st == 200:
            advertisers = (res.get('providers') or {}).get('relay', {}).get('devices')
        if not record('NET-09..11 signed round-trip', scan_ok,
                      'st=%s advertisers=%s %s' % (st, advertisers, json.dumps(res)[:200])):
            raise SystemExit(1)
        rc, svcs = sh('adb', 'shell', 'dumpsys', 'activity', 'services')
        rc2, fwd = sh('adb', 'forward', '--list')
        oracle = ('RelayService' in svcs) and ('tcp:47800' in fwd.replace(' ', ''))
        if not record('oracle: service + adb-forward agree', oracle, fwd.strip()[:160]):
            raise SystemExit(1)
        # NET-12/13: relay-side revoke (pm clear wipes the pairing key) -> denied.
        sh('adb', 'shell', 'pm', 'clear', 'fr.openbridge.companion')
        time.sleep(3)
        st2, res2 = post('/api/relay-scan', {'device_id': handle, 'relay_id': rid, 'seconds': 4}, timeout=120)
        denied = st2 != 200
        if not record('NET-12/13 revoked relay denied', denied, 'st=%s' % st2):
            raise SystemExit(1)
        verdict['status'] = 'PASS'
        verdict['relay_id'] = rid
        verdict['advertisers'] = advertisers
    finally:
        with open(os.path.join(outdir, 'verdict.json'), 'w', encoding='utf-8') as f:
            json.dump(verdict, f, indent=1)
        srv.terminate()
        try:
            srv.wait(timeout=15)
        except subprocess.TimeoutExpired:
            srv.kill()
    print('E2E RESULT: ' + verdict['status'])
    return 0 if verdict['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
