"""Owner toggle for per-PC full control (deep Windows rights).

Usage:
  python -m dev.pc_full_control --status --device-key <key>
  python -m dev.pc_full_control --on --device-key <key>    # warning + typed YES
  python -m dev.pc_full_control --off --device-key <key>

Enabling prints the full warning and requires typing YES (no default,
no flag bypass). Disabling is immediate and unconditional.
"""
import argparse
import sys


def confirm(warning, input_fn=input):
    print(warning, flush=True)
    try:
        answer = input_fn('Type YES to enable full control (anything else aborts): ')
    except EOFError:
        return False
    return answer.strip() == 'YES'


def main(argv=None, input_fn=input):
    ap = argparse.ArgumentParser()
    ap.add_argument('--device-key', required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--status', action='store_true')
    g.add_argument('--on', action='store_true')
    g.add_argument('--off', action='store_true')
    args = ap.parse_args(argv)
    from argparse import Namespace
    from src.server import create_server
    from src.adapters.android import default_remember_path
    from src.cli import ensure_discovery, default_providers
    from src.runtime import api_v2
    from src.fabric import pc_consent as PC
    from pathlib import Path
    import os
    server = create_server(adb_remember=default_remember_path())
    ensure_discovery(server, default_providers(Namespace()))
    if getattr(server, 'pc_consent', None) is None:
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
        server.pc_consent = PC.PcConsentStore(root / PC.FILENAME)
    if args.status:
        code, body = api_v2.get(server, '/api/v2/pc/full-control',
                                'device_key=' + args.device_key)
        print('full control: %s (http %d)' % ('ON' if body.get('enabled') else 'OFF', code))
        return 0 if code == 200 else 1
    if args.on:
        code, body = api_v2.get(server, '/api/v2/pc/full-control',
                                'device_key=' + args.device_key)
        if code != 200:
            print('error: %s' % body.get('error'), flush=True)
            return 1
        if not confirm(body.get('warning', PC.FULL_CONTROL_WARNING), input_fn):
            print('aborted: full control stays OFF', flush=True)
            return 1
        code, body = api_v2.post(server, '/api/v2/pc/full-control',
                                 {'device_key': args.device_key, 'enable': True, 'confirm': True})
        print('full control: %s' % ('ON' if body.get('enabled') else 'OFF'), flush=True)
        return 0 if code == 200 and body.get('enabled') else 1
    code, body = api_v2.post(server, '/api/v2/pc/full-control',
                             {'device_key': args.device_key, 'enable': False})
    print('full control: %s' % ('ON' if body.get('enabled') else 'OFF'), flush=True)
    return 0 if code == 200 and not body.get('enabled') else 1


if __name__ == '__main__':
    sys.exit(main())
