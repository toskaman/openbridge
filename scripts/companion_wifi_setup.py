"""One-time Companion Wi-Fi setup: ADB grants, first pairing, ADB-disconnected proof.

Usage (serial = `adb devices` entry, e.g. 192.168.1.14:37565):
    python scripts/companion_wifi_setup.py --serial SERIAL [--timeout 120]

Flow: grant DUMP + READ_LOGS over ADB (persist until uninstall) -> pair via
Core (code prompt, shown on the device) -> `adb disconnect` -> signed
get_status over the direct-LAN URL with ADB fully out of the picture.
Exit 0 prints PROOF with the relay id and the transport used.
"""
import argparse
import subprocess
import sys
import time

sys.path.insert(0, '.')

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
    import secrets
    from src.cli import Core, ensure_discovery
    from src.fabric import relay as R
    t0 = time.time()
    for perm in ('android.permission.DUMP', 'android.permission.READ_LOGS'):
        rc, out = run('-s', args.serial, 'shell', 'pm', 'grant', 'fr.openbridge.companion', perm)
        print(('granted ' if rc == 0 else 'GRANT-FAILED ') + perm)
        if rc != 0:
            return 1
    with Core() as server:
        ensure_discovery(server, ['android'])
        handle = None
        for d in (server.fabric_snapshot or {}).get('devices', []):
            for serial, h in (server.android._handles or {}).items():
                if serial == args.serial and h in (d.get('handles') or {}).values():
                    handle = h
        if not handle:
            print('SERIAL NOT IN DISCOVERY')
            return 1
        urls = server.android.relay_urls(handle)
        print('URLS', urls)
        send = R.failover_transport(urls)
        pc_nonce = secrets.token_hex(16)
        hello = send(None, {'op': 'pair_request', 'pc_nonce': pc_nonce})
        code = input('Enter the %s code shown on the device: ' % hello.get('relay_id')).strip().replace(' ', '')
        key = R.derive_key(code, hello['relay_nonce'], pc_nonce)
        rid = hello['relay_id']
        reply = send(None, R.command(key, rid, 'discover_capabilities'))
        R.verify(key, reply, None)
        print('PAIRED', rid)
        run('disconnect', args.serial)
        time.sleep(2)
        direct = [u for u in urls if not u.startswith('http://127.0.0.1')]
        if not direct:
            print('NO DIRECT URL (USB serial without mDNS match)')
            return 1
        proof = R.http_transport(direct[0])(None, R.command(key, rid, 'get_status'))
        R.verify(key, proof, {})
        print('PROOF relay=%s transport=direct-lan url=%s elapsed=%.0fs' % (rid, direct[0], time.time() - t0))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
