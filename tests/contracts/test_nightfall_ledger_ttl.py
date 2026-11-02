import unittest

from src.runtime.route_contract import InvocationIdReused, InvocationLedger
from src.runtime.state_store import StateStore


class LedgerTtlContractTests(unittest.TestCase):
    """Pin the 600 s invocation-id TTL contract (N-22/B-20).

    All three layers (in-memory ledger, durable state store, routing
    completed-map) prune with strict `>`: refusal lasts AT LEAST ttl_s
    (an entry at exactly TTL age is still refused), in-flight entries
    are never pruned, and a full journal refuses rather than forgets
    a live id. After expiry the id is reusable as new (Stripe-style
    key expiry); nothing may assume refusal beyond TTL.
    """

    def test_finished_id_reused_within_ttl_single_dispatch(self):
        now = [1000.0]
        ledger = InvocationLedger(ttl_s=600, clock=lambda: now[0])
        calls = []
        first = ledger.run('a', 'id1', 'b', lambda: calls.append(1) or {'ok': 1})
        now[0] += 599.0
        second = ledger.run('a', 'id1', 'b', lambda: calls.append(1) or {'ok': 2})
        self.assertEqual(calls, [1])
        self.assertEqual(first, second)

    def test_finished_id_reusable_after_ttl(self):
        now = [1000.0]
        ledger = InvocationLedger(ttl_s=600, clock=lambda: now[0])
        ledger.run('a', 'id1', 'b', lambda: {'ok': 1})
        now[0] += 601.0
        out = ledger.run('a', 'id1', 'b', lambda: {'ok': 2})
        self.assertEqual(out, {'ok': 2})

    def test_boundary_age_still_refused(self):
        now = [1000.0]
        ledger = InvocationLedger(ttl_s=600, clock=lambda: now[0])
        ledger.run('a', 'id1', 'b', lambda: {'ok': 1})
        now[0] += 600.0
        with self.assertRaises(InvocationIdReused):
            ledger.run('a', 'id1', 'DIFFERENT', lambda: {'ok': 2})

    def test_binding_mismatch_forgotten_after_ttl(self):
        now = [1000.0]
        ledger = InvocationLedger(ttl_s=600, clock=lambda: now[0])
        ledger.run('a', 'id1', 'b', lambda: {'ok': 1})
        now[0] += 601.0
        out = ledger.run('a', 'id1', 'DIFFERENT', lambda: {'ok': 2})
        self.assertEqual(out, {'ok': 2})

    def test_state_store_prune_matches_ledger_operators(self):
        done = {'state': 'DONE', 'finished_at': 1000.0}
        ex = {'state': 'EXECUTING', 'started_at': 1000.0}
        self.assertEqual(len(StateStore._prune_invocations([done], 1600.0)), 1)
        self.assertEqual(StateStore._prune_invocations([done], 1601.0), [])
        self.assertEqual(len(StateStore._prune_invocations([ex], 87400.0)), 1)
        self.assertEqual(StateStore._prune_invocations([ex], 87401.0), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
