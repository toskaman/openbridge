"""Campaign Three §5.6 + judge-C W3: one-command scripted UI replay fallback.

Runs the REAL OpenBridge UI on loopback with the S5/S5b receipt replay and
opens it in a browser — fully offline, no owner hardware, no model, no ADB::

    python scripts/run/demo_fallback.py

Loopback only. No pairing, install, command, model request, or discovery
probe is issued; the replay view performs a single GET of the recorded
receipt bundle. ``--check`` verifies headlessly (CI-friendly) instead.
"""
import argparse
import json
import sys
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.server import create_server  # noqa: E402


REPLAY_ROUTE = '/#/replay/autoplay'
CHECK_WANT = ('tx-ab731d7b885b5e1a', 'tx-4a96f8f626a1adc5',
              'relay-dabd2a796665', '7e39303524c8a032', '0ffdd012f9e02118')


def fetch_bundle(port):
    url = 'http://127.0.0.1:%d/api/demo-replay' % port
    request = urllib.request.Request(url, headers={'Host': '127.0.0.1:%d' % port})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read().decode('utf-8'))


def check(port):
    """Headless verification: bundle identity, 9 stages × 2 scenarios, labels."""
    from src.runtime.demo_replay import STAGES
    status, payload = fetch_bundle(port)
    assert status == 200, 'demo-replay endpoint status %r' % status
    assert payload.get('playback') == 'SIMULATED', 'playback label missing'
    assert payload.get('live_request') is False, 'must declare live_request=false'
    bundle = payload['bundle']
    assert bundle['bundle_id'] == 'demo-replay-s5-s5b', 'bundle identity'
    assert list(bundle['stages_order']) == list(STAGES), '9-stage chain'
    assert len(bundle['scenarios']) == 2, 'S5 + S5b scenarios'
    text = json.dumps(bundle)
    for want in CHECK_WANT:
        assert want in text, 'receipt value missing: %s' % want
    for scenario in bundle['scenarios']:
        assert set(scenario['stages']) == set(STAGES), scenario['scenario_id']
        assert scenario['honest_limits'], scenario['scenario_id']
    print('demo_fallback --check: PASS (2 scenarios × 9 stages, SIMULATED, receipts present)')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0,
                        help='Loopback port (default 0 = automatic free port; '
                             'avoids colliding with any live server)')
    parser.add_argument('--no-browser', action='store_true',
                        help='Serve without opening a browser')
    parser.add_argument('--check', action='store_true',
                        help='Headless verify then exit (no browser, CI-friendly)')
    args = parser.parse_args(argv)
    server = create_server(args.port)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = 'http://127.0.0.1:%d%s' % (server.server_port, REPLAY_ROUTE)
    try:
        if args.check:
            check(server.server_port)
            return 0
        print('OpenBridge demo fallback (OFFLINE REPLAY, SIMULATED):')
        print('  UI: %s' % url)
        print('  Loopback only · no hardware · no model · no pairing · no discovery probes')
        print('  Stop with Ctrl+C.')
        if not args.no_browser:
            import webbrowser
            webbrowser.open(url)
        worker.join()
    except KeyboardInterrupt:
        print('\nDemo fallback stopped.')
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
