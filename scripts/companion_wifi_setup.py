"""One-time Companion Wi-Fi setup: ADB grants, first pairing, ADB-disconnected proof.

Usage (serial = `adb devices` entry, e.g. 192.168.1.14:37565):
    python scripts/companion_wifi_setup.py --serial SERIAL [--timeout 120]

Flow: grant DUMP + READ_LOGS over ADB (persist until uninstall) -> pair via
Core (code prompt, shown on the device) -> `adb disconnect` -> signed
get_status over the direct-LAN URL with ADB fully out of the picture.
Exit 0 prints PROOF with the relay id and the transport used.
"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ADB = 'adb'


def run(*args, timeout=60):
    r = subprocess.run([ADB, *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--serial', required=True)
    ap.add_argument('--timeout', type=int, default=120)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    if args.dry_run:
        print('DRY-RUN OK (no device touched)')
        return 0
    if shutil.which(ADB) is None:
        print('ADB_MISSING')
        return 1
    import secrets
    from src.cli import Core, ensure_discovery
    from src.fabric import relay as R
    t0 = time.time()
    for perm in ('android.permission.DUMP', 'android.permission.READ_LOGS'):
        rc, out = run('-s', args.serial, 'shell', 'pm', 'grant',
                      'fr.openbridge.companion', perm, timeout=args.timeout)
        print(('granted ' if rc == 0 else 'GRANT-FAILED ') + perm)
        if rc != 0:
            print(out.strip()[:200])
            return 1
    with Core() as server:
        ensure_discovery(server, ['android'])
        handle = server.android.handle_for(args.serial)
        if handle is not None and not any(
                handle in (d.get('handles') or {}).values()
                for d in (server.fabric_snapshot or {}).get('devices', [])):
            handle = None
        if not handle:
            print('SERIAL NOT IN DISCOVERY')
            return 1
        urls = server.android.relay_urls(handle)
        print('URLS', urls)
        # The pairing code only renders while MainActivity is foreground
        # (TVs fall back to ambient mode within a minute), so raise it now.
        # A keypress first: a fullscreen Dream ignores plain `am start`.
        run('-s', args.serial, 'shell', 'input', 'keyevent',
            'KEYCODE_DPAD_CENTER')
        run('-s', args.serial, 'shell', 'am', 'start', '-n',
            'fr.openbridge.companion/.MainActivity')
        for _ in range(10):
            time.sleep(3)
            _rc, acts = run('-s', args.serial, 'shell', 'dumpsys',
                            'activity', 'activities')
            if 'fr.openbridge.companion/.MainActivity' in acts and (
                    'topResumedActivity' in acts or 'mResumedActivity' in acts):
                break
        send = R.failover_transport(urls)
        pc_nonce = secrets.token_hex(16)
        try:
            hello = send(None, {'op': 'pair_request', 'pc_nonce': pc_nonce})
            rid = hello.get('relay_id')
            relay_nonce = hello.get('relay_nonce')
            if rid is None or relay_nonce is None:
                print('PAIRING-FAILED hello missing relay_id or relay_nonce')
                return 1
            code = input('Enter the %s code shown on the device: '
                         % rid).strip().replace(' ', '')
            key = R.derive_key(code, relay_nonce, pc_nonce)
            reply = send(None, R.command(key, rid, 'discover_capabilities'))
            R.verify(key, reply, None)
        except (EOFError, KeyboardInterrupt, R.RelayError, OSError,
                KeyError) as e:
            print('PAIRING-FAILED %s: %s' % (type(e).__name__, e))
            return 1
        print('PAIRED', rid)
        rc, out = run('disconnect', args.serial)
        if rc != 0:
            print('ADB-DISCONNECT-WARNING', out.strip()[:120])
        time.sleep(2)
        direct = server.android.direct_url(handle)
        if direct is None:
            direct = server.android.lan_url_for_relay(rid)
        if direct is None:
            print('NO DIRECT URL (no serial IP and no mDNS match)')
            return 1
        proof = R.http_transport(direct)(
            None, R.command(key, rid, 'get_status'))
        R.verify(key, proof, None)
        print('PROOF relay=%s transport=direct-lan url=%s elapsed=%.0fs'
              % (rid, direct, time.time() - t0))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
