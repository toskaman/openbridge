"""Broker evaluation allowance (Sol audit finding): explicit larger allowance with
canonical observation identity/time and a shared ledger — no derived slots."""
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.ai.broker import CreditPermit, ModelBlocked, RuntimeModelBroker, resolve_ledger


def permit(obs='obs-1', age_s=10, free=135.0, budget=0.20):
    return CreditPermit(observation_id=obs, verified_at=datetime.now(timezone.utc) - timedelta(seconds=age_s),
                        free_balance_usd=free, session_budget_usd=budget)


class LegacyPath(unittest.TestCase):
    def test_two_reserves_ok_third_refused(self):
        with tempfile.TemporaryDirectory() as d:
            b = RuntimeModelBroker(Path(d) / 'b.sqlite3', permit())
            b._reserve()
            b._reserve()
            with self.assertRaises(ModelBlocked):
                b._reserve()

    def test_stale_permit_refused(self):
        with tempfile.TemporaryDirectory() as d:
            b = RuntimeModelBroker(Path(d) / 'b.sqlite3', permit(age_s=400))
            with self.assertRaises(ModelBlocked):
                b._reserve()


class AllowancePath(unittest.TestCase):
    def mk(self, d, age_s=600, allowance=0.80, authz='owner-20261028-eval', obs='obs-eval'):
        return RuntimeModelBroker(Path(d) / 'b.sqlite3', permit(obs, age_s),
                                  evaluation_allowance_usd=allowance, evaluation_authz=authz)

    def test_eight_reserves_one_identity_ninth_refused(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.mk(d)
            for _ in range(8):
                b._reserve()
            with self.assertRaises(ModelBlocked):
                b._reserve()

    def test_missing_authz_refused(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.mk(d, authz=None)
            with self.assertRaises(ModelBlocked):
                b._reserve()

    def test_allowance_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in (0, -1, 1.01, math.nan, True):
                b = self.mk(d, allowance=bad)
                with self.assertRaises(ModelBlocked, msg=repr(bad)):
                    b._reserve()

    def test_observation_backstop_24h(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.mk(d, age_s=25 * 3600)
            with self.assertRaises(ModelBlocked):
                b._reserve()

    def test_shared_ledger_across_instances(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'b.sqlite3'
            for _ in range(4):
                RuntimeModelBroker(p, permit('obs-eval', 600), evaluation_allowance_usd=0.80,
                                   evaluation_authz='a')._reserve()
            b2 = RuntimeModelBroker(p, permit('obs-eval', 600), evaluation_allowance_usd=0.80,
                                    evaluation_authz='a')
            for _ in range(4):
                b2._reserve()
            with self.assertRaises(ModelBlocked):
                b2._reserve()

    def test_allowance_bound_to_observation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'b.sqlite3'
            RuntimeModelBroker(p, permit('obs-eval', 600), evaluation_allowance_usd=0.80,
                               evaluation_authz='a')._reserve()
            sneakier = RuntimeModelBroker(p, permit('obs-eval', 600), evaluation_allowance_usd=1.00,
                                          evaluation_authz='a')
            with self.assertRaises(ModelBlocked):
                sneakier._reserve()

    def test_authz_bound_to_observation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'b.sqlite3'
            RuntimeModelBroker(p, permit('obs-eval', 600), evaluation_allowance_usd=0.80,
                               evaluation_authz='a')._reserve()
            other = RuntimeModelBroker(p, permit('obs-eval', 600), evaluation_allowance_usd=0.80,
                                       evaluation_authz='b')
            with self.assertRaises(ModelBlocked):
                other._reserve()

    def test_two_processes_capped_at_first_allowance(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'b.sqlite3'
            first = RuntimeModelBroker(p, permit('obs-eval', 600), evaluation_allowance_usd=0.80,
                                       evaluation_authz='a')
            for _ in range(8):
                first._reserve()
            second = RuntimeModelBroker(p, permit('obs-eval', 600), evaluation_allowance_usd=1.00,
                                        evaluation_authz='a')
            with self.assertRaises(ModelBlocked):
                second._reserve()

    def test_whitespace_authz_refused(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.mk(d, authz='   ')
            with self.assertRaises(ModelBlocked):
                b._reserve()

    def test_global_lifetime_cap_two_dollars(self):
        # Owner-raised 2026-10-29 ($1.00 exhausted; $128 observed). Hermetic:
        # 20 x $0.10 across two observations pass, the 21st is refused.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'b.sqlite3'
            for obs in ('obs-a', 'obs-b'):
                b = RuntimeModelBroker(p, permit(obs, 600), evaluation_allowance_usd=1.00,
                                       evaluation_authz='a')
                for _ in range(10):
                    b._reserve()
            c = RuntimeModelBroker(p, permit('obs-c', 600), evaluation_allowance_usd=1.00,
                                   evaluation_authz='a')
            with self.assertRaises(ModelBlocked):
                c._reserve()

    def test_ledger_row_records_allowance_and_authz(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'b.sqlite3'
            RuntimeModelBroker(p, permit('obs-eval', 600), evaluation_allowance_usd=0.80,
                               evaluation_authz='owner-ref-1')._reserve()
            db = sqlite3.connect(p)
            try:
                row = db.execute(
                    'SELECT observation, reserved, allowance, authz FROM reservations').fetchone()
            finally:
                db.close()
            self.assertEqual(row, ('obs-eval', 100000, 800000, 'owner-ref-1'))


class CanonicalLedger(unittest.TestCase):
    def test_default_is_stable_user_level_path(self):
        a, b = resolve_ledger(None), resolve_ledger(None)
        self.assertEqual(a, b)
        self.assertIn('OpenBridge', str(a))
        self.assertTrue(str(a).endswith('budget.sqlite3'))
        self.assertFalse(str(a).startswith(str(Path.cwd())))

    def test_explicit_path_respected(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / 'custom.sqlite3')
            self.assertEqual(resolve_ledger(p), Path(p))

    def test_two_ledgers_are_independent_files(self):
        with tempfile.TemporaryDirectory() as d:
            p1, p2 = Path(d) / 'a.sqlite3', Path(d) / 'b.sqlite3'
            for p in (p1, p2):
                RuntimeModelBroker(p, permit('obs-eval', 600), evaluation_allowance_usd=0.80,
                                   evaluation_authz='a')._reserve()
            import sqlite3
            for p in (p1, p2):
                db = sqlite3.connect(p)
                try:
                    n = db.execute('SELECT COUNT(*) FROM reservations').fetchone()[0]
                finally:
                    db.close()
                self.assertEqual(n, 1)


if __name__ == '__main__':
    unittest.main()
