"""S3b obv4.1-wf emitter: my plan objects -> Claude's workflow schema.

Contract test: every emitted doc must pass substrate validate_workflow.
A step without a compiled+approved manifest hash is refused (never invented).
"""
import unittest

from src.forge import v4_plan as P
from src.substrate import workflow as W

CAPS = {'tv1': {'tv shot'}, 'watch1': {'notify.show'}}
READS = {'tv shot'}
MH = 'sha256:' + 'ab' * 32

PLAN = {'plan_id': 'pl-1', 'goal': 'shot then notify', 'steps': [
    {'step_id': 's1', 'primitive': 'tv shot', 'target': 'tv1',
     'needs_consent': False, 'depends_on': [],
     'verify': {'kind': 'artifact', 'expect': 'png'}},
    {'step_id': 's2', 'primitive': 'notify.show', 'target': 'watch1',
     'needs_consent': True, 'depends_on': ['s1'],
     'verify': {'kind': 'receipt', 'expect': 'ok'}}]}


class Emit(unittest.TestCase):
    def test_emitted_doc_passes_substrate_validator(self):
        P.validate_plan(PLAN, CAPS, READS)
        wf = P.emit_workflow(PLAN, {'s1': MH, 's2': MH},
                             {'provider': 'meta', 'model': 'muse-spark-1.3', 'run_id': 'mr-test'},
                             title='shot then notify', max_parallel=2)
        order = W.validate_workflow(wf)
        self.assertEqual([n['node_id'] for n in order], ['s1', 's2'])
        self.assertEqual(wf['workflow_version'], 'obv4.1-wf')

    def test_missing_manifest_hash_refused(self):
        with self.assertRaises(P.PlanError) as cm:
            P.emit_workflow(PLAN, {'s1': MH},
                            {'provider': 'meta', 'model': 'm', 'run_id': 'r'})
        self.assertIn('MANIFEST_REQUIRED', str(cm.exception))

    def test_non_meta_model_run_refused(self):
        with self.assertRaises(P.PlanError) as cm:
            P.emit_workflow(PLAN, {'s1': MH, 's2': MH},
                            {'provider': 'other', 'model': 'm', 'run_id': 'r'})
        self.assertIn('META_RUN_REQUIRED', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
