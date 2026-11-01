"""S6 runbook (DEMO_PHYSICAL_RUNBOOK.md section 3): Watch7 -> TV volume, owner press.

In-process Core(): pair watch + TV, install the 'tv' dashboard on the watch
relay, owner presses Volume + on the watch, exactly one tv_volume_step is
dispatched, TV volume read back over adb, then revoke + denied re-press.
Evidence under E:/shots/demo-s6-. Unattended-safe until the owner presses.
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, r'C:\users\TheBox\Desktop\Hackaton\OpenBridge')

ADB = r'E:\Android\sdk\platform-tools\adb.exe'
WATCH = sys.argv[1] if len(sys.argv) > 1 else '192.168.1.14:45593'
TV = '192.168.1.15:5555'
OUT = r'E:\shots'
verdict = {'steps': {}, 'status': 'FAIL'}


def record(name, ok, detail=''):
    verdict['steps'][name] = {'ok': bool(ok), 'detail': str(detail)[:300]}
    print(('PASS ' if ok else 'FAIL ') + name + (' -- ' + str(detail)[:160] if detail and not ok else ''),
          flush=True)
    return ok


def adb(serial, *args, timeout=90):
    r = subprocess.run([ADB, '-s', serial, *args], capture_output=True, text=True,
                       timeout=timeout, encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def wake(serial):
    adb(serial, 'shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
    time.sleep(1)


def shot(serial, name):
    adb(serial, 'shell', 'screencap', '-p', '/sdcard/%s.png' % name)
    adb(serial, 'pull', '/sdcard/%s.png' % name, os.path.join(OUT, '%s.png' % name))


def read_code(serial, secs=60):
    """Read the 6-digit pairing code from the Companion screen."""
    end = time.time() + secs
    n = 0
    while time.time() < end:
        n += 1
        rc, top = adb(serial, 'shell', 'dumpsys', 'activity', 'top')
        print('code-read %s try=%d dumpsys=%dB' % (serial, n, len(top)), flush=True)
        flat = re.sub(r'\s+', ' ', top)
        m = re.search(r'Pairing code (\d{6})', flat)
        if m:
            return m.group(1)
        m2 = re.search(r'(?i)(?:pair\w*|code).{0,200}?(\d{3})\s(\d{3})', flat)
        if m2:
            return m2.group(1) + m2.group(2)
        # Bare 3+3 fallback (TV code card): last resort, digits near 'enter'.
        m2b = re.search(r'(?i)enter.{0,200}?(\d{3})\s(\d{3})', flat)
        if m2b:
            return m2b.group(1) + m2b.group(2)
        rc, out = adb(serial, 'shell', 'uiautomator', 'dump', '/sdcard/code.xml')
        print('code-read %s try=%d uiauto rc=%d %s' % (serial, n, rc, out.strip().splitlines()[:1]), flush=True)
        if rc == 0:
            rc2, _ = adb(serial, 'pull', '/sdcard/code.xml', os.path.join(OUT, 'code-%s.xml' % serial.replace(':', '_')))
            if rc2 == 0:
                with open(os.path.join(OUT, 'code-%s.xml' % serial.replace(':', '_')), encoding='utf-8') as f:
                    xml = f.read()
                m3 = re.search(r'(\d{3})\s(\d{3})', xml)
                if m3:
                    return m3.group(1) + m3.group(2)
        time.sleep(5)
    return None


def tv_volume():
    rc, out = adb(TV, 'shell', 'dumpsys', 'audio')
    vols = {}
    cur = None
    for ln in out.splitlines():
        m = re.search(r'STREAM_(\w+)', ln)
        if m:
            cur = m.group(1)
        m2 = re.search(r'Muted: (true|false)', ln)
        if m2 and cur:
            vols[cur + '_muted'] = m2.group(1)
        # streamVolume:N is the index; 'Current: <device>' is the output device, NOT the level.
        m3 = re.search(r'streamVolume:(\d+)', ln)
        if m3 and cur and cur not in vols:
            vols[cur] = int(m3.group(1))
    return vols


def main():
    import secrets
    from src.cli import Core, ensure_discovery
    from src.fabric import relay as R
    from src.runtime import api_v2, dashboards as D

    for serial in (WATCH, TV):  # collapse any stacked MainActivity instances from earlier runs
        adb(serial, 'shell', 'am', 'force-stop', 'fr.openbridge.companion')
    time.sleep(2)
    wake(WATCH)
    adb(WATCH, 'shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
    adb(TV, 'shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
    time.sleep(4)
    with Core() as server:
        ensure_discovery(server, ['android'])
        devs = (server.fabric_snapshot or {}).get('devices', [])
        handles = {}
        for d in devs:
            hs = list((d.get('handles') or {}).values())
            if hs:
                handles[d.get('label')] = hs[0]
        print('HANDLES', {k: v for k, v in handles.items()}, flush=True)
        if not record('discover watch+tv', 'SM-L310' in handles and 'Android TV' in handles):
            raise SystemExit(1)

        def pair(label):
            handle = handles[label]
            serial = WATCH if label == 'SM-L310' else TV
            # The code card only renders while MainActivity is foreground; the
            # TV falls back to ambient mode within a minute, so raise it fresh.
            # Single instance only: a second `am start` stacks MainActivity #B
            # on top of #A, and any BACK press then pops #B (with the code
            # card) revealing card-less #A. So start only when not on top.
            wake(serial)
            rc, acts = adb(serial, 'shell', 'dumpsys', 'activity', 'activities')
            if not re.search(r'(topResumedActivity|mResumedActivity).*fr\.openbridge\.companion/\.MainActivity', acts):
                adb(serial, 'shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
                for _ in range(20):  # wait for truly resumed (post-reboot/doze starts are slow)
                    time.sleep(3)
                    rc, acts = adb(serial, 'shell', 'dumpsys', 'activity', 'activities')
                    if re.search(r'(topResumedActivity|mResumedActivity).*fr\.openbridge\.companion/\.MainActivity', acts):
                        break
            time.sleep(2)
            url = server.android.forward_companion(handle)
            send = R.http_transport(url)
            pc_nonce = secrets.token_hex(16)
            hello = send(None, {'op': 'pair_request', 'pc_nonce': pc_nonce})
            assert hello.get('protocol') == R.PROTOCOL, hello
            code = read_code(serial)
            assert code, 'no pairing code on %s' % label
            key = R.derive_key(code, hello['relay_nonce'], pc_nonce)
            rid = hello['relay_id']
            reply = send(None, R.command(key, rid, 'discover_capabilities'))
            declared = R.verify(key, reply, None).get('params', {})
            server.relays.enroll(rid, key, handle, declared)
            server.relays.relays[rid]['send'] = send
            if 'aead1' in (declared.get('capabilities') or []):
                from src.fabric import aead
                server.relays.relays[rid]['send'] = aead.encrypting_send(send, rid)
                server.relays.relays[rid]['aead'] = aead.VERSION
            server.relays.relays[rid]['url'] = url
            server.relay_ledger.proved(rid)
            return rid

        wrid = pair('SM-L310')
        if not record('watch paired', bool(wrid), wrid):
            raise SystemExit(1)
        trid = pair('Android TV')
        if not record('tv paired', bool(trid), trid):
            raise SystemExit(1)
        controls = api_v2.remote_controls(server)
        router = api_v2.router(server)
        target = router.resolve_target('Android TV')
        state = D.create(controls, wrid, 'tv', target, consent=True)
        labels = sorted(c['label'] for c in state.get('controls', []) if c.get('relay_id') == wrid)
        if not record('tv controls on watch', labels == ['Volume +', 'Volume -', 'YouTube'], labels):
            raise SystemExit(1)
        # Watch QUICK CONTROLS proof shot (scroll to controls first).
        adb(WATCH, 'shell', 'input', 'swipe', '240', '350', '240', '120')
        time.sleep(1)
        adb(WATCH, 'shell', 'input', 'swipe', '240', '350', '240', '120')
        time.sleep(1)
        shot(WATCH, 'demo-s6-watch-controls')
        # WIFI route leases live 60 s: a press minutes after install is
        # BLOCKED ('lease stale'). So: wait for the owner to be ready (go
        # sentinel), THEN rediscover + reinstall fresh, and take the press
        # inside a tight 90 s window.
        gof = os.path.join(OUT, 'demo-s6-go.json')
        try:
            os.unlink(gof)
        except OSError:
            pass
        with open(os.path.join(OUT, 'demo-s6-installed.json'), 'w', encoding='utf-8') as f:
            json.dump({'watch_relay': wrid, 'at': time.time()}, f)
        print('INSTALLED -- waiting for owner-ready sentinel ' + gof, flush=True)
        for _ in range(300):
            if os.path.exists(gof):
                break
            time.sleep(2)
        else:
            record('owner ready', False, 'no go sentinel in 600 s')
            raise SystemExit(1)
        ensure_discovery(server, ['android'])
        router2 = api_v2.router(server)
        target2 = router2.resolve_target('Android TV')
        D.create(controls, wrid, 'tv', target2, consent=True)
        print('REINSTALLED fresh target; press window 90 s', flush=True)
        before = tv_volume()
        print('TV VOL BEFORE', before, flush=True)
        print('READY-FOR-OWNER-PRESS ' + json.dumps({'watch_relay': wrid, 'before': before}), flush=True)
        with open(os.path.join(OUT, 'demo-s6-press.json'), 'w', encoding='utf-8') as f:
            json.dump({'watch_relay': wrid, 'before': before, 'at': time.time()}, f)
        print('KEEPALIVE-PID %d -- press Volume + on the watch now' % os.getpid(), flush=True)
        diag = open(os.path.join(OUT, 'demo-s6-diag.log'), 'w', encoding='utf-8')
        hist0 = len(controls.history)
        deadline = time.time() + 90
        while time.time() < deadline:
            time.sleep(2)
            if len(controls.history) > hist0:
                break
        new = controls.history[hist0:]
        print('HISTORY', json.dumps(new, indent=1)[:2000], flush=True)
        with open(os.path.join(OUT, 'demo-s6-history.json'), 'w', encoding='utf-8') as f:
            json.dump(new, f, indent=1)
        dispatches = [h for h in new if h.get('state') == 'EXECUTED']
        if not record('exactly one dispatch', len(dispatches) == 1 and len(new) == 1,
                      '%d events (%s)' % (len(new), [h.get('state') for h in new])):
            raise SystemExit(1)
        time.sleep(3)
        after = tv_volume()
        print('TV VOL AFTER', after, flush=True)
        moved = before.get('MUSIC') is not None and after.get('MUSIC') == before.get('MUSIC') + 1
        if not record('tv volume +1 read-back', moved, '%s -> %s' % (before, after)):
            raise SystemExit(1)
        shot(TV, 'demo-s6-tv-after')
        shot(WATCH, 'demo-s6-watch-after')
        st = controls.set_controls({'relay_id': wrid, 'controls': [], 'consent': True})
        if not record('revoked', not [c for c in st.get('controls', []) if c.get('relay_id') == wrid]):
            raise SystemExit(1)
        print('REVOKE-OK -- press Volume + on the watch again (must be denied)', flush=True)
        with open(os.path.join(OUT, 'demo-s6-revoked.json'), 'w', encoding='utf-8') as f:
            json.dump({'at': time.time()}, f)
        hist1 = len(controls.history)
        deadline = time.time() + 180
        while time.time() < deadline:
            time.sleep(2)
            if len(controls.history) > hist1:
                break
        new2 = controls.history[hist1:]
        print('HISTORY2', json.dumps(new2, indent=1)[:2000], flush=True)
        denied = bool(new2) and all(h.get('outcome') in ('DENIED', 'DROPPED', 'EXPIRED', 'SUSPENDED', 'UNKNOWN_CONTROL')
                                for h in new2)
        if not record('re-press denied', denied, json.dumps(new2)[:200]):
            raise SystemExit(1)
        verdict['status'] = 'PASS'
    with open(os.path.join(OUT, 'demo-s6-verdict.json'), 'w', encoding='utf-8') as f:
        json.dump(verdict, f, indent=1)
    print('S6 RESULT: ' + verdict['status'])


if __name__ == '__main__':
    try:
        main()
    finally:
        with open(os.path.join(OUT, 'demo-s6-verdict.json'), 'w', encoding='utf-8') as f:
            json.dump(verdict, f, indent=1)
