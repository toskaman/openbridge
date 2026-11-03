"""NIGHTFALL R-1 regression: cross-process double-approve (F-14).

Without an atomic approval transition, two approvers both drive the same
waiting step: each dispatches under the same deterministic invocation id,
the loser hits DUPLICATE_REQUEST, and the loser's FAILED save can land
first -- pinning stored 'failed' over a step that actually executed
(observed deterministically with a barrier: outcomes failed|done,
stored failed, 1 dispatch).

The fix: store.claim_approval() transitions WAITING->approved/running
atomically (mirrors claim_running). Exactly one approver drives; the
loser gets the stored terminal record (if the winner finished) or a
loud WorkflowError (if the winner is mid-drive). Dispatches stay 1 and
the stored record always matches the executed truth.

Safety: SIMULATED only (fake read_facts; temp journals; never live).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

SEED = 20261102

WORKER = '''
import json, os, sys, time, uuid
def main():
    with open(sys.argv[1], encoding='utf-8') as f:
        args = json.load(f)
    sys.path.insert(0, args['root'])
    _ctr = [0]
    def _det():
        _ctr[0] += 1
        return uuid.UUID(hex='%012x' % _ctr[0] + '0' * 20)
    uuid.uuid4 = _det
    t0 = time.time()
    while not os.path.exists(args['gate']):
        if time.time() - t0 > 60:
            raise RuntimeError('gate timeout')
        time.sleep(0.005)
    shared = os.path.realpath(args['shared'])
    tmp = os.path.realpath(args['tmpdir'])
    assert os.path.commonpath([shared, tmp]) == tmp, 'shared outside tmpdir'
    assert 'OpenBridge' not in shared, 'live state touched'
    from tests.runtime.test_routing import world, Clock
    from src.fabric.session import SessionJournal
    from src.runtime import workflows as W
    from src.runtime.api_v2 import executor, router
    from src.runtime.primitives import Executor
    server, keys = world(Clock(1793100000.0))
    server.session_journal = SessionJournal(os.path.join(shared, 's.json'))
    n = [0]
    def fake(self_, key, params):
        n[0] += 1
        time.sleep(0.1)
        return 'VERIFIED', None, {'ok': True}, True, {'ok': True}
    ex = executor(server)
    ex.RUNNERS = dict(Executor.RUNNERS, read_facts=fake)
    rt = router(server)
    from src.runtime.state_store import StateStore
    journal = W.StateStoreJournal(StateStore.for_server(server))
    try:
        rec = W.approve(args['workflow_id'], 's1', True, rt, journal)
        outcome = rec['status']
    except Exception as e:
        outcome = '%s: %s' % (type(e).__name__, str(e)[:100])
    with open(args['result_file'], 'w', encoding='utf-8') as f:
        json.dump({'outcome': outcome, 'dispatches': n[0]}, f)
main()
'''


def _emit(name, value):
    print('NIGHTFALL_COUNT %s=%s' % (name, value), flush=True)


class _DetUuid:
    """Deterministic uuid4 (counter) so worlds built in different processes
    mint identical device keys (mirrors test_nightfall_workflow_races)."""
    def __enter__(self):
        import uuid
        self._real = uuid.uuid4
        self._ctr = [0]

        def _det():
            self._ctr[0] += 1
            return uuid.UUID(hex='%012x' % self._ctr[0] + '0' * 20)
        uuid.uuid4 = _det
        return self

    def __exit__(self, *a):
        import uuid
        uuid.uuid4 = self._real
        return False


def _waiting_record(wid):
    return {'workflow_id': wid, 'status': 'waiting_approval',
            'steps': [{'id': 's1', 'state': 'WAITING'}],
            'spec': {'levels': [], 'steps': {}}}


class ClaimApprovalAtomic(unittest.TestCase):
    def test_memory_store_claim_winner_and_loser(self):
        from src.runtime import workflows as W
        m = W.MemoryStore()
        m.save(_waiting_record('wf-claim-mem'))
        self.assertTrue(m.claim_approval('wf-claim-mem', 's1'))
        rec = m.get('wf-claim-mem')
        self.assertEqual(rec['status'], 'running')
        self.assertEqual(rec['steps'][0]['state'], 'QUEUED')
        self.assertTrue(rec['steps'][0]['approved'])
        self.assertFalse(m.claim_approval('wf-claim-mem', 's1'))
        self.assertFalse(m.claim_approval('wf-claim-mem', 'nope'))
        self.assertFalse(m.claim_approval('wf-missing', 's1'))

    def test_state_store_claim_winner_loser_and_cancel(self):
        from src.fabric.session import SessionJournal
        from src.runtime import workflows as W
        from src.runtime.state_store import StateStore
        d = tempfile.mkdtemp(prefix='r1-claim-')
        try:
            sj = SessionJournal(os.path.join(d, 's.json'))
            j = W.StateStoreJournal(StateStore.for_server(
                SimpleNamespace(session_journal=sj)))
            j.save(_waiting_record('wf-claim-a'))
            j.save(_waiting_record('wf-claim-b'))
            self.assertTrue(j.claim_approval('wf-claim-a', 's1'))
            self.assertFalse(j.claim_approval('wf-claim-a', 's1'))
            rec = j.get('wf-claim-a')
            self.assertEqual(rec['status'], 'running')
            # A cancel racing the approve blocks the claim.
            doomed = _waiting_record('wf-claim-b')
            doomed['cancel_requested'] = True
            j.save(doomed)
            self.assertFalse(j.claim_approval('wf-claim-b', 's1'))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class ForcedOverlap(unittest.TestCase):
    def test_barrier_forced_double_approve_dispatches_once_and_stores_done(self):
        from tests.runtime.test_routing import world, Clock
        from src.fabric.session import SessionJournal
        from src.runtime import workflows as W
        from src.runtime.api_v2 import executor, router
        from src.runtime.primitives import Executor
        from src.runtime.state_store import StateStore
        det = _DetUuid()
        det.__enter__()
        try:
            d = tempfile.mkdtemp(prefix='r1f-')
            try:
                shared = os.path.join(d, 'shared')
                os.mkdir(shared)
                sj_path = os.path.join(shared, 's.json')
                server, keys = world(Clock(1793100000.0))
                server.session_journal = SessionJournal(sj_path)
                ex = executor(server)
                ex.RUNNERS = dict(Executor.RUNNERS, read_facts=lambda s, k, p: ('VERIFIED', None, {'ok': True}, True, {'ok': True}))
                journal = W.StateStoreJournal(StateStore.for_server(server))
                body = {'consent': True, 'steps': [
                    {'id': 's1', 'skill_id': 'device_facts', 'target': keys['tv'],
                     'params': {}, 'approval': True}]}
                rec = W.run(body, router(server), journal, 'wf-r1-forced')
                self.assertEqual(rec['status'], 'waiting_approval')

                def sibling():
                    return SimpleNamespace(
                        fabric_registry=server.fabric_registry,
                        fabric_snapshot=server.fabric_snapshot,
                        relays=server.relays, relay_ledger=server.relay_ledger,
                        session_journal=SessionJournal(sj_path),
                        fabric_salt=server.fabric_salt,
                        runtime_executor=None, skill_router=None)
                n = [0]
                nlock = threading.Lock()
                def fake(self_, key, params):
                    with nlock:
                        n[0] += 1
                    return 'VERIFIED', None, {'ok': True}, True, {'ok': True}
                sides = []
                for _ in range(2):
                    s = sibling()
                    e = executor(s)
                    e.RUNNERS = dict(Executor.RUNNERS, read_facts=fake)
                    sides.append((router(s), W.StateStoreJournal(StateStore.for_server(s))))
                barrier = threading.Barrier(2)
                armed = threading.Event()
                armed.set()
                real_lock = W._lock_for
                real_saves = [j.save for _, j in sides]
                def gated_save(record):
                    if armed.is_set():
                        try:
                            barrier.wait(timeout=5)
                        except threading.BrokenBarrierError:
                            pass
                        armed.clear()
                    return real_saves[0](record)
                for _, j in sides:
                    j.save = gated_save
                W._lock_for = lambda wid: threading.Lock()
                outs = {}
                def one(i):
                    try:
                        r = W.approve('wf-r1-forced', 's1', True, sides[i][0], sides[i][1])
                        outs[i] = r['status']
                    except Exception as e:
                        outs[i] = '%s: %s' % (type(e).__name__, str(e)[:80])
                try:
                    ta = threading.Thread(target=one, args=(0,))
                    tb = threading.Thread(target=one, args=(1,))
                    ta.start(); tb.start(); ta.join(60); tb.join(60)
                finally:
                    for (_, j), rs in zip(sides, real_saves):
                        j.save = rs
                    W._lock_for = real_lock
                _emit('r1f_outcomes', '%s|%s' % (outs[0], outs[1]))
                _emit('r1f_total_dispatches', n[0])
                stored = (journal.get('wf-r1-forced') or {}).get('status')
                _emit('r1f_stored_status', stored)
                self.assertEqual(n[0], 1, 'double-approve must dispatch once, saw %d (%s)' % (n[0], outs))
                self.assertEqual(stored, 'done', 'stored record must match the executed truth, saw %s (%s)' % (stored, outs))
            finally:
                shutil.rmtree(d, ignore_errors=True)
        finally:
            det.__exit__(None, None, None)


class CrossProcessApprove(unittest.TestCase):
    def test_two_processes_approve_once(self):
        from tests.runtime.test_routing import world, Clock
        from src.fabric.session import SessionJournal
        from src.runtime import workflows as W
        from src.runtime.api_v2 import executor, router
        from src.runtime.primitives import Executor
        from src.runtime.state_store import StateStore
        det = _DetUuid()
        det.__enter__()
        try:
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            d = tempfile.mkdtemp(prefix='r1-')
            try:
                shared = os.path.join(d, 'shared')
                os.mkdir(shared)
                server, keys = world(Clock(1793100000.0))
                server.session_journal = SessionJournal(os.path.join(shared, 's.json'))
                ex = executor(server)
                ex.RUNNERS = dict(Executor.RUNNERS, read_facts=lambda s, k, p: ('VERIFIED', None, {'ok': True}, True, {'ok': True}))
                journal = W.StateStoreJournal(StateStore.for_server(server))
                body = {'consent': True, 'steps': [
                    {'id': 's1', 'skill_id': 'device_facts', 'target': keys['tv'],
                     'params': {}, 'approval': True}]}
                rec = W.run(body, router(server), journal, 'wf-r1-xproc')
                self.assertEqual(rec['status'], 'waiting_approval')
                gate = os.path.join(d, 'gate')
                worker_py = os.path.join(d, 'worker_r1.py')
                with open(worker_py, 'w', encoding='utf-8') as f:
                    f.write(WORKER)
                procs, logs = [], []
                results = [os.path.join(d, 'r0.json'), os.path.join(d, 'r1.json')]
                try:
                    for i in range(2):
                        ap = os.path.join(d, 'args%d.json' % i)
                        with open(ap, 'w', encoding='utf-8') as f:
                            json.dump({'root': root, 'shared': shared, 'tmpdir': d,
                                       'gate': gate, 'result_file': results[i],
                                       'workflow_id': 'wf-r1-xproc'}, f)
                        log = open(os.path.join(d, 'w%d.log' % i), 'w', encoding='utf-8')
                        logs.append(log)
                        env = dict(os.environ)
                        env['PYTHONPATH'] = root + os.pathsep + env.get('PYTHONPATH', '')
                        procs.append(subprocess.Popen(
                            [sys.executable, worker_py, ap],
                            stdout=log, stderr=subprocess.STDOUT, env=env))
                    time.sleep(1.0)
                    with open(gate, 'w', encoding='utf-8') as f:
                        f.write('go')
                    for p in procs:
                        p.wait(timeout=240)
                finally:
                    for p in procs:
                        if p.poll() is None:
                            p.kill()
                    for log in logs:
                        log.close()
                rcs = [p.returncode for p in procs]
                _emit('r1_worker_returncodes', '%s,%s' % tuple(rcs))
                self.assertEqual(rcs, [0, 0], 'worker crashed; logs kept at ' + d)
                outs = [json.load(open(rp, encoding='utf-8')) for rp in results]
                total = sum(o['dispatches'] for o in outs)
                _emit('r1_outcomes', '%s|%s' % (outs[0]['outcome'], outs[1]['outcome']))
                _emit('r1_total_dispatches', total)
                stored = (journal.get('wf-r1-xproc') or {}).get('status')
                _emit('r1_stored_status', stored)
                self.assertEqual(total, 1, 'double-approve must dispatch once, saw %d (%s)' % (total, outs))
                self.assertEqual(stored, 'done', 'stored record must match the executed truth, saw %s (%s)' % (stored, outs))
            finally:
                shutil.rmtree(d, ignore_errors=True)
        finally:
            det.__exit__(None, None, None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
