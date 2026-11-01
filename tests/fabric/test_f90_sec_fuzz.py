"""Campaign One section 3.6 fuzz slice: adversarial parser fuzz (TESTS ONLY).

Covers pairing code/nonce mutations, AEAD envelope bit-flips and truncated
fields, signed-reply forgeries (wrong key, role confusion, adversarial JSON
shapes), malformed capability declarations, and oversized HTTP bodies.

Contract for every case: fail-closed. Wire input must either raise
RelayError (or AeadError at the AEAD layer, wrapped as RelayError on the
transport path) or be safely refused/dropped (empty grant, dropped entry,
HTTP 4xx). Phantom success is a failure. No uncaught non-RelayError except
the documented ones:

  * AeadError (ValueError subclass) from src.fabric.aead.open_/unwrap/open_voice
  * TypeError from relay.verify for a non-dict seen_nonces cache (programming guard)
  * OSError/TimeoutError from transports for dead links (propagate untouched)
  * AttributeError from validate_* only when called with a non-dict report
    (requires a valid MAC with non-dict params, i.e. key compromise; never
    from wire bytes alone since http_transport only yields dict replies)

All fuzz is deterministic (fixed seeds) and bounded (explicit case caps).
"""
import base64
import copy
import json
import random
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from src.fabric import aead as A
from src.fabric import relay as R

# Deterministic seeds: one per fuzz family so a failure reproduces by name.
SEED_PAIRING = 0xF903601
SEED_NONCE = 0xF903602
SEED_AEAD = 0xF903603
SEED_REPLY = 0xF903604
SEED_CAPS = 0xF903605
SEED_HTTP = 0xF903606

# Case caps: every loop asserts it stays within its bound.
MAX_PAIRING_CASES = 64
MAX_NONCE_CASES = 64
MAX_AEAD_CASES = 96
MAX_REPLY_CASES = 96
MAX_CAPS_CASES = 64
MAX_HTTP_CASES = 48

KEY = R.derive_key('123456', 'rn', 'pn')
KEY_WRONG = R.derive_key('654321', 'rn', 'pn')
RID = 'f90-fuzz'
FIXED_NONCE = bytes.fromhex('101112131415161718191a1b1c1d1e1f')


def _signed(params, key=KEY, rid=RID, nonce='f90-nonce-0001', op='reply', now=None):
    now = int(time.time()) if now is None else now
    msg = {'protocol': R.PROTOCOL, 'relay_id': rid, 'op': op, 'params': params,
           'nonce': nonce, 'issued_at': now, 'expires_at': now + 30}
    return {**msg, 'mac': R.sign(key, msg)}


def _flip_bit(data: bytes, pos: int, bit: int = 0) -> bytes:
    out = bytearray(data)
    out[pos % len(out)] ^= (1 << bit)
    return bytes(out)


def _assert_bound(testcase, n, cap, label):
    testcase.assertLessEqual(n, cap, f'{label}: {n} cases exceed cap {cap}')


class PairingCodeFuzz(unittest.TestCase):
    """derive_key pairing-code mutations + pair() hello/nonce mutations."""

    def test_pairing_code_mutations_fail_closed(self):
        rng = random.Random(SEED_PAIRING)
        # Malformed shapes: cheap (rejected before PBKDF2), so we can cover many.
        bad_codes = [
            None, 123456, 123.0, True, False, [], {}, ('123456',), b'123456',
            '', '1', '12', '12345', '1234567', '12345678',
            '12ab56', 'abcdef', ' 12345', '12345 ', '12 456', '12-456',
            '12345\n', '\t123456', '123456\x00', '\x00123456',
            '１２３４５', '00000a', '99999 ', '+12345', '-12345',
            '12.456', 'NaN123', 'None', 'null', 'undefined',
        ]
        # Deterministic random digit-strings of wrong length.
        for _ in range(8):
            bad_codes.append(''.join(rng.choice('0123456789') for _ in range(rng.choice([1, 2, 5, 7, 8, 12]))))
        # Deterministic random 6-char non-digit strings.
        for _ in range(8):
            bad_codes.append(''.join(rng.choice('abcdefXYZ \x00é') for _ in range(6)))
        _assert_bound(self, len(bad_codes), MAX_PAIRING_CASES, 'pairing-code cases')
        for code in bad_codes:
            with self.subTest(code=repr(code)):
                with self.assertRaises(R.RelayError):
                    R.derive_key(code, 'relay-nonce', 'pc-nonce')
        # Valid-format codes still derive (bounded: 3 PBKDF2 runs here).
        for code in ('000000', '123456', '999999'):
            with self.subTest(code=code):
                self.assertEqual(len(R.derive_key(code, 'rn', 'pn')), 32)
        # Unicode decimal digits pass isdigit() so they derive (documented
        # str.isdigit behavior), but to a different key than the ASCII code
        # the relay shows: pairing still fails closed downstream on the MAC.
        uni = R.derive_key('１２３４５６', 'rn', 'pn')
        self.assertEqual(len(uni), 32)
        self.assertNotEqual(uni, R.derive_key('123456', 'rn', 'pn'))

    def test_pair_hello_nonce_mutations_fail_closed(self):
        # relay_nonce / relay_id / protocol mutations: refused before any key
        # derivation, so both cheap and fail-closed as RelayError.
        bad_hellos = [
            None, 123, 'hello', [], ('x',),
            {}, {'protocol': R.PROTOCOL}, {'relay_nonce': 'nn'},
            {'protocol': 'openbridge-relay/9', 'relay_id': RID, 'relay_nonce': 'nn' * 8},
            {'protocol': R.PROTOCOL, 'relay_id': RID, 'relay_nonce': None},
            {'protocol': R.PROTOCOL, 'relay_id': RID, 'relay_nonce': 12345},
            {'protocol': R.PROTOCOL, 'relay_id': RID, 'relay_nonce': ''},
            {'protocol': R.PROTOCOL, 'relay_id': RID, 'relay_nonce': 'x' * 100000},
            {'protocol': R.PROTOCOL, 'relay_id': RID, 'relay_nonce': {'n': 1}},
            {'protocol': R.PROTOCOL, 'relay_id': RID, 'relay_nonce': ['n']},
            {'protocol': R.PROTOCOL, 'relay_id': RID, 'relay_nonce': 'nn' * 8, 'extra': 'junk-ok-shape-still-valid'},
        ]
        _assert_bound(self, len(bad_hellos), MAX_PAIRING_CASES, 'hello cases')
        for i, hello in enumerate(bad_hellos):
            with self.subTest(i=i, hello=repr(hello)[:80]):
                if i == len(bad_hellos) - 1:
                    # Last entry is a well-formed hello with an ignored extra key:
                    # pairing proceeds to the code check, so a bad code still fails.
                    def send(_r, msg, h=hello):
                        if msg.get('op') == 'pair_request':
                            return h
                        return {'not': 'a signed reply'}
                    with self.assertRaises(R.RelayError):
                        R.pair(send, lambda: 'not-six-digits!!')
                    continue
                def send(_r, _m, h=hello):
                    return h
                with self.assertRaises(R.RelayError):
                    R.pair(send, lambda: '123456')

    def test_pair_wrong_code_with_valid_hello_fails_closed(self):
        # Bounded PBKDF2: 2 valid-format wrong codes (derive, then MAC fails).
        state = {}

        def send(_r, msg):
            if msg.get('op') == 'pair_request':
                state['pc'] = msg['pc_nonce']
                return {'protocol': R.PROTOCOL, 'relay_id': RID, 'relay_nonce': 'ab' * 8}
            good = R.derive_key('424242', 'ab' * 8, state['pc'])
            now = int(time.time())
            rep = {'protocol': R.PROTOCOL, 'relay_id': RID, 'op': 'reply',
                   'params': {'capabilities': ['ble_scan']}, 'nonce': 'n-wrong-code',
                   'issued_at': now, 'expires_at': now + 30}
            return {**rep, 'mac': R.sign(good, rep)}

        for code in ('000000', '999999'):
            with self.subTest(code=code):
                with self.assertRaises(R.RelayError):
                    R.pair(send, lambda c=code: c)


class NonceMutationFuzz(unittest.TestCase):
    """verify() nonce/expiry mutations: tamper without a valid MAC always fails."""

    def test_nonce_tamper_without_resign_is_bad_signature(self):
        rng = random.Random(SEED_NONCE)
        now = int(time.time())
        base = R.command(KEY, RID, 'get_status', now=now)
        mutations = [
            ('missing', lambda m: m.pop('nonce')),
            ('none', lambda m: m.update(nonce=None)),
            ('int', lambda m: m.update(nonce=12345)),
            ('empty', lambda m: m.update(nonce='')),
            ('huge', lambda m: m.update(nonce='n' * 100000)),
            ('spaces', lambda m: m.update(nonce='  nonce with spaces  ')),
            ('null-byte', lambda m: m.update(nonce='ab\x00cd')),
            ('unicode', lambda m: m.update(nonce='noncé-🔑')),
            ('bool', lambda m: m.update(nonce=True)),
            ('float', lambda m: m.update(nonce=1.5)),
            ('dict', lambda m: m.update(nonce={'n': 1})),
            ('list', lambda m: m.update(nonce=['n'])),
        ]
        for _ in range(8):
            mutations.append((f'rand-{_}', lambda m, r=rng: m.update(
                nonce=''.join(r.choice('abcdef0123456789XZ') for _ in range(r.randint(1, 64))))))
        _assert_bound(self, len(mutations), MAX_NONCE_CASES, 'nonce cases')
        for label, mutate in mutations:
            with self.subTest(label=label):
                tampered = dict(base)
                mutate(tampered)
                # No re-sign: MAC cannot verify for any mutation.
                with self.assertRaises(R.RelayError):
                    R.verify(KEY, tampered, {}, now=now)
                with self.assertRaises(R.RelayError):
                    R.verify(KEY, tampered, None, now=now)

    def test_replay_expiry_and_resigned_nonce_logic(self):
        now = int(time.time())
        seen = {}
        cmd = R.command(KEY, RID, 'get_status', now=now)
        R.verify(KEY, cmd, seen, now=now)
        with self.assertRaisesRegex(R.RelayError, 'Replay'):
            R.verify(KEY, cmd, dict(seen), now=now)
        # Expired command (valid MAC, stale timestamps).
        old = R.command(KEY, RID, 'get_status', now=now - 100)
        with self.assertRaisesRegex(R.RelayError, 'Expired'):
            R.verify(KEY, old, None, now=now)
        # Future issued_at beyond skew.
        future = R.command(KEY, RID, 'get_status', now=now + 600)
        with self.assertRaises(R.RelayError):
            R.verify(KEY, future, None, now=now)
        # Missing nonce with a valid MAC is still refused (dict cache path).
        msg = {'protocol': R.PROTOCOL, 'relay_id': RID, 'op': 'get_status',
               'params': {}, 'issued_at': now, 'expires_at': now + 30}
        signed = {**msg, 'mac': R.sign(KEY, msg)}
        with self.assertRaisesRegex(R.RelayError, 'missing nonce'):
            R.verify(KEY, signed, {}, now=now)
        # One-shot path (pairing replies) remembers nothing: valid twice.
        R.verify(KEY, cmd, None, now=now)
        R.verify(KEY, cmd, None, now=now)
        # Programming guard keeps its type (documented, not RelayError).
        with self.assertRaises(TypeError):
            R.verify(KEY, cmd, set(), now=now)


class AeadEnvelopeFuzz(unittest.TestCase):
    """AEAD envelope bit-flips, truncated fields, and type mutations."""

    def _base_envelope(self):
        return A.seal(KEY, A.aad_for(RID, 'relay>pc'), b'{"ok": true}', nonce=FIXED_NONCE)

    def test_bitflips_and_truncations_rejected(self):
        rng = random.Random(SEED_AEAD)
        base = self._base_envelope()
        cases = []
        # Deterministic bit-flips: first/middle/last byte of n/c/t, bits 0 and 7.
        for field, raw in (('n', bytes.fromhex(base['n'])),
                           ('c', base64.b64decode(base['c'])),
                           ('t', bytes.fromhex(base['t']))):
            for pos in (0, len(raw) // 2, len(raw) - 1):
                for bit in (0, 7):
                    cases.append((f'{field}-flip-{pos}-{bit}', field, raw, pos, bit))
        # Deterministic random flips (bounded).
        for i in range(8):
            field, raw = rng.choice([('n', bytes.fromhex(base['n'])),
                                     ('c', base64.b64decode(base['c'])),
                                     ('t', bytes.fromhex(base['t']))])
            cases.append((f'{field}-rand-{i}', field, raw, rng.randrange(len(raw)), rng.randrange(8)))
        _assert_bound(self, len(cases), MAX_AEAD_CASES, 'aead flip cases')
        for label, field, raw, pos, bit in cases:
            with self.subTest(label=label):
                bad = dict(base)
                flipped = _flip_bit(raw, pos, bit)
                if field == 'c':
                    bad['c'] = base64.b64encode(flipped).decode('ascii')
                else:
                    bad[field] = flipped.hex() if field == 'n' else flipped.hex()
                    if field == 't':
                        # tag is hex string; keep length, flip content.
                        bad['t'] = flipped.hex()
                with self.assertRaises(A.AeadError):
                    A.open_(KEY, A.aad_for(RID, 'relay>pc'), bad)
        # Truncations: empty, 1 byte short, half, 1 byte over via pad.
        trunc_cases = []
        for field in ('n', 'c', 't'):
            trunc_cases.append((f'{field}-empty', field, ''))
            trunc_cases.append((f'{field}-one-short', field, base[field][:-1]))
            trunc_cases.append((f'{field}-half', field, base[field][:len(base[field]) // 2]))
            trunc_cases.append((f'{field}-one-over', field, base[field] + ('00' if field != 'c' else 'A')))
        _assert_bound(self, len(trunc_cases), MAX_AEAD_CASES, 'aead trunc cases')
        for label, field, val in trunc_cases:
            with self.subTest(label=label):
                bad = dict(base)
                bad[field] = val
                with self.assertRaises(A.AeadError):
                    A.open_(KEY, A.aad_for(RID, 'relay>pc'), bad)

    def test_envelope_shape_and_type_mutations_rejected(self):
        base = self._base_envelope()
        bad_envs = [
            None, 123, 'env', [], ('enc',),
            {}, {'enc': 'aead1'}, {'enc': 'none', 'n': base['n'], 'c': base['c'], 't': base['t']},
            {'enc': 'aead1', 'n': base['n'], 'c': base['c']},  # missing t
            {'enc': 'aead1', 'n': base['n'], 't': base['t']},  # missing c
            {'enc': 'aead1', 'c': base['c'], 't': base['t']},  # missing n
            {'enc': 'aead1', 'n': None, 'c': base['c'], 't': base['t']},
            {'enc': 'aead1', 'n': 123, 'c': base['c'], 't': base['t']},
            {'enc': 'aead1', 'n': base['n'], 'c': None, 't': base['t']},
            {'enc': 'aead1', 'n': base['n'], 'c': 12345, 't': base['t']},
            {'enc': 'aead1', 'n': base['n'], 'c': base['c'], 't': None},
            {'enc': 'aead1', 'n': base['n'], 'c': base['c'], 't': 0},
            {'enc': 'aead1', 'n': 'zz' * 16, 'c': base['c'], 't': base['t']},
            {'enc': 'aead1', 'n': base['n'], 'c': '!!!not-base64!!!', 't': base['t']},
            {'enc': 'aead1', 'n': base['n'], 'c': base['c'], 't': '0' * 64},
            {'enc': 'aead1', 'n': '00' * 16, 'c': base['c'], 't': base['t']},
            {'enc': 'aead1', 'n': base['n'], 'c': base['c'], 't': base['t'], 'extra': 'ignored-but-mac-still-valid'},
        ]
        _assert_bound(self, len(bad_envs), MAX_AEAD_CASES, 'aead shape cases')
        for i, env in enumerate(bad_envs):
            with self.subTest(i=i, env=repr(env)[:60]):
                if i == len(bad_envs) - 1:
                    # Extra key is ignored by open_ (only n/c/t verified): still opens.
                    # This is not a forgery: the tag still authenticates n/c.
                    self.assertEqual(A.open_(KEY, A.aad_for(RID, 'relay>pc'), env), b'{"ok": true}')
                    continue
                with self.assertRaises(A.AeadError):
                    A.open_(KEY, A.aad_for(RID, 'relay>pc'), env)
        # Wrong key, wrong aad, wrong direction: all rejected.
        with self.assertRaises(A.AeadError):
            A.open_(KEY_WRONG, A.aad_for(RID, 'relay>pc'), base)
        with self.assertRaises(A.AeadError):
            A.open_(KEY, 'other aad', base)
        with self.assertRaises(A.AeadError):
            A.open_(KEY, A.aad_for(RID, 'pc>relay'), base)
        # Oversize ciphertext rejected without decrypting.
        big = {'enc': 'aead1', 'n': base['n'], 't': '0' * 64,
               'c': base64.b64encode(b'x' * (A.MAX_PLAINTEXT + 1)).decode('ascii')}
        with self.assertRaises(A.AeadError):
            A.open_(KEY, A.aad_for(RID, 'relay>pc'), big)

    def test_encrypting_send_wraps_forgery_as_relay_error(self):
        now = int(time.time())
        msg = {'protocol': R.PROTOCOL, 'relay_id': RID, 'op': 'reply', 'params': {'ok': True},
               'nonce': 'r-voice-1', 'issued_at': now, 'expires_at': now + 30}
        signed = {**msg, 'mac': R.sign(KEY, msg)}
        good_env = A.seal(KEY, A.aad_for(RID, 'relay>pc'), json.dumps(signed).encode())

        def raw_ok(_relay, _env):
            return dict(good_env)

        def raw_plaintext(_relay, _env):
            return dict(signed)

        def raw_tampered(_relay, _env):
            bad = dict(good_env)
            ct = bytearray(base64.b64decode(bad['c']))
            ct[0] ^= 1
            bad['c'] = base64.b64encode(bytes(ct)).decode('ascii')
            return bad

        def raw_non_dict(_relay, _env):
            return ['not', 'a', 'dict']

        send = A.encrypting_send(raw_ok, RID)
        self.assertEqual(send({'key': KEY}, {}), signed)
        for label, raw in (('plaintext', raw_plaintext), ('tampered', raw_tampered), ('non-dict', raw_non_dict)):
            with self.subTest(label=label):
                with self.assertRaises(R.RelayError):
                    A.encrypting_send(raw, RID)({'key': KEY}, {})

    def test_voice_blob_truncations_rejected(self):
        pt = b'\x00\x01\x02\x03' * 256
        env = A.seal(KEY, 'aead1|%s|voice|vclip01' % RID, pt, nonce=FIXED_NONCE)
        blob = bytes.fromhex(env['n']) + bytes.fromhex(env['t']) + base64.b64decode(env['c'])
        self.assertEqual(A.open_voice(KEY, RID, 'vclip01', blob), pt)
        bad_blobs = [
            b'', blob[:10], blob[:16], blob[:48 - 1],
            blob[:-1], blob[1:], blob + b'\x00',
            _flip_bit(blob, 0), _flip_bit(blob, 20), _flip_bit(blob, len(blob) - 1),
        ]
        _assert_bound(self, len(bad_blobs), MAX_AEAD_CASES, 'voice blob cases')
        for i, bad in enumerate(bad_blobs):
            with self.subTest(i=i):
                with self.assertRaises(A.AeadError):
                    A.open_voice(KEY, RID, 'vclip01', bad)
        with self.assertRaises(A.AeadError):
            A.open_voice(KEY, RID, 'other-clip', blob)
        with self.assertRaises(A.AeadError):
            A.open_voice(KEY_WRONG, RID, 'vclip01', blob)


class SignedReplyForgeryFuzz(unittest.TestCase):
    """Wrong-key forgeries, role confusion, adversarial JSON shapes."""

    def test_wrong_key_forgeries_rejected(self):
        rng = random.Random(SEED_REPLY)
        now = int(time.time())
        # Attacker signs with wrong key, or tampers a valid reply: always RelayError.
        valid = _signed({'observations': []}, now=now)
        cases = []
        for i in range(8):
            forged = _signed({'observations': [], 'tag': i}, key=KEY_WRONG, nonce=f'evil-{i:04d}', now=now)
            cases.append((f'wrong-key-{i}', forged))
        for i in range(8):
            tampered = dict(valid)
            tampered['params'] = {'observations': [], 'injected': rng.randrange(1 << 30)}
            tampered['nonce'] = f'tamper-{i:04d}'
            cases.append((f'tampered-{i}', tampered))
        _assert_bound(self, len(cases), MAX_REPLY_CASES, 'wrong-key cases')
        for label, msg in cases:
            with self.subTest(label=label):
                with self.assertRaises(R.RelayError):
                    R.verify(KEY, msg, {}, now=now)
                with self.assertRaises(R.RelayError):
                    R.verify(KEY, msg, None, now=now)

    def test_role_confusion_rejected(self):
        now = int(time.time())
        # A PC->relay command reflected back is not a fresh reply: same nonce
        # would replay if the cache were shared, and without the key the MAC
        # cannot be refreshed for a new nonce. Both paths fail closed.
        cmd = R.command(KEY, RID, 'get_status', now=now)
        seen = {cmd['nonce']: cmd['expires_at']}
        with self.assertRaises(R.RelayError):
            R.verify(KEY, cmd, seen, now=now)
        # Attacker without the key cannot turn a command into a reply.
        reflected = dict(cmd, op='reply')
        with self.assertRaises(R.RelayError):
            R.verify(KEY, reflected, {}, now=now)
        # Unknown ops are refused even with a valid MAC.
        for op in ('shell', 'exec', 'admin', '', None, 123, 'REPLY', 'Reply'):
            msg = {'protocol': R.PROTOCOL, 'relay_id': RID, 'op': op, 'params': {},
                   'nonce': f'role-{hash(str(op)) & 0xffff:04x}', 'issued_at': now, 'expires_at': now + 30}
            signed = {**msg, 'mac': R.sign(KEY, msg)}
            with self.subTest(op=repr(op)):
                with self.assertRaises(R.RelayError):
                    R.verify(KEY, signed, None, now=now)
        # Wrong protocol version refused even with a valid MAC.
        msg = {'protocol': 'openbridge-relay/9', 'relay_id': RID, 'op': 'reply', 'params': {},
               'nonce': 'role-proto', 'issued_at': now, 'expires_at': now + 30}
        with self.assertRaises(R.RelayError):
            R.verify(KEY, {**msg, 'mac': R.sign(KEY, msg)}, None, now=now)

    def test_adversarial_json_shapes_rejected(self):
        now = int(time.time())
        # Non-dict envelopes: RelayError (documented normalization).
        for bad in (None, 123, 'blob', ['op'], ('x',), True, 4.5):
            with self.subTest(bad=repr(bad)[:40]):
                with self.assertRaises(R.RelayError):
                    R.verify(KEY, bad, None, now=now)
                with self.assertRaises(R.RelayError):
                    R.verify(KEY, bad, {}, now=now)
        # Signed envelopes with adversarial field shapes (valid MAC, bad semantics).
        base_params = {'observations': []}
        adversarial = [
            {'op': 'reply', 'params': base_params, 'mac': None},
            {'op': 'reply', 'params': base_params, 'mac': 12345},
            {'op': 'reply', 'params': base_params, 'mac': ''},
            {'op': 'reply', 'params': base_params, 'protocol': None},
            {'op': 'reply', 'params': base_params, 'protocol': 123},
            {'op': 'reply', 'params': base_params, 'protocol': ''},
            {'op': None, 'params': base_params},
            {'op': 123, 'params': base_params},
            {'op': 'reply'},  # missing params is fine (defaults); tested separately
        ]
        _assert_bound(self, len(adversarial), MAX_REPLY_CASES, 'json shape cases')
        for i, overrides in enumerate(adversarial):
            with self.subTest(i=i):
                if overrides == {'op': 'reply'}:
                    # Missing params with valid MAC verifies (params default to {}).
                    # This is not phantom success: no observations, no grants.
                    msg = {'protocol': R.PROTOCOL, 'relay_id': RID, 'op': 'reply',
                           'nonce': f'adv-{i:04d}', 'issued_at': now, 'expires_at': now + 30}
                    signed = {**msg, 'mac': R.sign(KEY, msg)}
                    out = R.verify(KEY, signed, None, now=now)
                    self.assertNotIn('observations', out.get('params', {}))
                    continue
                if 'mac' in overrides and overrides['mac'] is not True:
                    # Corrupt MAC without re-sign: Bad signature.
                    msg = _signed(base_params, nonce=f'adv-{i:04d}', now=now)
                    msg['mac'] = overrides['mac']
                    with self.assertRaises(R.RelayError):
                        R.verify(KEY, msg, None, now=now)
                    continue
                msg = {'protocol': R.PROTOCOL, 'relay_id': RID, 'op': 'reply', 'params': base_params,
                       'nonce': f'adv-{i:04d}', 'issued_at': now, 'expires_at': now + 30}
                msg.update({k: v for k, v in overrides.items() if k != 'mac'})
                signed = {**msg, 'mac': R.sign(KEY, msg)}
                with self.assertRaises(R.RelayError):
                    R.verify(KEY, signed, None, now=now)

    def test_report_request_command_shapes_fail_closed(self):
        rng = random.Random(SEED_REPLY + 1)
        # validate_report: oversize raises; malformed entries raise; junk fields cleaned.
        with self.assertRaises(R.RelayError):
            R.validate_report({'observations': [{'address': 'x'}] * (R.MAX_OBSERVATIONS + 1)})
        with self.assertRaises(R.RelayError):
            R.validate_report({'observations': 'not-a-list'})
        with self.assertRaises(R.RelayError):
            R.validate_report({})
        for bad_obs in ([None], [123], [{'address': None}], [{'address': 'x' * 41}],
                        [{'address': 123}], ['addr-string']):
            with self.subTest(obs=repr(bad_obs)[:50]):
                with self.assertRaises(R.RelayError):
                    R.validate_report({'observations': bad_obs})
        # 200 observations is the documented cap: accepted and bounded.
        many = [{'address': 'A:%02d' % i, 'name': 'n' * 500, 'rssi': 999,
                 'company_ids': [-1, 70000, 6], 'service_uuids': ['u'] * 50} for i in range(200)]
        clean = R.validate_report({'observations': many})
        self.assertEqual(len(clean), 200)
        self.assertEqual(len(clean[0]['name']), 60)
        self.assertIsNone(clean[0]['rssi'])
        # validate_requests: oversize raises; malformed/unknown dropped, never executed.
        with self.assertRaises(R.RelayError):
            R.validate_requests({'requests': [{}] * (R.MAX_REQUESTS + 1)}, {'ctrl-1'})
        with self.assertRaises(R.RelayError):
            R.validate_requests({'requests': 'nope'}, {'ctrl-1'})
        with self.assertRaises(R.RelayError):
            R.validate_requests({}, {'ctrl-1'})
        req_id = 'a' * 32
        dropped = R.validate_requests({'requests': [
            {'request_id': req_id, 'control_id': 'unknown-ctrl'},
            {'request_id': 'bad-id', 'control_id': 'ctrl-1'},
            {'request_id': req_id}, {'control_id': 'ctrl-1'}, None, 123, 'x',
            {'request_id': req_id, 'control_id': 'ctrl-1', 'pressed_at': 'not-int',
             'seq': -1, 'gesture': 'evil', 'touch': 'not-dict'},
        ]}, {'ctrl-1'})
        # Only the last entry has a known control; junk fields are stripped.
        self.assertEqual(len(dropped), 1)
        self.assertEqual(set(dropped[0]), {'request_id', 'control_id'})
        # validate_commands: oversize raises; malformed dropped; voice/text bounded.
        with self.assertRaises(R.RelayError):
            R.validate_commands({'commands': [{}] * (R.MAX_COMMANDS + 1)})
        with self.assertRaises(R.RelayError):
            R.validate_commands({'commands': 'nope'})
        cmds = R.validate_commands({'commands': [
            {'request_id': req_id, 'lang': 'en', 'quality': 'high', 'kind': 'text', 'text': '  turn on  '},
            {'request_id': req_id, 'lang': 'xx', 'quality': 'high', 'kind': 'text', 'text': 'bad lang'},
            {'request_id': req_id, 'lang': 'en', 'quality': 'ultra', 'kind': 'text', 'text': 'bad quality'},
            {'request_id': 'bad', 'lang': 'en', 'quality': 'high', 'kind': 'text', 'text': 'bad id'},
            {'request_id': req_id, 'lang': 'en', 'quality': 'high', 'kind': 'text', 'text': ''},
            {'request_id': req_id, 'lang': 'en', 'quality': 'high', 'kind': 'text', 'text': 'x' * (R.MAX_COMMAND_TEXT + 1)},
            {'request_id': req_id, 'lang': 'en', 'quality': 'high', 'kind': 'voice', 'clip_id': 'vclip01',
             'bytes': 480000, 'sha256': 'a' * 64},
            {'request_id': req_id, 'lang': 'en', 'quality': 'high', 'kind': 'voice', 'clip_id': 'BAD!',
             'bytes': 100, 'sha256': 'a' * 64},
        ]})
        self.assertEqual(len(cmds), 2)
        self.assertEqual(cmds[0]['text'], 'turn on')
        self.assertEqual(cmds[1]['kind'], 'voice')
        # Second batch (still within the 8-entry cap): oversize voice + junk dropped.
        cmds2 = R.validate_commands({'commands': [
            {'request_id': req_id, 'lang': 'en', 'quality': 'high', 'kind': 'voice', 'clip_id': 'vclip01',
             'bytes': R.VOICE_MAX_BYTES + 2, 'sha256': 'a' * 64},
            None, 123, {'request_id': req_id},
        ]})
        self.assertEqual(cmds2, [])
        # Deterministic random command spam: never raises non-RelayError, never over-admits.
        spam = []
        for _ in range(R.MAX_COMMANDS):
            spam.append({'request_id': ''.join(rng.choice('abcdef0123456789') for _ in range(rng.choice([31, 32, 33]))),
                         'lang': rng.choice(['en', 'fr', 'de', None, 123]),
                         'quality': rng.choice(['low', 'high', 'auto', 'ultra', None]),
                         'kind': rng.choice(['text', 'voice', 'exec', None]),
                         'text': rng.choice(['hi', '', 'x' * 600, None, 123])})
        out = R.validate_commands({'commands': spam})
        self.assertLessEqual(len(out), R.MAX_COMMANDS)
        for c in out:
            self.assertIn(c['kind'], ('text', 'voice'))
            self.assertIn(c['lang'], ('en', 'fr'))


class CapabilityDeclarationFuzz(unittest.TestCase):
    """Malformed capability declarations: RelayError or empty grant, never phantom."""

    def test_relay_id_mutations_fail_closed(self):
        bad_ids = [None, 123, 4.5, True, [], {}, ('x',), '', 'has space', 'bad!char',
                   'x' * 61, '-lead', '_lead-ok?'[0:0] + '-x', 'a/b', 'a.b', 'a:b', 'relay id',
                   'é-unicode', 'a' * 0, '\x00abc', 'abc\x00']
        _assert_bound(self, len(bad_ids), MAX_CAPS_CASES, 'relay-id cases')
        for rid in bad_ids:
            with self.subTest(rid=repr(rid)[:40]):
                mgr = R.RelayManager(lambda r, m: {})
                with self.assertRaises(R.RelayError):
                    mgr.enroll(rid, KEY, 'dev', {'capabilities': ['ble_scan']})
                # No partial state under a string key either.
                if isinstance(rid, str) and rid:
                    self.assertNotIn(rid, mgr.relays)
        # Valid ids (including 60-char upper bound) still enroll.
        for rid in ('tv', 'relay-abc123', 'A-9_z', 'r' * 60):
            with self.subTest(rid=rid[:20]):
                mgr = R.RelayManager(lambda r, m: {})
                mgr.enroll(rid, KEY, 'dev', {'capabilities': []})
                self.assertIn(rid, mgr.relays)

    def test_declared_shape_mutations_fail_closed(self):
        rng = random.Random(SEED_CAPS)
        # Non-dict declared: RelayError, no partial state.
        for i, declared in enumerate((None, 123, 4.5, True, 'x', [], ('ble_scan',), b'dict')):
            with self.subTest(i=i, declared=repr(declared)[:40]):
                mgr = R.RelayManager(lambda r, m: {})
                rid = 'caps-shape-%d' % i
                with self.assertRaisesRegex(R.RelayError, 'must be an object'):
                    mgr.enroll(rid, KEY, 'dev', declared)
                self.assertNotIn(rid, mgr.relays)
        # Non-list capabilities (non-str/dict): RelayError.
        for i, caps in enumerate((123, None, 4.5, True, b'ble_scan')):
            with self.subTest(i=i, caps=repr(caps)[:40]):
                mgr = R.RelayManager(lambda r, m: {})
                rid = 'caps-list-%d' % i
                with self.assertRaisesRegex(R.RelayError, 'capabilities must be a list'):
                    mgr.enroll(rid, KEY, 'dev', {'capabilities': caps})
                self.assertNotIn(rid, mgr.relays)
        # Malformed containers grant nothing (documented coercion), never raise.
        for i, caps in enumerate(('ble_scan', {'ble_scan': True}, '', {})):
            with self.subTest(i=i, caps=repr(caps)[:40]):
                mgr = R.RelayManager(lambda r, m: {})
                mgr.enroll('caps-coerce-%d' % i, KEY, 'dev', {'capabilities': caps})
                self.assertEqual(mgr.relays['caps-coerce-%d' % i]['capabilities'], set())
                self.assertEqual(mgr.eligible('ble_scan'), [])
        # Lists with junk: filtered to the closed set, junk never enables anything.
        junk_lists = [
            [None, 123, 'ble_scan'],
            ['BLE_SCAN', 'Ble_Scan', ' ble_scan '],
            [{'ble_scan': True}, ['ble_scan'], ('ble_scan',)],
            ['shell', 'exec', 'admin', 'ble_scan;rm -rf', ''],
            ['remote_controls', 'command_submit', 'evil_cap'],
            ['ble_scan'] * 100,
            [],
        ]
        for _ in range(8):
            junk_lists.append([rng.choice(['ble_scan', 'evil', None, 123, '', 'REMOTE']) for _ in range(rng.randint(0, 10))])
        _assert_bound(self, len(junk_lists), MAX_CAPS_CASES, 'caps junk cases')
        for i, caps in enumerate(junk_lists):
            with self.subTest(i=i):
                mgr = R.RelayManager(lambda r, m: {})
                mgr.enroll('caps-junk-%d' % i, KEY, 'dev', {'capabilities': caps})
                got = mgr.relays['caps-junk-%d' % i]['capabilities']
                self.assertTrue(got <= {'ble_scan', 'remote_controls', 'command_submit'})
                if 'ble_scan' not in caps:
                    self.assertNotIn('ble_scan', got)
        # Non-dict permissions: RelayError, no partial state.
        for i, perms in enumerate(('oops', [1, 2], 123, None, True, ['BLUETOOTH_SCAN'])):
            with self.subTest(i=i, perms=repr(perms)[:40]):
                mgr = R.RelayManager(lambda r, m: {})
                rid = 'caps-perm-%d' % i
                with self.assertRaisesRegex(R.RelayError, 'permissions must be an object'):
                    mgr.enroll(rid, KEY, 'dev', {'capabilities': ['ble_scan'], 'permissions': perms})
                self.assertNotIn(rid, mgr.relays)
        # Failed re-enroll preserves the existing entry byte-for-byte.
        mgr = R.RelayManager(lambda r, m: {})
        mgr.enroll(RID, KEY, 'dev-good', {'capabilities': ['ble_scan'],
                                          'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
        mgr.relays[RID]['failures'] = 2
        before = copy.deepcopy(mgr.relays[RID])
        for bad in (None, {'capabilities': 123}, {'capabilities': ['ble_scan'], 'permissions': 'oops'}):
            with self.assertRaises(R.RelayError):
                mgr.enroll(RID, KEY, 'dev-evil', bad)
        self.assertEqual(mgr.relays[RID], before)
        self.assertEqual(mgr.eligible('ble_scan'), [RID])


class OversizedHttpBodyFuzz(unittest.TestCase):
    """Oversized and malformed HTTP bodies: refused, never truncated-then-parsed."""

    def test_relay_reply_sizes_and_shapes_refused(self):
        bodies = {}
        rng = random.Random(SEED_HTTP)

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

        srv = HTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        send = R.http_transport('http://127.0.0.1:%d' % srv.server_port)
        # Oversize bodies: refused with a structured reason.
        for i, size in enumerate((R.MAX_REPLY_BYTES + 1, R.MAX_REPLY_BYTES + 4096, 2 << 20)):
            with self.subTest(size=size):
                bodies['current'] = b'{"ok": true, "pad": "' + b'x' * size + b'"}'
                with self.assertRaisesRegex(R.RelayError, 'too large'):
                    send(None, {'op': 'probe'})
        # Exact cap: accepted; one byte over (still valid JSON): refused on size.
        base = json.dumps({'ok': True, 'pad': ''}).encode()
        at_cap = json.dumps({'ok': True, 'pad': 'x' * (R.MAX_REPLY_BYTES - len(base))}).encode()
        self.assertEqual(len(at_cap), R.MAX_REPLY_BYTES)
        bodies['current'] = at_cap
        self.assertTrue(send(None, {'op': 'probe'})['ok'])
        bodies['current'] = at_cap + b' '
        with self.assertRaisesRegex(R.RelayError, 'too large'):
            send(None, {'op': 'probe'})
        # Malformed JSON bytes: refused, never a ValueError/RecursionError leak.
        malformed = [b'not json{{{', b'\xff\xfe\x00binary', b'{"truncated": true',
                     b'\x00' * 100, b'']
        _assert_bound(self, len(malformed) + 5, MAX_HTTP_CASES, 'malformed json cases')
        for raw in malformed:
            with self.subTest(raw=repr(raw[:16])):
                bodies['current'] = raw
                with self.assertRaisesRegex(R.RelayError, 'not valid JSON'):
                    send(None, {'op': 'probe'})
        # Hostile nesting depth: either refused as invalid JSON (RecursionError
        # path) or parsed then refused as a non-object. Both are RelayError.
        bodies['current'] = b'[' * 15000 + b']' * 15000
        with self.assertRaises(R.RelayError):
            send(None, {'op': 'probe'})
        # Random bytes: fail-closed as RelayError either way (malformed JSON,
        # or valid-JSON scalar refused as non-object). Both are refusals.
        for i in range(4):
            raw = bytes(rng.randrange(256) for _ in range(rng.randint(1, 256)))
            with self.subTest(i=i, raw=repr(raw[:16])):
                bodies['current'] = raw
                with self.assertRaises(R.RelayError):
                    send(None, {'op': 'probe'})
        # Valid JSON of the wrong shape: refused as non-object.
        for raw in (b'[1, 2, 3]', b'"str"', b'42', b'null', b'true'):
            with self.subTest(raw=raw):
                bodies['current'] = raw
                with self.assertRaisesRegex(R.RelayError, 'must be a JSON object'):
                    send(None, {'op': 'probe'})
        # Explicit relay refusal propagates as RelayError, never success.
        bodies['current'] = json.dumps({'error': 'companion busy'}).encode()
        with self.assertRaisesRegex(R.RelayError, 'refused'):
            send(None, {'op': 'probe'})
        bodies['current'] = json.dumps({'ok': True}).encode()
        self.assertEqual(send(None, {'op': 'probe'}), {'ok': True})

    def test_fetch_voice_validation_fails_closed(self):
        import hashlib
        raw = bytes((i * 7) % 256 for i in range(1024))
        digest = hashlib.sha256(raw).hexdigest()
        # Pre-network validation: bad size/hash refused without any I/O.
        for bad_size in (0, -1, None, '1024', R.VOICE_MAX_BYTES + 1, R.VOICE_MAX_BYTES + 2):
            with self.subTest(size=repr(bad_size)):
                with self.assertRaises(R.RelayError):
                    R.fetch_voice('http://127.0.0.1:9', KEY, 'vclip01', bad_size, digest)
        for bad_hash in (None, '', 'xyz', 'a' * 63, 'a' * 65, 'Z' * 64):
            with self.subTest(hash=repr(bad_hash)[:20]):
                with self.assertRaises(R.RelayError):
                    R.fetch_voice('http://127.0.0.1:9', KEY, 'vclip01', 1024, bad_hash)
        # Non-string hash is a caller bug (wire hashes are validated str by
        # validate_commands): TypeError is documented, never phantom success.
        with self.assertRaises(TypeError):
            R.fetch_voice('http://127.0.0.1:9', KEY, 'vclip01', 1024, 123)
        with self.assertRaises(R.RelayError):
            R.fetch_voice('http://8.8.8.8:9', KEY, 'vclip01', 1024, digest)

        class FakeResp:
            def __init__(self, payload, headers=None):
                self._payload = payload
                self.headers = headers or {}

            def read(self, n=-1):
                return self._payload[:n] if isinstance(n, int) and n >= 0 else self._payload

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _mocked(payload, headers=None):
            opener = mock.Mock()
            opener.open.return_value = FakeResp(payload, headers or {})
            return mock.patch.object(R, '_opener', return_value=opener)

        # Correct download succeeds; size/hash mismatches are refused.
        with _mocked(raw):
            self.assertEqual(R.fetch_voice('http://127.0.0.1:9', KEY, 'vclip01', 1024, digest), raw)
        with _mocked(raw[:-1]):
            with self.assertRaisesRegex(R.RelayError, 'size mismatch'):
                R.fetch_voice('http://127.0.0.1:9', KEY, 'vclip01', 1024, digest)
        with _mocked(raw + b'\x00'):
            with self.assertRaisesRegex(R.RelayError, 'size mismatch'):
                R.fetch_voice('http://127.0.0.1:9', KEY, 'vclip01', 1024, digest)
        with _mocked(_flip_bit(raw, 0)):
            with self.assertRaisesRegex(R.RelayError, 'hash mismatch'):
                R.fetch_voice('http://127.0.0.1:9', KEY, 'vclip01', 1024, digest)
        # After aead1: plaintext (missing header) refused; sealed+tampered refused.
        env = A.seal(KEY, 'aead1|%s|voice|vclip01' % RID, raw, nonce=FIXED_NONCE)
        blob = bytes.fromhex(env['n']) + bytes.fromhex(env['t']) + base64.b64decode(env['c'])
        with _mocked(raw, headers={}):
            with self.assertRaisesRegex(R.RelayError, 'unencrypted'):
                R.fetch_voice('http://127.0.0.1:9', KEY, 'vclip01', 1024, digest,
                              relay_id=RID, aead_version='aead1')
        with _mocked(blob, headers={'X-OB-Enc': 'aead1'}):
            self.assertEqual(R.fetch_voice('http://127.0.0.1:9', KEY, 'vclip01', 1024, digest,
                                           relay_id=RID, aead_version='aead1'), raw)
        with _mocked(_flip_bit(blob, 50), headers={'X-OB-Enc': 'aead1'}):
            with self.assertRaises(R.RelayError):
                R.fetch_voice('http://127.0.0.1:9', KEY, 'vclip01', 1024, digest,
                              relay_id=RID, aead_version='aead1')
        with self.assertRaises(R.RelayError):
            R.fetch_voice_urls([], KEY, 'vclip01', 1024, digest)

    def test_server_post_body_limits(self):
        import tempfile
        import urllib.error
        import urllib.request
        from src.fabric.session import SessionJournal
        from src.server import create_server
        server = create_server(0, fabric_salt=b's',
                               session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        base = 'http://127.0.0.1:%d' % server.server_port
        with urllib.request.urlopen(base + '/api/session') as r:
            csrf = json.loads(r.read())['csrf_token']

        def post(path, body_bytes):
            req = urllib.request.Request(base + path, body_bytes,
                                         {'Content-Type': 'application/json', 'Origin': base,
                                          'X-CSRF-Token': csrf})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())

        # v1 route: oversize -> 413; exact cap parses (400 for unknown device, not 413).
        big = json.dumps({'device_id': 'x', 'source': 'demo', 'pad': 'y' * 9000}).encode()
        self.assertGreater(len(big), 8192)
        code, doc = post('/api/inspect', big)
        self.assertEqual(code, 413)
        self.assertIn('too large', doc['error'].lower())
        pad_len = 8192 - len(json.dumps({'device_id': 'x', 'source': 'demo', 'pad': ''}).encode())
        at_cap = json.dumps({'device_id': 'x', 'source': 'demo', 'pad': 'y' * pad_len}).encode()
        self.assertEqual(len(at_cap), 8192)
        code, _doc = post('/api/inspect', at_cap)
        self.assertNotEqual(code, 413)
        # Duplicate Content-Length / Transfer-Encoding cannot smuggle a body past the guard.
        import http.client
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        conn.putrequest('POST', '/api/inspect', skip_host=False)
        # NOTE: putrequest already sends one Host header; do not add a second
        # or the request fails the single-Host check (403) before the body guard.
        conn.putheader('Origin', base)
        conn.putheader('X-CSRF-Token', csrf)
        conn.putheader('Content-Type', 'application/json')
        conn.putheader('Content-Length', '10')
        conn.putheader('Content-Length', '20')
        conn.endheaders()
        conn.send(b'{"a": 1}   ')
        resp = conn.getresponse()
        self.assertEqual(resp.status, 400)
        resp.read()
        conn.close()
        # v2 route: oversize -> 400 Invalid request (fail-closed, never 500).
        big_v2 = json.dumps({'device_id': 'x', 'pad': 'z' * 9000}).encode()
        code, doc = post('/api/v2/execute', big_v2)
        self.assertEqual(code, 400)
        code, _doc = post('/api/v2/execute', json.dumps({'device_id': 'x'}).encode())
        self.assertNotEqual(code, 500)
        # Server still answers after the fuzz (no crash, no hang).
        code, _doc = post('/api/inspect', json.dumps({'device_id': 'x', 'source': 'demo'}).encode())
        self.assertIn(code, (200, 400, 409))


if __name__ == '__main__':
    unittest.main()
