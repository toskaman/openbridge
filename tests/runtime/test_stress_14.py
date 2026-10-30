"""§14 stress: concurrency and storage limits for §7 paths (all fakes/tmp)."""
import json
import threading
import time
import unittest
from pathlib import Path
import tempfile

from src.runtime import capture_store as C
from src.runtime import workflows as W


class FakeRouter:
    def __init__(self, delay=0.05):
        self.delay = delay
        self.dispatches = []
        self._lock = threading.Lock()

    def skill_routes(self, skill_id, target=None):
        return {'skill_id': skill_id, 'selected_route_id': 'rt-x', 'routes': []}

    def arm(self, body, actor='owner', invocation_id=None):
        return {'invocation_id': invocation_id or 'inv-x', 'lease_id': 'ls-x',
                'route_id': 'rt-x', 'graph_revision': 'g1',
                'lease_expires_at': 't', 'lease_expires_in_s': 30}

    def invoke(self, body, actor='owner'):
        time.sleep(self.delay)
        with self._lock:
            self.dispatches.append(body['invocation_id'])
        return {'state': 'EXECUTED', 'result': {'ok': True},
                'invocation_id': body['invocation_id'], 'route_id': 'rt-x',
                'skill_id': body['skill_id']}


class WorkflowConcurrency(unittest.TestCase):
    def test_concurrent_same_id_dispatches_once(self):
        r = FakeRouter()
        store = W.MemoryStore()
        body = {'consent': True, 'steps': [
            {'id': 'a', 'skill_id': 'device_facts', 'target': 'dev', 'params': {}},
            {'id': 'b', 'skill_id': 'device_facts', 'target': 'dev', 'params': {},
             'needs': ['a']}]}
        recs = []
        ts = [threading.Thread(target=lambda: recs.append(
            W.run(body, r, store, 'wf-race'))) for _ in range(2)]
        [t.start() for t in ts]
        [t.join(timeout=30) for t in ts]
        self.assertEqual(len(r.dispatches), 2)
        self.assertTrue(all(x['status'] == 'done' for x in recs))

    def test_concurrent_approve_dispatches_once(self):
        r = FakeRouter(delay=0.1)
        store = W.MemoryStore()
        body = {'consent': True, 'steps': [
            {'id': 'a', 'skill_id': 'device_facts', 'target': 'dev', 'params': {},
             'approval': True}]}
        W.run(body, r, store, 'wf-appr')
        outs = []
        ts = [threading.Thread(target=lambda: outs.append(self._try_approve(r, store)))
              for _ in range(2)]
        [t.start() for t in ts]
        [t.join(timeout=30) for t in ts]
        self.assertEqual(sorted(outs), ['denied-race', 'done'])
        self.assertEqual(len(r.dispatches), 1)

    @staticmethod
    def _try_approve(r, store):
        try:
            rec = W.approve('wf-appr', 'a', True, r, store)
            return rec['status']
        except W.WorkflowError:
            return 'denied-race'


class StoreConcurrency(unittest.TestCase):
    def test_parallel_puts_keep_index_complete(self):
        with tempfile.TemporaryDirectory() as d:
            cids, lock = [], threading.Lock()

            def worker(n):
                s = C.CaptureStore(d, max_files=1000)
                for i in range(20):
                    cid = s.put(bytes([n, i]) * 16, kind='cap')
                    with lock:
                        cids.append(cid)

            ts = [threading.Thread(target=worker, args=(n,)) for n in range(16)]
            [t.start() for t in ts]
            [t.join(timeout=60) for t in ts]
            idx = json.loads((Path(d) / 'index.json').read_text(encoding='utf-8'))
            self.assertEqual(len(cids), 320)
            for cid in cids:
                self.assertIn(cid, idx)
                self.assertEqual(len(C.CaptureStore(d).get(cid)), 32)


class StoreLimits(unittest.TestCase):
    def test_total_bytes_cap_evicts_oldest(self):
        with tempfile.TemporaryDirectory() as d:
            s = C.CaptureStore(d, max_files=64, max_bytes=100)
            a = s.put(b'a' * 40, kind='cap')
            b = s.put(b'b' * 40, kind='cap')
            c = s.put(b'c' * 40, kind='cap')
            with self.assertRaises(C.StoreError):
                s.get(a)
            self.assertEqual(s.get(b), b'b' * 40)
            self.assertEqual(s.get(c), b'c' * 40)

    def test_single_file_bigger_than_cap_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            s = C.CaptureStore(d, max_files=64, max_bytes=100)
            with self.assertRaises(C.StoreError):
                s.put(b'x' * 101, kind='cap')

    def test_os_errors_surface_as_store_errors(self):
        with tempfile.TemporaryDirectory() as d:
            s = C.CaptureStore(d)
            cid = s.put(b'data', kind='cap')
            real_rb = Path.read_bytes
            Path.read_bytes = lambda self: (_ for _ in ()).throw(OSError('disk gone'))
            try:
                with self.assertRaises(C.StoreError):
                    s.get(cid)
            finally:
                Path.read_bytes = real_rb
            real_wb = Path.write_bytes
            Path.write_bytes = lambda self, data: (_ for _ in ()).throw(OSError('disk full'))
            try:
                with self.assertRaises(C.StoreError):
                    s.put(b'data', kind='cap')
            finally:
                Path.write_bytes = real_wb


if __name__ == '__main__':
    unittest.main()
