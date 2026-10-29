"""S3 plan objects (offline): DAG validation, consent gates, partial states."""
import unittest

from src.forge import v4_plan as P

CAPS = {'tv1': {'vacuum.dock', 'tv shot'},
        'watch1': {'notify.show'}}
READS = {'tv shot'}


def plan(steps):
    return {'plan_id': 'pl-test', 'goal': 'demo', 'steps': steps}


class Validate(unittest.TestCase):
    def test_valid_two_device_plan(self):
        steps = [{'step_id': 's1', 'primitive': 'tv shot', 'target': 'tv1',
                  'needs_consent': False, 'depends_on': [],
                  'verify': {'kind': 'artifact', 'expect': 'png'}},
                 {'step_id': 's2', 'primitive': 'notify.show', 'target': 'watch1',
                  'needs_consent': True, 'depends_on': ['s1'],
                  'verify': {'kind': 'receipt', 'expect': 'ok'}}]
        out = P.validate_plan(plan(steps), CAPS, READS)
        self.assertEqual([s['step_id'] for s in out['order']], ['s1', 's2'])

    def test_unknown_target_refused(self):
        steps = [{'step_id': 's1', 'primitive': 'tv shot', 'target': 'ghost',
                  'needs_consent': False, 'depends_on': [],
                  'verify': {'kind': 'artifact', 'expect': 'png'}}]
        with self.assertRaises(P.PlanError) as cm:
            P.validate_plan(plan(steps), CAPS, READS)
        self.assertIn('UNKNOWN_TARGET', str(cm.exception))

    def test_capability_gap_refused(self):
        steps = [{'step_id': 's1', 'primitive': 'vacuum.dock', 'target': 'watch1',
                  'needs_consent': True, 'depends_on': [],
                  'verify': {'kind': 'receipt', 'expect': 'ok'}}]
        with self.assertRaises(P.PlanError) as cm:
            P.validate_plan(plan(steps), CAPS, READS)
        self.assertIn('CAPABILITY_GAP', str(cm.exception))

    def test_effect_without_consent_refused(self):
        steps = [{'step_id': 's1', 'primitive': 'notify.show', 'target': 'watch1',
                  'needs_consent': False, 'depends_on': [],
                  'verify': {'kind': 'receipt', 'expect': 'ok'}}]
        with self.assertRaises(P.PlanError) as cm:
            P.validate_plan(plan(steps), CAPS, READS)
        self.assertIn('CONSENT_REQUIRED', str(cm.exception))

    def test_cycle_refused(self):
        mk = lambda i, deps: {'step_id': i, 'primitive': 'tv shot', 'target': 'tv1',
                              'needs_consent': False, 'depends_on': deps,
                              'verify': {'kind': 'artifact', 'expect': 'png'}}
        with self.assertRaises(P.PlanError) as cm:
            P.validate_plan(plan([mk('s1', ['s2']), mk('s2', ['s1'])]), CAPS, READS)
        self.assertIn('CYCLE', str(cm.exception))

    def test_missing_verify_hook_refused(self):
        nodict = [{'step_id': 's1', 'primitive': 'tv shot', 'target': 'tv1',
                   'needs_consent': False, 'depends_on': []}]
        with self.assertRaises(P.PlanError) as cm:
            P.validate_plan(plan(nodict), CAPS, READS)
        self.assertIn('STEP_MISSING_VERIFY', str(cm.exception))
        badkind = [{'step_id': 's1', 'primitive': 'tv shot', 'target': 'tv1',
                    'needs_consent': False, 'depends_on': [],
                    'verify': {'kind': 'vibes', 'expect': 'x'}}]
        with self.assertRaises(P.PlanError) as cm:
            P.validate_plan(plan(badkind), CAPS, READS)
        self.assertIn('VERIFY_REQUIRED', str(cm.exception))


class Summarize(unittest.TestCase):
    def test_partial_success_report(self):
        steps = [{'step_id': 's1'}, {'step_id': 's2'}, {'step_id': 's3'}]
        receipts = {'s1': {'status': 'ok'}, 's2': {'status': 'failed', 'error': 'timeout'}}
        rep = P.summarize(plan(steps), receipts)
        self.assertEqual(rep['states'], {'s1': 'ok', 's2': 'failed', 's3': 'pending'})
        self.assertEqual(rep['overall'], 'partial')


if __name__ == '__main__':
    unittest.main()
