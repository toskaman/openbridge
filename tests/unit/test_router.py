"""Router tiers: explicit choice, auditable AUTO, no silent local<->paid switch."""
import unittest

from src.ai.router import TIERS, route, RoutingError


class RouterTests(unittest.TestCase):
    def test_tiers_are_the_documented_five(self):
        self.assertEqual(sorted(TIERS), ['AUTO', 'CLOUD-HIGH', 'CLOUD-MAX', 'LOCAL-FAST', 'LOCAL-QUALITY'])

    def test_explicit_local_tier_needs_no_consent(self):
        decision = route('LOCAL-FAST', task='intent', availability={'local_fast': True})
        self.assertEqual(decision['model_id'], 'llama3.2:3b-instruct-q4_K_M')
        self.assertFalse(decision['needs_cloud_consent'])

    def test_explicit_cloud_tier_requires_consent(self):
        decision = route('CLOUD-HIGH', task='plan', availability={'cloud': True})
        self.assertTrue(decision['needs_cloud_consent'])
        self.assertTrue(decision['reasons'])

    def test_cloud_tier_without_availability_is_blocked_not_rerouted(self):
        with self.assertRaises(RoutingError) as ctx:
            route('CLOUD-HIGH', task='plan', availability={'cloud': False})
        self.assertIn('CLOUD_MODEL_UNAVAILABLE', str(ctx.exception))

    def test_explicit_local_never_silently_escalates_to_cloud(self):
        with self.assertRaises(RoutingError):
            route('LOCAL-QUALITY', task='plan', availability={'local_quality': False, 'cloud': True})

    def test_auto_prefers_local_and_logs_reasons(self):
        decision = route('AUTO', task='intent', availability={'local_fast': True, 'cloud': True})
        self.assertEqual(decision['tier'], 'LOCAL-FAST')
        self.assertTrue(decision['reasons'])
        self.assertFalse(decision['needs_cloud_consent'])

    def test_auto_complex_task_can_propose_cloud_but_flags_consent(self):
        decision = route('AUTO', task='orchestration', availability={'local_fast': True, 'cloud': True},
                         privacy='allow-cloud')
        self.assertIn(decision['tier'], ('LOCAL-QUALITY', 'CLOUD-HIGH'))
        if decision['tier'].startswith('CLOUD'):
            self.assertTrue(decision['needs_cloud_consent'])

    def test_auto_never_cloud_without_privacy_opt_in(self):
        decision = route('AUTO', task='orchestration', availability={'local_fast': True, 'cloud': True},
                         privacy='local-only')
        self.assertTrue(decision['tier'].startswith('LOCAL'))

    def test_unknown_tier_rejected(self):
        with self.assertRaises(RoutingError):
            route('CLOUD-ULTRA', task='intent', availability={})

    def test_reasons_never_carry_raw_user_text(self):
        decision = route('AUTO', task='intent', availability={'local_fast': True}, user_text='my secret lamp')
        for reason in decision['reasons']:
            self.assertNotIn('secret', reason)
