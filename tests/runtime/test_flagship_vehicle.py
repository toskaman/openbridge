"""Flagship-C O3 vehicle logic over doubles (no hardware, no server)."""
import json
import unittest
from types import SimpleNamespace

from dev.flagship_c_vehicle import run_vehicle


def make_io(script):
    """script: list per round of dicts(v0, v1, exec_count, post_revoke_exec)."""
    state = {'round': -1}

    def install(controls):
        return ['ctl-%d' % i for i in range(len(controls))]

    def await_press(control_id, timeout_s):
        return 'req-r%d' % state['round']

    def read_volume():
        r = script[state['round']]
        key = 'reads'
        r[key] = r.get(key, 0) + 1
        return r['v0'] if r[key] == 1 else r['v1']

    def journal_count(request_id):
        return script[state['round']]['exec_count']

    def revoke():
        pass

    def post_revoke_probe(control_id):
        return script[state['round']]['post_revoke_exec']

    return SimpleNamespace(install=install, await_press=await_press,
                           read_volume=read_volume,
                           journal_count=journal_count, revoke=revoke,
                           post_revoke_probe=post_revoke_probe,
                           prompt=lambda text: None, state=state)


class VehicleTest(unittest.TestCase):
    def test_two_perfect_rounds_pass(self):
        script = [{'v0': 10, 'v1': 11, 'exec_count': 1, 'post_revoke_exec': 0},
                  {'v0': 11, 'v1': 12, 'exec_count': 1, 'post_revoke_exec': 0}]
        receipt = run_vehicle(make_io(script), rounds=2)
        self.assertEqual(receipt['verdict'], 'PASS')
        self.assertEqual([r['verdict'] for r in receipt['rounds']],
                         ['PASS', 'PASS'])
        self.assertEqual(receipt['rounds'][0]['delta'], 1)

    def test_unchanged_volume_fails_the_round(self):
        script = [{'v0': 10, 'v1': 10, 'exec_count': 1, 'post_revoke_exec': 0}]
        receipt = run_vehicle(make_io(script), rounds=1)
        self.assertEqual(receipt['verdict'], 'FAIL')
        self.assertIn('no volume change', receipt['rounds'][0]['reason'])

    def test_post_revoke_execution_fails_the_round(self):
        script = [{'v0': 10, 'v1': 11, 'exec_count': 1, 'post_revoke_exec': 1}]
        receipt = run_vehicle(make_io(script), rounds=1)
        self.assertEqual(receipt['verdict'], 'FAIL')
        self.assertIn('post-revoke', receipt['rounds'][0]['reason'])

    def test_duplicate_execution_fails_the_round(self):
        script = [{'v0': 10, 'v1': 11, 'exec_count': 2, 'post_revoke_exec': 0}]
        receipt = run_vehicle(make_io(script), rounds=1)
        self.assertEqual(receipt['verdict'], 'FAIL')
        self.assertIn('exactly-one', receipt['rounds'][0]['reason'])

    def test_receipt_is_json_sanitized(self):
        script = [{'v0': 10, 'v1': 11, 'exec_count': 1, 'post_revoke_exec': 0}]
        receipt = run_vehicle(make_io(script), rounds=1)
        text = json.dumps(receipt)
        self.assertNotIn('654321', text)
        self.assertIn('vehicle', receipt)


if __name__ == '__main__':
    unittest.main()
