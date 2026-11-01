"""S6b: Watch7 -> TV volume over DIRECT LAN (no watch adb needed).

Watch pairs over http://192.168.1.14:47800; the owner reads the 6-digit code
on the watch screen and relays it via chat (operator writes demo-s6b-code.json).
TV stays on adb for the independent volume read-back + screenshots only.

Fixes vs S6: (1) no watch adb at all; (2) volume baseline re-read at the
moment the press is detected (not 90 s earlier); (3) +1 awaited with a poll
loop instead of a single read; (4) full audio snapshots archived.
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, r'C:\users\TheBox\Desktop\Hackaton\OpenBridge')

ADB = r'E:\Android\sdk\platform-tools\adb.exe'
TV = '192.168.1.15:5555'
WATCH_URL = 'http://192.168.1.14:47800'
OUT = r'E:\shots'
CODEF = os.path.join(OUT, 'demo-s6b-code.json')
verdict = {'steps': {}, 'status': 'FAIL'}


def record(name, ok, detail=''):
    verdict['steps'][name] = {'ok': bool(ok), 'detail': str(detail)[:300]}
    print(('PASS ' if ok else 'FAIL ') + name + (' -- ' + str(detail)[:160] if detail and not ok else ''),
          flush=True)
    return ok


def adb(*args, timeout=60):
    r = subprocess.run([ADB, '-s', TV, *args], capture_output=True, text=True,
                       timeout=timeout, encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def tv_audio_snapshot(tag):
    _rc, out = adb('shell', 'dumpsys', 'audio')
    with open(os.path.join(OUT, 'demo-s6b-audio-%s.txt' % tag), 'w', encoding='utf-8') as f:
        f.write(out)
    vols, cur = {}, None
    for ln in out.splitlines():
        m = re.search(r'STREAM_(\w+)', ln)
        if m:
            cur = m.group(1)
        m3 = re.search(r'streamVolume:(\d+)', ln)
        if m3 and cur and cur not in vols:
            vols[cur] = int(m3.group(1))
    return vols


def wait_code(rounds=4, wait_s=100):
    """Wait for the operator-written code file. Returns code or None."""
    try:
        os.unlink(CODEF)
    except OSError:
        pass
    for rd in range(rounds):
        print('CODE-ROUND %d/%d -- owner: open the Companion on the watch, read the 6-digit code'
              % (rd + 1, rounds), flush=True)
        print('READY-FOR-CODE round=%d (operator writes %s)' % (rd, CODEF), flush=True)
        end = time.time() + wait_s
        while time.time() < end:
            if os.path.exists(CODEF):
                try:
                    with open(CODEF, encoding='utf-8') as f:
                        code = json.load(f).get('code', '')
                except Exception:
                    code = ''
                if isinstance(code, str) and re.fullmatch(r'\d{6}', code):
                    return code, rd
                print('CODE-FILE invalid, still waiting', flush=True)
                try:
                    os.unlink(CODEF)
                except OSError:
                    pass
            time.sleep(2)
        print('CODE-ROUND %d expired, re-requesting' % (rd + 1), flush=True)
    return None, None


def main():
    import secrets
    from src.cli import Core, ensure_discovery
    from src.fabric import relay as R
    from src.fabric.relay import RelayError
    from src.runtime import api_v2, dashboards as D

    subprocess.run([ADB, 'connect', TV], capture_output=True, timeout=30)
    with Core() as server:
        ensure_discovery(server, ['android'])
        devs = (server.fabric_snapshot or {}).get('devices', [])
        labels = [d.get('label') for d in devs]
        print('LABELS', labels, flush=True)
        if not record('discover tv', 'Android TV' in labels, labels):
            raise SystemExit(1)

        # Pair the watch over direct LAN; owner reads the code on the watch.
        send = R.http_transport(WATCH_URL)
        rid, key, declared = None, None, None
        for attempt in range(4):
            pc_nonce = secrets.token_hex(16)
            try:
                hello = send(None, {'op': 'pair_request', 'pc_nonce': pc_nonce})
            except Exception as e:
                record('watch pair_request', False, '%s: %s' % (type(e).__name__, e))
                raise SystemExit(1)
            assert hello.get('protocol') == R.PROTOCOL, hello
            code, _rd = wait_code(rounds=1)
            if not code:
                print('no code this round, re-requesting', flush=True)
                continue
            try:
                os.unlink(CODEF)
            except OSError:
                pass
            try:
                key = R.derive_key(code, hello['relay_nonce'], pc_nonce)
                rid = hello['relay_id']
                reply = send(None, R.command(key, rid, 'discover_capabilities'))
                declared = R.verify(key, reply, None).get('params', {})
                break
            except RelayError as e:
                print('CODE-REJECTED (%s), re-requesting' % e, flush=True)
                rid = None
        if not record('watch paired direct-lan', bool(rid), rid or 'no valid code in 4 rounds'):
            raise SystemExit(1)
        server.relays.enroll(rid, key, 'direct-watch', declared)
        server.relays.relays[rid]['send'] = send
        if 'aead1' in (declared.get('capabilities') or []):
            from src.fabric import aead
            server.relays.relays[rid]['send'] = aead.encrypting_send(send, rid)
            server.relays.relays[rid]['aead'] = aead.VERSION
        server.relays.relays[rid]['url'] = WATCH_URL
        server.relays.relays[rid]['urls'] = [WATCH_URL]
        server.relay_ledger.proved(rid)
        print('WATCH-PAIRED %s' % rid, flush=True)

        controls = api_v2.remote_controls(server)
        router = api_v2.router(server)
        target = router.resolve_target('Android TV')
        state = D.create(controls, rid, 'tv', target, consent=True)
        labels = sorted(c['label'] for c in state.get('controls', []) if c.get('relay_id') == rid)
        if not record('tv controls on watch', labels == ['Volume +', 'Volume -', 'YouTube'], labels):
            raise SystemExit(1)
        ready_vol = tv_audio_snapshot('ready')
        print('READY-FOR-OWNER-PRESS -- press Volume + on the watch now', flush=True)
        with open(os.path.join(OUT, 'demo-s6b-press.json'), 'w', encoding='utf-8') as f:
            json.dump({'watch_relay': rid, 'ready_vol': ready_vol, 'at': time.time()}, f)
        hist0 = len(controls.history)
        pressed = False
        for window in range(3):
            # One 55 s press window per install: the route lease lives ~60 s
            # after discovery, and a rediscovery WITHOUT reinstall voids the
            # grant (R3: 'no route'). Rediscovery and reinstall move together,
            # only between windows, never while a press may be in flight.
            deadline = time.time() + 55
            while time.time() < deadline:
                time.sleep(2)
                if len(controls.history) > hist0:
                    pressed = True
                    break
            if not pressed:
                time.sleep(5)  # grace: the fetcher lands a queued press in ~2 s
                pressed = len(controls.history) > hist0
            if pressed or window == 2:
                break
            print('WINDOW %d empty, rediscover+reinstall for a fresh lease' % (window + 1), flush=True)
            ensure_discovery(server, ['android'])
            router = api_v2.router(server)
            target = router.resolve_target('Android TV')
            D.create(controls, rid, 'tv', target, consent=True)
            print('NEW-WINDOW %d -- press Volume + on the watch' % (window + 2), flush=True)
        tv_audio_snapshot('press')  # auxiliary: dispatch already applied by detect time
        base = ready_vol  # pre-window baseline: the in-process dispatch lands inside
        # the 2 s poll granularity, so a post-detect baseline already contains +1
        new = controls.history[hist0:]
        print('HISTORY', json.dumps(new, indent=1)[:2000], flush=True)
        with open(os.path.join(OUT, 'demo-s6b-history.json'), 'w', encoding='utf-8') as f:
            json.dump(new, f, indent=1)
        dispatches = [h for h in new if h.get('state') == 'EXECUTED']
        if not record('exactly one dispatch', len(dispatches) == 1 and len(new) == 1,
                      '%d events (%s)' % (len(new), [h.get('state') for h in new])):
            raise SystemExit(1)
        # Await +1 with a poll loop (single reads proved flaky on the TV).
        moved, after = False, base
        end = time.time() + 15
        while time.time() < end:
            time.sleep(2)
            after = tv_audio_snapshot('after')
            if base.get('MUSIC') is not None and after.get('MUSIC') == base.get('MUSIC') + 1:
                moved = True
                break
        if not record('tv volume +1 read-back', moved, '%s -> %s' % (base, after)):
            raise SystemExit(1)
        adb('shell', 'screencap', '-p', '/sdcard/demo-s6b-tv-after.png')
        adb('pull', '/sdcard/demo-s6b-tv-after.png', os.path.join(OUT, 'demo-s6b-tv-after.png'))
        st = controls.set_controls({'relay_id': rid, 'controls': [], 'consent': True})
        if not record('revoked', not [c for c in st.get('controls', []) if c.get('relay_id') == rid]):
            raise SystemExit(1)
        print('REVOKE-OK -- press Volume + on the watch again (must be denied)', flush=True)
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
    with open(os.path.join(OUT, 'demo-s6b-verdict.json'), 'w', encoding='utf-8') as f:
        json.dump(verdict, f, indent=1)
    print('S6b RESULT: ' + verdict['status'])


if __name__ == '__main__':
    try:
        main()
    finally:
        with open(os.path.join(OUT, 'demo-s6b-verdict.json'), 'w', encoding='utf-8') as f:
            json.dump(verdict, f, indent=1)
