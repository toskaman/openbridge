"""C1 second-pass fix-loop regressions (F1/F2/F3/F5).

Each class pins one audit finding; every unexpected escape (KeyError,
AttributeError, RuntimeError) fails the test instead of passing silently.
"""
import io
import socket
import threading
import time
import unittest

from src.fabric import relay as R

KEY = R.derive_key('123456', 'rn', 'pn')


def _declared():
    return {'capabilities': ['ble_scan'],
            'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}}


def _signed_reply(key, rid, params, nonce):
    now = int(time.time())
    rep = {'protocol': R.PROTOCOL, 'relay_id': rid, 'op': 'reply', 'params': params,
           'nonce': nonce, 'issued_at': now, 'expires_at': now + 30}
    return {**rep, 'mac': R.sign(key, rep)}


def _enroll(mgr, rid):
    mgr.enroll(rid, KEY, 'dev-' + rid, _declared())


class PairStartContractTests(unittest.TestCase):
    """F1: relay_action pair-start validates the hello exactly like R.pair."""

    def setUp(self):
        from unittest.mock import patch
        from src.server import create_server
        from src.fabric.session import SessionJournal
        import tempfile
        self.server = create_server(0, fabric_salt=b's',
                                    session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        self._patch = patch.object(self.server.android, 'relay_urls',
                                   return_value=['http://127.0.0.1:47800'])
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.addCleanup(self.server.server_close)

    def start(self, hello):
        return self.server.relay_action('/api/relay-pair-start', {'device_id': 'android-h'},
                                        transport_factory=lambda u: (lambda _r, _m: hello))

    def test_non_dict_hello_is_relay_error(self):
        # Was AttributeError (hello.get on a non-dict) escaping as a dropped connection.
        for hello in (None, 123, 'pair-hello', ['pair_request']):
            with self.assertRaisesRegex(R.RelayError, 'not an object', msg=repr(hello)):
                self.start(hello)
            self.assertNotIn('android-h', self.server.relay_pending)

    def test_missing_or_malformed_relay_id_is_relay_error(self):
        # Missing was KeyError at hello['relay_id']; malformed ids now fail closed here.
        base = {'protocol': R.PROTOCOL, 'relay_nonce': 'ab' * 8}
        cases = [dict(base)]
        for bad in ('', 'has space', 'bad!char', 'x' * 61, '-lead', 123, None):
            cases.append(dict(base, relay_id=bad))
        for hello in cases:
            with self.assertRaisesRegex(R.RelayError, 'valid relay id', msg=repr(hello)):
                self.start(hello)
            self.assertNotIn('android-h', self.server.relay_pending)

    def test_wrong_protocol_or_nonce_is_relay_error(self):
        bad = {'protocol': R.PROTOCOL, 'relay_id': 'phone', 'relay_nonce': 'ab' * 8}
        for hello in (dict(bad, protocol='nope'), dict(bad, relay_nonce=123),
                      dict(bad, protocol=None)):
            with self.assertRaisesRegex(R.RelayError, 'Not an OpenBridge Companion', msg=repr(hello)):
                self.start(hello)
            self.assertNotIn('android-h', self.server.relay_pending)

    def test_valid_hello_still_starts_pairing(self):
        hello = {'protocol': R.PROTOCOL, 'relay_id': 'phone', 'relay_nonce': 'ab' * 8,
                 'declared': {'capabilities': ['ble_scan']}}
        out = self.start(hello)
        self.assertEqual((out['state'], out['relay_id']), ('CODE_SHOWN_ON_DEVICE', 'phone'))
        self.assertEqual(out['declared'], {'capabilities': ['ble_scan']})
        self.assertIn('android-h', self.server.relay_pending)


class ConcurrentScanHammerTests(unittest.TestCase):
    """F2: enroll/revoke racing eligible()/scan() yields only RelayError, never
    RuntimeError (dict changed size) or KeyError (revoke between check and lookup)."""

    def test_hammer_mutation_against_scan_and_eligible(self):
        import itertools

        class HammerWire:
            """Thread-safe fake wire: one-shot command checks (no shared nonce
            cache, so transport-level races cannot pollute the manager verdict)."""

            def __init__(self):
                self._lock = threading.Lock()
                self._nonces = itertools.count()
                self.calls = 0

            def __call__(self, relay, message):
                msg = R.verify(KEY, message, None)
                with self._lock:
                    self.calls += 1
                    nonce = 'hammer-%d' % next(self._nonces)
                return _signed_reply(KEY, msg['relay_id'], {'observations': []}, nonce)

        wire = HammerWire()
        mgr = R.RelayManager(wire)
        for i in range(8):
            _enroll(mgr, 'hammer-%d' % i)
        errors = []
        barrier = threading.Barrier(8)

        def grow():
            # Constant size changes + dict resizes: trips unlocked eligible() iteration.
            try:
                barrier.wait(10)
                for i in range(3000):
                    _enroll(mgr, 'grow-%d' % i)
            except Exception as e:  # noqa: BLE001 - collected, asserted below
                errors.append(e)

        def churn():
            # Revoke/re-enroll the duel relay in a tight loop: trips check-then-lookup TOCTOU.
            try:
                barrier.wait(10)
                for _ in range(3000):
                    mgr.revoke('hammer-0')
                    _enroll(mgr, 'hammer-0')
            except Exception as e:  # noqa: BLE001 - collected, asserted below
                errors.append(e)

        def probe(explicit):
            try:
                barrier.wait(10)
                for i in range(1500):
                    try:
                        mgr.eligible('ble_scan')
                    except R.RelayError:
                        pass
                    try:
                        if explicit:
                            mgr.scan(1, relay_id='hammer-0')
                        else:
                            mgr.scan(1)
                    except (R.RelayError, OSError, TimeoutError):
                        pass  # no eligible relay / busy / revoked mid-flight: all contractual
            except Exception as e:  # noqa: BLE001 - collected, asserted below
                errors.append(e)

        threads = ([threading.Thread(target=grow), threading.Thread(target=churn)] +
                   [threading.Thread(target=probe, args=(True,)) for _ in range(3)] +
                   [threading.Thread(target=probe, args=(False,)) for _ in range(3)])
        for th in threads:
            th.start()
        for th in threads:
            th.join(60)
        self.assertFalse([th for th in threads if th.is_alive()])
        self.assertGreater(wire.calls, 100, 'the hammer never got a scan through')
        escapes = [e for e in errors if not isinstance(e, (R.RelayError, OSError, TimeoutError))]
        self.assertEqual(escapes, [])
        self.assertEqual(errors, [])


class RevokedScanTests(unittest.TestCase):
    """F3: a revoke (or permission loss) after verify voids the scan result."""

    def _manager(self, hook):
        seen = {}

        def send(relay, message):
            msg = R.verify(KEY, message, seen)
            if msg['op'] == 'start_discovery':
                hook()
            return _signed_reply(KEY, msg['relay_id'],
                                 {'observations': [{'address': 'AA:BB:CC:DD:EE:FF'}]},
                                 'f3-%d' % len(seen))

        mgr = R.RelayManager(send)
        _enroll(mgr, 'tv')
        return mgr

    def test_revoke_mid_scan_voids_result(self):
        mgr = self._manager(lambda: mgr.revoke('tv'))
        with self.assertRaisesRegex(R.RelayError, 'revoked during scan'):
            mgr.scan(1)
        self.assertNotIn('tv', mgr.relays)

    def test_permission_loss_mid_scan_voids_result(self):
        def hook():
            mgr.relays['tv']['permissions'] = {}  # owner consent withdrawn mid-flight

        mgr = self._manager(hook)
        with self.assertRaisesRegex(R.RelayError, 'revoked during scan'):
            mgr.scan(1)

    def test_unrevoked_scan_still_returns_observations(self):
        mgr = self._manager(lambda: None)
        rid, found = mgr.scan(1)
        self.assertEqual((rid, found[0]['address']), ('tv', 'AA:BB:CC:DD:EE:FF'))
        self.assertEqual(mgr.relays['tv']['failures'], 0)


class BodyDeadlineTests(unittest.TestCase):
    """F5: the POST body read has a monotonic total deadline, not just a per-recv timeout."""

    def test_read_body_returns_full_body(self):
        from src import server as S
        self.assertEqual(S._read_body(io.BytesIO(b'{"a":1}'), 7), b'{"a":1}')
        self.assertEqual(S._read_body(io.BytesIO(b''), 0), b'')

    def test_read_body_short_read_is_value_error(self):
        from src import server as S
        with self.assertRaises(ValueError):
            S._read_body(io.BytesIO(b'{"a"'), 7)

    def test_read_body_deadline_fires_on_slow_drip(self):
        from src import server as S

        class Drip:
            def read(self, n):
                time.sleep(0.3)
                return b'x' * n

        old, S.BODY_TIMEOUT_S = S.BODY_TIMEOUT_S, 0.2
        try:
            t0 = time.monotonic()
            with self.assertRaises(TimeoutError):
                S._read_body(Drip(), 10)
            self.assertLess(time.monotonic() - t0, 5)
        finally:
            S.BODY_TIMEOUT_S = old

    def test_slow_drip_post_is_closed_and_server_stays_healthy(self):
        import json
        import tempfile
        import urllib.request
        from src import server as S
        from src.fabric.session import SessionJournal
        server = S.create_server(0, fabric_salt=b's',
                                 session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        base = 'http://127.0.0.1:%d' % server.server_port
        with urllib.request.urlopen(base + '/api/session') as r:
            csrf = json.loads(r.read())['csrf_token']
        old, S.BODY_TIMEOUT_S = S.BODY_TIMEOUT_S, 2
        try:
            # 1 byte every 0.6 s: never trips the 5 s per-recv timeout, must trip the 2 s total.
            sock = socket.create_connection(('127.0.0.1', server.server_port), timeout=10)
            try:
                sock.sendall(
                    ('POST /api/inspect HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nOrigin: %s\r\n'
                     'X-CSRF-Token: %s\r\nContent-Type: application/json\r\n'
                     'Content-Length: 100\r\nConnection: close\r\n\r\n'
                     % (server.server_port, base, csrf)).encode())
                sock.sendall(b'{')
                t0 = time.monotonic()
                for _ in range(20):
                    time.sleep(0.6)
                    try:
                        sock.sendall(b'x')
                    except OSError:
                        break  # server already closed us: the deadline fired
                    sock.settimeout(0.1)
                    try:
                        if sock.recv(1):
                            break  # a reply arrived: the handler moved on
                    except (TimeoutError, OSError):
                        pass
                elapsed = time.monotonic() - t0
                self.assertGreaterEqual(elapsed, 1.5, 'reply came before the deadline: the drip never reached the body guard')
                self.assertLess(elapsed, 10, 'slow drip held the handler past the total deadline')
            finally:
                sock.close()
        finally:
            S.BODY_TIMEOUT_S = old
        with urllib.request.urlopen(base + '/api/session', timeout=10) as r:  # still healthy
            self.assertEqual(r.status, 200)


if __name__ == '__main__':
    unittest.main()
