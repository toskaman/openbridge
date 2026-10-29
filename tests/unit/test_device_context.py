"""N5: read-only device context snapshot for model reasoning (pure, no I/O)."""
import unittest

from src.runtime.device_context import build_snapshot


class DeviceContext(unittest.TestCase):
    def test_snapshot_lists_devices_with_reachability(self):
        devs = {'dev-vac1': {'label': 'Vacuum', 'category': 'vacuum', 'online': True},
                'dev-tv1': {'label': 'TV salon', 'category': 'tv', 'online': False},
                'dev-x': {'label': 'Mystery'}}
        snap = build_snapshot(devs)
        by_key = {d['key']: d for d in snap['devices']}
        self.assertEqual(by_key['dev-vac1']['reachability'], 'online')
        self.assertEqual(by_key['dev-tv1']['reachability'], 'offline')
        # Missing flag is NEVER assumed online: honest 'unknown'.
        self.assertEqual(by_key['dev-x']['reachability'], 'unknown')
        self.assertEqual(by_key['dev-x']['category'], 'unknown')
        self.assertEqual(snap['counts'], {'total': 3, 'by_category': {'vacuum': 1, 'tv': 1, 'unknown': 1},
                                          'unknown_reachability': 1})

    def test_empty_registry_is_honest(self):
        snap = build_snapshot({})
        self.assertEqual(snap['devices'], [])
        self.assertIn('no devices', snap['note'])

    def test_malformed_registry_fails_closed(self):
        with self.assertRaises(ValueError):
            build_snapshot({'k': 'not-a-dict'})
        with self.assertRaises(ValueError):
            build_snapshot(['not-a-dict'])

    def test_snapshot_is_detached_copy(self):
        devs = {'a': {'label': 'A', 'online': True}}
        snap = build_snapshot(devs)
        snap['devices'][0]['label'] = 'MUT'
        self.assertEqual(devs['a']['label'], 'A')


if __name__ == '__main__':
    unittest.main()
