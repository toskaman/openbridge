"""The ENGO feature registry stays honest: unique stable IDs, known statuses, evidence categories never merged,
referenced tests exist, nothing claims real-hardware validation without real-hardware evidence, and the
traceability matrix is regenerated from it."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = json.loads((ROOT / 'docs' / 'partners' / 'engo' / 'feature_registry.json').read_text(encoding='utf-8'))


class RegistryTests(unittest.TestCase):
    def test_ids_unique_and_statuses_known(self):
        ids = [f['feature_id'] for f in REG['features']]
        self.assertEqual(len(ids), len(set(ids)))
        for f in REG['features']:
            self.assertIn(f['status'], REG['statuses'], f['feature_id'])
            for e in f['evidence_refs']:
                self.assertIn(e.split(':')[0], REG['evidence_categories'], f['feature_id'])

    def test_claims_are_backed(self):
        for f in REG['features']:
            for t in f['tests']:
                self.assertTrue((ROOT / t).exists(), '%s: %s missing' % (f['feature_id'], t))
            if f['status'] == 'VALIDATED_REAL':
                self.assertTrue(any(e.startswith('REAL_HARDWARE') for e in f['evidence_refs']), f['feature_id'])
            if f['status'] == 'EXISTING':
                self.assertTrue(f['tests'] or f['evidence_refs'] or f['owner_module'], f['feature_id'])

    def test_matrix_is_up_to_date(self):
        r = subprocess.run([sys.executable, str(ROOT / 'dev' / 'engo_feature_matrix.py'), '--check'])
        self.assertEqual(r.returncode, 0, 'run: python dev/engo_feature_matrix.py')


if __name__ == '__main__':
    unittest.main()
