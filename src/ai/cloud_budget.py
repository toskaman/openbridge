"""Paid-cloud budget guard: caps, per-model permission, stable CLOUD_* codes.

Estimates are authorized before spend; actuals reconcile after. Separate
from the advisory broker's ledger on purpose: this guards benchmark/CLI
spend, the broker guards advisory calls. Both fail closed.
"""
import time

CODES = ('CLOUD_API_KEY_MISSING', 'CLOUD_AUTH_FAILED', 'CLOUD_QUOTA_EXCEEDED',
         'CLOUD_BUDGET_BLOCKED', 'CLOUD_MODEL_UNAVAILABLE')


class BudgetBlocked(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def key_status(api_key):
    return 'OK' if api_key else 'CLOUD_API_KEY_MISSING'


class Budget:
    def __init__(self, config):
        self.config = dict(config)
        self.spent_session = 0.0
        self.spent_day = 0.0
        self.spent_total = 0.0
        self.pending_estimate = 0.0
        self.day = time.strftime('%Y-%m-%d', time.gmtime())

    def _roll_day(self):
        today = time.strftime('%Y-%m-%d', time.gmtime())
        if today != self.day:
            self.day, self.spent_day = today, 0.0

    def authorize(self, model_id, estimate_usd):
        self._roll_day()
        cfg = self.config
        if not cfg.get('enabled'):
            raise BudgetBlocked('CLOUD_BUDGET_BLOCKED', 'Cloud spend is disabled.')
        if model_id not in (cfg.get('allowed_models') or []):
            raise BudgetBlocked('CLOUD_MODEL_UNAVAILABLE', 'Model %r is not permitted.' % model_id)
        for cap, spent in (('per_request_usd', 0.0), ('per_session_usd', self.spent_session),
                           ('per_day_usd', self.spent_day), ('total_usd', self.spent_total)):
            limit = cfg.get(cap)
            if limit is not None and spent + estimate_usd > limit:
                raise BudgetBlocked('CLOUD_BUDGET_BLOCKED', 'Cap %s exceeded (%.4f > %.4f).'
                                    % (cap, spent + estimate_usd, limit))
        self.pending_estimate = estimate_usd
        return {'model_id': model_id, 'estimate_usd': estimate_usd}

    def record_spend(self, model_id, actual_usd):
        self.spent_session += actual_usd
        self.spent_day += actual_usd
        self.spent_total += actual_usd
        report = {'model_id': model_id, 'estimated_usd': self.pending_estimate,
                  'actual_usd': actual_usd}
        self.pending_estimate = 0.0
        return report

    def state(self):
        return {'enabled': bool(self.config.get('enabled')), 'spent_session_usd': self.spent_session,
                'spent_day_usd': self.spent_day, 'spent_total_usd': self.spent_total,
                'caps': {k: self.config.get(k) for k in
                         ('per_request_usd', 'per_session_usd', 'per_day_usd', 'total_usd')}}
