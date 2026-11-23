"""Router tiers: explicit choice, auditable AUTO, no paid model built in, no silent local->remote switch."""
import unittest

from src.ai.router import TIERS, route, RoutingError

REMOTE = {'custom': True, 'custom_model': 'my-model', 'custom_execution': 'remote'}
LOCAL_CUSTOM = {'custom': True, 'custom_model': 'lmstudio-model', 'custom_execution': 'local'}


class RouterTests(unittest.TestCase):
    def test_tiers_are_the_documented_four_without_paid_cloud(self):
        self.assertEqual(sorted(TIERS), ['AUTO', 'CUSTOM', 'LOCAL-FAST', 'LOCAL-QUALITY'])
        self.assertFalse([t for t in TIERS if t.startswith('CLOUD')])

    def test_explicit_local_tier_needs_no_consent(self):
        decision = route('LOCAL-FAST', task='intent', availability={'local_fast': True})
        self.assertEqual(decision['model_id'], 'llama3.2:3b-instruct-q4_K_M')
        self.assertFalse(decision['needs_cloud_consent'])

    def test_explicit_custom_remote_requires_consent(self):
        decision = route('CUSTOM', task='plan', availability=REMOTE)
        self.assertEqual(decision['model_id'], 'my-model')
        self.assertTrue(decision['needs_cloud_consent'])
        self.assertTrue(decision['reasons'])

    def test_explicit_custom_on_this_pc_needs_no_consent(self):
        decision = route('CUSTOM', task='plan', availability=LOCAL_CUSTOM)
        self.assertFalse(decision['needs_cloud_consent'])

    def test_custom_tier_without_connected_ai_is_blocked_not_rerouted(self):
        with self.assertRaises(RoutingError) as ctx:
            route('CUSTOM', task='plan', availability={'custom': False, 'local_fast': True})
        self.assertIn('CUSTOM_PROVIDER_MISSING', str(ctx.exception))

    def test_paid_cloud_tiers_are_gone(self):
        for tier in ('CLOUD-HIGH', 'CLOUD-MAX'):
            with self.assertRaises(RoutingError):
                route(tier, task='plan', availability={'cloud': True})

    def test_explicit_local_never_silently_escalates(self):
        with self.assertRaises(RoutingError):
            route('LOCAL-QUALITY', task='plan', availability=dict(REMOTE, local_quality=False))

    def test_auto_prefers_local_and_logs_reasons(self):
        decision = route('AUTO', task='intent', availability=dict(REMOTE, local_fast=True))
        self.assertEqual(decision['tier'], 'LOCAL-FAST')
        self.assertTrue(decision['reasons'])
        self.assertFalse(decision['needs_cloud_consent'])

    def test_auto_complex_prefers_local_quality_then_connected_ai(self):
        decision = route('AUTO', task='orchestration', availability=dict(REMOTE, local_quality=True),
                         privacy='allow-cloud')
        self.assertEqual(decision['tier'], 'LOCAL-QUALITY')
        decision = route('AUTO', task='orchestration', availability=dict(REMOTE, local_fast=True),
                         privacy='allow-cloud')
        self.assertEqual(decision['tier'], 'CUSTOM')
        self.assertTrue(decision['needs_cloud_consent'])

    def test_auto_never_remote_without_privacy_opt_in(self):
        decision = route('AUTO', task='orchestration', availability=dict(REMOTE, local_fast=True),
                         privacy='local-only')
        self.assertTrue(decision['tier'].startswith('LOCAL'))
        with self.assertRaises(RoutingError):
            route('AUTO', task='orchestration', availability=REMOTE, privacy='local-only')

    def test_auto_may_use_a_connected_ai_running_on_this_pc_without_opt_in(self):
        decision = route('AUTO', task='intent', availability=LOCAL_CUSTOM, privacy='local-only')
        self.assertEqual(decision['tier'], 'CUSTOM')
        self.assertFalse(decision['needs_cloud_consent'])

    def test_unknown_tier_rejected(self):
        with self.assertRaises(RoutingError):
            route('CLOUD-ULTRA', task='intent', availability={})

    def test_reasons_never_carry_raw_user_text(self):
        decision = route('AUTO', task='intent', availability={'local_fast': True}, user_text='my secret lamp')
        for reason in decision['reasons']:
            self.assertNotIn('secret', reason)
