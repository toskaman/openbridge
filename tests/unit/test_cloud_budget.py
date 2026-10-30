"""Cloud budget guard: caps, per-model permission, stable CLOUD_* error codes."""
import unittest

from src.ai.cloud_budget import Budget, BudgetBlocked


def config(**over):
    base = {'enabled': True, 'per_request_usd': 0.20, 'per_session_usd': 1.00,
            'per_day_usd': 3.00, 'total_usd': 3.00, 'allowed_models': ['muse-spark-1.3'],
            'retries': 1}
    base.update(over)
    return base


class BudgetTests(unittest.TestCase):
    def test_disabled_cloud_is_blocked(self):
        with self.assertRaises(BudgetBlocked) as ctx:
            Budget(config(enabled=False)).authorize('muse-spark-1.3', 0.01)
        self.assertEqual(ctx.exception.code, 'CLOUD_BUDGET_BLOCKED')

    def test_unlisted_model_is_blocked(self):
        with self.assertRaises(BudgetBlocked) as ctx:
            Budget(config()).authorize('muse-wonder-1.0', 0.01)
        self.assertEqual(ctx.exception.code, 'CLOUD_MODEL_UNAVAILABLE')

    def test_estimate_above_per_request_cap_is_blocked(self):
        with self.assertRaises(BudgetBlocked) as ctx:
            Budget(config()).authorize('muse-spark-1.3', 0.50)
        self.assertEqual(ctx.exception.code, 'CLOUD_BUDGET_BLOCKED')

    def test_spend_accumulates_and_trips_session_cap(self):
        budget = Budget(config(per_session_usd=0.10))
        budget.authorize('muse-spark-1.3', 0.06)
        budget.record_spend('muse-spark-1.3', 0.06)
        with self.assertRaises(BudgetBlocked):
            budget.authorize('muse-spark-1.3', 0.06)

    def test_record_reconciles_estimate_vs_actual(self):
        budget = Budget(config())
        budget.authorize('muse-spark-1.3', 0.10)
        report = budget.record_spend('muse-spark-1.3', 0.04)
        self.assertEqual(report['estimated_usd'], 0.10)
        self.assertEqual(report['actual_usd'], 0.04)

    def test_missing_key_code(self):
        from src.ai.cloud_budget import key_status
        self.assertEqual(key_status(None), 'CLOUD_API_KEY_MISSING')

    def test_budget_state_is_json_safe(self):
        import json
        json.dumps(Budget(config()).state())
