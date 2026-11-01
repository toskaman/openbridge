"""E1 robustness (A3, F-07/08): transplant verification, compensation, races.

- verify-via-fresh-provider (never the same live object) + candidate binding;
- publish -> dispatch/verify failure compensation (no orphaned live service);
- _seq/_records race safety; failure reports persisted under the tid.
"""
import copy
import threading
import unittest

from src.forge import transplant as T
from src.forge.fixtures import manifest as fx
from src.forge.service import ForgeService, MemoryProvider
from tests.forge.test_transplant import NOW, run_full, service


class PoisonOnReread(MemoryProvider):
    """Serves valid data for publish + its check, then poisons live re-reads."""

    def __init__(self, manifest):
        super().__init__(manifest)
        self.calls = 0

    def snapshot(self, capability_id):
        self.calls += 1
        snap = super().snapshot(capability_id)
        if self.calls > 2:
            snap['observations'] = []
        return snap


class StripBinding(MemoryProvider):
    """Drops candidate binding markers: the binding check must catch this."""

    def snapshot(self, capability_id):
        snap = super().snapshot(capability_id)
        snap['evidence_refs'] = [r for r in snap['evidence_refs']
                                 if not r.startswith('txbind-')]
        return snap


class FreshProviderVerify(unittest.TestCase):
    def test_live_object_poisoning_does_not_break_verification(self):
        svc = service()
        svc.service_factory = lambda m: ForgeService(
            PoisonOnReread(copy.deepcopy(m)), clock=lambda: NOW)
        made = []
        base = svc.provider_factory
        svc.provider_factory = lambda m: (made.append(1), base(m))[1]
        out = run_full(svc)
        self.assertEqual(out['state'], 'active')
        self.assertTrue(made, 'verify must construct a fresh provider')

    def test_missing_candidate_binding_fails_verification(self):
        svc = service()
        svc.provider_factory = lambda m: StripBinding(copy.deepcopy(m))
        with self.assertRaisesRegex(T.TransplantError, 'VERIFICATION_FAILED.*binding'):
            run_full(svc)
        failed = [r for r in svc._records.values() if r['state'] == 'failed']
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]['report']['verify']['status'], 'failed')


class Compensation(unittest.TestCase):
    def _watched(self, svc):
        created = []
        base = svc.service_factory
        svc.service_factory = lambda m: created.append(base(m)) or created[-1]
        return created

    def _failed_record(self, svc):
        failed = [r for r in svc._records.values() if r['state'] == 'failed']
        self.assertEqual(len(failed), 1)
        return failed[0]

    def test_verify_failure_revokes_receipt_and_removes_service(self):
        svc = service()
        created = self._watched(svc)
        svc.provider_factory = lambda m: StripBinding(copy.deepcopy(m))
        with self.assertRaises(T.TransplantError):
            run_full(svc)
        self.assertEqual(created[0].list_services(), [])
        self.assertEqual(svc.dispatcher.receipts, {})
        self.assertEqual(len(svc.dispatcher.revoked), 1)
        rec = self._failed_record(svc)
        self.assertEqual(rec['report']['dispatch']['status'], 'ok')
        self.assertEqual(rec['report']['verify']['status'], 'failed')
        self.assertEqual(rec['report']['revoke']['status'], 'ok')
        self.assertEqual(rec['report']['cleanup']['status'], 'ok')
        self.assertEqual(svc.report(rec['transplant_id'])['verify']['status'], 'failed')

    def test_dispatch_failure_removes_service_and_persists_report(self):
        svc = service()
        created = self._watched(svc)

        class Boom(T.SimulatedDispatcher):
            def dispatch(self, route, candidate):
                raise T.TransplantError('DISPATCH_BOOM')

        svc.dispatcher = Boom()
        with self.assertRaisesRegex(T.TransplantError, 'DISPATCH_BOOM'):
            run_full(svc)
        self.assertEqual(created[0].list_services(), [])
        self.assertEqual(svc.dispatcher.receipts, {})
        rec = self._failed_record(svc)
        self.assertEqual(rec['report']['dispatch']['status'], 'failed')
        self.assertEqual(svc.get(rec['transplant_id'])['state'], 'failed')


class CandidateBinding(unittest.TestCase):
    def test_mismatched_manifest_capability_rejected_before_publish(self):
        svc = service()
        created = []
        base = svc.service_factory
        svc.service_factory = lambda m: created.append(base(m)) or created[-1]
        other = fx(NOW)
        other['capability_id'] = 'other.capability'
        with self.assertRaisesRegex(T.TransplantError, 'MANIFEST_CAPABILITY_MISMATCH'):
            run_full(svc, manifest=other)
        self.assertEqual(created, [])

    def test_published_service_carries_candidate_marker(self):
        svc = service()
        out = run_full(svc)
        record = svc._records[out['transplant_id']]
        refs = record['service'].provider.current['evidence_refs']
        markers = [r for r in refs if r.startswith('txbind-')]
        self.assertEqual(len(markers), 1)


class SeqRace(unittest.TestCase):
    def test_concurrent_transplants_mint_unique_tids(self):
        svc = service()
        tids, errors = [], []
        lock = threading.Lock()

        def one():
            try:
                out = run_full(svc)
            except Exception as e:  # noqa: BLE001 - collected, asserted below
                with lock:
                    errors.append(e)
            else:
                with lock:
                    tids.append(out['transplant_id'])

        threads = [threading.Thread(target=one) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(set(tids)), 16)
        self.assertEqual(len(svc._records), 16)


if __name__ == '__main__':
    unittest.main()
