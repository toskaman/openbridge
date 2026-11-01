"""E1 robustness (A4): composer evidence/TTL/idempotency + router errors.

- to_workflow embeds per-step route evidence, composed_at/expires_at and a
  deterministic idempotency key;
- the DAG engine refuses expired compositions and drifted routes at dispatch
  (re-resolve immediately before dispatch) and carries the key into receipts;
- only the router's declared RouteError becomes a refusal; anything else
  (TypeError/AttributeError from drift or bad doubles) must raise.
"""
import time
import unittest

from src.runtime import composer as C
from src.runtime import workflows as W
from src.runtime.routing import RouteError
from tests.runtime.test_composer import DEVICES, REPLY, FakeRoutes
from tests.runtime.test_workflows import FakeRouter


class EvidenceBody(unittest.TestCase):
    def test_route_evidence_ttl_and_idempotency_keys(self):
        doc = C.compose(C.proposal_from_reply(REPLY), DEVICES, FakeRoutes())
        body = C.to_workflow(doc, now=1000.0)
        self.assertEqual((body['composed_at'], body['expires_at']), (1000.0, 1300.0))
        keys = set()
        for s in body['steps']:
            self.assertEqual(s['route_id'], 'rt-x')
            self.assertEqual(s['route_evidence'], 'REAL_HARDWARE')
            self.assertEqual(s['selection_rule'], 'auto_score')
            self.assertEqual((s['composed_at'], s['expires_at']), (1000.0, 1300.0))
            self.assertTrue(s['idempotency_key'].startswith('idem-'))
            keys.add(s['idempotency_key'])
        self.assertEqual(len(keys), 2)
        again = C.to_workflow(doc, now=1000.0)
        self.assertEqual([s['idempotency_key'] for s in again['steps']],
                         [s['idempotency_key'] for s in body['steps']])

    def test_validate_rejects_malformed_evidence(self):
        bad = {'consent': True, 'steps': [
            {'id': 'a', 'skill_id': 'device_facts', 'target': 'dev-a',
             'params': {}, 'route_id': 123}]}
        with self.assertRaises(W.WorkflowError):
            W.validate_workflow(bad)
        bad['steps'][0] = {'id': 'a', 'skill_id': 'device_facts', 'target': 'dev-a',
                           'params': {}, 'expires_at': 'soon'}
        with self.assertRaises(W.WorkflowError):
            W.validate_workflow(bad)


class RouterErrors(unittest.TestCase):
    def test_infrastructure_errors_raise_never_refuse(self):
        prop = C.proposal_from_reply(REPLY)
        with self.assertRaises(TypeError):
            C.compose(prop, DEVICES, FakeRoutes(error=TypeError('schema drift')))
        with self.assertRaises(AttributeError):
            C.compose(prop, DEVICES, FakeRoutes(error=AttributeError('bad mock')))

    def test_declared_route_errors_still_refuse(self):
        prop = C.proposal_from_reply(REPLY)
        doc = C.compose(prop, DEVICES, FakeRoutes(error=RouteError(500, 'X', 'boom')))
        self.assertEqual(doc['allowed'], 0)
        self.assertIn('no permitted route', doc['steps'][0]['reason'])


class ReadyRouter(FakeRouter):
    """Route truth that keeps (or drops) the composed route at dispatch."""

    def __init__(self, ready=True, **kw):
        super().__init__(**kw)
        self.ready = ready

    def skill_routes(self, skill_id, target=None):
        if self.ready:
            return {'skill_id': skill_id, 'selected_route_id': 'rt-x',
                    'routes': [{'route_id': 'rt-x', 'state': 'READY'}]}
        return {'skill_id': skill_id, 'selected_route_id': None,
                'routes': [{'route_id': 'rt-x', 'state': 'UNAVAILABLE',
                            'reason': 'revoked'}]}


class EngineEnforcement(unittest.TestCase):
    def _body(self, now):
        doc = C.compose(C.proposal_from_reply(REPLY), DEVICES, FakeRoutes())
        return C.to_workflow(doc, now=now)

    def _run_with_approvals(self, body, router, wf):
        store = W.MemoryStore()
        rec = W.run(body, router, store, workflow_id=wf)
        for s in body['steps']:
            st = next(x for x in rec['steps'] if x['id'] == s['id'])
            if st['state'] == 'WAITING':
                rec = W.approve(wf, s['id'], True, router, store)
        return rec

    def test_expired_composition_refuses_without_dispatch(self):
        router = ReadyRouter(results={'tv_volume_step': {'state': 'VERIFIED', 'verified': True},
                                      'vacuum_command': {'state': 'VERIFIED', 'verified': True}})
        rec = self._run_with_approvals(self._body(now=1000.0), router, 'wf-exp')
        self.assertEqual(router.dispatches, [])
        for s in rec['steps']:
            self.assertEqual(s['receipt']['state'], 'BLOCKED')
            self.assertIn('expired', ';'.join(s['receipt']['errors']))
            outcome, _ = C.outcome_of(s['state'], s['receipt'])
            self.assertEqual(outcome, 'REFUSED')

    def test_drifted_route_refuses_without_dispatch(self):
        router = ReadyRouter(ready=False)
        rec = self._run_with_approvals(self._body(now=time.time()), router, 'wf-drift')
        self.assertEqual(router.dispatches, [])
        for s in rec['steps']:
            self.assertEqual(s['receipt']['state'], 'BLOCKED')
            self.assertIn('drift', ';'.join(s['receipt']['errors']))

    def test_fresh_ready_route_dispatches_with_idempotency_keys(self):
        router = ReadyRouter()
        body = self._body(now=time.time())
        rec = self._run_with_approvals(body, router, 'wf-ok')
        self.assertEqual(len(router.dispatches), 2)
        want = {s['id']: s['idempotency_key'] for s in body['steps']}
        for s in rec['steps']:
            self.assertEqual(s['receipt'].get('idempotency_key'), want[s['id']])

    def test_hand_built_bodies_without_evidence_still_run(self):
        router = ReadyRouter()
        rec = W.run({'consent': True, 'steps': [
            {'id': 'a', 'skill_id': 'device_facts', 'target': 'dev-a', 'params': {}}]},
            router, W.MemoryStore(), workflow_id='wf-plain')
        self.assertEqual(len(router.dispatches), 1)
        self.assertEqual(rec['status'], 'done')


if __name__ == '__main__':
    unittest.main()
