import copy
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from src.ai.broker import CreditPermit, ModelBlocked
from src.forge.spark_diagnostic import SparkDiagnostic


class SparkDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'budget.sqlite'
        self.calls = []
        self.proposal = {
            'summary': 'USB inspection works, but the Wi-Fi relay has a permission blocker before BLE observations can be refreshed.',
            'hypotheses': [{'explanation': 'Missing relay permission may explain the unavailable BLE path.', 'evidence_refs': ['usb', 'wifi', 'permission', 'ble']}],
            'checks': [{'id': 'inspect_permission', 'reason': 'Read the on-device permission status first.', 'evidence_refs': ['permission']},
                       {'id': 'review_relay', 'reason': 'Review relay readiness after inspecting the permission blocker.', 'evidence_refs': ['wifi', 'ble']}],
            'uncertainty': 'Synthetic evidence only; hypotheses are not verified causes.',
            'authorizes_execution': False,
        }

    def broker(self, *, permit=True, mutate=None):
        def transport(payload):
            self.calls.append(payload)
            response = {'model': 'muse-spark-1.3', 'id': 'mock-only',
                        'usage': {'prompt_tokens': 300, 'completion_tokens': 200},
                        'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(self.proposal)}}]}
            if mutate: mutate(response)
            return response
        p = CreditPermit('mock-observation', datetime.now(timezone.utc), 148, .10) if permit is True else permit
        return SparkDiagnostic(self.path, p, transport)

    def test_fixed_synthetic_case_and_ordered_advisory(self):
        result = self.broker().diagnose('blocked_relay')
        self.assertEqual(result['source'], 'SIMULATED')
        self.assertFalse(result['authorizes_execution'])
        self.assertEqual(result['proposal'], self.proposal)
        self.assertEqual(self.calls[0]['model'], 'muse-spark-1.3')
        self.assertNotIn('LLM_', json.dumps(self.calls))

    def test_arbitrary_topology_rejected_before_call(self):
        for bad in ({'serial': 'private'}, 'http://device', None):
            with self.assertRaises(ModelBlocked): self.broker().diagnose(bad)
        self.assertFalse(self.calls)

    def test_no_fresh_credit_blocks_before_transport(self):
        for permit in (None, CreditPermit('old', datetime.now(timezone.utc)-timedelta(minutes=6), 148, .10)):
            with self.assertRaises(ModelBlocked): self.broker(permit=permit).diagnose('blocked_relay')
        self.assertFalse(self.calls)

    def test_rejects_unknown_refs_order_duplicates_and_execution(self):
        original = copy.deepcopy(self.proposal)
        changes = [lambda p: p['hypotheses'][0].update(evidence_refs=['invented']),
                   lambda p: p.update(checks=list(reversed(p['checks']))),
                   lambda p: p['checks'].append(copy.deepcopy(p['checks'][0])),
                   lambda p: p.update(authorizes_execution=True),
                   lambda p: p['checks'][0].update(id='grant_permission'),
                   lambda p: p.update(summary='x'*1201)]
        for i, change in enumerate(changes):
            self.proposal = copy.deepcopy(original); change(self.proposal)
            broker = self.broker(); broker.budget_path = Path(self.temp.name) / f'bad-{i}.sqlite'
            with self.assertRaises(ModelBlocked): broker.diagnose('blocked_relay')

    def test_model_tools_and_truncation_rejected(self):
        for i, mutation in enumerate((lambda r: r.update(model='other'),
                                      lambda r: r['choices'][0]['message'].update(tool_calls=[{}]),
                                      lambda r: r['choices'][0].update(finish_reason='length'))):
            broker = self.broker(mutate=mutation); broker.budget_path = Path(self.temp.name) / f'model-{i}.sqlite'
            with self.assertRaises(ModelBlocked): broker.diagnose('blocked_relay')

    def test_failure_retains_reservation_and_no_retry(self):
        broker = self.broker(mutate=lambda r: r.update(model='other'))
        with self.assertRaises(ModelBlocked): broker.diagnose('blocked_relay')
        with self.assertRaises(ModelBlocked): broker.diagnose('blocked_relay')
        self.assertEqual(len(self.calls), 1)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT SUM(reserved) FROM reservations').fetchone()[0], 100000)

    def test_reasoning_and_json_share_a_bounded_completion_allowance(self):
        broker=self.broker()
        original=broker.transport
        def reasoning_transport(payload):
            response=original(payload)
            if payload['max_completion_tokens']<4000:
                response['choices'][0].update(finish_reason='length')
                response['choices'][0]['message']['content']=''
            return response
        broker.transport=reasoning_transport
        result=broker.diagnose('blocked_relay')
        self.assertEqual(result['proposal'],self.proposal)
        self.assertEqual(self.calls[0]['max_completion_tokens'],4000)
