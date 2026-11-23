"""Matter TLV codec: hand-derived vectors, failures, round-trip fuzz, official loader.

The vectors below are derived by hand from the encoding rules (control byte =
tag form | element type, minimal widths); each is checked in both directions.
Round-trip fuzz uses fixed seeds. `tests/fabric/matter_tlv_vectors.json`, when
present (git-ignored), must hold official vectors as [{"hex": "..."}] that
decode and re-encode canonically; extract them from the Matter specification
examples or connectedhomeip's TestTLV.
"""
import json
import random
import unittest
from pathlib import Path

from src.fabric import matter_tlv as T

VECTORS = Path(__file__).resolve().parent / 'matter_tlv_vectors.json'

# (python value, tag, expected bytes) — anonymous unless tagged.
CASES = [
    (0x42, None, '0442'),
    (0, None, '0400'),
    (255, None, '04ff'),
    (256, None, '050001'),
    (300, None, '052c01'),
    (2 ** 32 - 1, None, '06ffffffff'),
    (2 ** 32, None, '070000000001000000'),
    (2 ** 64 - 1, None, '07ffffffffffffffff'),
    (-1, None, '00ff'),
    (-128, None, '0080'),
    (-129, None, '017fff'),
    (-2 ** 63, None, '030000000000000080'),
    (True, None, '09'),
    (False, None, '08'),
    (None, None, '0c'),
    (True, 1, '2901'),
    (0.0, None, '0a00000000'),
    ('hi', 2, '2d02026869'),
    ('', None, '0d00'),
    (b'', None, '1000'),
    (b'\x01\x02', None, '10020102'),
    ({1: 300}, None, '1525012c0118'),
    ([True, False], None, '17090818'),
    ({1: {2: 7}}, None, '1535012402071818'),
    ({}, None, '1518'),
    ([], None, '1718'),
]


class Vectors(unittest.TestCase):
    def test_encode_vectors(self):
        for value, tag, hx in CASES:
            with self.subTest(value=value):
                self.assertEqual(T.encode(value, tag).hex(), hx)

    def test_decode_vectors(self):
        for value, tag, hx in CASES:
            with self.subTest(hex=hx):
                t, v, pos = T.decode_one(bytes.fromhex(hx))
                self.assertEqual(pos, len(hx) // 2)
                self.assertEqual(t, None if tag is None else ('context', tag))
                self.assertEqual(v, _canon_value(value))

    def test_decode_all_rejects_trailing(self):
        with self.assertRaises(T.TlvError):
            T.decode_all(bytes.fromhex('04010402'))

    def test_profile_and_qualified_tags_decode(self):
        t, v, _ = T.decode_one(bytes.fromhex('44123407'))
        self.assertEqual((t, v), (('common2', b'\x124'), 7))
        t, v, _ = T.decode_one(bytes.fromhex('e4aabbccddeeff112207'))
        self.assertEqual(t, ('qualified8', bytes.fromhex('aabbccddeeff1122')))
        self.assertEqual(v, 7)

    def test_non_minimal_accepted_on_decode(self):
        self.assertEqual(T.decode_one(bytes.fromhex('062a000000'))[1], 42)

    def test_malformed_rejected(self):
        for hx in ('04', '052c', '24', '2d020268', '13', '1c', '18', '150401', '0401ff',
                   '0d01ff', '1718ff', 'ff' * 40):
            with self.subTest(hex=hx):
                with self.assertRaises(T.TlvError):
                    T.decode_all(bytes.fromhex(hx))

    def test_encoder_refusals(self):
        for bad in (2 ** 64, -2 ** 63 - 1, float('nan'), float('inf'), {1, 2}, {'x': 1}, object()):
            with self.assertRaises(T.TlvError):
                T.encode(bad)
        with self.assertRaises(T.TlvError):
            T.encode(1, tag=256)
        deep = 1
        for _ in range(40):
            deep = [deep]
        with self.assertRaises(T.TlvError):
            T.encode(deep)


def _canon_value(v):
    if isinstance(v, dict):
        return ('struct', [(('context', k), _canon_value(x)) for k, x in v.items()])
    if isinstance(v, list):
        return ('list', [_canon_value(x) for x in v])
    return v


class Roundtrip(unittest.TestCase):
    def _gen(self, rng, depth=0):
        r = rng.random()
        if depth > 3 or r < 0.35:
            return rng.choice([0, 1, 42, 255, 256, 70000, 2 ** 40, 2 ** 64 - 1, -1, -129,
                               -2 ** 40, True, False, None, 0.5, -3.25, 100000.125, 0.1,
                               '', 'hi', 'héllo wörld 🌍', 'x' * 300, b'', b'\0\xff' * 40])
        if r < 0.55:
            return {rng.randrange(256): self._gen(rng, depth + 1) for _ in range(rng.randrange(5))}
        return [self._gen(rng, depth + 1) for _ in range(rng.randrange(5))]

    def test_roundtrip_fuzz(self):
        rng = random.Random(0x7A0)
        for i in range(300):
            v = self._gen(rng)
            tag = rng.choice([None, 0, 1, 250])
            # The encoder picks f32 only when bit-exact, so == always holds.
            t, back, pos = T.decode_one(T.encode(v, tag))
            self.assertEqual(back, _canon_value(v))
            self.assertEqual(pos, len(T.encode(v, tag)))
            self.assertEqual(t, None if tag is None else ('context', tag))

    def test_struct_member_order_preserved(self):
        v = {3: 'c', 1: 'a', 2: 'b'}
        _, (kind, items), _ = T.decode_one(T.encode(v))
        self.assertEqual([t for t, _ in items], [('context', 3), ('context', 1), ('context', 2)])


@unittest.skipUnless(VECTORS.exists(), 'official Matter TLV vectors not vendored: save them as %s' % VECTORS.name)
class OfficialVectors(unittest.TestCase):
    def test_official_vectors_roundtrip(self):
        rows = json.loads(VECTORS.read_text(encoding='utf-8'))
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0)
        for i, row in enumerate(rows):
            with self.subTest(row=i):
                raw = bytes.fromhex(row['hex'])
                tag, value = T.decode_all(raw)
                if _simple(tag, value):       # re-encodable shapes must round-trip byte-identically
                    back = T.encode(_to_python(tag, value), None if tag is None else tag[1])
                    self.assertEqual(back, raw)


def _simple(tag, value):
    if tag is not None and not (isinstance(tag, tuple) and tag[0] == 'context'):
        return False
    if isinstance(value, tuple) and value and value[0] == 'struct':
        return all(_simple(t, v) for t, v in value[1])
    if isinstance(value, tuple) and value and value[0] in ('array', 'list'):
        return all(_simple(None, v) for v in value[1])
    return True


def _to_python(tag, value):
    if isinstance(value, tuple) and value and value[0] == 'struct':
        return {t[1]: _to_python(None, v) for t, v in value[1]}
    if isinstance(value, tuple) and value and value[0] in ('array', 'list'):
        return [_to_python(None, v) for v in value[1]]
    return value


if __name__ == '__main__':
    unittest.main()
