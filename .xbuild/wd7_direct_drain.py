"""Direct-LAN drain proof (Task 7): pair + drain the TV with TV adb DOWN.

No adb is used for the relay at all: single direct URL
http://192.168.1.15:47800. The owner reads the pairing code on the TV and
types one text order with the remote; sentinel files pace the run:
  E:/shots/wd7-wait.json   written here when the code is on screen
  E:/shots/wd7-code.json   {"code": "123456"} (controller writes on owner reply)
  E:/shots/wd7-paired.json written here once enrolled
  E:/shots/wd7-order.json  (controller writes when the owner typed the order)
  E:/shots/wd7-result.json outcome transcript
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, r'C:\users\TheBox\Desktop\Hackaton\OpenBridge')

URL = 'http://192.168.1.15:47800'
OUT = r'E:\shots'


def wait_for(name, secs):
    end = time.time() + secs
    p = os.path.join(OUT, name)
    while time.time() < end:
        if os.path.exists(p):
            try:
                with open(p, encoding='utf-8-sig') as f:
                    return json.load(f)
            except (OSError, ValueError):
                pass  # partial write: retry on next tick
        time.sleep(2)
    return None


def main():
    import secrets
    from src.cli import Core
    from src.fabric import relay as R
    from src.runtime import command_drain as drain

    adv = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=30)
    assert '192.168.1.15' not in (adv.stdout or ''), 'TV adb must stay DOWN for this proof'
    print('ADB-CHECK TV absent from adb devices: OK', flush=True)
    for stale in ('wd7-code.json', 'wd7-order.json', 'wd7-paired.json', 'wd7-result.json', 'wd7-wait.json',
                'wd7-go.json'):
        try:
            os.unlink(os.path.join(OUT, stale))
        except OSError:
            pass
    print('WAITING for owner GO (no TTL pressure yet)...', flush=True)
    assert wait_for('wd7-go.json', 600), 'no GO from owner'
    with Core() as server:
        send = R.http_transport(URL)
        pc_nonce = secrets.token_hex(16)
        hello = send(None, {'op': 'pair_request', 'pc_nonce': pc_nonce})
        assert hello.get('protocol') == R.PROTOCOL, hello
        rid = hello['relay_id']
        with open(os.path.join(OUT, 'wd7-wait.json'), 'w', encoding='utf-8') as f:
            json.dump({'relay_id': rid, 'at': time.time()}, f)
        print('CODE-ON-TV relay=%s waiting 110 s' % rid, flush=True)
        code_msg = wait_for('wd7-code.json', 110)
        assert code_msg and code_msg.get('code'), 'no code from owner in time'
        code = code_msg['code'].strip().replace(' ', '')
        key = R.derive_key(code, hello['relay_nonce'], pc_nonce)
        reply = send(None, R.command(key, rid, 'discover_capabilities'))
        declared = R.verify(key, reply, None).get('params', {})
        assert 'command_submit' in (declared.get('capabilities') or []), declared
        server.relays.enroll(rid, key, 'direct-tv', declared)
        relay = server.relays.relays[rid]
        relay['send'] = send
        relay['url'] = URL
        relay['urls'] = [URL]
        print('PAIRED-DIRECT %s caps=%s' % (rid, declared.get('capabilities')), flush=True)
        with open(os.path.join(OUT, 'wd7-paired.json'), 'w', encoding='utf-8') as f:
            json.dump({'relay_id': rid, 'at': time.time()}, f)
        assert wait_for('wd7-order.json', 300), 'no order typed in time'
        print('DRAINING over direct LAN (Llama reloads if needed)...', flush=True)
        t0 = time.time()
        seen = 0
        while time.time() - t0 < 120:
            n = drain.poll_once(server, sync=True)
            seen += n
            if n:
                break
            time.sleep(5)
        print('DRAINED commands=%d' % seen, flush=True)
        with open(os.path.join(OUT, 'wd7-result.json'), 'w', encoding='utf-8') as f:
            json.dump({'relay_id': rid, 'drained': seen}, f)
        assert seen >= 1, 'no command drained'
        print('WD7 RESULT: PASS (typed order drained + reported over direct LAN, adb down)', flush=True)


if __name__ == '__main__':
    main()
