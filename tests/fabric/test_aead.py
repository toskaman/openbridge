"""aead1 relay confidentiality (stdlib encrypt-then-MAC). Shared vector: tests/fabric/fixtures/aead1_vector.json is
also checked by the Java implementation (dev/aead_vector_check)."""
import base64
import json
import unittest
from pathlib import Path

from src.fabric import aead as A
from src.fabric import relay as R

V = json.loads((Path(__file__).parent / 'fixtures' / 'aead1_vector.json').read_text())
KEY = bytes.fromhex(V['key_hex'])


class Primitive(unittest.TestCase):
    def test_vector_is_stable(self):
        env = A.seal(KEY, V['aad'], V['plaintext'].encode(), nonce=bytes.fromhex(V['nonce_hex']))
        self.assertEqual(env, V['envelope'])
        self.assertEqual(A.open_(KEY, V['aad'], V['envelope']).decode(), V['plaintext'])

    def test_roundtrip_sizes(self):
        for n in (0, 1, 31, 32, 33, 4096, 480000):
            pt = bytes((i * 7) % 256 for i in range(n))
            self.assertEqual(A.open_(KEY, 'x', A.seal(KEY, 'x', pt)), pt)

    def test_any_tamper_is_rejected_before_decryption(self):
        env = A.seal(KEY, 'aad', b'secret command')
        ct = bytearray(base64.b64decode(env['c'])); ct[0] ^= 1
        for bad in (dict(env, c=base64.b64encode(bytes(ct)).decode()), dict(env, t='0' * 64),
                    dict(env, n='00' * 16), dict(env, enc='none'), dict(env, n='zz')):
            with self.assertRaises(A.AeadError):
                A.open_(KEY, 'aad', bad)
        with self.assertRaises(A.AeadError):
            A.open_(KEY, 'other aad', env)
        with self.assertRaises(A.AeadError):
            A.open_(b'x' * 32, 'aad', env)

    def test_direction_binding_blocks_reflection(self):
        env = A.wrap(KEY, 'relay-1', {'op': 'get_status'})
        with self.assertRaises(A.AeadError):
            A.unwrap_reply(KEY, 'relay-1', env)                 # a PC->relay envelope is not a valid reply

    def test_ciphertext_hides_the_message(self):
        env = A.wrap(KEY, 'relay-1', {'op': 'set_controls', 'params': {'controls': [{'label': 'Unlock door'}]}})
        self.assertNotIn('Unlock', json.dumps(env))
        self.assertNotIn('set_controls', json.dumps(env))
        self.assertEqual(set(env), {'enc', 'n', 'c', 't', 'relay_id'})


class Transport(unittest.TestCase):
    def relay_reply(self, env, plaintext=False):
        msg = json.loads(A.open_(KEY, A.aad_for('relay-1', 'pc>relay'), env))
        R.verify(KEY, msg, {})
        t = msg['issued_at']
        reply = {'protocol': R.PROTOCOL, 'relay_id': 'relay-1', 'op': 'reply', 'params': {'ok': True},
                 'nonce': 'r' + msg['nonce'], 'issued_at': t, 'expires_at': t + 30}
        reply['mac'] = R.sign(KEY, reply)
        return reply if plaintext else A.seal(KEY, A.aad_for('relay-1', 'relay>pc'), json.dumps(reply).encode())

    def test_sealed_exchange_and_wire_privacy(self):
        wire = []
        def raw(relay, env):
            wire.append(env); return self.relay_reply(env)
        send = A.encrypting_send(raw, 'relay-1')
        reply = send({'key': KEY}, R.command(KEY, 'relay-1', 'get_status'))
        self.assertEqual(R.verify(KEY, reply, {})['params'], {'ok': True})
        self.assertNotIn('get_status', json.dumps(wire))

    def test_plaintext_reply_after_negotiation_is_refused(self):
        send = A.encrypting_send(lambda relay, env: self.relay_reply(env, plaintext=True), 'relay-1')
        with self.assertRaises(R.RelayError):
            send({'key': KEY}, R.command(KEY, 'relay-1', 'get_status'))

    def test_forged_reply_is_a_relay_error(self):
        send = A.encrypting_send(lambda relay, env: dict(self.relay_reply(env), t='0' * 64), 'relay-1')
        with self.assertRaises(R.RelayError):
            send({'key': KEY}, R.command(KEY, 'relay-1', 'get_status'))

    def test_voice_body(self):
        v = V['voice']
        env = v['envelope']
        blob = bytes.fromhex(env['n']) + bytes.fromhex(env['t']) + base64.b64decode(env['c'])
        self.assertEqual(A.open_voice(KEY, 'relay-abc123', 'vclip01', blob).hex(), v['plaintext_hex'])
        with self.assertRaises(A.AeadError):
            A.open_voice(KEY, 'relay-abc123', 'other-clip', blob)


if __name__ == '__main__':
    unittest.main()
