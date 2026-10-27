"""Controlled evaluation-harness tests: no sockets, devices or local models."""
import copy
import unittest
from unittest.mock import patch
from dev import benchmark_forge_v2 as bench
from src.ai.local_meta import MODEL_ID, MODEL_DIGEST
from src.forge.planner import GOAL

class FakeBroker:
    local_only = True
    model_id = MODEL_ID
    model_digest = MODEL_DIGEST
    options = {}
    extra = {}
    def __init__(self, failure=None):
        self.calls = 0
        self.failure = failure
    def ready(self):
        return self.failure != 'unavailable'
    def _call(self, payload):
        self.calls += 1
        options = __import__('json').loads(payload['messages'][1]['content'])['verified_eligible_candidates']
        chosen = options[0]
        plan = {'goal': GOAL, 'decision': 'propose', 'steps': [
            {'capability_id': chosen['capability_id'], 'operation': 'read_observations'},
            {'capability_id': 'pc.virtual_api.publish', 'operation': 'publish_readonly'}],
            'evidence_refs': chosen['evidence_refs'], 'requires_consent': True}
        if self.failure == 'hallucination':
            plan['steps'][0]['capability_id'] = 'invented.id'
        if self.failure == 'permission':
            plan['steps'][0]['capability_id'] = 'denied.capability'
        if self.failure == 'wrong_order':
            plan['steps'].reverse()
        if self.failure == 'consent':
            plan['requires_consent'] = False
        return plan, {'prompt_eval_count': 12, 'eval_count': 7}

class BenchmarkV2Tests(unittest.TestCase):
    def setUp(self):
        self.cases = bench.load_cases()
        self.supported = next(c for c in self.cases if c['category'] == 'single_route')
    def test_frozen_dataset_shape_and_disjoint_split(self):
        self.assertEqual(len(self.cases), 80)
        self.assertEqual(len({c['id'] for c in self.cases}), 80)
        self.assertEqual(sum(c['split'] == 'development' for c in self.cases), 40)
        self.assertEqual(sum(c['split'] == 'heldout' for c in self.cases), 40)
        self.assertGreaterEqual(len({c['category'] for c in self.cases}), 16)
        self.assertEqual(bench.dataset_sha256(), bench.FROZEN_SHA256)
    def test_rules_gold_all_cases_without_model_io(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network forbidden')):
            result = bench.evaluate('rules', self.cases)
        self.assertEqual(result['correct'], 80)
        self.assertEqual(result['model_calls'], 0)
    def test_current_v2_complete_plan_with_fake_broker(self):
        broker = FakeBroker()
        row = bench.evaluate('llama3b', [self.supported], broker=broker)['rows'][0]
        self.assertTrue(row['correct'])
        self.assertTrue(row['model_called'])
        self.assertEqual(broker.calls, 1)
        self.assertEqual(row['usage']['completion_tokens'], 7)
        self.assertEqual(row['provider_cost_usd'], 0)
    def test_scope_refusal_is_harness_gate_not_model_reasoning(self):
        cases = [c for c in self.cases if c['requested_goal'] != GOAL]
        broker = FakeBroker()
        result = bench.evaluate('llama3b', cases, broker=broker)
        self.assertEqual(broker.calls, 0)
        self.assertTrue(all(r['decision_source'] == 'HARNESS_SCOPE_GATE' for r in result['rows']))
        self.assertTrue(all(r['correct'] for r in result['rows']))
    def test_unavailable_source_refused_without_model(self):
        case = next(c for c in self.cases if c['category'] == 'all_unavailable')
        broker = FakeBroker('unavailable')
        row = bench.evaluate('llama3b', [case], broker=broker)['rows'][0]
        self.assertTrue(row['correct'])
        self.assertFalse(row['model_called'])
    def test_unavailable_model_fails_without_retry_or_fallback(self):
        broker = FakeBroker('unavailable')
        row = bench.evaluate('llama3b', [self.supported], broker=broker)['rows'][0]
        self.assertFalse(row['correct'])
        self.assertEqual(row['error'], 'META_UNAVAILABLE')
        self.assertEqual(broker.calls, 0)
    def test_invalid_output_retained_and_metrics_counted(self):
        for failure in ['hallucination', 'wrong_order', 'consent']:
            with self.subTest(failure=failure):
                broker = FakeBroker(failure)
                row = bench.evaluate('llama3b', [self.supported], broker=broker)['rows'][0]
                self.assertFalse(row['correct'])
                self.assertEqual(broker.calls, 1)
                self.assertIsNotNone(row['raw_plan'])
                self.assertEqual(row['usage']['prompt_tokens'], 12)
                if failure == 'hallucination': self.assertTrue(row['hallucinated_id'])
    def test_proposed_permission_violation_counted_before_validator(self):
        case = copy.deepcopy(self.supported)
        denied = copy.deepcopy(case['manifests'][0])
        denied.update(capability_id='denied.capability', permissions=['observe'])
        case['manifests'].append(denied)
        row = bench.evaluate('llama3b', [case], broker=FakeBroker('permission'))['rows'][0]
        self.assertTrue(row['permission_violation_proposed'])
        self.assertFalse(row['correct'])
    def test_wrong_valid_candidate_fails_exact_gold(self):
        case = copy.deepcopy(self.supported)
        case['expected_capability'] = 'other.eligible'
        row = bench.evaluate('llama3b', [case], broker=FakeBroker())['rows'][0]
        self.assertFalse(row['correct'])
    def test_explicit_glimmer_service_selects_without_network(self):
        gpu = bench.select_broker('glimmer', 'gpu-v2')
        cpu = bench.select_broker('glimmer', 'cpu-v2')
        self.assertEqual(gpu.endpoint, 'http://127.0.0.1:11438')
        self.assertEqual(cpu.endpoint, 'http://127.0.0.1:11439')
        self.assertEqual(cpu.timeout, 180)
        self.assertEqual(cpu.provider, 'Ollama isolated local CPU')
    def test_report_uses_selected_broker_metadata(self):
        broker = FakeBroker()
        broker.endpoint = 'http://127.0.0.1:11439'
        broker.provider = 'controlled fake CPU'
        broker.timeout = 180
        with patch.object(bench, 'model_memory', return_value={}):
            result = bench.evaluate('glimmer', [self.supported], broker=broker)
        self.assertEqual(result['route'], 'glimmer')
        self.assertEqual(result['endpoint'], broker.endpoint)
        self.assertEqual(result['broker_timeout_seconds'], 180)
        self.assertEqual(result['provider'], broker.provider)
        self.assertIn('180', result['budget_note'])
    def test_hard_call_budget_blocks_second_inference(self):
        broker = FakeBroker()
        result = bench.evaluate('llama3b', [self.supported, self.supported], broker=broker, max_calls=1)
        self.assertEqual(broker.calls, 1)
        self.assertEqual(result['model_calls'], 1)
        self.assertFalse(result['rows'][1]['correct'])
    def test_budget_stops_before_calls(self):
        broker = FakeBroker()
        result = bench.evaluate('llama3b', [self.supported], broker=broker, budget_seconds=0)
        self.assertEqual(broker.calls, 0)
        self.assertFalse(result['complete'])
    def test_memory_labels_do_not_claim_python_peak_is_model_rss(self):
        row = bench.evaluate('rules', [self.supported])['rows'][0]
        self.assertIn('python_peak_allocated_bytes', row)
        self.assertIsNone(row['model_process_rss_bytes'])
        self.assertIsNone(row['loaded_model_size_bytes'])

if __name__ == '__main__': unittest.main()
