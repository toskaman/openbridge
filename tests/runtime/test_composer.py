"""Campaign Two section 4.3: cross-device workflow composer.

Meta proposes (stubbed here, never trusted); the deterministic composer
allows or refuses each step against live routes; the DAG engine executes.
No hardware or model calls: fake routers, the synthetic world() graph and a
stub proposer only.
"""
import json
import unittest

from src.runtime import composer as C


DEVICES = [
    {'key': 'dev-tv1', 'label': 'android tv', 'category': 'tv',
     'handles': {'WIFI': 'h-tv'}},
    {'key': 'dev-vac1', 'label': 'Robot vacuum (Tuya)', 'category': 'vacuum',
     'handles': {'LAN': 'h-vac'}},
]

REPLY = json.dumps({'steps': [
    {'skill_id': 'tv_volume_step', 'target': 'android tv',
     'params': {'direction': 'down'}},
    {'skill_id': 'vacuum_command', 'target': 'Robot vacuum (Tuya)',
     'params': {'command': 'dock'}, 'on_fail': 'continue'},
]})


class FakeRoutes:
    """Route-truth double: allow, refuse or fail the route check."""

    def __init__(self, selected=True, error=None, reasons=('link_down',)):
        self.selected = selected
        self.error = error
        self.reasons = reasons
        self.calls = []

    def skill_routes(self, skill_id, target=None):
        self.calls.append((skill_id, target))
        if self.error is not None:
            raise self.error
        if not self.selected:
            return {'selected_route_id': None, 'selection': {'rule': 'none_eligible'},
                    'routes': [{'route_id': 'rt-dead', 'state': 'UNAVAILABLE',
                                'reason': r} for r in self.reasons]}
        key = target or 'fabric'
        return {'selected_route_id': 'rt-x', 'selection': {'rule': 'auto_score'},
                'routes': [{'route_id': 'rt-x', 'state': 'READY',
                            'hops': [{'device_key': key, 'transport': 'WIFI',
                                      'primitive_id': 'p-' + skill_id}],
                            'operation_id': 'op:' + skill_id,
                            'evidence': 'REAL_HARDWARE'}]}


def stub_proposer(content=REPLY, model_id='stub-meta'):
    def run(prompt):
        run.prompts.append(prompt)
        return {'model_id': model_id, 'endpoint': 'stub://test', 'content': content}
    run.prompts = []
    return run


class PromptTest(unittest.TestCase):
    def test_prompt_lists_labels_and_candidates_without_device_keys(self):
        prompt = C.build_prompt('make it quiet', DEVICES)
        self.assertIn('android tv', prompt)
        self.assertIn('tv_volume_step', prompt)
        self.assertIn('vacuum_command', prompt)
        self.assertNotIn('dev-tv1', prompt)
        self.assertNotIn('dev-vac1', prompt)

    def test_prompt_states_no_atomic_rollback_and_failure_rules(self):
        prompt = C.build_prompt('make it quiet', DEVICES)
        self.assertIn('never atomically rolled back', prompt)
        self.assertIn('"on_fail"', prompt)
        self.assertIn('"needs"', prompt)

    def test_unlinked_device_has_no_candidates(self):
        devs = DEVICES + [{'key': 'dev-ghost', 'label': 'ghost speaker',
                           'category': 'speaker', 'handles': {}}]
        self.assertEqual(C.candidates_for(devs[2]), [])
        self.assertIn('do not use', C.build_prompt('x', devs))

    def test_candidates_follow_device_category(self):
        tv = C.candidates_for(DEVICES[0])
        vac = C.candidates_for(DEVICES[1])
        self.assertIn('tv_volume_step', tv)
        self.assertNotIn('vacuum_command', tv)
        self.assertIn('vacuum_command', vac)
        self.assertNotIn('tv_volume_step', vac)
        self.assertIn('device_facts', tv)
        self.assertIn('device_facts', vac)


class ProposalTest(unittest.TestCase):
    def test_happy_path_assigns_ids_and_defaults(self):
        prop = C.proposal_from_reply(REPLY)
        self.assertEqual([s['id'] for s in prop['steps']], ['step1', 'step2'])
        self.assertEqual(prop['steps'][0]['on_fail'], 'fail')
        self.assertEqual(prop['steps'][1]['on_fail'], 'continue')
        self.assertEqual(prop['steps'][0]['needs'], [])

    def test_needs_may_reference_earlier_steps_only(self):
        ok = json.dumps({'steps': [
            {'skill_id': 'device_facts', 'target': 'android tv', 'params': {}},
            {'skill_id': 'device_facts', 'target': 'android tv', 'params': {},
             'needs': ['step1']}]})
        self.assertEqual(C.proposal_from_reply(ok)['steps'][1]['needs'], ['step1'])
        bad = json.dumps({'steps': [
            {'skill_id': 'device_facts', 'target': 'android tv', 'params': {},
             'needs': ['step2']},
            {'skill_id': 'device_facts', 'target': 'android tv', 'params': {}}]})
        with self.assertRaises(C.ComposerError):
            C.proposal_from_reply(bad)

    def test_malformed_replies_rejected(self):
        many = {'steps': [{'skill_id': 'device_facts', 'target': 'android tv',
                            'params': {}} for _ in range(9)]}
        for bad in ('not json{{', '', json.dumps({'steps': []}),
                    json.dumps(many),
                    json.dumps({'steps': [{'skill_id': 'device_facts'}]}),
                    json.dumps({'steps': [{'skill_id': 'device_facts',
                                           'target': 'android tv', 'params': {},
                                           'smuggle': 1}]}),
                    json.dumps({'steps': [{'skill_id': 'device_facts',
                                           'target': 'android tv', 'params': {},
                                           'on_fail': 'retry'}]})):
            with self.assertRaises(C.ComposerError, msg=bad[:40]):
                C.proposal_from_reply(bad)


class ComposeTest(unittest.TestCase):
    def test_happy_path_carries_all_seven_step_fields(self):
        doc = C.compose(C.proposal_from_reply(REPLY), DEVICES, FakeRoutes())
        self.assertEqual((doc['allowed'], doc['refused']), (2, 0))
        s = doc['steps'][0]
        self.assertEqual(s['status'], 'allowed')
        self.assertEqual(s['device_key'], 'dev-tv1')          # verified device
        self.assertEqual(s['route']['route_id'], 'rt-x')      # permitted route
        self.assertEqual(s['route']['rule'], 'auto_score')
        self.assertTrue(s['authorization']['approval'])       # authorization
        self.assertIn('volume', s['expected_effect'])         # expected effect
        self.assertTrue(s['verification_method'])             # verification
        self.assertEqual(s['failure_strategy']['on_fail'], 'fail')
        self.assertIn('never atomically rolled back',
                      s['failure_strategy']['note'])           # failure strategy
        self.assertEqual(doc['steps'][1]['failure_strategy']['on_fail'], 'continue')
        self.assertIn('never atomically rolled back', doc['rollback'])

    def test_read_skill_needs_no_approval(self):
        prop = C.proposal_from_doc({'steps': [
            {'skill_id': 'device_facts', 'target': 'android tv', 'params': {}}]})
        doc = C.compose(prop, DEVICES, FakeRoutes())
        s = doc['steps'][0]
        self.assertEqual(s['status'], 'allowed')
        self.assertFalse(s['authorization']['approval'])

    def test_unknown_skill_bad_params_and_bad_targets_refused(self):
        prop = C.proposal_from_doc({'steps': [
            {'skill_id': 'nope', 'target': 'android tv', 'params': {}},
            {'skill_id': 'tv_volume_step', 'target': 'android tv',
             'params': {'direction': 'sideways'}},
            {'skill_id': 'tv_volume_step', 'target': 'mars tv',
             'params': {'direction': 'down'}},
            {'skill_id': 'ble_scan_room', 'target': 'android tv', 'params': {}},
        ]})
        doc = C.compose(prop, DEVICES, FakeRoutes())
        self.assertEqual((doc['allowed'], doc['refused']), (0, 4))
        reasons = [s['reason'] for s in doc['steps']]
        self.assertIn('unknown skill', reasons[0])
        self.assertIn('invalid params', reasons[1])
        self.assertIn('unverified device', reasons[2])
        self.assertIn('untargeted skill', reasons[3])

    def test_ambiguous_and_unlinked_devices_refused(self):
        devs = (DEVICES
                + [{'key': 'dev-tv2', 'label': 'Android TV', 'category': 'tv',
                    'handles': {'WIFI': 'h-tv2'}}])
        prop = C.proposal_from_doc({'steps': [
            {'skill_id': 'tv_volume_step', 'target': 'android tv',
             'params': {'direction': 'down'}}]})
        doc = C.compose(prop, devs, FakeRoutes())
        self.assertIn('unverified device', doc['steps'][0]['reason'])
        ghost = [{'key': 'dev-g', 'label': 'ghost tv', 'category': 'tv', 'handles': {}}]
        prop = C.proposal_from_doc({'steps': [
            {'skill_id': 'tv_volume_step', 'target': 'ghost tv',
             'params': {'direction': 'down'}}]})
        doc = C.compose(prop, ghost, FakeRoutes())
        self.assertIn('no live link', doc['steps'][0]['reason'])

    def test_no_permitted_route_refused_openly(self):
        prop = C.proposal_from_reply(REPLY)
        doc = C.compose(prop, DEVICES, FakeRoutes(selected=False))
        self.assertEqual((doc['allowed'], doc['refused']), (0, 2))
        self.assertIn('no permitted route', doc['steps'][0]['reason'])
        self.assertIn('link_down', doc['steps'][0]['reason'])

    def test_route_check_failure_refuses_never_admits(self):
        from src.runtime.routing import RouteError
        prop = C.proposal_from_reply(REPLY)
        doc = C.compose(prop, DEVICES,
                        FakeRoutes(error=RouteError(500, 'X', 'boom')))
        self.assertEqual(doc['allowed'], 0)
        self.assertIn('no permitted route', doc['steps'][0]['reason'])

    def test_compose_rejects_empty_inputs(self):
        with self.assertRaises(C.ComposerError):
            C.compose(C.proposal_from_reply(REPLY), [], FakeRoutes())
        with self.assertRaises(C.ComposerError):
            C.compose({'nope': 1}, DEVICES, FakeRoutes())


class RealRouteTest(unittest.TestCase):
    """compose() against the real Router over the synthetic world graph."""

    def setUp(self):
        from tests.runtime.test_routing import Clock, world
        from src.runtime.api_v2 import router
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        self.router = router(self.server)
        self.router.clock = self.clock

    def devices(self):
        return [{'key': k, 'label': d['label'], 'category': d['category'],
                 'handles': dict(d.get('handles') or {})}
                for k, d in sorted(self.server.fabric_registry.devices.items())]

    def test_live_routes_allow_and_category_mismatch_refuses(self):
        prop = C.proposal_from_doc({'steps': [
            {'skill_id': 'device_facts', 'target': 'BV9300_Pro', 'params': {}},
            {'skill_id': 'tv_volume_step', 'target': 'Android TV',
             'params': {'direction': 'down'}},
            {'skill_id': 'vacuum_command', 'target': 'Android TV',
             'params': {'command': 'dock'}},
        ]})
        doc = C.compose(prop, self.devices(), self.router)
        self.assertEqual([s['status'] for s in doc['steps']],
                         ['allowed', 'allowed', 'refused'])
        self.assertIn('no permitted route', doc['steps'][2]['reason'])

    def test_exact_skill_refused_without_measured_range(self):
        # tv_volume_set must never claim EXACT without a probed range.
        prop = C.proposal_from_doc({'steps': [
            {'skill_id': 'tv_volume_set', 'target': 'Android TV',
             'params': {'value': 10}}]})
        doc = C.compose(prop, self.devices(), self.router)
        self.assertEqual(doc['steps'][0]['status'], 'refused')
        self.assertIn('dependency_unready', doc['steps'][0]['reason'])


class ToWorkflowTest(unittest.TestCase):
    def test_allowed_steps_compile_to_valid_dag(self):
        from src.runtime.workflows import validate_workflow
        doc = C.compose(C.proposal_from_reply(REPLY), DEVICES, FakeRoutes())
        body = C.to_workflow(doc)
        self.assertEqual(body['consent'], True)
        self.assertEqual(len(validate_workflow(body)['steps']), 2)
        self.assertTrue(body['steps'][0]['approval'])

    def test_any_refusal_blocks_compilation(self):
        prop = C.proposal_from_doc({'steps': [
            {'skill_id': 'device_facts', 'target': 'android tv', 'params': {}},
            {'skill_id': 'nope', 'target': 'android tv', 'params': {}}]})
        doc = C.compose(prop, DEVICES, FakeRoutes())
        with self.assertRaises(C.ComposerError) as cm:
            C.to_workflow(doc)
        self.assertIn('step2', str(cm.exception))

    def test_empty_composition_rejected(self):
        with self.assertRaises(C.ComposerError):
            C.to_workflow({'steps': []})


class OutcomeTest(unittest.TestCase):
    def check(self, state, receipt, want):
        outcome, note = C.outcome_of(state, receipt)
        self.assertEqual(outcome, want, (state, receipt))
        self.assertTrue(note)

    def test_all_six_outcomes(self):
        self.check('EXECUTED', {'state': 'VERIFIED', 'verified': True},
                   'EXECUTED_VERIFIED')
        self.check('EXECUTED', {'state': 'EXECUTED', 'verified': True},
                   'EXECUTED_VERIFIED')
        self.check('EXECUTED', {'state': 'EXECUTED', 'verified': False},
                   'EXECUTED_UNVERIFIED')
        self.check('UNVERIFIED', {'state': 'EXECUTED_UNVERIFIED'}, 'EXECUTED_UNVERIFIED')
        self.check('DENIED', None, 'REFUSED')
        self.check('FAILED', {'state': 'BLOCKED', 'errors': ['GATE_DENIED: x']}, 'REFUSED')
        self.check('SKIPPED', None, 'REFUSED')
        self.check('FAILED', {'state': 'FAILED', 'errors': ['boom']}, 'FAILED')
        self.check('TIMEOUT', None, 'UNKNOWN')
        self.check('TIMEOUT', {'state': 'UNKNOWN_TIMEOUT'}, 'UNKNOWN')
        self.check('EXECUTED', {'state': 'REVERTED', 'verified': True}, 'RESTORED')
        self.check('QUEUED', None, 'UNKNOWN')

    def test_unverified_restore_never_claims_restored(self):
        self.check('EXECUTED', {'state': 'REVERTED', 'verified': False},
                   'EXECUTED_UNVERIFIED')


class SummarizeTest(unittest.TestCase):
    def test_record_summarizes_with_counts_and_disclaimer(self):
        from tests.runtime.test_workflows import FakeRouter
        from src.runtime import workflows as W
        store = W.MemoryStore()
        rec = W.run({'consent': True, 'steps': [
            {'id': 'a', 'skill_id': 'device_facts', 'target': 'dev-a', 'params': {}}]},
            FakeRouter(results={'device_facts': {'state': 'VERIFIED', 'verified': True}}),
            store, workflow_id='wf-sum')
        summary = C.summarize(rec)
        self.assertEqual(summary['verdict'], 'completed')
        self.assertEqual(summary['steps'][0]['outcome'], 'EXECUTED_VERIFIED')
        self.assertEqual(summary['steps'][0]['label'], 'Executed and verified')
        self.assertEqual(summary['counts']['EXECUTED_VERIFIED'], 1)
        self.assertIn('never atomically rolled back', summary['rollback'])

    def test_partial_and_failed_verdicts(self):
        self.assertEqual(C.summarize({'workflow_id': 'w', 'status': 'partial',
                                      'steps': []})['verdict'],
                         'completed with unverified steps')
        self.assertEqual(C.summarize({'workflow_id': 'w', 'status': 'failed',
                                      'steps': []})['verdict'], 'failed')


class BridgeTest(unittest.TestCase):
    def test_stub_proposer_flows_to_composition_with_provenance(self):
        stub = stub_proposer()
        doc = C.propose_and_compose('make it quiet', DEVICES, FakeRoutes(), stub)
        self.assertEqual(doc['allowed'], 2)
        self.assertEqual(doc['model_run']['provider'], 'meta')
        self.assertEqual(len(doc['reply_sha256']), 64)
        self.assertTrue(doc['reply_chars'] > 0)
        self.assertEqual(len(stub.prompts), 1)

    def test_dead_model_is_a_refusal_never_a_guess(self):
        def boom(prompt):
            raise RuntimeError('endpoint down')
        with self.assertRaises(C.ComposerError):
            C.propose_and_compose('x', DEVICES, FakeRoutes(), boom)
        with self.assertRaises(C.ComposerError):
            C.propose_and_compose('', DEVICES, FakeRoutes(), stub_proposer())
        with self.assertRaises(C.ComposerError):
            C.propose_and_compose('x', [], FakeRoutes(), stub_proposer())


class CatalogTest(unittest.TestCase):
    def test_catalog_covers_skills_outcomes_and_rollback(self):
        from src.runtime.routing import SKILLS
        cat = C.catalog()
        self.assertEqual(len(cat['skills']), len(SKILLS))
        self.assertEqual([o['id'] for o in cat['outcomes']], list(C.OUTCOMES))
        self.assertTrue(all(s['verification'] for s in cat['skills']))
        self.assertIn('never atomically rolled back', cat['rollback'])


class ComposerApiTest(unittest.TestCase):
    def setUp(self):
        from tests.runtime.test_routing import Clock, world
        from src.runtime.api_v2 import executor
        from src.runtime.primitives import Executor
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        ex = executor(self.server)

        def fake_read(self_, key, params):
            return 'VERIFIED', None, None, True, {'facts': {}}

        ex.RUNNERS = dict(Executor.RUNNERS, read_facts=fake_read)

    def test_catalog_get(self):
        from src.runtime.api_v2 import get
        code, body = get(self.server, '/api/v2/composer/catalog', '')
        self.assertEqual(code, 200)
        self.assertEqual(len(body['outcomes']), 6)

    def test_compose_post_is_a_dry_run(self):
        from src.runtime.api_v2 import post
        code, body = post(self.server, '/api/v2/composer/compose',
                          {'proposal': {'steps': [{'skill_id': 'device_facts',
                                                   'target': 'BV9300_Pro',
                                                   'params': {}}]}})
        self.assertEqual(code, 200)
        self.assertEqual(body['allowed'], 1)
        self.assertEqual(body['steps'][0]['device_key'], self.keys['phone'])

    def test_compose_post_rejects_malformed(self):
        from src.runtime.api_v2 import post
        code, _ = post(self.server, '/api/v2/composer/compose', {'proposal': {'steps': []}})
        self.assertEqual(code, 400)
        code, _ = post(self.server, '/api/v2/composer/compose', {})
        self.assertEqual(code, 400)

    def test_summary_get_round_trip(self):
        from src.runtime.api_v2 import get, post
        _, rec = post(self.server, '/api/v2/orchestration/run',
                      {'consent': True, 'workflow_id': 'wf-compsum',
                       'steps': [{'id': 'a', 'skill_id': 'device_facts',
                                  'target': self.keys['phone'], 'params': {}}]})
        self.assertEqual(rec['status'], 'done')
        code, body = get(self.server, '/api/v2/composer/summary',
                         'workflow_id=wf-compsum')
        self.assertEqual(code, 200)
        self.assertEqual(body['steps'][0]['outcome'], 'EXECUTED_VERIFIED')
        code, _ = get(self.server, '/api/v2/composer/summary', 'workflow_id=wf-nope')
        self.assertEqual(code, 404)


if __name__ == '__main__':
    unittest.main()
