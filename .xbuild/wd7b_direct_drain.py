"""Direct-LAN drain proof v2 (Task 7): one-time adb setup, relay 100% adb-free.

1. (adb up) pair over direct URL, code auto-read via adb screencap-free path
   (dumpsys content-desc; TV needs the app foreground: DPAD dismiss + start).
2. (adb up) type one text order into the TV ask field via adb input.
3. adb disconnect the TV. Assert it is gone from `adb devices`.
4. Drain over the DIRECT url only + signed report. Print outcome. PASS.
5. (Bonus) reconnect adb, screenshot the caption for the evidence pack.
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
URL = 'http://192.168.1.15:47800'
OUT = r'E:\shots'


def adb(*args, timeout=60):
    r = subprocess.run([ADB, '-s', TV, *args], capture_output=True, text=True,
                       timeout=timeout, encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def dump_code(tag):
    """Dump TV UI, pull it, extract the pairing code from text nodes. Returns code or None."""
    rc, _ = adb('shell', 'uiautomator', 'dump', '/sdcard/wdcode.xml')
    if rc != 0:
        return None
    subprocess.run([ADB, '-s', TV, 'pull', '/sdcard/wdcode.xml',
                    os.path.join(OUT, 'wdcode-%s.xml' % tag)], capture_output=True)
    try:
        with open(os.path.join(OUT, 'wdcode-%s.xml' % tag), encoding='utf-8') as f:
            xml = f.read()
    except OSError:
        return None
    for m in re.finditer(r'text="([^"]*)"', xml):
        t = m.group(1)
        m2 = re.search(r'(\d{3})\s?(\d{3})', t)
        if m2:
            return m2.group(1) + m2.group(2)
    m = re.search(r'(\d{3})\s(\d{3})', xml)
    return m.group(1) + m.group(2) if m else None


def main():
    import secrets
    from src.cli import Core
    from src.fabric import relay as R
    from src.runtime import command_drain as drain

    # 1. foreground + pair over direct
    subprocess.run([ADB, 'connect', TV], capture_output=True, timeout=30)
    time.sleep(2)
    adb('shell', 'input', 'keyevent', 'KEYCODE_DPAD_CENTER')
    time.sleep(2)
    adb('shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity')
    time.sleep(3)
    base = dump_code('base')
    print('BASE-CODE', base, flush=True)
    send = R.http_transport(URL)
    pc_nonce = secrets.token_hex(16)
    hello = send(None, {'op': 'pair_request', 'pc_nonce': pc_nonce})
    assert hello.get('protocol') == R.PROTOCOL, hello
    rid = hello['relay_id']
    print('HELLO relay_nonce=%s' % hello.get('relay_nonce'), flush=True)
    timeline = [('base', base)]
    code, last = None, base
    for i in range(10):
        c = dump_code('poll%d' % i)
        timeline.append(('poll%d' % i, c))
        if c:
            last = c
        if c and c != base:
            code = c
            break
        time.sleep(4)
    if code is None:
        code = last  # card never changed: fall back to last seen (old behavior), evidence kept
    with open(os.path.join(OUT, 'wd7-codes.log'), 'w', encoding='utf-8') as f:
        json.dump({'timeline': timeline, 'used': code, 'relay_nonce': hello.get('relay_nonce')}, f)
    assert code, 'no pairing code rendered'
    print('CODE', code, 'changed' if code != base else 'UNCHANGED-STALE?', flush=True)
    key = R.derive_key(code, hello['relay_nonce'], pc_nonce)
    with Core() as server:
        reply = send(None, R.command(key, rid, 'discover_capabilities'))
        declared = R.verify(key, reply, None).get('params', {})
        assert 'command_submit' in (declared.get('capabilities') or []), declared
        server.relays.enroll(rid, key, 'direct-tv', declared)
        relay = server.relays.relays[rid]
        relay['send'] = send
        relay['url'] = URL
        relay['urls'] = [URL]
        print('PAIRED-DIRECT %s' % rid, flush=True)
        # 2. type the order via adb (test tooling; the relay stays adb-free)
        _rc, _ = adb('shell', 'uiautomator', 'dump', '/sdcard/wdask.xml')
        subprocess.run([ADB, '-s', TV, 'pull', '/sdcard/wdask.xml',
                        os.path.join(OUT, 'wdask.xml')], capture_output=True)
        import xml.etree.ElementTree as ET
        bounds = None
        try:
            tree = ET.parse(os.path.join(OUT, 'wdask.xml'))
            for node in tree.iter('node'):
                if node.get('class') == 'android.widget.EditText':
                    bounds = node.get('bounds')
                    break
        except Exception:
            pass
        if bounds:
            m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
            x = (int(m.group(1)) + int(m.group(3))) // 2
            y = (int(m.group(2)) + int(m.group(4))) // 2
        else:
            x, y = (400, 480)
        adb('shell', 'input', 'tap', str(x), str(y))
        time.sleep(2)
        adb('shell', 'input', 'text', 'testwifi')
        time.sleep(1)
        adb('shell', 'input', 'keyevent', 'KEYCODE_ENTER')
        time.sleep(2)
        print('ORDER TYPED', flush=True)
        # 3. adb down
        subprocess.run([ADB, 'disconnect', TV], capture_output=True)
        time.sleep(2)
        adv = subprocess.run([ADB, 'devices'], capture_output=True, text=True, timeout=30)
        assert '192.168.1.15' not in (adv.stdout or ''), 'TV adb still up!'
        print('ADB-DOWN confirmed', flush=True)
        # 4. drain over direct only
        t0 = time.time()
        seen = 0
        while time.time() - t0 < 150:
            st = drain.poll_once(server, sync=True)
            seen += st.get('reported', 0)
            if seen:
                break
            time.sleep(5)
        print('DRAINED commands=%d' % seen, flush=True)
        with open(os.path.join(OUT, 'wd7-result.json'), 'w', encoding='utf-8') as f:
            json.dump({'relay_id': rid, 'drained': seen, 'adb_down': True}, f)
        assert seen >= 1, 'no command drained over direct LAN'
        print('WD7 RESULT: PASS (order drained + reported, TV adb down throughout)', flush=True)


if __name__ == '__main__':
    main()
