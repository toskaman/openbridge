"""Development-only cases; frozen benchmark cases are never scored by unit tests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dev import evaluate_routing as ev


def example():
    return {'case_id':'development-only-order','family':'development','clock_epoch':1793189000,'skill_id':'ble_scan_room',
            'hop_count':2,'policy':{'mode':'AUTO'},'nodes':[
                {'alias':'old','category':'tv','transport':'WIFI','age_s':40,'online':True,'control_grant':True,'scan_permission':True,'owner_enabled':True},
                {'alias':'young','category':'phone','transport':'USB','age_s':4,'online':True,'control_grant':True,'scan_permission':True,'owner_enabled':True}]}

class Evaluation(unittest.TestCase):
    def test_router_and_baselines_do_not_receive_gold_or_sorted_response(self):
        case=example();before=copy.deepcopy(case);out=ev.run_case(case)
        self.assertEqual(case,before)
        self.assertEqual(out['predictions']['router'],'young')
        self.assertEqual(out['predictions']['catalog_first'],'old')
        self.assertEqual(out['predictions']['first_eligible'],'old')
        self.assertEqual(out['predictions']['policy_aware'],'young')
        self.assertEqual(out['contract_errors'],[])
        self.assertEqual(out['dispatch_attempts'],0);self.assertEqual(out['transport_attempts'],0)
        self.assertTrue(out['events']);self.assertTrue(out['setup_documents'])

    def test_pinned_down_abstains_without_fallback(self):
        case=example();case['policy']={'mode':'PINNED','pinned':'young'};case['nodes'][1]['online']=False
        out=ev.run_case(case)
        self.assertIsNone(out['predictions']['router']);self.assertIsNone(out['predictions']['policy_aware'])
        self.assertEqual(out['reasons']['young'],'link_down')
        self.assertEqual(out['predictions']['first_eligible'],'old')

    def test_abstention_metrics_and_empty_denominators(self):
        out=ev.score_predictions([None,None,'x'],[None,'x','x'])
        self.assertEqual((out['hits'],out['n']),(2,3))
        self.assertEqual(out['abstention_precision'],.5);self.assertEqual(out['abstention_recall'],1)
        empty=ev.score_predictions([],[])
        self.assertIsNone(empty['accuracy']);self.assertIsNone(empty['abstention_recall'])

    def test_hash_guard_and_output_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'cases.json').write_bytes(b'{}');(root/'SHA256SUMS').write_text('0'*64+'  cases.json\n')
            with self.assertRaises(ValueError):ev.verify_frozen(root)
            p=root/'report.json';ev.write_report(p,{'status':'first'})
            with self.assertRaises(FileExistsError):ev.write_report(p,{'status':'second'})
            self.assertEqual(json.loads(p.read_text())['status'],'first')

    def test_other_skill_is_refused_before_context_creation(self):
        case=example();case['skill_id']='tv_volume_step'
        with self.assertRaises(ValueError):ev.run_case(case)

    def test_case_exception_stays_in_denominator_even_for_expected_abstention(self):
        case=example();label={'case_id':case['case_id'],'selected_alias':None,'unavailable_reasons':{'old':'link_down','young':'link_down'}}
        with patch.object(ev,'run_case',side_effect=ValueError('development failure')):
            report=ev.evaluate([case],[label])
        for score in report['summary'].values():
            self.assertEqual((score['hits'],score['n'],score['errors']),(0,1,1))
        self.assertEqual(report['rows'][0]['error'],'ValueError')

    def test_frozen_case_tampering_is_refused_without_scoring(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ('SHA256SUMS','cases.json','gold.json','REGISTRATION.md','CORRIGENDUM.md'):
                (root/name).write_bytes((ev.DATA/name).read_bytes())
            ev.verify_frozen(root)
            (root/'cases.json').write_bytes(b'changed')
            with self.assertRaises(ValueError):ev.verify_frozen(root)
