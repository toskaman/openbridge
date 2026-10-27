"""Planner transport tests use controlled Meta responses, never hardware or providers."""
import unittest
from src.forge.fixtures import manifest
from src.forge.planner import rules_plan
from src.forge.meta_planner import MetaCapabilityPlanner
from src.forge.compiler import ForgeError

class Broker:
    model_id='muse-glimmer:30b-q4_K_M'
    model_digest='de878ce33ad81d060001db1469a02eebe4d86f0ad58cfe52dc062fdcbe4464c1'
    options={}; extra={}; local_only=True
    def __init__(self,p):self.p=p;self.payload=None
    def ready(self):return True
    def _call(self,payload):self.payload=payload;return self.p,{'prompt_eval_count':50,'eval_count':20}

class MetaPlannerTests(unittest.TestCase):
    def test_exact_local_meta_route_and_validated_plan(self):
        m=manifest(1000); b=Broker(rules_plan([m],1000))
        r=MetaCapabilityPlanner(b).plan([m],1000)
        self.assertEqual(r['plan']['steps'][0]['capability_id'],m['capability_id'])
        self.assertEqual(r['provider_cost_usd'],0)
        self.assertNotIn('Demo beacon',str(b.payload))
    def test_no_nonmeta_or_unknown_digest(self):
        for field,value in [('model_id','other'),('model_digest','retagged')]:
            b=Broker({});setattr(b,field,value)
            with self.assertRaises(ForgeError):MetaCapabilityPlanner(b)
    def test_model_does_not_authorize(self):
        m=manifest(1000);p=rules_plan([m],1000);p['requires_consent']=False
        with self.assertRaises(ForgeError):MetaCapabilityPlanner(Broker(p)).plan([m],1000)
    def test_unavailable_has_no_silent_rule_or_cloud_fallback(self):
        b=Broker({});b.ready=lambda:False
        with self.assertRaises(ForgeError):MetaCapabilityPlanner(b).plan([manifest(1000)],1000)
