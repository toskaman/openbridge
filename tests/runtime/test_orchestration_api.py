"""§7 orchestration API (SIMULATED_VERIFIED: synthetic registry, fake runners)."""
import tempfile
import unittest

from tests.runtime.test_routing import Clock, world
from src.runtime.api_v2 import executor, get, post
from src.runtime.primitives import Executor


class OrchestrationApi(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        ex = executor(self.server)

        def fake(result):
            def run(self_, key, params):
                return 'EXECUTED', None, 'ok', True, dict(result)
            return run

        ex.RUNNERS = dict(Executor.RUNNERS, read_facts=fake({'facts': 1}))
        self.tmp = tempfile.mkdtemp()
        from src.fabric.session import SessionJournal
        self.server.session_journal = SessionJournal(self.tmp + '/s.json')

    def test_run_happy_path(self):
        code, rec = post(self.server, '/api/v2/orchestration/run',
                         {'consent': True,
                          'steps': [{'id': 'a', 'skill_id': 'device_facts',
                                     'target': self.keys['phone'], 'params': {}}]})
        self.assertEqual(code, 200)
        self.assertEqual(rec['status'], 'done')
        self.assertTrue(rec['workflow_id'].startswith('wf-'))
        self.assertEqual(rec['steps'][0]['state'], 'EXECUTED')

    def test_run_needs_consent(self):
        code, body = post(self.server, '/api/v2/orchestration/run',
                          {'consent': False, 'steps': []})
        self.assertEqual(code, 400)

    def test_run_rejects_bad_dag(self):
        code, body = post(self.server, '/api/v2/orchestration/run',
                          {'consent': True,
                           'steps': [{'id': 'a', 'skill_id': 'device_facts',
                                      'target': self.keys['phone'], 'params': {},
                                      'needs': ['a']}]})
        self.assertEqual(code, 400)

    def test_status_round_trip_and_unknown(self):
        _, rec = post(self.server, '/api/v2/orchestration/run',
                      {'consent': True, 'workflow_id': 'wf-status1',
                       'steps': [{'id': 'a', 'skill_id': 'device_facts',
                                  'target': self.keys['phone'], 'params': {}}]})
        code, got = get(self.server, '/api/v2/orchestration/status',
                        'workflow_id=wf-status1')
        self.assertEqual(code, 200)
        self.assertEqual(got['status'], 'done')
        code, _ = get(self.server, '/api/v2/orchestration/status',
                      'workflow_id=wf-nope')
        self.assertEqual(code, 404)

    def test_approve_flow(self):
        _, rec = post(self.server, '/api/v2/orchestration/run',
                      {'consent': True,
                       'steps': [{'id': 'a', 'skill_id': 'device_facts',
                                  'target': self.keys['phone'], 'params': {},
                                  'approval': True}]})
        self.assertEqual(rec['status'], 'waiting_approval')
        code, rec = post(self.server, '/api/v2/orchestration/approve',
                         {'workflow_id': rec['workflow_id'], 'step_id': 'a',
                          'consent': True})
        self.assertEqual(code, 200)
        self.assertEqual(rec['status'], 'done')

    def test_cancel_flow(self):
        _, rec = post(self.server, '/api/v2/orchestration/run',
                      {'consent': True,
                       'steps': [{'id': 'a', 'skill_id': 'device_facts',
                                  'target': self.keys['phone'], 'params': {},
                                  'approval': True}]})
        code, rec = post(self.server, '/api/v2/orchestration/cancel',
                         {'workflow_id': rec['workflow_id']})
        self.assertEqual(code, 200)
        self.assertEqual(rec['status'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
