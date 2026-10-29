"""CI gate for the V7 device evidence registry (Gate 4).

Fails when: a registry record is invalid, the public matrix is out of sync
with the registry, or the README claims a VERIFIED device the registry does
not back. Run: python -m pytest tests/unit/test_device_registry.py -q
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
from dev.device_registry import check, render  # noqa: E402


class RegistryGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = json.loads((ROOT / 'docs' / 'DEVICE_EVIDENCE.json').read_text(encoding='utf8'))

    def test_every_record_validates(self):
        for r in self.records:
            with self.subTest('%s/%s' % (r['public_device_id'], r['test_id'])):
                check(dict(r))

    def test_matrix_in_sync_with_registry(self):
        actual = (ROOT / 'docs' / 'HARDWARE_TEST_MATRIX.md').read_text(encoding='utf8')
        self.assertEqual(actual, render(self.records), 'run: python -m dev.device_registry --render')

    def test_verified_records_have_distinct_provenance(self):
        seen = set()
        for r in self.records:
            if r['status'] == 'VERIFIED':
                key = (r['public_device_id'], r['environment'], r['test_id'])
                self.assertNotIn(key, seen, key)
                seen.add(key)
                self.assertTrue(r['commit_sha'] != '0' * 40)

    def test_companion_vm_claims_need_native_companion(self):
        bad = dict(self.records[0])
        bad.update({'environment': 'FULL_GUEST_OS', 'integration': 'HOST_APP_ADAPTER',
                    'status': 'VERIFIED', 'operations': ['companion launch'],
                    'evidence': ['docs/x.md'], 'independent_oracle': 'dump'})
        with self.assertRaises(ValueError):
            check(bad)

    def test_private_data_rejected(self):
        bad = dict(self.records[0])
        bad['evidence'] = ['reachable at 192.168.1.50, see docs/x.md']
        with self.assertRaises(ValueError):
            check(bad)

    def test_readme_verified_devices_are_backed(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf8')
        backed = {r['public_device_id'] for r in self.records if r['status'] == 'VERIFIED'}
        for m in re.finditer(r'\[device:([A-Za-z0-9_-]{8,48})\]', readme):
            self.assertIn(m.group(1), backed, 'README verified-device tag without registry backing: ' + m.group(1))


if __name__ == '__main__':
    unittest.main()
