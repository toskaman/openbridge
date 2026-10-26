import json
import unittest
from src.fabric.advisor import candidate_steps, rule_choice, advise, LIMIT
from src.ai.local_meta import LocalMetaBroker, MODEL_ID, MODEL_DIGEST
from src.ai.broker import ModelBlocked

SNAP={'devices':[{'key':'a','category':'router','label':'Box','capabilities':[{'name':'lan_inventory','status':'BLOCKED'}],'possibly_same_as':[]},
                 {'key':'b','category':'phone','label':'Phone','capabilities':[{'name':'inspect','status':'REAL_HARDWARE_VERIFIED'},{'name':'ble_relay','status':'NOT_SUPPORTED'}],'possibly_same_as':[]},
                 {'key':'c','category':'tv','label':'TV','capabilities':[{'name':'tv_remote_protocol','status':'NOT_SUPPORTED'}],'possibly_same_as':['d']},
                 {'key':'d','category':'media','label':'Cast','capabilities':[],'possibly_same_as':['c']}],
      'links':[{'parent':'pc','child':k} for k in 'abcd']}


def broker(out):
    return LocalMetaBroker(catalog=lambda:{'models':[{'name':MODEL_ID,'digest':MODEL_DIGEST}]},
        chat=lambda p:{'model':MODEL_ID,'done':True,'done_reason':'stop','prompt_eval_count':300,'eval_count':60,'message':{'role':'assistant','content':json.dumps(out)}})


class AdvisorTests(unittest.TestCase):
    def test_candidates_are_deterministic_and_anonymous(self):
        steps,_=candidate_steps(SNAP);ids=[s['id'] for s in steps]
        self.assertEqual(ids,['authorize_freebox:d1','install_companion:d2','pair_wifi_adb:d3','review_duplicate:d3'])
        self.assertNotIn('Phone',json.dumps(steps))
        self.assertEqual(rule_choice(steps,'find_bluetooth'),'install_companion:d2');self.assertEqual(rule_choice(steps,'tidy_inventory'),'review_duplicate:d3')

    def test_model_must_choose_a_listed_step_and_not_invent_numbers(self):
        ok=advise(broker({'summary':'4 devices are known; authorizing the router reveals more.','step':'authorize_freebox:d1','uncertainty':LIMIT}),SNAP,'extend_coverage')
        self.assertEqual((ok['step'],ok['rule_choice']),('authorize_freebox:d1','authorize_freebox:d1'))
        for bad in ({'summary':'x','step':'flash_firmware:d1','uncertainty':LIMIT},{'summary':'There are 12 devices.','step':'authorize_freebox:d1','uncertainty':LIMIT},
                    {'summary':'x','step':'authorize_freebox:d1','uncertainty':'none'},
                    {'summary':'authorize_freebox:d1','step':'authorize_freebox:d1','uncertainty':LIMIT},
                    {'summary':"{'id': 'authorize_freebox:d1', 'description': 'x'}",'step':'authorize_freebox:d1','uncertainty':LIMIT}):
            with self.assertRaises(ModelBlocked):advise(broker(bad),SNAP,'extend_coverage')
        with self.assertRaises(ModelBlocked):advise(broker({}),SNAP,'hack_neighbours')
