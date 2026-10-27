"""V4-12 inference scheduler (SIMULATED_VERIFIED: fake /api/tags; no second PC in CI)."""
import json
import tempfile
import unittest
from pathlib import Path

from src.ai import scheduler as s
from src.ai.glimmer import GLIMMER_ID, GLIMMER_DIGEST


def tags(ok=True):
    return lambda ep: {'models': [{'name': GLIMMER_ID, 'digest': 'sha256:' + (GLIMMER_DIGEST if ok else '0' * 64)}]}


class Scheduler(unittest.TestCase):
    def workers(self, lan_ok=True, local_ok=True, lan_tps=30.0, local_tps=4.0):
        local = s.Worker('http://127.0.0.1:11438', GLIMMER_ID, 'local'); local.probe(tags(local_ok)); local.tokens_per_s = local_tps
        lan = s.Worker('http://192.168.1.20:11438', GLIMMER_ID, 'lan', 'PC 2'); lan.probe(tags(lan_ok)); lan.tokens_per_s = lan_tps
        return [local, lan]

    def test_faster_lan_worker_for_redacted_data(self):
        w, why = s.choose(self.workers(), GLIMMER_ID, 'redacted')
        self.assertEqual(w.label, 'PC 2')
        self.assertEqual(why['candidates'][0]['cost_usd'], 0.0)

    def test_raw_data_never_leaves_this_pc(self):
        w, why = s.choose(self.workers(), GLIMMER_ID, 'raw')
        self.assertEqual(w.kind, 'local')
        self.assertIn('never leaves', [c['why'] for c in why['candidates'] if c['kind'] == 'lan'][0])
        with self.assertRaises(s.SchedulerBlocked):
            s.choose(self.workers(local_ok=False), GLIMMER_ID, 'raw')

    def test_digest_mismatch_excluded(self):
        w, _ = s.choose(self.workers(lan_ok=False), GLIMMER_ID, 'redacted')
        self.assertEqual(w.kind, 'local')

    def test_endpoint_rules(self):
        for ep, kind in (('http://8.8.8.8:11438', 'lan'), ('http://127.0.0.1:11438', 'lan'), ('http://192.168.1.2:1', 'local'),
                         ('https://192.168.1.2:1', 'lan'), ('http://192.168.1.2:1/api/chat', 'lan'), ('http://169.254.1.1:1', 'lan')):
            with self.subTest(ep=ep), self.assertRaises(s.SchedulerBlocked):
                s.Worker(ep, GLIMMER_ID, kind)
        with self.assertRaises(s.SchedulerBlocked):
            s.Worker('http://192.168.1.2:1', 'gpt-x', 'lan')

    def test_owner_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'workers.json'
            p.write_text(json.dumps({'workers': [{'endpoint': 'http://192.168.1.20:11438', 'model_id': GLIMMER_ID},
                                                 {'endpoint': 'http://1.1.1.1:1', 'model_id': GLIMMER_ID}]}))
            ws = s.owner_workers(p)
            self.assertEqual([w.endpoint for w in ws], ['http://192.168.1.20:11438'])
            self.assertEqual(s.owner_workers(Path(d) / 'none.json'), [])


if __name__ == '__main__':
    unittest.main()
