"""CPace pairing (src/fabric/cpace.py): X25519 vectors, Java/Python agreement, and the pairing protocol end to end.

The pinned cross-language vectors were produced by companion/android/src/fr/openbridge/companion/Cpace.java
(javac/java, 23 Nov 2026) and must keep matching: the PC and the Companion derive the same key or pairing breaks.
"""
import hashlib
import os
import time
import unittest
from unittest import mock

from src.fabric import cpace as C
from src.fabric import relay as R

JAVA_VECTORS = [  # i, generator, Ya, Yb, ISK  (inputs: see _inputs)
    (0, '014f7d34504268f325c51797cfc60d27167691007eb4457755e80adc15228c56', 'd23b131055ee24e28e97452cd9797c5f2cf5cef50efdbc2e09d59de37c4a971e', '7156928646cfe04fd61886acc94f308b70b71b44923282cc829aa5312a309844',
     '29132c045c723a5282e9a02b8a9d130d7d1b2078fd8504407b361bea1291177688c2cc6cbdffa0465bb32b892063c9d5a6aae977df9e257c7bc239f7cb397c77'),
    (6, '9dea94737da1a502ff08c7743bcd9bba3118f385a279093b479738e23fdf7145', 'e00499dfeea2b2f648cfc65fb81f29681d0c440db4b120927476fa31f6767b1e', 'd17472088a74cc5fb920ce6116accc9a1a7fd365223b0e23f620f6237e014c24',
     'db25506da60cf4a7b5cfb18a2743a52a782dad6591a53fecbc8bc21954e4d4e679f966258026b580a5291d3b71b2b4ecbb9379612d5b5d5dbbf376349855f20b'),
    (22, 'e95797012a1faf29e4068521e96fe44fe625bc965cceb2e402c7e1c14079fb6c', 'ea8897ef42f11bc319319ead7869e354d2b9d107c53627956d3441791d6d0b4c', '9aed273e331b80fd46bd97515e57f268e01ae59f5f948e465118e094b4da7972',
     '23526267a08c6ee2f80fed9444af45b67e70c4fa870b8f6ff0373ab5670f334c394730be77835a96e86bf6e5f581a5d1b4fcf7eabdd7538473d4b52a308ba0ab')
]


def _inputs(i):
    sha = lambda s: hashlib.sha256(s.encode()).digest()
    prs = ('%06d' % ((i * 7919) % 1000000)).encode()
    return prs, ('relay-%d' % i).encode(), sha('sid%d' % i).hex().encode(), sha('ya%d' % i), sha('yb%d' % i)


class X25519(unittest.TestCase):
    def test_rfc7748_vectors(self):
        h = bytes.fromhex
        self.assertEqual(C.x25519(h('a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4'),
                                  h('e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c')).hex(),
                         'c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552')
        self.assertEqual(C.x25519(h('4b66e9d4d1b4673c5ad22691957d6af5c11b6421e0ea01d42ca4169e7918ba0d'),
                                  h('e5210f12786811d3f4b7959d0538ae2c31dbe7106fc03c3efc4cd549c715a493')).hex(),
                         '95cbde9476e8907d7aade45cb4b873f88b595a68799fa152e6f8f7647aac7957')
        a = h('77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a')
        b = h('5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb')
        nine = C.encode_u(9)
        self.assertEqual(C.x25519(a, nine).hex(), '8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a')
        self.assertEqual(C.x25519(a, C.x25519(b, nine)).hex(),
                         '4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742')

    def test_rfc7748_iterated_1000(self):
        k = u = C.encode_u(9)
        for _ in range(1000):
            k, u = C.x25519(k, u), k
        self.assertEqual(k.hex(), '684cf59ba83309552800ef566f2f4d3c1c3887c49360e3875f2eb94d99532c51')

    def test_elligator_lands_on_the_curve(self):
        for i in range(100):
            x = C.elligator2(int.from_bytes(hashlib.sha256(bytes([i])).digest(), 'little'))
            self.assertTrue(C._is_square((x ** 3 + C.A * x * x + x) % C.P))


class CPace(unittest.TestCase):
    def test_java_and_python_derive_the_same_values(self):
        for i, g, ya_pub, yb_pub, isk in JAVA_VECTORS:
            prs, ci, sid, ya, yb = _inputs(i)
            with self.subTest(i=i):
                gen = C.generator(prs, ci, sid)
                self.assertEqual(gen.hex(), g)
                self.assertEqual(C.x25519(ya, gen).hex(), ya_pub)
                self.assertEqual(C.x25519(yb, gen).hex(), yb_pub)
                self.assertEqual(C.isk(ya, bytes.fromhex(yb_pub), sid, bytes.fromhex(ya_pub), bytes.fromhex(yb_pub)).hex(), isk)

    def test_same_code_same_key_other_code_other_key(self):
        sid, ci = b'n1n2', b'relay-x'
        g = C.generator(b'123456', ci, sid)
        ya, A = C.share(g)
        yb, B = C.share(g)
        self.assertEqual(C.isk(ya, B, sid, A, B), C.isk(yb, A, sid, A, B))
        yc, Cc = C.share(C.generator(b'123457', ci, sid))
        self.assertNotEqual(C.isk(yc, B, sid, Cc, B), C.isk(yb, Cc, sid, Cc, B))

    def test_low_order_share_is_refused(self):
        with self.assertRaises(C.CPaceError):
            C.isk(os.urandom(32), b'\0' * 32, b'sid', b'\0' * 32, b'\0' * 32)


class ReferenceCompanion:
    """Python mirror of RelayServer.java's pairing (pairRequest / confirmPairing)."""

    def __init__(self, code='424242', relay_id='relay-0123456789ab', cpace=True):
        self.code, self.rid, self.cpace = code, relay_id, cpace
        self.failed, self.key, self.transcript = 0, None, []

    def __call__(self, _relay, msg):
        self.transcript.append(msg)
        if msg.get('op') == 'pair_request':
            self.pc, self.rn = msg['pc_nonce'], 'ab' * 8
            hello = {'protocol': R.PROTOCOL, 'relay_id': self.rid, 'relay_nonce': self.rn, 'declared': {}}
            self.scalar = None
            if self.cpace and R.PAKE in (msg.get('pake') or []):
                g = C.generator(self.code.encode(), self.rid.encode(), (self.rn + self.pc).encode())
                self.scalar, self.share = C.share(g)
                hello.update(pake=R.PAKE, pake_share=self.share.hex())
            self.transcript.append(hello)
            return hello
        if self.scalar is not None:
            theirs = msg.get('pake_share') or ''
            if not R.HEX64.match(theirs):               # no downgrade once CPace was asked for
                self.failed += 1
                raise R.RelayError('refused')
            ya = bytes.fromhex(theirs)
            k = C.isk(self.scalar, ya, (self.rn + self.pc).encode(), ya, self.share)[:32]
        else:
            k = R.derive_key(self.code, self.rn, self.pc)
        try:
            R.verify(k, msg, None)
        except R.RelayError:
            self.failed += 1
            raise
        self.key = k
        now = int(time.time())
        rep = {'protocol': R.PROTOCOL, 'relay_id': self.rid, 'op': 'reply', 'params': {'capabilities': ['ble_scan']},
               'nonce': os.urandom(6).hex(), 'issued_at': now, 'expires_at': now + 30}
        return {**rep, 'mac': R.sign(k, rep)}


class Pairing(unittest.TestCase):
    def test_cpace_pairing_with_the_right_code(self):
        dev = ReferenceCompanion()
        rid, key, declared = R.pair(dev, lambda: '424242')
        self.assertEqual((rid, key, declared['capabilities']), (dev.rid, dev.key, ['ble_scan']))
        self.assertIn('pake_share', dev.transcript[2])

    def test_wrong_code_fails_and_counts(self):
        dev = ReferenceCompanion()
        with self.assertRaises(R.RelayError):
            R.pair(dev, lambda: '000000')
        self.assertEqual(dev.failed, 1)

    def test_recorded_exchange_does_not_allow_an_offline_guess(self):
        dev = ReferenceCompanion()
        rid, key, _ = R.pair(dev, lambda: '424242')
        hello, first = dev.transcript[1], dev.transcript[2]
        # An eavesdropper knows everything on the wire and even guesses the right code; without one of the two
        # secret scalars, the key it computes does not verify the recorded command.
        guess, _ = R.pake_key('424242', rid, hello['relay_nonce'], dev.transcript[0]['pc_nonce'], hello['pake_share'])
        self.assertNotEqual(guess, key)
        with self.assertRaises(R.RelayError):
            R.verify(guess, first, None)
        # The legacy derivation is no use either.
        with self.assertRaises(R.RelayError):
            R.verify(R.derive_key('424242', hello['relay_nonce'], dev.pc), first, None)

    def test_legacy_companion_still_pairs_unless_cpace_is_required(self):
        dev = ReferenceCompanion(cpace=False)
        self.assertEqual(R.pair(dev, lambda: '424242')[1], dev.key)
        with mock.patch.dict(os.environ, {'OPENBRIDGE_PAIRING_REQUIRE_PAKE': '1'}):
            with self.assertRaises(R.RelayError):
                R.pair(ReferenceCompanion(cpace=False), lambda: '424242')

    def test_companion_refuses_a_legacy_proof_after_offering_cpace(self):
        dev = ReferenceCompanion()
        hello = dev(None, {'op': 'pair_request', 'pc_nonce': 'cd' * 16, 'pake': [R.PAKE]})
        legacy = R.command(R.derive_key('424242', hello['relay_nonce'], 'cd' * 16), dev.rid, 'discover_capabilities')
        with self.assertRaises(R.RelayError):
            dev(None, legacy)

    def test_server_flow_reports_cpace_and_counts_wrong_codes(self):
        from src.server import create_server
        from src.fabric.session import SessionJournal
        import tempfile
        server = create_server(0, fabric_salt=b's', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        self.addCleanup(server.server_close)
        dev = ReferenceCompanion(relay_id='phone')
        with mock.patch.object(server.android, 'relay_urls', return_value=['http://127.0.0.1:47800']), \
                mock.patch.object(server.android, 'lan_url_for_relay', return_value=None), \
                mock.patch.object(server.android, 'serial_for', return_value='SERIAL'):
            start = server.relay_action('/api/relay-pair-start', {'device_id': 'h1'}, transport_factory=lambda u: dev)
            self.assertEqual((start['state'], start['pairing']), ('CODE_SHOWN_ON_DEVICE', 'cpace'))
            self.assertNotIn('warning', start)
            with self.assertRaises(R.RelayError):
                server.relay_action('/api/relay-pair-confirm', {'device_id': 'h1', 'code': '111111'})
            self.assertEqual(server.relay_pending['h1']['attempts'], 1)
            done = server.relay_action('/api/relay-pair-confirm', {'device_id': 'h1', 'code': '424242'})
        self.assertEqual((done['state'], done['pairing']), ('PAIRED', 'cpace'))
        self.assertEqual(server.relays.relays['phone']['key'], dev.key)

    def test_server_warns_about_a_legacy_companion(self):
        from src.server import create_server
        from src.fabric.session import SessionJournal
        import tempfile
        server = create_server(0, fabric_salt=b's', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        self.addCleanup(server.server_close)
        with mock.patch.object(server.android, 'relay_urls', return_value=['http://127.0.0.1:47800']):
            start = server.relay_action('/api/relay-pair-start', {'device_id': 'h2'},
                                        transport_factory=lambda u: ReferenceCompanion(relay_id='tv', cpace=False))
        self.assertEqual(start['pairing'], 'legacy-v1')
        self.assertIn('update', start['warning'])


if __name__ == '__main__':
    unittest.main()
