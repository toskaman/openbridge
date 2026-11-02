"""Wallpaper vehicle: one staged image -> N full-control PCs, per-PC receipts."""
import hashlib
import unittest

from dev import wallpaper_vehicle as W
from src.runtime import montage as M


PNG = M.encode_png(16, 16, bytes((4, 5, 6, 255)) * 256)


class FakeIO(W.VehicleIO):
    def __init__(self, pcs):
        self.pcs = pcs
        self.placed = []

    def stage(self, path):
        return {'transfer_id': 't-9', 'sha256': hashlib.sha256(PNG).hexdigest(),
                'bytes': len(PNG), 'name': 'wall.png'}

    def place(self, pc_key, transfer_id, name):
        self.placed.append(pc_key)
        if pc_key == 'pc-down':
            raise W.StepError('DEVICE_UNAVAILABLE: agent gone')
        return {'remote': 'managed\\' + name, 'sha256': hashlib.sha256(PNG).hexdigest()}

    def apply(self, pc_key, name):
        return {'previous': 'C:\\win\\old.png', 'current': 'managed\\' + name,
                'restorable': False}


class Pipeline(unittest.TestCase):
    def test_all_pcs_get_per_pc_receipts(self):
        r = W.run_wallpaper(FakeIO(['pc-1', 'pc-2']), 'wall.png')
        self.assertEqual(r['verdict'], 'PASS')
        self.assertEqual(sorted(p['pc'] for p in r['pcs']), ['pc-1', 'pc-2'])
        self.assertTrue(all(p['ok'] for p in r['pcs']))
        self.assertTrue(all('sha256' in p and 'previous' in p for p in r['pcs']))

    def test_one_failure_is_partial_never_global_success(self):
        r = W.run_wallpaper(FakeIO(['pc-1', 'pc-down']), 'wall.png')
        self.assertEqual(r['verdict'], 'PARTIAL')
        by_pc = {p['pc']: p for p in r['pcs']}
        self.assertTrue(by_pc['pc-1']['ok'])
        self.assertFalse(by_pc['pc-down']['ok'])
        self.assertIn('DEVICE_UNAVAILABLE', by_pc['pc-down']['reason'])

    def test_place_before_apply_order(self):
        io = FakeIO(['pc-1'])
        order = []
        orig_place, orig_apply = io.place, io.apply
        io.place = lambda k, t, n: (order.append('place'), orig_place(k, t, n))[1]
        io.apply = lambda k, n: (order.append('apply'), orig_apply(k, n))[1]
        W.run_wallpaper(io, 'wall.png')
        self.assertEqual(order, ['place', 'apply'])

    def test_no_pcs_is_loud(self):
        r = W.run_wallpaper(FakeIO([]), 'wall.png')
        self.assertEqual(r['verdict'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
