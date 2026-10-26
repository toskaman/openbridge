import json
import threading
import unittest
from src.ai.local_meta import LocalMetaBroker, MODEL_ID, MODEL_DIGEST

LIMIT='Device health and write permission are unknown from these limited facts.'
from src.ai.broker import ModelBlocked


class LocalMetaTests(unittest.TestCase):
    def setUp(self):self.calls=[]
    def broker(self,digest=MODEL_DIGEST,content=None,model=MODEL_ID):
        catalog=lambda:{'models':[{'name':MODEL_ID,'digest':digest}]}
        def chat(payload):
            self.calls.append(payload)
            return {'model':model,'done':True,'done_reason':'stop','prompt_eval_count':100,'eval_count':60,
                'message':{'role':'assistant','content':content or json.dumps({'summary':'Battery is 72 percent.','evidence_refs':['battery_percent'],'action':'inspect_only','uncertainty':LIMIT})}}
        return LocalMetaBroker(catalog=catalog,chat=chat)

    def test_pinned_meta_model_cpu_options_and_no_provider_cost(self):
        result=self.broker().recommend({'battery_percent':72},source='ADB')
        self.assertEqual(result['model_id'],MODEL_ID)
        self.assertEqual(result['model_manifest_digest'],MODEL_DIGEST)
        self.assertEqual(result['source'],'ADB')
        self.assertEqual(result['estimated_cost_usd'],0)
        self.assertEqual(self.calls[0]['options']['num_gpu'],0)
        self.assertEqual(self.calls[0]['options']['num_thread'],4)

    def test_unknown_digest_blocks_before_inference(self):
        with self.assertRaises(ModelBlocked):self.broker(digest='unknown').recommend({'battery_percent':72})
        self.assertFalse(self.calls)

    def test_private_or_arbitrary_facts_are_never_sent(self):
        for facts in ({'serial':123},{'ssid':'private'},{'battery_percent':True},{'battery_percent':101}):
            with self.assertRaises(ModelBlocked):self.broker().recommend(facts)
        self.assertFalse(self.calls)

    def test_unknown_returned_model_and_write_advice_block(self):
        with self.assertRaises(ModelBlocked):self.broker(model='unknown').recommend({'battery_percent':72})
        content=json.dumps({'summary':'Change a setting','evidence_refs':['battery_percent'],'action':'write','uncertainty':LIMIT})
        with self.assertRaises(ModelBlocked):self.broker(content=content).recommend({'battery_percent':72})

    def test_invented_numeric_claim_is_rejected(self):
        content=json.dumps({'summary':'Battery is 99 percent.','evidence_refs':['battery_percent'],'action':'inspect_only','uncertainty':LIMIT})
        with self.assertRaises(ModelBlocked):self.broker(content=content).recommend({'battery_percent':72})

    def test_unknown_evidence_reference_is_rejected(self):
        content=json.dumps({'summary':'Limited facts.','evidence_refs':['private_field'],'action':'inspect_only','uncertainty':LIMIT})
        with self.assertRaises(ModelBlocked):self.broker(content=content).recommend({'battery_percent':72})

    def test_concurrent_inference_is_refused_without_queue_or_fallback(self):
        entered=threading.Event();release=threading.Event();broker=self.broker();chat=broker.chat
        def slow(payload):entered.set();release.wait(3);return chat(payload)
        broker.chat=slow
        worker=threading.Thread(target=lambda:broker.recommend({'battery_percent':72}));worker.start()
        self.assertTrue(entered.wait(1))
        with self.assertRaises(ModelBlocked):broker.recommend({'battery_percent':72})
        release.set();worker.join(3)
        self.assertEqual(len(self.calls),1)

    def test_overconfident_or_missing_limit_statement_is_rejected(self):
        content=json.dumps({'summary':'Battery is 72 percent.','evidence_refs':['battery_percent'],'action':'inspect_only','uncertainty':'No uncertainty available.'})
        with self.assertRaises(ModelBlocked):self.broker(content=content).recommend({'battery_percent':72})
