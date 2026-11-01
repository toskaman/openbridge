"""Voice loop: drain owner-spoken watch orders over direct LAN (no adb).

Pair the watch over http://192.168.1.14:47800 (owner code via sentinel file),
then poll get_commands + fetch_voice + local STT + local parse + signed report
for ~6 minutes. Every drained voice order is logged with its transcript and
report outcome. Nothing is executed from this channel (reports only).
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, r'C:\users\TheBox\Desktop\Hackaton\OpenBridge')

ADB = r'E:\Android\sdk\platform-tools\adb.exe'
WATCH_URL = 'http://192.168.1.14:47800'
OUT = r'E:\shots'
CODEF = os.path.join(OUT, 'voice-code.json')
LOGF = os.path.join(OUT, 'voice-loop-log.json')


def wait_code(rounds=4, wait_s=100):
    try:
        os.unlink(CODEF)
    except OSError:
        pass
    for rd in range(rounds):
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
                    try:
                        os.unlink(CODEF)
                    except OSError:
                        pass
                    return code
                try:
                    os.unlink(CODEF)
                except OSError:
                    pass
            time.sleep(2)
    return None


def main():
    import secrets
    from src.cli import Core
    from src.fabric import relay as R
    from src.fabric.relay import RelayError
    from src.runtime import command_drain as drain

    log = {'started': time.time(), 'orders': [], 'errors': []}
    send = R.http_transport(WATCH_URL)
    rid = key = declared = None
    for attempt in range(4):
        pc_nonce = secrets.token_hex(16)
        try:
            hello = send(None, {'op': 'pair_request', 'pc_nonce': pc_nonce})
        except Exception as e:
            print('PAIR-REQUEST-FAILED %s: %s' % (type(e).__name__, e), flush=True)
            return 1
        code = wait_code(rounds=1)
        if not code:
            print('no code this round, re-requesting', flush=True)
            continue
        try:
            key = R.derive_key(code, hello['relay_nonce'], pc_nonce)
            rid = hello['relay_id']
            reply = send(None, R.command(key, rid, 'discover_capabilities'))
            declared = R.verify(key, reply, None).get('params', {})
            break
        except RelayError as e:
            print('CODE-REJECTED (%s), re-requesting' % e, flush=True)
            rid = None
    if not rid:
        print('PAIR-FAILED', flush=True)
        return 1
    print('WATCH-PAIRED %s caps=%s' % (rid, declared.get('capabilities')), flush=True)
    with Core() as server:
        server.relays.enroll(rid, key, 'direct-watch', declared)
        relay = server.relays.relays[rid]
        relay['send'] = send
        if 'aead1' in (declared.get('capabilities') or []):
            from src.fabric import aead
            relay['send'] = aead.encrypting_send(send, rid)
            relay['aead'] = aead.VERSION
        relay['url'] = WATCH_URL
        relay['urls'] = [WATCH_URL]
        print('READY-FOR-VOICE -- speak into the watch mic now (6 min window)', flush=True)
        with open(os.path.join(OUT, 'voice-ready.json'), 'w', encoding='utf-8') as f:
            json.dump({'watch_relay': rid, 'at': time.time()}, f)
        end = time.time() + 360
        while time.time() < end:
            st = drain.poll_once(server, sync=True)
            if st.get('commands'):
                print('DRAINED %s' % json.dumps(st), flush=True)
                log['orders'].append({'at': time.time(), 'stats': st})
            for e in st.get('errors', []):
                if e not in log['errors']:
                    log['errors'].append(e)
                    print('DRAIN-ERR %s' % e, flush=True)
            with open(LOGF, 'w', encoding='utf-8') as f:
                json.dump(log, f, indent=1)
            time.sleep(4)
    n = sum(o['stats'].get('reported', 0) for o in log['orders'])
    print('VOICE RESULT: reported=%d errors=%d' % (n, len(log['errors'])), flush=True)
    return 0 if n >= 1 else 1


if __name__ == '__main__':
    sys.exit(main())
