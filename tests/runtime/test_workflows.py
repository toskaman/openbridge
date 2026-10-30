"""§7 multi-device orchestration (SIMULATED_VERIFIED: fake router + fake devices; no hardware calls)."""
import threading
import time
import unittest

from src.runtime import workflows as W


class FakeRouter:
    """Minimal arm/invoke double. dispatches records (invocation_id, skill, target, params)."""

    def __init__(self, results=None, delay=0.0):
        self.results = results or {}
        self.delay = delay
        self.dispatches = []
        self.live = 0
        self.max_live = 0
        self._lock = threading.Lock()

    def skill_routes(self, skill_id, target=None):
        return {'skill_id': skill_id, 'selected_route_id': 'rt-x', 'routes': []}

    def arm(self, body, actor='owner', invocation_id=None):
        return {'invocation_id': invocation_id or 'inv-x',
                'lease_id': 'ls-x', 'route_id': 'rt-x', 'graph_revision': 'g1',
                'lease_expires_at': 't', 'lease_expires_in_s': 30}

    def invoke(self, body, actor='owner'):
        with self._lock:
            self.live += 1
            self.max_live = max(self.max_live, self.live)
        try:
            if self.delay:
                time.sleep(self.delay)
            self.dispatches.append((body['invocation_id'], body['skill_id'],
                                    body.get('target'), dict(body['params'])))
            res = self.results.get(body['skill_id'], {'state': 'EXECUTED', 'result': {'ok': True}})
            if isinstance(res, Exception):
                raise res
            out = dict(res)
            out.setdefault('state', 'EXECUTED')
            return dict(out, invocation_id=body['invocation_id'],
                        route_id='rt-x', skill_id=body['skill_id'])
        finally:
            with self._lock:
                self.live -= 1


def wf(*steps, **kw):
    body = {'consent': True, 'steps': list(steps)}
    body.update(kw)
    return body


def step(sid, target='dev-a', params=None, **kw):
    s = {'id': kw.pop('id', sid + '-' + target), 'skill_id': sid, 'target': target,
         'params': params or {}}
    s.update(kw)
    return s


class ValidateTest(unittest.TestCase):
    def test_happy_dag_topological_levels(self):
        doc = W.validate_workflow(wf(step('device_facts', id='a'),
                                     step('device_facts', id='b', needs=['a']),
                                     step('device_facts', id='c', needs=['a'])))
        self.assertEqual([[s['id'] for s in lvl] for lvl in doc['levels']],
                         [['a'], ['b', 'c']])

    def test_cycle_rejected(self):
        with self.assertRaises(W.WorkflowError):
            W.validate_workflow(wf(step('device_facts', id='a', needs=['b']),
                                   step('device_facts', id='b', needs=['a'])))

    def test_unknown_need_rejected(self):
        with self.assertRaises(W.WorkflowError):
            W.validate_workflow(wf(step('device_facts', id='a', needs=['ghost'])))

    def test_unknown_skill_rejected(self):
        with self.assertRaises(W.WorkflowError):
            W.validate_workflow(wf(step('nope_not_a_skill', id='a')))

    def test_duplicate_step_id_rejected(self):
        with self.assertRaises(W.WorkflowError):
            W.validate_workflow(wf(step('device_facts', id='a'),
                                   step('device_facts', id='a')))

    def test_consent_required(self):
        with self.assertRaises(W.WorkflowError):
            W.validate_workflow(wf(step('device_facts', id='a'), consent=False))

    def test_bad_ref_rejected(self):
        with self.assertRaises(W.WorkflowError):
            W.validate_workflow(wf(step('device_facts', id='a',
                                        params={'v': {'$ref': 'ghost.result.x'}})))

    def test_forward_ref_rejected(self):
        with self.assertRaises(W.WorkflowError):
            W.validate_workflow(wf(step('device_facts', id='a',
                                        params={'v': {'$ref': 'b.result.x'}}),
                                   step('device_facts', id='b')))


class RunnerTest(unittest.TestCase):
    def run_wf(self, body, router):
        store = W.MemoryStore()
        return W.run(body, router, store, workflow_id='wf-1'), store

    def test_sequential_executes_in_order(self):
        r = FakeRouter()
        rec, _ = self.run_wf(wf(step('device_facts', id='a'),
                                step('device_facts', id='b', needs=['a'])), r)
        self.assertEqual(rec['status'], 'done')
        self.assertEqual([d[0] for d in r.dispatches],
                         [W.invocation_id('wf-1', 'a'), W.invocation_id('wf-1', 'b')])

    def test_target_fabric_rule(self):
        with self.assertRaises(W.WorkflowError):
            W.validate_workflow(wf(step('device_facts', id='a', target='fabric')))
        with self.assertRaises(W.WorkflowError):
            W.validate_workflow(wf(step('ble_scan_room', id='a', target='dev-a')))
        doc = W.validate_workflow(wf(step('ble_scan_room', id='a', target='fabric')))
        self.assertEqual(doc['levels'][0][0]['id'], 'a')

    def test_unverified_step_runs_dependents_but_caps_at_partial(self):
        r = FakeRouter(results={'device_facts': {'state': 'EXECUTED_UNVERIFIED',
                                                 'result': {'ok': True}}})
        rec, _ = self.run_wf(wf(step('device_facts', id='a'),
                                step('tv_volume_step', id='b', needs=['a'])), r)
        states = {s['id']: s['state'] for s in rec['steps']}
        self.assertEqual(states, {'a': 'UNVERIFIED', 'b': 'EXECUTED'})
        self.assertEqual(rec['status'], 'partial')

    def test_unknown_timeout_receipt_maps_to_timeout(self):
        r = FakeRouter(results={'device_facts': {'state': 'UNKNOWN_TIMEOUT',
                                                 'errors': ['TIMEOUT: nope'],
                                                 'result': {}}})
        rec, _ = self.run_wf(wf(step('device_facts', id='a', on_fail='continue'),
                                step('tv_volume_step', id='b')), r)
        states = {s['id']: s['state'] for s in rec['steps']}
        self.assertEqual(states['a'], 'TIMEOUT')
        self.assertEqual(rec['status'], 'partial')

    def test_invocation_ids_are_contract_shaped_and_deterministic(self):
        import re
        a1, a2 = W.invocation_id('wf-1', 'a'), W.invocation_id('wf-1', 'a')
        b = W.invocation_id('wf-1', 'b')
        self.assertEqual(a1, a2)
        self.assertNotEqual(a1, b)
        for i in (a1, b):
            self.assertTrue(re.fullmatch(r'inv-[0-9a-f]{32}', i), i)

    def test_independent_steps_run_in_parallel(self):
        r = FakeRouter(delay=0.2)
        rec, _ = self.run_wf(wf(step('device_facts', id='a'),
                                step('device_facts', id='b')), r)
        self.assertEqual(rec['status'], 'done')
        self.assertGreaterEqual(r.max_live, 2)

    def test_ref_substitutes_prior_result(self):
        r = FakeRouter(results={'device_facts': {'state': 'EXECUTED',
                                                 'result': {'sha': 'abc'}}})
        rec, _ = self.run_wf(wf(step('device_facts', id='a'),
                                step('device_facts', id='b', needs=['a'],
                                     params={'v': {'$ref': 'a.result.sha'}})), r)
        by_id = {d[0]: d[3] for d in r.dispatches}
        self.assertEqual(by_id[W.invocation_id('wf-1', 'b')], {'v': 'abc'})

    def test_when_condition_skips_step(self):
        r = FakeRouter(results={'device_facts': {'state': 'EXECUTED',
                                                 'result': {'ready': False}}})
        rec, _ = self.run_wf(wf(step('device_facts', id='a'),
                                step('device_facts', id='b', needs=['a'],
                                     when={'step': 'a', 'path': 'result.ready',
                                           'equals': True})), r)
        self.assertEqual(rec['status'], 'done')
        states = {s['id']: s['state'] for s in rec['steps']}
        self.assertEqual(states, {'a': 'EXECUTED', 'b': 'SKIPPED'})
        self.assertEqual(len(r.dispatches), 1)

    def test_approval_pauses_then_resumes(self):
        r = FakeRouter()
        store = W.MemoryStore()
        rec = W.run(wf(step('device_facts', id='a', approval=True)), r, store,
                    workflow_id='wf-1')
        self.assertEqual(rec['status'], 'waiting_approval')
        self.assertEqual(len(r.dispatches), 0)
        rec = W.approve('wf-1', 'a', True, r, store)
        self.assertEqual(rec['status'], 'done')
        self.assertEqual(len(r.dispatches), 1)

    def test_approval_denied_fails_workflow(self):
        r = FakeRouter()
        store = W.MemoryStore()
        W.run(wf(step('device_facts', id='a', approval=True)), r, store,
              workflow_id='wf-1')
        rec = W.approve('wf-1', 'a', False, r, store)
        self.assertEqual(rec['status'], 'failed')
        self.assertEqual(len(r.dispatches), 0)

    def test_partial_failure_continues_independents(self):
        r = FakeRouter(results={'device_facts': RuntimeError('boom')})
        rec, _ = self.run_wf(wf(step('device_facts', id='a', on_fail='continue'),
                                step('tv_volume_step', id='b')), r)
        self.assertEqual(rec['status'], 'partial')
        states = {s['id']: s['state'] for s in rec['steps']}
        self.assertEqual(states['a'], 'FAILED')
        self.assertEqual(states['b'], 'EXECUTED')

    def test_failing_step_blocks_dependents_by_default(self):
        r = FakeRouter(results={'device_facts': RuntimeError('boom')})
        rec, _ = self.run_wf(wf(step('device_facts', id='a'),
                                step('device_facts', id='b', needs=['a'])), r)
        self.assertEqual(rec['status'], 'failed')
        states = {s['id']: s['state'] for s in rec['steps']}
        self.assertEqual(states, {'a': 'FAILED', 'b': 'SKIPPED'})

    def test_step_timeout_marks_timeout(self):
        r = FakeRouter(delay=0.3)
        rec, _ = self.run_wf(wf(step('device_facts', id='a', timeout_s=0.05,
                                     on_fail='continue'),
                                step('device_facts', id='b')), r)
        states = {s['id']: s['state'] for s in rec['steps']}
        self.assertEqual(states['a'], 'TIMEOUT')
        self.assertEqual(states['b'], 'EXECUTED')
        self.assertEqual(rec['status'], 'partial')

    def test_verified_and_reverted_receipts_count_as_success(self):
        r = FakeRouter(results={'device_facts': {'state': 'VERIFIED', 'result': {'ok': True}},
                                'tv_volume_step': {'state': 'REVERTED', 'result': {'ok': True}}})
        rec, _ = self.run_wf(wf(step('device_facts', id='a'),
                                step('tv_volume_step', id='b')), r)
        self.assertEqual(rec['status'], 'done')
        states = {s['id']: s['state'] for s in rec['steps']}
        self.assertEqual(states, {'a': 'EXECUTED', 'b': 'EXECUTED'})

    def test_retry_same_workflow_dispatches_once_per_step(self):
        r = FakeRouter()
        store = W.MemoryStore()
        W.run(wf(step('device_facts', id='a')), r, store, workflow_id='wf-1')
        rec = W.run(wf(step('device_facts', id='a')), r, store, workflow_id='wf-1')
        self.assertEqual(rec['status'], 'done')
        self.assertEqual(len(r.dispatches), 1)

    def test_cancel_blocks_approval(self):
        r = FakeRouter()
        store = W.MemoryStore()
        W.run(wf(step('device_facts', id='a', approval=True)), r, store,
              workflow_id='wf-1')
        rec = W.cancel('wf-1', store)
        self.assertEqual(rec['status'], 'cancelled')
        with self.assertRaises(W.WorkflowError):
            W.approve('wf-1', 'a', True, r, store)
        self.assertEqual(len(r.dispatches), 0)

    def test_receipts_are_durable_in_journal(self):
        r = FakeRouter()
        _, store = self.run_wf(wf(step('device_facts', id='a')), r)
        rec = store.get('wf-1')
        self.assertEqual(rec['steps'][0]['receipt']['skill_id'], 'device_facts')
        self.assertIn('finished_at', rec)


class JournalTest(unittest.TestCase):
    def test_state_store_journal_survives_reload(self):
        import tempfile
        from src.runtime.state_store import StateStore
        with tempfile.TemporaryDirectory() as d:
            path = d + '/state.json'
            store = W.StateStoreJournal(StateStore(path))
            r = FakeRouter()
            W.run(wf(step('device_facts', id='a')), r, store,
                  workflow_id='wf-1')
            reloaded = W.StateStoreJournal(StateStore(path)).get('wf-1')
            self.assertEqual(reloaded['status'], 'done')
            self.assertEqual(reloaded['steps'][0]['receipt']['skill_id'],
                             'device_facts')


if __name__ == '__main__':
    unittest.main()
