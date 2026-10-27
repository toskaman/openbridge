import unittest
from src.forge.fixtures import manifest
from src.forge.planner import rules_plan
from src.forge.compiler import ForgeError
from src.forge.planner_v2 import SchemaConstrainedPlanner
from tests.forge.test_meta_planner import Broker

class PlannerV2Tests(unittest.TestCase):
    def test_unavailable_is_decided_by_rules_without_model(self):
        m=manifest(1000);m['available']=False;b=Broker({});b.ready=lambda:False
        result=SchemaConstrainedPlanner(b).plan([m],1000)
        self.assertEqual(result['plan']['decision'],'unavailable');self.assertFalse(result['model_called']);self.assertIsNone(b.payload)
    def test_model_still_returns_and_validates_the_complete_plan(self):
        m=manifest(1000);b=Broker(rules_plan([m],1000));result=SchemaConstrainedPlanner(b).plan([m],1000)
        self.assertEqual(result['source'],'LOCAL_META');self.assertTrue(result['model_called']);self.assertEqual(result['planner_version'],2)
        self.assertEqual(b.payload['format']['properties']['decision']['enum'],['propose'])
    def test_unknown_evidence_or_transitions_are_not_repaired(self):
        m=manifest(1000)
        for failure in ('ref','steps','refusal'):
            p=rules_plan([m],1000)
            if failure=='ref':p['evidence_refs']=['wrong']
            elif failure=='steps':p['steps'].reverse()
            else:p.update(decision='unavailable',steps=[],evidence_refs=[])
            with self.subTest(failure=failure),self.assertRaises(ForgeError):SchemaConstrainedPlanner(Broker(p)).plan([m],1000)

    def test_evidence_expiring_during_model_call_is_rejected(self):
        from unittest.mock import patch
        m=manifest(1000);m['max_age_seconds']=1
        with patch('src.forge.planner_v2.time.monotonic',side_effect=[0,0,2,2]):
            with self.assertRaises(ForgeError):SchemaConstrainedPlanner(Broker(rules_plan([m],1000))).plan([m],1000)

    def test_schema_rejects_publication_on_the_relay(self):
        try:import jsonschema
        except ImportError:self.skipTest('Optional schema validator unavailable')
        m=manifest(1000);p=rules_plan([m],1000);b=Broker(p);SchemaConstrainedPlanner(b).plan([m],1000)
        p['steps'][1]['capability_id']=m['capability_id']
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(p,b.payload['format'])
