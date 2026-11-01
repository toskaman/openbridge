"""C1 relay contract: externally visible pairing/transport failures are RelayError.

F30 (tests/fabric/test_f30_redteam_safe.py) pinned the then-current behavior, including unclean types
(AttributeError/KeyError/ValueError) for hostile relay input. Campaign One normalizes those to RelayError
with one structured reason per cause, keeps the programming-error guards (verify's seen_nonces TypeError)
untouched, and guarantees a refused enroll leaves no partial pairing state.
"""
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from src.fabric import relay as R

KEY = R.derive_key('123456', 'rn', 'pn')
RID = 'c1-relay'


def _hello(rid=RID, nonce='relay-nonce'):
    return {'protocol': R.PROTOCOL, 'relay_id': rid, 'relay_nonce': nonce}


def _signed(params, key=KEY, rid=RID, nonce='n-c1'):
    now = int(time.time())
    msg = {'protocol': R.PROTOCOL, 'relay_id': rid, 'op': 'reply', 'params': params,
           'nonce': nonce, 'issued_at': now, 'expires_at': now + 30}
    return {**msg, 'mac': R.sign(key, msg)}


class PairContractTests(unittest.TestCase):
    def test_non_dict_hello_is_relay_error(self):
        # Was AttributeError (hello.get on a non-dict).
        for hello in (None, 123, 'pair-hello', ['pair_request'], ('x',)):
            with self.assertRaisesRegex(R.RelayError, 'not an object'):
                R.pair(lambda _r, _m, h=hello: h, lambda: '123456')

    def test_missing_or_malformed_relay_id_is_relay_error(self):
        # Missing was KeyError; malformed shapes now fail closed here instead of downstream.
        bad_ids = [None, 123, '', 'has space', 'bad!char', 'x' * 61, '-lead']
        for rid in bad_ids:
            hello = _hello()
            if rid is None:
                del hello['relay_id']
            else:
                hello['relay_id'] = rid
            with self.assertRaisesRegex(R.RelayError, 'valid relay id', msg=repr(rid)):
                R.pair(lambda _r, _m, h=hello: h, lambda: '123456')

    def test_valid_long_relay_id_still_pairs(self):
        # The shape check must not reject legitimate ids (upper bound: 60 chars).
        rid = 'r' * 60
        state = {}

        def send(_r, msg):
            if msg.get('op') == 'pair_request':
                state['pc'] = msg['pc_nonce']
                return _hello(rid=rid, nonce='nn' * 8)
            key = R.derive_key('424242', 'nn' * 8, state['pc'])
            R.verify(key, msg, None)
            return _signed({'capabilities': ['ble_scan']}, key=key, rid=rid)

        got_rid, _key, declared = R.pair(send, lambda: '424242')
        self.assertEqual((got_rid, declared['capabilities']), (rid, ['ble_scan']))

    def test_non_dict_pairing_reply_is_relay_error(self):
        # Was AttributeError inside verify (message.items on a non-dict).
        for reply in (None, ['signed'], 'blob', 42):
            def send(_r, msg, r=reply):
                if msg.get('op') == 'pair_request':
                    return _hello()
                return r

            with self.assertRaises(R.RelayError):
                R.pair(send, lambda: '123456')

    def test_transport_errors_propagate_untouched(self):
        # Normalization covers malformed data, not dead links: transport errors keep their type.
        for boom in (OSError('refused'), TimeoutError('slow')):
            def send(_r, _m, b=boom):
                raise b

            with self.assertRaises(type(boom)):
                R.pair(send, lambda: '123456')


class EnrollContractTests(unittest.TestCase):
    def test_non_dict_declared_is_relay_error_without_partial_state(self):
        # Was AttributeError (declared.get on a non-dict).
        for i, declared in enumerate((None, 123, 'x', [], ('ble_scan',))):
            mgr = R.RelayManager(lambda r, m: {})
            rid = 'c1-%d' % i
            with self.assertRaisesRegex(R.RelayError, 'must be an object'):
                mgr.enroll(rid, KEY, 'dev', declared)
            self.assertNotIn(rid, mgr.relays)

    def test_non_dict_permissions_is_relay_error_without_partial_state(self):
        # Was ValueError/TypeError from dict(...) on a non-mapping.
        for i, perms in enumerate(('oops', [1, 2], 123, None)):
            mgr = R.RelayManager(lambda r, m: {})
            rid = 'c1p-%d' % i
            with self.assertRaisesRegex(R.RelayError, 'permissions must be an object'):
                mgr.enroll(rid, KEY, 'dev', {'capabilities': ['ble_scan'], 'permissions': perms})
            self.assertNotIn(rid, mgr.relays)

    def test_non_list_capabilities_is_relay_error_without_partial_state(self):
        # Was TypeError from iterating a non-iterable.
        for i, caps in enumerate((123, None, 4.5, True)):
            mgr = R.RelayManager(lambda r, m: {})
            rid = 'c1c-%d' % i
            with self.assertRaisesRegex(R.RelayError, 'capabilities must be a list'):
                mgr.enroll(rid, KEY, 'dev', {'capabilities': caps})
            self.assertNotIn(rid, mgr.relays)

    def test_malformed_shapes_coerce_to_empty_without_grant(self):
        # Preserved F30 coercion: malformed capability containers grant nothing.
        for declared in ({'capabilities': 'ble_scan'},
                         {'capabilities': {'ble_scan': True}},
                         {'capabilities': [None, 123]}):
            mgr = R.RelayManager(lambda r, m: {})
            mgr.enroll(RID, KEY, 'dev', declared)
            self.assertEqual(mgr.relays[RID]['capabilities'], set())
            self.assertEqual(mgr.eligible('ble_scan'), [])

    def test_failed_enroll_preserves_existing_entry(self):
        # A refused re-enroll under an existing id must not wipe or half-rewrite it.
        mgr = R.RelayManager(lambda r, m: {})
        mgr.enroll(RID, KEY, 'dev-c1',
                   {'capabilities': ['ble_scan'],
                    'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
        mgr.relays[RID]['failures'] = 2
        before = dict(mgr.relays[RID])
        before['capabilities'] = set(before['capabilities'])
        before['permissions'] = dict(before['permissions'])
        before['seen'] = dict(before['seen'])
        for bad in (None, {'capabilities': ['ble_scan'], 'permissions': 'oops'}):
            with self.assertRaises(R.RelayError):
                mgr.enroll(RID, KEY, 'dev-evil', bad)
        self.assertEqual(mgr.relays[RID], before)
        self.assertEqual(mgr.eligible('ble_scan'), [RID])  # still fully usable


class VerifyContractTests(unittest.TestCase):
    def test_non_dict_message_is_relay_error(self):
        # Was AttributeError (message.items on a non-dict).
        for bad in (None, ['op'], 'blob', 42):
            with self.assertRaisesRegex(R.RelayError, 'not an object'):
                R.verify(KEY, bad, None)
            with self.assertRaisesRegex(R.RelayError, 'not an object'):
                R.verify(KEY, bad, {})

    def test_missing_nonce_is_relay_error(self):
        # Was KeyError (msg['nonce'] on a nonce-less envelope).
        now = int(time.time())
        msg = {'protocol': R.PROTOCOL, 'relay_id': RID, 'op': 'get_status',
               'params': {}, 'issued_at': now, 'expires_at': now + 30}
        signed = {**msg, 'mac': R.sign(KEY, msg)}
        with self.assertRaisesRegex(R.RelayError, 'missing nonce'):
            R.verify(KEY, signed, {})

    def test_programming_error_guards_keep_their_types(self):
        # Normalization covers wire data only: API misuse still raises TypeError, never RelayError.
        cmd = R.command(KEY, RID, 'get_status')
        with self.assertRaises(TypeError):
            R.verify(KEY, cmd, set())
        with self.assertRaises(TypeError):
            R.verify(KEY, cmd, [])


class HttpTransportContractTests(unittest.TestCase):
    def setUp(self):
        bodies = self._bodies = {}

        class H(BaseHTTPRequestHandler):
            def do_POST(h):
                n = int(h.headers.get('Content-Length', 0))
                h.rfile.read(n)
                body = bodies['current']
                h.send_response(200)
                h.send_header('Content-Type', 'application/json')
                h.send_header('Content-Length', str(len(body)))
                h.end_headers()
                h.wfile.write(body)

            def log_message(self, *a):
                pass

        self._srv = HTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        self.send = R.http_transport('http://127.0.0.1:%d' % self._srv.server_port)

    def tearDown(self):
        self._srv.shutdown()
        self._srv.server_close()

    def test_oversize_refused_with_structured_reason(self):
        # Was JSONDecodeError from read(300_000)-truncation; now an explicit size check.
        self._bodies['current'] = json.dumps({'ok': True, 'pad': 'x' * (2 << 20)}).encode()
        with self.assertRaisesRegex(R.RelayError, 'too large'):
            self.send(None, {'op': 'probe'})
        self._bodies['current'] = json.dumps({'ok': True}).encode()
        self.assertEqual(self.send(None, {'op': 'probe'}), {'ok': True})

    def test_size_boundary_exact_cap_ok(self):
        base = json.dumps({'ok': True, 'pad': ''}).encode()
        at_cap = json.dumps({'ok': True, 'pad': 'x' * (R.MAX_REPLY_BYTES - len(base))}).encode()
        self.assertEqual(len(at_cap), R.MAX_REPLY_BYTES)
        self._bodies['current'] = at_cap
        self.assertTrue(self.send(None, {'op': 'probe'})['ok'])
        # One byte over is still valid JSON (trailing space): refused on size, not on parse.
        self._bodies['current'] = at_cap + b' '
        with self.assertRaisesRegex(R.RelayError, 'too large'):
            self.send(None, {'op': 'probe'})

    def test_malformed_json_refused_with_structured_reason(self):
        # Was JSONDecodeError (a ValueError).
        for raw in (b'not json{{{', b'\xff\xfe\x00binary', b'{"truncated": true'):
            self._bodies['current'] = raw
            with self.assertRaisesRegex(R.RelayError, 'not valid JSON', msg=repr(raw[:20])):
                self.send(None, {'op': 'probe'})
        self._bodies['current'] = json.dumps({'ok': True}).encode()
        self.assertEqual(self.send(None, {'op': 'probe'}), {'ok': True})

    def test_deep_nesting_refused_with_structured_reason(self):
        # Deeply nested input was bare RecursionError. The exact reason is
        # platform-dependent (C-stack-limited parse: RecursionError on small
        # stacks -> 'not valid JSON'; successful parse on large stacks ->
        # 'must be a JSON object'), but it is always a structured RelayError,
        # never a bare exception or a phantom success.
        self._bodies['current'] = b'[' * 20000 + b']' * 20000
        with self.assertRaises(R.RelayError):
            self.send(None, {'op': 'probe'})
        self._bodies['current'] = json.dumps({'ok': True}).encode()
        self.assertEqual(self.send(None, {'op': 'probe'}), {'ok': True})

    def test_non_object_json_refused_with_structured_reason(self):
        # Valid JSON of the wrong shape: refused here, never passed downstream to crash verify.
        for raw in (b'[1, 2, 3]', b'"just a string"', b'42', b'null', b'true'):
            self._bodies['current'] = raw
            with self.assertRaisesRegex(R.RelayError, 'must be a JSON object', msg=repr(raw)):
                self.send(None, {'op': 'probe'})

    def test_reply_read_is_bounded(self):
        # The cap is enforced by one bounded read: a 2 MiB body never lands in memory whole.
        seen = []
        big = b'x' * (2 << 20)

        class FakeResp:
            def read(self, n=-1):
                seen.append(n)
                return big[:n] if isinstance(n, int) and n >= 0 else big

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        opener = mock.Mock()
        opener.open.return_value = FakeResp()
        with mock.patch.object(R, '_opener', return_value=opener):
            send = R.http_transport('http://127.0.0.1:9')
            with self.assertRaises(R.RelayError):
                send(None, {'op': 'probe'})
        self.assertTrue(seen, 'expected at least one bounded read')
        self.assertLessEqual(max(seen), R.MAX_REPLY_BYTES + 1)

    def test_failover_propagates_malformed_reply_without_rerouting(self):
        # Malformed replies (now RelayError) fail closed on the first URL, like refusals.
        calls = []

        def fake(url, timeout=25):
            def send(_r, m):
                calls.append(url)
                raise R.RelayError('Relay reply is not valid JSON')
            return send

        with mock.patch.object(R, 'http_transport', side_effect=fake):
            send = R.failover_transport(['http://127.0.0.1:1', 'http://127.0.0.1:2'])
            with self.assertRaises(R.RelayError):
                send(None, {'op': 'x'})
        self.assertEqual(calls, ['http://127.0.0.1:1'])


if __name__ == '__main__':
    unittest.main()
