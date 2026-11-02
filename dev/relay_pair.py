"""Owner-run companion pairing (watch/TV/phone) through the production API.

Usage: python -m dev.relay_pair --category watch [--handle <adb-handle>]

Starts a real server on loopback, runs discovery, sends pair_request
to the chosen device (the code shows ON THE DEVICE), reads the code
the owner types, confirms, enrolls and saves the pairing. Nothing is
simulated; wrong codes count against the 5-attempt budget.
"""
import argparse
import json
import sys
import threading
import urllib.request


def post(base, token, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'X-CSRF-Token': token,
                                          'Origin': base}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main(argv=None, input_fn=input):
    ap = argparse.ArgumentParser()
    ap.add_argument('--category', default='watch')
    ap.add_argument('--handle', default=None)
    args = ap.parse_args(argv)
    from argparse import Namespace
    from src.server import create_server
    from src.adapters.android import default_remember_path
    from src.cli import ensure_discovery, default_providers
    from src.fabric.relay_store import default_owner_store

    store = default_owner_store()
    server = create_server(0, relay_store=store, adb_remember=default_remember_path())
    ensure_discovery(server, default_providers(Namespace()))
    if args.handle:
        handle = args.handle
    else:
        cands = [(d.get('key'), d.get('label')) for d in (server.fabric_snapshot or {}).get('devices', [])
                 if d.get('category') == args.category and d.get('handles')]
        if len(cands) != 1:
            print('FAIL: %d %s candidates %s; pass --handle' % (len(cands), args.category, cands), flush=True)
            return 1
        # map device key -> live adb handle (registry handle values are adapter handles)
        dev = server.fabric_registry.devices[cands[0][0]]
        handle = next((h for h in (dev.get('handles') or {}).values()
                       if server.android.serial_for(h)), None)
        if handle is None:
            print('FAIL: no live ADB handle for %s' % cands[0][1], flush=True)
            return 1
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = 'http://127.0.0.1:%d' % server.server_port
    try:
        hello = post(base, server.csrf_token, '/api/relay-pair-start', {'device_id': handle})
    except Exception as e:  # noqa: BLE001 - owner tool reports, not crashes
        print('FAIL pair-start: %s: %s' % (type(e).__name__, e), flush=True)
        server.shutdown()
        return 1
    print('CODE SHOWN ON DEVICE (relay %s). Read it on the %s, type it here (120s):'
          % (hello.get('relay_id'), args.category), flush=True)
    try:
        code = input_fn('code: ').strip()
    except EOFError:
        print('aborted', flush=True)
        server.shutdown()
        return 1
    try:
        done = post(base, server.csrf_token, '/api/relay-pair-confirm',
                    {'device_id': handle, 'code': code})
    except Exception as e:  # noqa: BLE001 - owner tool reports, not crashes
        print('FAIL pair-confirm: %s: %s' % (type(e).__name__, e), flush=True)
        server.shutdown()
        return 1
    print('PAIRED relay=%s caps=%s' % (done.get('relay_id'), sorted((done.get('declared') or {}).get('capabilities', []))), flush=True)
    server.shutdown()
    return 0 if done.get('state') == 'PAIRED' else 1


if __name__ == '__main__':
    sys.exit(main())
