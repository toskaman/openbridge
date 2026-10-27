from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from concurrent.futures import ThreadPoolExecutor
from src.ai.broker import RuntimeModelBroker, CreditPermit, ModelBlocked


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.now = datetime.now(timezone.utc)
        self.permit = CreditPermit('session-test', self.now, 150, 0.20)
        self.calls = []

    def broker(self, response=None, permit=None):
        def transport(payload):
            self.calls.append(payload)
            return response or {'model': 'muse-spark-1.3', 'id': 'request-test',
                'usage': {'prompt_tokens': 100, 'completion_tokens': 100},
                'choices': [{'message': {'content': '{"summary":"Fixture reviewed","evidence_refs":["battery_percent"],"action":"inspect_only","uncertainty":"Synthetic fixture only"}'}}]}
        return RuntimeModelBroker(Path(self.directory.name) / 'budget.sqlite', permit, transport=transport)

    def test_missing_credit_permit_blocks_before_transport(self):
        with self.assertRaises(ModelBlocked):
            self.broker().recommend({'battery_percent': 72})
        self.assertFalse(self.calls)

    def test_expired_or_future_credit_observation_blocks(self):
        for age in (timedelta(minutes=6), timedelta(seconds=-10)):
            permit = CreditPermit('test', self.now-age, 150, 0.20)
            with self.assertRaises(ModelBlocked):
                self.broker(permit=permit).recommend({'battery_percent':72})

    def test_meta_model_and_bounded_proposal(self):
        result = self.broker(permit=self.permit).recommend({'battery_percent':72})
        self.assertEqual(result['model_id'], 'muse-spark-1.3')
        self.assertEqual(result['proposal']['action'], 'inspect_only')
        self.assertEqual(self.calls[0]['max_completion_tokens'], 4000)

    def test_empty_content_reasoning_exhausted_blocks(self):
        # muse-spark-1.3 reasoning model can spend the whole budget on reasoning and return content=None
        for content in (None, '', '   '):
            response = {'model': 'muse-spark-1.3', 'id': 'x', 'usage': {'prompt_tokens': 110, 'completion_tokens': 4000},
                        'choices': [{'message': {'content': content}}]}
            with self.assertRaises(ModelBlocked):
                self.broker(response=response, permit=self.permit).recommend({'battery_percent': 72})

    def test_unknown_evidence_and_write_proposal_rejected(self):
        for content in ('{"summary":"x","evidence_refs":["private"],"action":"inspect_only","uncertainty":"x"}',
                        '{"summary":"x","evidence_refs":["battery_percent"],"action":"reboot","uncertainty":"x"}'):
            response = {'model':'muse-spark-1.3','id':'x','usage':{'prompt_tokens':1,'completion_tokens':1},'choices':[{'message':{'content':content}}]}
            with self.assertRaises(ModelBlocked):
                self.broker(response=response,permit=self.permit).recommend({'battery_percent':72})

    def test_wrong_returned_model_rejected(self):
        with self.assertRaises(ModelBlocked):
            self.broker(response={'model':'unknown'},permit=self.permit).recommend({'battery_percent':72})

    def test_budget_is_durable_and_conservative(self):
        broker = self.broker(permit=self.permit)
        broker.recommend({'battery_percent':72})
        self.broker(permit=self.permit).recommend({'battery_percent':72})
        with self.assertRaises(ModelBlocked):
            self.broker(permit=self.permit).recommend({'battery_percent':72})
        self.assertEqual(len(self.calls),2)

    def test_unknown_input_fields_never_transmitted(self):
        with self.assertRaises(ModelBlocked):
            self.broker(permit=self.permit).recommend({'serial':'PRIVATE'})
        self.assertFalse(self.calls)

    def test_invalid_credit_values_block(self):
        for amount in (float('nan'),float('inf'),-1,0):
            permit=CreditPermit('test',self.now,amount,0.20)
            with self.assertRaises(ModelBlocked):
                self.broker(permit=permit).recommend({'battery_percent':72})

    def test_network_failure_keeps_reservation(self):
        broker=self.broker(permit=CreditPermit('small',self.now,150,0.10))
        def fail(_):
            raise TimeoutError('Do not expose provider internals')
        broker.transport=fail
        with self.assertRaises(ModelBlocked):
            broker.recommend({'battery_percent':72})
        with self.assertRaises(ModelBlocked):
            self.broker(permit=CreditPermit('small',self.now,150,0.10)).recommend({'battery_percent':72})

    def test_concurrent_calls_share_the_same_allowance(self):
        def call(_):
            try:
                self.broker(permit=self.permit).recommend({'battery_percent':72})
                return True
            except ModelBlocked:
                return False
        with ThreadPoolExecutor(max_workers=6) as pool:
            self.assertEqual(sum(pool.map(call,range(6))),2)

    def test_malformed_and_missing_usage_block(self):
        for response in ({'model':'muse-spark-1.3'}, {'model':'muse-spark-1.3','usage':{'prompt_tokens':True,'completion_tokens':2}}):
            with self.assertRaises(ModelBlocked):
                self.broker(response=response,permit=self.permit).recommend({'battery_percent':72})
