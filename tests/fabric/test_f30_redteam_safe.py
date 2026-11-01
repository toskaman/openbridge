"""F30 SAFE red-team: replay/expiry, AEAD tamper, malformed pairing, oversize bounds.

Tests-only, no exploits, no network beyond loopback fixtures. Each test asserts the
bridge refuses or caps hostile/malformed input with a catchable error and stays usable.
"""
import base64
import json
import struct
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.adapters import windows_bridge as WB
from src.fabric import aead as A
from src.fabric import relay as R

KEY = R.derive_key('123456', 'rn', 'pn')
RID = 'red-relay'


def _signed_reply(key, rid, params, issued_at):
    reply = {'protocol': R.PROTOCOL, 'relay_id': rid, 'op': 'reply', 'params': params,
             'nonce': 'r%s' % issued_at, 'issued_at': issued_at, 'expires_at': issued_at + 30}
    return {**reply, 'mac': R.sign(key, reply)}


class ExpiredReplayTests(unittest.TestCase):
    def test_expired_command_refused_one_shot(self):
        t0 = int(time.time()) - 100
        cmd = R.command(KEY, RID, 'get_status', now=t0)
        with self.assertRaises(R.RelayError):
            R.verify(KEY, cmd, None, now=t0 + R.COMMAND_TTL + 1)
        # Replay of the same expired command is refused again, never admitted.
        with self.assertRaises(R.RelayError):
            R.verify(KEY, cmd, None, now=t0 + R.COMMAND_TTL + 2)

    def test_expired_replay_refused_with_cache(self):
        t0 = int(time.time())
        cmd = R.command(KEY, RID, 'get_status', now=t0)
        seen = {}
        R.verify(KEY, cmd, seen, now=t0)  # fresh: accepted once
        with self.assertRaises(R.RelayError):  # immediate replay: refused
            R.verify(KEY, cmd, seen, now=t0)
        with self.assertRaises(R.RelayError):  # replay after expiry: still refused
            R.verify(KEY, cmd, seen, now=t0 + R.COMMAND_TTL + 1)

    def test_extended_expiry_without_key_is_forgery(self):
        t0 = int(time.time()) - 100
        cmd = R.command(KEY, RID, 'get_status', now=t0)
        forged = dict(cmd, expires_at=int(time.time()) + 600)  # attacker stretches TTL
        with self.assertRaises(R.RelayError):
            R.verify(KEY, forged, None)

    def test_boundary_last_second_valid_then_expired(self):
        t0 = 1_700_000_000
        cmd = R.command(KEY, RID, 'get_status', now=t0)
        R.verify(KEY, cmd, None, now=t0 + R.COMMAND_TTL)  # expires_at inclusive
        with self.assertRaises(R.RelayError):
            R.verify(KEY, cmd, None, now=t0 + R.COMMAND_TTL + 1)


class AeadTamperTests(unittest.TestCase):
    def _sealed(self):
        return A.seal(KEY, 'aad-red', b'secret command bytes')

    def test_bit_flip_at_each_offset_rejected(self):
        env = self._sealed()
        raw = base64.b64decode(env['c'])
        for off in (0, len(raw) // 2, len(raw) - 1):
            buf = bytearray(raw)
            buf[off] ^= 1
            bad = dict(env, c=base64.b64encode(bytes(buf)).decode())
            with self.assertRaises(A.AeadError):
                A.open_(KEY, 'aad-red', bad)

    def test_truncated_and_extended_ciphertext_rejected(self):
        env = self._sealed()
        raw = base64.b64decode(env['c'])
        for mutant in (raw[:-1], raw + b'\x00', b'', raw[:1]):
            bad = dict(env, c=base64.b64encode(mutant).decode())
            with self.assertRaises(A.AeadError):
                A.open_(KEY, 'aad-red', bad)

    def test_tag_nonce_aad_key_confusion_rejected(self):
        env = self._sealed()
        self.assertEqual(len(env['t']), 64)
        bad_tag = ('0' if env['t'][0] != '0' else '1') + env['t'][1:]
        for bad, aad, key in ((dict(env, t=bad_tag), 'aad-red', KEY),
                              (dict(env, t=env['t'][:32]), 'aad-red', KEY),
                              (dict(env, n='00' * 16), 'aad-red', KEY),
                              (env, 'aad-other', KEY),
                              (env, 'aad-red', b'x' * 32)):
            with self.assertRaises(A.AeadError):
                A.open_(key, aad, bad)

    def test_direction_binding_blocks_reflection(self):
        outbound = A.wrap(KEY, RID, {'op': 'get_status'})
        with self.assertRaises(A.AeadError):
            A.unwrap_reply(KEY, RID, outbound)

    def test_tampered_sealed_reply_is_relay_error(self):
        msg = R.command(KEY, RID, 'get_status')
        blob = json.dumps(_signed_reply(KEY, RID, {'ok': True}, msg['issued_at'])).encode()

        def raw(relay, env):
            good = A.seal(KEY, A.aad_for(RID, 'relay>pc'), blob)
            ct = bytearray(base64.b64decode(good['c']))
            ct[0] ^= 1
            return dict(good, c=base64.b64encode(bytes(ct)).decode())

        with self.assertRaises(R.RelayError):
            A.encrypting_send(raw, RID)({'key': KEY}, msg)


class PairingEnrollTests(unittest.TestCase):
    def test_malformed_pairing_code_refused_cleanly(self):
        for bad in ('', '12345', '1234567', '12ab56', 'abcdef', None, 123456, ' 12345'):
            with self.assertRaises(R.RelayError):
                R.derive_key(bad, 'relay-nonce', 'pc-nonce')

    def test_malformed_hello_dict_refused_cleanly(self):
        for hello in ({}, {'protocol': 'wrong'}, {'protocol': R.PROTOCOL},
                      {'protocol': R.PROTOCOL, 'relay_nonce': 123}):
            with self.assertRaises(R.RelayError):
                R.pair(lambda _r, _m, h=hello: h, lambda: '123456')
        # C1 contract: a hello without a relay id is refused as RelayError
        # (narrowed from KeyError); the pairing is refused and the caller survives.
        with self.assertRaises(R.RelayError):
            R.pair(lambda _r, _m: {'protocol': R.PROTOCOL, 'relay_nonce': 'rn'},
                   lambda: '123456')

    def test_malformed_pairing_reply_refused_cleanly(self):
        def send(_r, msg):
            if msg.get('op') == 'pair_request':
                return {'protocol': R.PROTOCOL, 'relay_id': 'ph', 'relay_nonce': 'rn'}
            return {'not': 'a signed reply'}

        with self.assertRaises(R.RelayError):
            R.pair(send, lambda: '123456')

    def test_enroll_malformed_declared_never_crashes_or_escalates(self):
        # C1 contract: non-dict / non-coercible payloads are refused as RelayError
        # (narrowed from AttributeError/ValueError/TypeError); dict-shaped junk
        # coerces to safe empty defaults. In every case the bridge survives,
        # nothing is half-enrolled, and no unknown capability is granted.
        must_raise = [None, 123, 'x', [],
                      {'capabilities': ['ble_scan'], 'permissions': 'oops'},
                      {'capabilities': ['ble_scan'], 'permissions': [1, 2]}]
        for i, declared in enumerate(must_raise):
            mgr = R.RelayManager(lambda r, m: {})
            rid = 'red-%d' % i
            with self.assertRaises(R.RelayError):
                mgr.enroll(rid, KEY, 'dev', declared)
            self.assertNotIn(rid, mgr.relays)  # no partial enrollment
            # Manager stays usable after the hostile payload.
            mgr.enroll('good-%d' % i, KEY, 'dev',
                       {'capabilities': ['ble_scan'],
                        'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
            self.assertEqual(mgr.eligible('ble_scan'), ['good-%d' % i])
        coerce = [{'capabilities': 'ble_scan'},
                  {'capabilities': [None, 123]},
                  {'capabilities': ['root_shell', 'ble_scan'],
                   'permissions': {'BLUETOOTH_SCAN': 'yes'}}]
        for j, declared in enumerate(coerce):
            mgr = R.RelayManager(lambda r, m: {})
            mgr.enroll('coerce-%d' % j, KEY, 'dev', declared)
            caps = mgr.relays['coerce-%d' % j]['capabilities']
            self.assertLessEqual(caps, {'ble_scan', 'remote_controls', 'command_submit'})
            self.assertNotIn('root_shell', caps)
            self.assertEqual(mgr.eligible('ble_scan'), [])  # junk grants nothing

    def test_enroll_unknown_capabilities_grant_nothing(self):
        mgr = R.RelayManager(lambda r, m: {})
        mgr.enroll(RID, KEY, 'dev', {'capabilities': ['root_shell', 'key_exfil'],
                                     'permissions': {'BLUETOOTH_SCAN': True,
                                                   'owner_enabled': True}})
        self.assertEqual(mgr.relays[RID]['capabilities'], set())
        self.assertEqual(mgr.eligible('ble_scan'), [])


class OversizeBoundsTests(unittest.TestCase):
    def test_observation_list_refused_over_200(self):
        with self.assertRaises(R.RelayError):
            R.validate_report({'observations': [{'address': 'x'}] * 201})
        ok = R.validate_report({'observations': [{'address': 'x'}] * 200})
        self.assertEqual(len(ok), 200)

    def test_observation_fields_truncated_and_capped(self):
        clean = R.validate_report({'observations': [{
            'address': 'A' * 40, 'name': 'n' * 5000, 'rssi': 999,
            'company_ids': list(range(50)), 'service_uuids': ['u' * 100] * 50,
            'service_data_uuids': ['leak'] * 9, 'address_kind': 'k' * 100}]})[0]
        self.assertEqual(len(clean['name']), 60)
        self.assertEqual(len(clean['company_ids']), 8)
        self.assertEqual(len(clean['service_uuids']), 12)
        self.assertTrue(all(len(u) <= 40 for u in clean['service_uuids']))
        self.assertEqual(clean['service_data_uuids'], [])
        self.assertEqual(len(clean['address_kind']), 24)
        self.assertIsNone(clean['rssi'])
        with self.assertRaises(R.RelayError):
            R.validate_report({'observations': [{'address': 'A' * 41}]})

    def test_requests_and_commands_bounded(self):
        with self.assertRaises(R.RelayError):
            R.validate_requests({'requests': []} | {'requests': [{}] * 17}, {'c1'})
        dropped = R.validate_requests(
            {'requests': [{'request_id': 'a' * 32, 'control_id': 'revoked'}]},
            {'c1'})
        self.assertEqual(dropped, [])
        with self.assertRaises(R.RelayError):
            R.validate_commands({'commands': [{}] * 9})
        cmds = R.validate_commands({'commands': [
            {'request_id': 'b' * 32, 'lang': 'en', 'quality': 'high',
             'text': 'x' * 501},
            {'request_id': 'c' * 32, 'lang': 'en', 'quality': 'high',
             'kind': 'voice', 'clip_id': 'clip1', 'bytes': R.VOICE_MAX_BYTES + 2,
             'sha256': 'd' * 64},
            {'request_id': 'e' * 32, 'lang': 'en', 'quality': 'high', 'text': 'ok'},
        ]})
        self.assertEqual([c['request_id'] for c in cmds], ['e' * 32])

    def test_aead_plaintext_capped_at_1mib(self):
        with self.assertRaises(A.AeadError):
            A.seal(KEY, 'aad', b'x' * (A.MAX_PLAINTEXT + 1))
        env = A.seal(KEY, 'aad', b'ok')
        big = base64.b64encode(b'y' * (A.MAX_PLAINTEXT + 1)).decode()
        with self.assertRaises(A.AeadError):
            A.open_(KEY, 'aad', dict(env, c=big))

    def test_windows_bridge_frame_capped_without_buffering_body(self):
        reads = []

        class FakeConn:
            def recv(self, n):
                reads.append(n)
                if len(reads) == 1:
                    return struct.pack('!I', WB.MAX_FRAME + 1)
                raise AssertionError('body must never be buffered')

        bridge = WB.WindowsBridge.__new__(WB.WindowsBridge)
        with self.assertRaises(ValueError):
            bridge._read_frame(FakeConn())
        self.assertEqual(reads, [4])  # only the length header was read

    def test_http_transport_oversize_reply_refused(self):
        # C1 contract: a reply over MAX_REPLY_BYTES is refused as RelayError by
        # an explicit size check (narrowed from read(300_000)-truncation surfacing
        # as JSONDecodeError), never a phantom success.
        payloads = {'big': json.dumps({'ok': True, 'pad': 'x' * (2 << 20)}).encode(),
                    'small': json.dumps({'ok': True}).encode()}
        mode = {'name': 'big'}

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get('Content-Length', 0))
                self.rfile.read(n)
                body = payloads[mode['name']]
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = HTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            send = R.http_transport('http://127.0.0.1:%d' % srv.server_port)
            with self.assertRaises(R.RelayError):
                send(None, {'op': 'probe'})
            mode['name'] = 'small'  # bridge still usable after the hostile reply
            self.assertEqual(send(None, {'op': 'probe'}), {'ok': True})
        finally:
            srv.shutdown()
            srv.server_close()

    def test_fetch_voice_size_hash_checked_before_network(self):
        with self.assertRaises(R.RelayError):
            R.fetch_voice('http://127.0.0.1:1', KEY, 'clip1', R.VOICE_MAX_BYTES + 2,
                          'd' * 64)
        with self.assertRaises(R.RelayError):
            R.fetch_voice('http://127.0.0.1:1', KEY, 'clip1', 2, 'not-a-hash')


if __name__ == '__main__':
    unittest.main()
