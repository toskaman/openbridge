import unittest
from src.adapters.simulated import discover
from src.core.policy import inspect_device, authorize


class PolicyTests(unittest.TestCase):
    def test_fixture_is_explicitly_simulated(self):
        self.assertTrue(discover()[0]['simulated'])
        self.assertEqual(discover()[0]['source'], 'SIMULATED')

    def test_inspection_has_evidence_without_claiming_inference(self):
        report = inspect_device('demo-android')
        self.assertEqual(report['model_status'], 'NOT_CONNECTED')
        self.assertTrue(report['evidence'])
        self.assertEqual(report['status'], 'READ_ONLY')

    def test_unknown_device_rejected(self):
        with self.assertRaises(ValueError):
            inspect_device('unknown')

    def test_all_writes_denied(self):
        for action in ('disable_package', 'flash', 'undo', 'unknown'):
            self.assertEqual(authorize(action), 'DENY')
