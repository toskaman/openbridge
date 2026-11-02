import unittest

from src.runtime.api_v2 import executor, router
from src.runtime.primitives import TransactionReceipt
from tests.runtime.test_routing import Clock, world


def _stuff(ex, tx, prim, key, state, errors, t):
    ex.receipts[tx] = TransactionReceipt(tx, prim, key, state, None, None,
                                         state == 'VERIFIED', t, t, tuple(errors))


class ReceiptEvidenceTests(unittest.TestCase):
    """Pin route-evidence labeling (N-23/B-18).

    `_last_receipt` labels evidence SIMULATED when the device key starts
    with 'sim-' or the receipt errors mention 'SIMULATED', else
    REAL_HARDWARE (NONE when blocked). Production status, verified by
    repo-wide search: NO producer of 'sim-' keys exists (registry keys
    are uuid hex) and NOTHING writes 'SIMULATED' into receipt errors,
    and simulated runs never reach Executor.execute (runners hit real
    adapters; demo playback uses the separate demo_replay path that
    mints no executor receipts). So in production every executor
    receipt is real-hardware and the SIMULATED label is currently
    unreachable -- these pins guard the defensive detectors against
    silent drift and document the invariant for any future caller
    that routes simulated executions through the executor.
    """

    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        self.ex = executor(self.server)
        self.router = router(self.server)
        self.router.clock = self.clock
        self.key = self.keys['tv']

    def _evidence(self, prim, key):
        return self.router._last_receipt(prim, key)['evidence']

    def test_sim_key_receipt_labeled_simulated(self):
        _stuff(self.ex, 'tx-sim', 'relay_ble_scan', 'sim-demo1', 'VERIFIED', (), 1_793_100_010.0)
        self.assertEqual(self._evidence('relay_ble_scan', 'sim-demo1'), 'SIMULATED')

    def test_error_mentioning_simulated_labeled_simulated(self):
        _stuff(self.ex, 'tx-err', 'relay_ble_scan', self.key, 'FAILED',
               ('SIMULATED run failed: demo fault',), 1_793_100_010.0)
        self.assertEqual(self._evidence('relay_ble_scan', self.key), 'SIMULATED')

    def test_plain_receipt_labeled_real_hardware(self):
        _stuff(self.ex, 'tx-ok', 'relay_ble_scan', self.key, 'VERIFIED', (), 1_793_100_010.0)
        self.assertEqual(self._evidence('relay_ble_scan', self.key), 'REAL_HARDWARE')

    def test_blocked_receipt_has_no_evidence(self):
        _stuff(self.ex, 'tx-bl', 'relay_ble_scan', self.key, 'BLOCKED',
               ('CONSENT_REQUIRED: owner consent required',), 1_793_100_010.0)
        self.assertEqual(self._evidence('relay_ble_scan', self.key), 'NONE')

    def test_registry_keys_carry_no_sim_prefix(self):
        for key in self.server.fabric_registry.devices:
            self.assertFalse(key.startswith('sim-'), key)


if __name__ == '__main__':
    unittest.main(verbosity=2)
