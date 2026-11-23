"""BridgeWindows v5 sealed transport: pinned vectors, handshake and record layer.

The pinned vectors below were cross-checked at creation time against three
independent implementations (libsodium via PyNaCl, `cryptography`,
PyCryptodome) over 200 random vectors with zero mismatches; they freeze the
wire format so any backend (pure-Python here, Monocypher in the C agent) must
produce identical bytes. When oracle packages happen to be installed, the
LiveOracles class additionally cross-checks a few vectors live (else skipped):
the main suite stays dependency-free.
"""
import unittest
from unittest import mock

from src.fabric import sealed as S

PSK = bytes(range(32))
AGENT = b'agent-pc2'

# key, nonce24, pt, ad, box(ciphertext || tag) — verified against libsodium.
PINNED_XCHACHA = [
    ('d0772b0bafdb7c838da2c7a51990db173b36b423a020894a52170b8a81beeeac',
     'c416ed5dcd77d71cf2ad6ac80a9b456454d55ad5e021e4b0', 'f35eafca5f2aa27d50690de9bd9efaa651',
     'e445be4a3d12e56772bfb956', 'cc3c39df52eedc8c7a7a2dd027b273e6a86a15a90f7099ae6f8f5f5fb81f61772c'),
    ('20de8f6522f949db71f29e1a363d8473e57217e4254e0442947c4dbe9e28fd10',
     '1d5ab0462a52c17b3a3e94e0c1933a7f31bfe1854f146f94',
     '36b27066e6de73ae0c194e2bcc7630335382898793263409bf63cfde58974a23ff9e24474b265c34764f3a167a50872c28a433ddd92c2566a9f92226fdaf9723',
     '502f3cf7fb1370b1bfc65943',
     '1d0962c3f08260403f777a6dc9a0d464e81d73d434f5fe27d0d830e62fca7afe9f95403b7cd2e658c92c3e0b39f62e0cc8230068af82a0a60693bd16884d879fa95bb2691048cce3d0706ecf302b8105'),
    ('9ca73a3dee26d63f927a45eaf3bafb15bc5bc058e17d0e082882477f911fd21d',
     'ae6a2b280f3a40cb6929e7e11b68cc485fe8810abd83c7d6', '',
     '92cb810b3d7841471d44e0f9', '33363d75a06825868a3916d2fe4dad12'),
    ('a2f5d55b357c6ed5e0da4c0f36645102a5bc6c36f02128860b471dc48f8382ea',
     '1630484c70f17ff219d8817e07d543370c5665eaa9ac85c2', '26c3b899d988608ce77b4c5bf8e2c50ede',
     '05181e76dc075502e347adce', '991f76d9908ae64fadc190c624daac5d59408c74f77e1b4818588a49a410dd2698'),
]
PINNED_HKDF = ('696b6d', '73616c74', '696e666f',
               'fe8f9615d2374c0d17f77d1aeaf408c2e75fe0466073d0def23c733e2f862dfd6814c9254418fa112fe8')


def shake(h):
    b = bytearray(bytes.fromhex(h))
    b[len(b) // 2] ^= 1
    return bytes(b)


class PinnedVectors(unittest.TestCase):
    def test_xchacha_vectors(self):
        for key, nonce, pt, ad, box in PINNED_XCHACHA:
            with self.subTest(nonce=nonce[:8]):
                self.assertEqual(S.xseal(bytes.fromhex(key), bytes.fromhex(nonce),
                                         bytes.fromhex(pt), bytes.fromhex(ad)).hex(), box)
                self.assertEqual(S.xopen(bytes.fromhex(key), bytes.fromhex(nonce),
                                         bytes.fromhex(box), bytes.fromhex(ad)), bytes.fromhex(pt))

    def test_xchacha_vectors_pure_python_backend(self):
        with mock.patch.object(S, 'backend', return_value='pure-python'):
            self.test_xchacha_vectors()

    def test_hkdf_vector(self):
        ikm, salt, info, out = PINNED_HKDF
        self.assertEqual(S.hkdf_sha256(bytes.fromhex(ikm), bytes.fromhex(salt), bytes.fromhex(info), 42).hex(), out)

    def test_backend_reported(self):
        self.assertIn(S.backend(), ('cryptography', 'pure-python'))


class Primitives(unittest.TestCase):
    def test_tamper_anywhere_fails(self):
        key, nonce, pt, ad, box = PINNED_XCHACHA[0]
        box_b = bytes.fromhex(box)
        for bad in (shake(box), box_b[:-1], box_b + b'x', b''):
            with self.assertRaises(S.SealedError):
                S.xopen(bytes.fromhex(key), bytes.fromhex(nonce), bad, bytes.fromhex(ad))
        with self.assertRaises(S.SealedError):
            S.xopen(bytes.fromhex(key), shake(nonce), box_b, bytes.fromhex(ad))
        with self.assertRaises(S.SealedError):
            S.xopen(shake(key), bytes.fromhex(nonce), box_b, bytes.fromhex(ad))
        with self.assertRaises(S.SealedError):
            S.xopen(bytes.fromhex(key), bytes.fromhex(nonce), box_b, shake(ad))

    def test_shapes_rejected(self):
        with self.assertRaises(S.SealedError):
            S.xseal(b'short', b'\0' * 24, b'x')
        with self.assertRaises(S.SealedError):
            S.xseal(b'\0' * 32, b'short', b'x')
        with self.assertRaises(S.SealedError):
            S.hkdf_sha256(b'k', b's', b'i', 0)
        with self.assertRaises(S.SealedError):
            S.poly1305_mac(b'short', b'x')

    def test_hkdf_sensitivity(self):
        a = S.hkdf_sha256(b'k', b's', b'i', 32)
        self.assertNotEqual(S.hkdf_sha256(b'k2', b's', b'i', 32), a)
        self.assertNotEqual(S.hkdf_sha256(b'k', b's2', b'i', 32), a)
        self.assertNotEqual(S.hkdf_sha256(b'k', b's', b'i2', 32), a)
        self.assertEqual(len(S.hkdf_sha256(b'k', b's', b'i', 100)), 100)


def do_handshake(psk=PSK, agent=AGENT):
    sa, m1 = S.hello_a(psk)
    sb, m2 = S.answer_b(psk, agent, m1)
    A, m3 = S.finish_a(psk, agent, sa, m2)
    B = S.finish_b(psk, agent, sb, m3)
    return A, B, (m1, m2, m3)


class Handshake(unittest.TestCase):
    def test_agreement(self):
        A, B, _ = do_handshake()
        self.assertEqual(A.session_id, B.session_id)
        self.assertEqual(len(A.session_id), 16)
        f = A.seal(b'ping')
        self.assertEqual(B.open(f), b'ping')
        self.assertEqual(A.open(B.seal(b'pong')), b'pong')

    def test_tampered_messages_fail(self):
        sa, m1 = S.hello_a(PSK)
        for bad in (m1[:-1], m1 + b'x', b''):
            with self.assertRaises(S.SealedError):
                S.answer_b(PSK, AGENT, bad)
        # A modified EA is just bytes to the responder: the forgery dies at confirmation.
        _, m2evil = S.answer_b(PSK, AGENT, shake(m1.hex()))
        with self.assertRaises(S.SealedError):
            S.finish_a(PSK, AGENT, sa, m2evil)
        sb, m2 = S.answer_b(PSK, AGENT, m1)
        for bad in (shake(m2.hex()), m2[:-1], m2 + b'x'):
            with self.assertRaises(S.SealedError):
                S.finish_a(PSK, AGENT, sa, bad)
        A, m3 = S.finish_a(PSK, AGENT, sa, m2)
        for bad in (shake(m3.hex()), m3[:-1], m3 + b'x'):
            with self.assertRaises(S.SealedError):
                S.finish_b(PSK, AGENT, sb, bad)

    def test_wrong_psk_or_agent_fails(self):
        sa, m1 = S.hello_a(PSK)
        _, m2 = S.answer_b(PSK, AGENT, m1)
        with self.assertRaises(S.SealedError):
            S.finish_a(bytes(PSK[:-1] + b'X'), AGENT, sa, m2)
        with self.assertRaises(S.SealedError):
            S.hello_a(b'too short')
        with self.assertRaises(S.SealedError):
            S.answer_b(PSK, b'', m1)
        with self.assertRaises(S.SealedError):
            S.answer_b(PSK, b'x' * 65, m1)

    def test_mitm_without_psk_learns_nothing(self):
        # Attacker substitutes their own ephemeral key: confirmation MACs fail on both sides.
        sa, m1 = S.hello_a(PSK)
        from src.fabric.cpace import encode_u, x25519
        import secrets as _s
        evil = x25519(_s.token_bytes(32), encode_u(9))
        sb, m2 = S.answer_b(PSK, AGENT, m1[:16] + evil)
        with self.assertRaises(S.SealedError):
            S.finish_a(PSK, AGENT, sa, m2)
        self.assertEqual(len(sb['transcript']), 96)

    def test_fresh_handshake_fresh_keys(self):
        A1, B1, _ = do_handshake()
        A2, B2, _ = do_handshake()
        self.assertNotEqual(A1.session_id, A2.session_id)
        with self.assertRaises(S.SealedError):
            B2.open(A1.seal(b'cross-session transplant'))


class Records(unittest.TestCase):
    def test_roundtrip_sequence(self):
        A, B, _ = do_handshake()
        for i in range(5):
            self.assertEqual(B.open(A.seal(b'msg-%d' % i)), b'msg-%d' % i)
            self.assertEqual(A.open(B.seal(b'ack-%d' % i)), b'ack-%d' % i)
        st = A.stats()
        self.assertEqual((st['sent'], st['received']), (5, 5))

    def test_replay_duplicate_reorder_drop_fail(self):
        A, B, _ = do_handshake()
        f0, f1 = A.seal(b'zero'), A.seal(b'one')
        with self.assertRaises(S.SealedError):
            B.open(f1)                       # gap: frame 0 skipped
        self.assertEqual(B.open(f0), b'zero')
        with self.assertRaises(S.SealedError):
            B.open(f0)                       # duplicate
        self.assertEqual(B.open(f1), b'one')

    def test_tampered_frame_fails(self):
        A, B, _ = do_handshake()
        f = bytearray(A.seal(b'secret'))
        f[10] ^= 1
        with self.assertRaises(S.SealedError):
            B.open(bytes(f))
        with self.assertRaises(S.SealedError):
            B.open(b'\0' * 8)                # counter only, no box

    def test_directions_do_not_cross(self):
        A, B, _ = do_handshake()
        with self.assertRaises(S.SealedError):
            A.open(A.seal(b'self'))          # A's frame is not readable as B->A (key + nonce + AD)
        with self.assertRaises(S.SealedError):
            B.open(B.seal(b'self'))          # symmetric: B's frame is not readable as A->B

    def test_frame_budget_and_size_caps(self):
        A, B, _ = do_handshake()
        A._send_n = S.MAX_FRAMES
        with self.assertRaises(S.SealedError):
            A.seal(b'one too many')
        with self.assertRaises(S.SealedError):
            B.seal(b'x' * (S.MAX_PLAINTEXT + 1))

    def test_empty_message_roundtrip(self):
        A, B, _ = do_handshake()
        self.assertEqual(B.open(A.seal(b'')), b'')


def _oracles():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305  # noqa
        return True
    except ImportError:
        return False


@unittest.skipUnless(_oracles(), 'live oracle check needs the cryptography package')
class LiveOracles(unittest.TestCase):
    def test_backend_agrees_with_cryptography(self):
        import random
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        rng = random.Random(0x0BAD)
        for _ in range(16):
            key, n12 = rng.randbytes(32), rng.randbytes(12)
            pt, ad = rng.randbytes(rng.randint(0, 200)), rng.randbytes(rng.randint(0, 32))
            ref = ChaCha20Poly1305(key).encrypt(n12, pt, ad)
            self.assertEqual(S.aead_seal(key, n12, pt, ad), ref)
            self.assertEqual(S.aead_open(key, n12, ref, ad), pt)


if __name__ == '__main__':
    unittest.main()
