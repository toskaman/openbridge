"""Verified by OpenBridge: earned from public real-hardware evidence only, never by hand, and it lapses."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'verify'))
import verified_label as V  # noqa: E402

NOW = datetime(2026, 11, 23, tzinfo=timezone.utc)


def run(day, ops, env='REAL_HARDWARE', oracle='adb dump', evidence=('proof.md',)):
    return {'public_device_id': 'lamp-01', 'status': 'VERIFIED', 'environment': env, 'test_utc': '2026-%sT10:00:00Z' % day,
            'operations': list(ops), 'independent_oracle': oracle, 'evidence': list(evidence)}


class Label(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'proof.md').write_text('x', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def good(self):
        return [run('10-01', 'abc'), run('10-02', 'de'), run('10-02', 'a')]

    def test_earned(self):
        r = V.assess(self.good(), 'lamp-01', NOW, self.root)
        self.assertTrue(r['earned'], r['reasons'])
        self.assertEqual(r['valid_until'], '2027-03-31')
        self.assertIn('until 2027-03-31', V.badge(r))

    def test_emulators_and_vms_never_count(self):
        recs = [dict(x, environment='FULL_GUEST_OS') for x in self.good()]
        self.assertFalse(V.assess(recs, 'lamp-01', NOW, self.root)['earned'])

    def test_missing_oracle_or_evidence_is_not_counted(self):
        recs = self.good()
        recs[0]['independent_oracle'] = ''
        recs[1]['evidence'] = ['missing.md']
        r = V.assess(recs, 'lamp-01', NOW, self.root)
        self.assertFalse(r['earned'])
        self.assertTrue(any('not counted' in x for x in r['reasons']))

    def test_one_day_is_not_enough_and_the_label_lapses(self):
        recs = [run('10-01', 'abc'), run('10-01', 'de'), run('10-01', 'f')]
        self.assertFalse(V.assess(recs, 'lamp-01', NOW, self.root)['earned'])
        later = datetime(2027, 6, 1, tzinfo=timezone.utc)
        r = V.assess(self.good(), 'lamp-01', later, self.root)
        self.assertFalse(r['earned'])
        self.assertIn('pending', V.badge(r))

    def test_registry_parses(self):
        records = json.loads((ROOT / 'docs' / 'DEVICE_EVIDENCE.json').read_text(encoding='utf-8'))
        results = V.assess_all(records, NOW)
        self.assertEqual(len(results), len({r['public_device_id'] for r in records}))


if __name__ == '__main__':
    unittest.main()
