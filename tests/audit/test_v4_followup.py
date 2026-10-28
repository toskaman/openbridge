"""Public development fixtures only; no held-out data or runtime providers."""
import socket
import unittest
from unittest.mock import patch
from dev import audit_v4_followup as audit

class Followup(unittest.TestCase):
    def test_agent_source_probes_are_network_free_and_report_observations(self):
        with patch.object(socket,'socket',side_effect=AssertionError('network refused')):
            r=audit.probe_agent_layer()
        self.assertEqual(r['actual_provider_calls'],0)
        self.assertEqual(r['actual_hardware_calls'],0)
        self.assertIsInstance(r['evidence_refs_sent_in_prompt'],bool)
        self.assertIn('untrusted_candidate_accepted',r)
        self.assertIn('unapproved_model_envelope_accepted',r)
        self.assertIn('registry_digest_changed_on_mapping_change',r)
