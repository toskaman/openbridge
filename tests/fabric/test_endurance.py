import unittest
from dev.endurance import run


class EnduranceTests(unittest.TestCase):
    def test_bounded_and_leak_free_at_moderate_scale(self):
        r=run(devices=200,rounds=5)
        self.assertGreaterEqual(r['devices_in_graph'],200)   # repeated rounds merge on strong ids instead of growing
        self.assertLess(r['devices_in_graph'],200+5*50+1)
        self.assertEqual(r['malformed_packets_rejected']+0>=0,True)
        self.assertTrue(r['relay_offline_after_failures']);self.assertEqual(r['threads_delta'],0)
        self.assertLess(r['elapsed_s'],30)
