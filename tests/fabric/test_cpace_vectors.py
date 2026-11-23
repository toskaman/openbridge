"""CPace: deterministic properties, plus the draft's own test vectors when present.

The pairing needs our two sides (Python here, Cpace.java in the Companion) to
agree, which tests/fabric/test_cpace.py checks with shared vectors. This file
adds two things:

1. Deterministic properties of this implementation (no randomness): stable
   generator, bilateral agreement with fixed scalars, sensitivity to every
   input, leb128 round-trips.
2. A loader for the test vectors of draft-irtf-cfrg-cpace itself. They are not
   vendored (the draft evolves); to run them, save them as JSON next to this
   file (tests/fabric/cpace_draft_vectors.json, ignored by git):

     [{"prs": "<hex>", "ci": "<hex>", "sid": "<hex>",
       "ya": "<hex scalar>", "yb": "<hex scalar>",
       "g": "<hex>", "Ya": "<hex>", "Yb": "<hex>", "isk": "<hex>"}]

   The test then checks generator(), both shares and isk() against each row.
   Until the file exists the test skips with this explanation.
"""
import json
import unittest
from pathlib import Path

from src.fabric import cpace as C

VECTORS = Path(__file__).resolve().parent / 'cpace_draft_vectors.json'

PRS = b'654321'
CI = b'relay-test-01'
SID = bytes(range(64))
YA = bytes.fromhex('02' * 32)
YB = bytes.fromhex('5d' * 32)


class Properties(unittest.TestCase):
    def test_leb128_roundtrip(self):
        for n in (0, 1, 127, 128, 255, 300, 16384, 2 ** 32 - 1, 2 ** 64):
            enc = C.leb128(n)
            val, shift = 0, 0
            for b in enc:
                val |= (b & 0x7F) << shift
                shift += 7
            self.assertEqual(val, n)
        self.assertEqual(C.leb128(0), b'\x00')
        self.assertEqual(C.leb128(300), bytes((0xAC, 0x02)))
        self.assertEqual(C.lv(b'AB'), b'\x02AB')

    def test_generator_stable_and_sensitive(self):
        g1 = C.generator(PRS, CI, SID)
        self.assertEqual(len(g1), 32)
        self.assertEqual(C.generator(PRS, CI, SID), g1)
        for prs, ci, sid in ((b'654322', CI, SID), (PRS, b'relay-test-02', SID),
                             (PRS, CI, bytes(range(1, 65))), (b'', CI, SID)):
            self.assertNotEqual(C.generator(prs, ci, sid), g1)

    def test_generator_is_a_field_element(self):
        self.assertLess(C.decode_u(C.generator(PRS, CI, SID)), C.P)

    def test_bilateral_agreement_with_fixed_scalars(self):
        g = C.generator(PRS, CI, SID)
        ya, Ya = C.share(g, scalar=YA)
        yb, Yb = C.share(g, scalar=YB)
        self.assertEqual((ya, yb), (YA, YB))
        # ya/yb in initiator/responder order on both sides: same ISK.
        isk_a = C.isk(ya, Yb, SID, Ya, Yb)
        isk_b = C.isk(yb, Ya, SID, Ya, Yb)
        self.assertEqual(len(isk_a), 64)
        self.assertEqual(isk_a, isk_b)

    def test_isk_sensitive_to_every_input(self):
        g = C.generator(PRS, CI, SID)
        _, Ya = C.share(g, scalar=YA)
        _, Yb = C.share(g, scalar=YB)
        base = C.isk(YA, Yb, SID, Ya, Yb)
        variants = [C.isk(YB, Yb, SID, Ya, Yb),
                    C.isk(YA, Yb, SID + b'x', Ya, Yb),
                    C.isk(YA, Yb, SID, Yb, Yb),
                    C.isk(YA, Yb, SID, Ya, Ya),
                    C.isk(YA, Yb, SID, Ya, Yb, ad_a=b'ctx'),
                    C.isk(YA, Yb, SID, Ya, Yb, ad_b=b'ctx')]
        for v in variants:
            self.assertNotEqual(v, base)

    def test_share_shapes(self):
        g = C.generator(PRS, CI, SID)
        y, Y = C.share(g)
        self.assertEqual((len(y), len(Y)), (32, 32))
        with self.assertRaises(C.CPaceError):
            C.decode_u(b'short')
        with self.assertRaises(C.CPaceError):
            C._clamp(b'short')

    def test_elligator2_deterministic_in_field(self):
        for r in (0, 1, 2, 123456789, C.P - 1, C.P, C.P + 5):
            x = C.elligator2(r)
            self.assertLessEqual(0, x)
            self.assertLess(x, C.P)
            self.assertEqual(C.elligator2(r), x)


@unittest.skipUnless(VECTORS.exists(), 'draft vectors not vendored: save them as %s (see module docstring)' % VECTORS.name)
class DraftVectors(unittest.TestCase):
    def test_draft_cpace255_rows(self):
        rows = json.loads(VECTORS.read_text(encoding='utf-8'))
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0)
        for i, row in enumerate(rows):
            with self.subTest(row=i):
                prs, ci, sid = (bytes.fromhex(row[k]) for k in ('prs', 'ci', 'sid'))
                ya, yb = bytes.fromhex(row['ya']), bytes.fromhex(row['yb'])
                self.assertEqual(C.generator(prs, ci, sid).hex(), row['g'].lower())
                _, Ya = C.share(C.generator(prs, ci, sid), scalar=ya)
                _, Yb = C.share(C.generator(prs, ci, sid), scalar=yb)
                self.assertEqual(Ya.hex(), row['Ya'].lower())
                self.assertEqual(Yb.hex(), row['Yb'].lower())
                ad_a = bytes.fromhex(row.get('ad_a', ''))
                ad_b = bytes.fromhex(row.get('ad_b', ''))
                self.assertEqual(C.isk(ya, Yb, sid, Ya, Yb, ad_a, ad_b).hex(), row['isk'].lower())


if __name__ == '__main__':
    unittest.main()
