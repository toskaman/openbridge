"""Multi-device workflows over the trust kernel (SIMULATED_VERIFIED: real registry, kernel and Executor; fake device
runners). Each test names the property it protects."""
import threading
import time
import unittest

from src.runtime.api_v2 import executor
from src.runtime.primitives import Executor
from src.substrate.kernel import SubstrateError, manifest_hash
from src.substrate.workflow import Workflows, node_operation_id, validate_workflow
from tests.substrate.test_kernel import Base


class Workflow(Base):
    def setUp(self):
        super().setUp()
        self.fail_keys, self.order, self.slow = set(), [], {}
        lock = threading.Lock()
        def runner(_self, key, params):
            if self.slow.get(key):
                time.sleep(self.slow[key])
            with lock:
                self.calls.append(('device_action', key, params)); self.order.append(key)
            if 'RAISE' in self.fail_keys:
                raise OSError('link lost')
            if key in self.fail_keys:
                return 'FAILED', None, None, False, {}
            return 'VERIFIED', None, None, True, {}
        ex = executor(self.server)
        ex.RUNNERS = dict(Executor.RUNNERS, device_action=runner, read_facts=runner)
        self.ph_fp = self.s.fingerprint(self.ph)
        self.ph_facts = self.s.facts(self.ph)
        self.wf = Workflows(self.s)

    def tv_m(self, key='mute', title='Mute the TV'):
        return self.manifest(title=title, steps=[{'step_id': 'k', 'primitive_id': 'input.key', 'args': {'key': key}, 'on_uncertain': 'INCONCLUSIVE'}])

    def ph_m(self, title='Phone home'):
        cat = next(f for f in self.ph_facts if f['name'] == 'category')
        return self.manifest(title=title, target={'device_fingerprint': self.ph_fp, 'category': 'phone'},
                             facts_required=[cat['fact_id']], evidence_refs=[cat['fact_id']],
                             steps=[{'step_id': 'k', 'primitive_id': 'input.key', 'args': {'key': 'home'}, 'on_uncertain': 'INCONCLUSIVE'}])

    def bind(self, *pairs):
        out = {}
        for m, facts in pairs:
            g, _ = self.s.issue_grant(m, facts, True)
            out[manifest_hash(m)] = {'manifest': m, 'grant': g, 'facts': facts}
        return out

    def workflow(self, nodes, max_parallel=2):
        return {'workflow_version': 'obv4.1-wf', 'workflow_id': 'wf.test', 'title': 'Test workflow', 'origin': 'meta_generated',
                'model_run': {'provider': 'meta', 'model': 'muse-spark-1.3', 'run_id': 'run_0003wf'}, 'nodes': nodes,
                'max_parallel': max_parallel}

    def node(self, nid, m, deps=()):
        return {'node_id': nid, 'manifest_hash': manifest_hash(m), 'depends_on': list(deps)}

    def run_wf(self, wf, b, op='a' * 32, cancel=None):
        g = self.wf.issue_grant(wf, b, True)
        return self.wf.run(wf, g, b, 'op-' + op, cancel=cancel)

    def test_cross_device_dag_completes_in_dependency_order(self):
        tv, ph = self.tv_m(), self.ph_m()
        b = self.bind((tv, self.facts), (ph, self.ph_facts))
        rec = self.run_wf(self.workflow([self.node('tv', tv), self.node('phone', ph, ['tv'])]), b)
        self.assertEqual(rec['status'], 'COMPLETED')
        self.assertEqual([n['status'] for n in rec['nodes']], ['VERIFIED', 'VERIFIED'])
        self.assertEqual(len(self.order), 2)
        self.assertTrue(self.wf.verify_receipt(rec))
        self.assertTrue(all(n['receipt_signature'] for n in rec['nodes']))

    def test_failure_skips_dependents_only_and_never_retries(self):
        tv, ph, tv2 = self.tv_m(), self.ph_m(), self.tv_m('volume_up', 'TV louder')
        b = self.bind((tv, self.facts), (ph, self.ph_facts), (tv2, self.facts))
        self.fail_keys = {self.ph}
        wf = self.workflow([self.node('phone', ph), self.node('tv_after_phone', tv, ['phone']), self.node('tv_independent', tv2)])
        rec = self.run_wf(wf, b)
        st = {n['node_id']: n['status'] for n in rec['nodes']}
        self.assertIn(st['phone'], ('FAILED', 'INCONCLUSIVE'))             # kernel: on_uncertain=INCONCLUSIVE
        self.assertEqual(st['tv_after_phone'], 'SKIPPED')
        self.assertEqual(st['tv_independent'], 'VERIFIED')
        self.assertEqual(rec['status'], 'PARTIAL')
        self.assertEqual(self.order.count(self.ph), 1)                      # no retry

    def test_unknown_outcome_is_inconclusive_and_blocks_dependents(self):
        tv, ph = self.tv_m(), self.ph_m()
        b = self.bind((tv, self.facts), (ph, self.ph_facts))
        self.fail_keys = {'RAISE'}
        rec = self.run_wf(self.workflow([self.node('tv', tv), self.node('phone', ph, ['tv'])]), b)
        self.assertEqual([n['status'] for n in rec['nodes']], ['INCONCLUSIVE', 'SKIPPED'])
        self.assertEqual(len(self.order), 1)

    def test_independent_nodes_run_in_parallel_within_the_bound(self):
        tv, ph = self.tv_m(), self.ph_m()
        b = self.bind((tv, self.facts), (ph, self.ph_facts))
        self.slow = {self.tv: 0.4, self.ph: 0.4}
        t0 = time.monotonic()
        rec = self.run_wf(self.workflow([self.node('tv', tv), self.node('phone', ph)], max_parallel=2), b)
        self.assertEqual(rec['status'], 'COMPLETED')
        self.assertLess(time.monotonic() - t0, 0.75)                        # two 0.4 s steps overlapped

    def test_owner_signs_the_exact_workflow(self):
        tv, ph = self.tv_m(), self.ph_m()
        b = self.bind((tv, self.facts), (ph, self.ph_facts))
        wf = self.workflow([self.node('tv', tv), self.node('phone', ph, ['tv'])])
        g = self.wf.issue_grant(wf, b, True)
        reordered = self.workflow([self.node('phone', ph), self.node('tv', tv, ['phone'])])
        self.rejects('WGRANT_OTHER_WORKFLOW', self.wf.run, reordered, g, b, 'op-' + 'b' * 32)
        self.rejects('WGRANT_FORGED', self.wf.run, wf, dict(g, signature='0' * 64), b, 'op-' + 'c' * 32)
        self.rejects('CONSENT_REQUIRED', self.wf.issue_grant, wf, b, False)
        g2 = self.wf.issue_grant(wf, b, True); self.wf.revoke(g2['wgrant_id'])
        self.rejects('WGRANT_REVOKED', self.wf.run, wf, g2, b, 'op-' + 'f' * 32)
        rec = self.wf.run(wf, g, b, 'op-' + 'd' * 32)
        self.assertEqual(rec['status'], 'COMPLETED')
        self.rejects('OPERATION_REPLAY', self.wf.run, wf, g, b, 'op-' + 'd' * 32)
        self.rejects('WGRANT_USED', self.wf.run, wf, g, b, 'op-' + 'e' * 32)
        self.assertEqual(len(self.order), 2)

    def test_revoked_node_grant_stops_everything_before_any_effect(self):
        tv, ph = self.tv_m(), self.ph_m()
        b = self.bind((tv, self.facts), (ph, self.ph_facts))
        wf = self.workflow([self.node('tv', tv), self.node('phone', ph, ['tv'])])
        g = self.wf.issue_grant(wf, b, True)
        self.s.revoke(b[manifest_hash(ph)]['grant']['grant_id'])
        self.rejects('GRANT_REVOKED', self.wf.run, wf, g, b, 'op-' + '1' * 32)
        self.assertEqual(self.order, [])

    def test_cancellation_stops_unstarted_nodes(self):
        tv, ph = self.tv_m(), self.ph_m()
        b = self.bind((tv, self.facts), (ph, self.ph_facts))
        cancel = threading.Event()
        self.slow = {self.tv: 0.3}
        threading.Timer(0.1, cancel.set).start()
        rec = self.run_wf(self.workflow([self.node('tv', tv), self.node('phone', ph, ['tv'])]), b, cancel=cancel)
        self.assertEqual([n['status'] for n in rec['nodes']], ['VERIFIED', 'CANCELLED'])
        self.assertEqual(rec['status'], 'CANCELLED')
        self.assertNotIn(self.ph, self.order)

    def test_static_validation(self):
        tv = self.tv_m()
        n = self.node('a', tv)
        for nodes in ([dict(n, depends_on=['a'])], [n, dict(n)], [dict(n, depends_on=['zz'])],
                      [dict(n, node_id='a', depends_on=['b']), dict(n, node_id='b', depends_on=['a'])], []):
            with self.assertRaises(SubstrateError):
                validate_workflow(self.workflow(nodes))
        with self.assertRaises(SubstrateError):
            validate_workflow(dict(self.workflow([n]), origin='owner'))
        with self.assertRaises(SubstrateError):
            validate_workflow(self.workflow([n], max_parallel=9))

    def test_node_operation_ids_are_deterministic_and_valid(self):
        a, b = node_operation_id('op-' + 'a' * 32, 'tv'), node_operation_id('op-' + 'a' * 32, 'phone')
        self.assertRegex(a, r'^op-[0-9a-f]{32}$')
        self.assertNotEqual(a, b)
        self.assertEqual(a, node_operation_id('op-' + 'a' * 32, 'tv'))


if __name__ == '__main__':
    unittest.main()


class WorkflowHttp(unittest.TestCase):
    def test_owner_path_needs_csrf_and_rejects_malformed(self):
        import json, tempfile, urllib.error, urllib.request
        from src.fabric.session import SessionJournal
        from src.server import create_server
        s = create_server(0, fabric_salt=b't', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        threading.Thread(target=s.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{s.server_port}'
        try:
            body = json.dumps({'workflow': {}, 'bindings': {}, 'consent': True}).encode()
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(base + '/api/v2/workflows/grant', body, {'Content-Type': 'application/json'}))
            self.assertEqual(e.exception.code, 403); e.exception.close()
            csrf = json.loads(urllib.request.urlopen(base + '/api/session').read())['csrf_token']
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(base + '/api/v2/workflows/grant', body,
                                                              {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Origin': base}))
            self.assertEqual(e.exception.code, 400)
            self.assertEqual(json.loads(e.exception.read())['code'], 'WORKFLOW_SCHEMA'); e.exception.close()
            self.assertEqual(json.loads(urllib.request.urlopen(base + '/api/v2/workflows/receipts').read()), {'receipts': []})
        finally:
            s.shutdown(); s.server_close()
