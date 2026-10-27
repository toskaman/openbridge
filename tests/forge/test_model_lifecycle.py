"""Local model memory control never sends facts/prompts or chooses a model from HTTP input."""
import unittest
from src.forge.local_models import IsolatedGlimmerCPU
from src.ai.glimmer import GLIMMER_ID,GLIMMER_DIGEST
from src.forge.compiler import ForgeError
from src.forge.planner_v2 import SchemaConstrainedPlanner

class LifecycleTests(unittest.TestCase):
    def broker(self,reply=None):
        captured=[]
        def chat(payload):
            captured.append(payload)
            return reply or {'model':GLIMMER_ID,'done':True,'done_reason':'unload' if payload['keep_alive']==0 else 'load','message':{'role':'assistant','content':''},'eval_count':0,'prompt_eval_count':0}
        b=IsolatedGlimmerCPU(catalog=lambda:{'models':[{'name':GLIMMER_ID,'digest':GLIMMER_DIGEST}]},chat=chat)
        return b,captured
    def test_prepare_and_release_are_pinned_without_prompt_or_facts(self):
        b,seen=self.broker();ready=b.prepare();released=b.release()
        self.assertEqual(ready['state'],'ready');self.assertEqual(released['state'],'released')
        for payload in seen:
            self.assertEqual(payload['model'],GLIMMER_ID);self.assertNotIn('messages',payload);self.assertNotIn('prompt',payload);self.assertEqual(payload['options']['num_gpu'],0);self.assertIs(payload['options']['use_mmap'],True)
        self.assertEqual(seen[0]['keep_alive'],'5m');self.assertEqual(seen[1]['keep_alive'],0)
    def test_unknown_digest_blocks_control_before_transport(self):
        b,seen=self.broker();b.catalog=lambda:{'models':[]}
        with self.assertRaises(ForgeError):b.prepare()
        self.assertEqual(seen,[])
    def test_unexpected_generation_or_identity_is_rejected(self):
        for response in ({'model':'unknown','done':True,'done_reason':'load'}, {'model':GLIMMER_ID,'done':True,'done_reason':'load','message':{'content':'generated text'}}, {'model':GLIMMER_ID,'done':True,'done_reason':'load','eval_count':1}):
            b,_=self.broker(response)
            with self.subTest(response=response),self.assertRaises(ForgeError):b.prepare()
    def test_control_uses_same_planner_lock_and_never_queues(self):
        b,seen=self.broker();p=SchemaConstrainedPlanner(b);p._lock.acquire()
        try:
            with self.assertRaisesRegex(ForgeError,'PLANNER_BUSY'):p.prepare()
        finally:p._lock.release()
        self.assertEqual(seen,[])
    def test_model_control_does_not_authorize_or_read_device_data(self):
        b,_=self.broker();r=SchemaConstrainedPlanner(b).prepare()
        self.assertFalse(r['device_data_read']);self.assertFalse(r['authorizes_execution']);self.assertEqual(r['provider_cost_usd'],0)
