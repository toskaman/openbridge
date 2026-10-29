"""Independent development probes; not frozen held-out hardware evaluation."""
import copy
import socket
import unittest
from unittest.mock import patch
from dev import audit_v4 as audit
from src.forge.fixtures import manifest
from src.forge.compiler import ForgeError,compile_manifest,eligible
from src.forge.planner import rules_plan,validate_plan

class AuditTool(unittest.TestCase):
    def test_registry_digest_is_stable_and_matches_contents(self):
        a=audit.registry_snapshot();b=audit.registry_snapshot()
        self.assertEqual(a,b);self.assertEqual(a['sha256'],audit.digest(a['registries']))
        self.assertTrue(a['registries']['primitives']);self.assertTrue(a['registries']['command_skills'])

    def test_concurrency_probe_accounts_for_mock_effects_without_network(self):
        with patch.object(socket,'socket',side_effect=AssertionError('network refused')):
            result=audit.probe_command_concurrency()
        self.assertEqual(result['mock_effects'],len(result['transactions']))
        self.assertEqual(result['single_effect_gate'],result['mock_effects']==1)
        self.assertEqual(result['actual_hardware_calls'],0)

    def test_credit_probe_uses_no_provider_and_reports_original_vs_minted(self):
        with patch.object(socket,'socket',side_effect=AssertionError('network refused')):
            result=audit.probe_explanation_credit_policy()
        self.assertTrue(result['expired_original_rejected'])
        self.assertEqual(result['actual_provider_calls'],0)
        self.assertEqual(result['guard_pass'],not(result['minted_next_slot_accepted'] or result['reservation_total_usd']>.20 or result['new_output_ledger_accepted']))

class ExistingBoundaries(unittest.TestCase):
    def test_untrusted_expansions_are_refused(self):
        original=manifest(1000)
        for key,value in [('operation','execute_shell'),('command','adb shell'),('recipients',['other']),('origin','meta_generated'),('permissions',['control'])]:
            with self.subTest(field=key):
                m=copy.deepcopy(original);m[key]=value
                with self.assertRaises(ForgeError):compile_manifest(m)

    def test_self_authorization_and_transition_rewrite_are_refused(self):
        m=manifest(1000);original=rules_plan([m],1000)
        for kind in ('consent','transition','evidence'):
            p=copy.deepcopy(original)
            if kind=='consent':p['requires_consent']=False
            elif kind=='transition':p['steps'].reverse()
            else:p['evidence_refs']=['invented']
            with self.subTest(kind=kind),self.assertRaises(ForgeError):validate_plan(p,[m],1000)

    def test_stale_evidence_cannot_be_published_as_fresh(self):
        with self.assertRaises(ForgeError):eligible(manifest(1000),1121)
