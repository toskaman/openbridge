"""NIGHTFALL N-10 regression: workflow cross-process double-run.

Two processes run() the SAME workflow_id against a SHARED temp journal.
The fix: run() takes an atomic cross-process claim (exactly one driver),
and terminal stored records are immutable (a racing driver can never
clobber 'done' with a bogus terminal state).

The early-return path may still hand a caller a fresh 'running' record
while another process drives (start-or-status semantics; in-process
callers keep execute-and-await via the run lock). What must NEVER happen:
two actuations, a stored non-done terminal record, or a returned 'failed'.

Safety: SIMULATED only (fake read_facts; temp journal; never live state).
Determinism: uuid4 patched to a counter in workers; winner/loser
assertions are order-agnostic. Seed: 20261102.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SEED = 20261102
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    from src.runtime.state_store import StateStore
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
    store = StateStore.for_server(server)
    journal = W.StateStoreJournal(store)
    body = {'consent': True, 'steps': [
        {'id': 's1', 'skill_id': 'device_facts',
         'target': keys['tv'], 'params': {}}]}
    rec = W.run(body, rt, journal, args['workflow_id'])
    steps = [{'id': s['id'], 'state': s['state']} for s in rec['steps']]
    with open(args['result_file'], 'w', encoding='utf-8') as f:
        json.dump({'status': rec['status'], 'steps': steps,
                   'dispatches': n[0]}, f)
main()
'''


def _emit(name, value):
    print('NIGHTFALL_COUNT %s=%s' % (name, value), flush=True)


def _record(wid, status):
    return {'workflow_id': wid, 'status': status, 'steps': []}


class ClaimRunningAtomic(unittest.TestCase):
    def test_memory_store_claim_returns_existing(self):
        from src.runtime.workflows import MemoryStore
        store = MemoryStore()
        self.assertIsNone(store.claim_running(_record('wf-a', 'running')))
        seen = store.claim_running(_record('wf-a', 'running'))
        self.assertIsNotNone(seen)
        self.assertEqual(seen['status'], 'running')

    def test_state_store_claim_returns_existing(self):
        from src.runtime.state_store import StateStore
        from src.runtime.workflows import StateStoreJournal
        d = tempfile.mkdtemp(prefix='n10-claim-')
        self.addCleanup(shutil.rmtree, d, True)
        journal = StateStoreJournal(
            StateStore(os.path.join(d, 'runtime-state.json')))
        self.assertIsNone(journal.claim_running(_record('wf-a', 'running')))
        seen = journal.claim_running(_record('wf-a', 'running'))
        self.assertIsNotNone(seen)
        self.assertEqual(seen['status'], 'running')


class TerminalWins(unittest.TestCase):
    def test_terminal_record_not_clobbered(self):
        from src.runtime.state_store import StateStore
        from src.runtime.workflows import StateStoreJournal
        d = tempfile.mkdtemp(prefix='n10-term-')
        self.addCleanup(shutil.rmtree, d, True)
        journal = StateStoreJournal(
            StateStore(os.path.join(d, 'runtime-state.json')))
        journal.save(_record('wf-a', 'done'))
        journal.save(_record('wf-a', 'failed'))
        self.assertEqual(journal.get('wf-a')['status'], 'done')

    def test_same_status_resave_allowed(self):
        from src.runtime.state_store import StateStore
        from src.runtime.workflows import StateStoreJournal
        d = tempfile.mkdtemp(prefix='n10-term-')
        self.addCleanup(shutil.rmtree, d, True)
        journal = StateStoreJournal(
            StateStore(os.path.join(d, 'runtime-state.json')))
        journal.save(_record('wf-a', 'done'))
        rec = _record('wf-a', 'done')
        rec['note'] = 'detail'
        journal.save(rec)
        self.assertEqual(journal.get('wf-a')['note'], 'detail')


class N10WorkflowDoubleRun(unittest.TestCase):
    def test_same_id_double_run_single_dispatch(self):
        from src.runtime import workflows as W
        from src.runtime.state_store import StateStore
        d = tempfile.mkdtemp(prefix='n10-')
        shared = os.path.join(d, 'shared')
        os.mkdir(shared)
        gate = os.path.join(d, 'gate')
        worker_py = os.path.join(d, 'worker_n10.py')
        with open(worker_py, 'w', encoding='utf-8') as f:
            f.write(WORKER)
        wid = 'wf-nightfall-n10'
        procs, logs = [], []
        results = [os.path.join(d, 'r0.json'), os.path.join(d, 'r1.json')]
        failed = True
        try:
            for i in range(2):
                args = {'root': ROOT, 'shared': shared, 'tmpdir': d,
                        'gate': gate, 'result_file': results[i],
                        'workflow_id': wid}
                ap = os.path.join(d, 'args%d.json' % i)
                with open(ap, 'w', encoding='utf-8') as f:
                    json.dump(args, f)
                log = open(os.path.join(d, 'w%d.log' % i), 'w',
                           encoding='utf-8')
                logs.append(log)
                procs.append(subprocess.Popen(
                    [sys.executable, worker_py, ap],
                    stdout=log, stderr=subprocess.STDOUT))
            time.sleep(1.0)
            with open(gate, 'w', encoding='utf-8') as f:
                f.write('go')
            for p in procs:
                p.wait(timeout=180)
            rcs = [p.returncode for p in procs]
            _emit('n10_worker_returncodes', '%s,%s' % tuple(rcs))
            self.assertEqual(rcs, [0, 0], 'worker failed; logs kept at ' + d)
            outs = []
            for rp in results:
                with open(rp, encoding='utf-8') as f:
                    outs.append(json.load(f))
            total = outs[0]['dispatches'] + outs[1]['dispatches']
            _emit('n10_statuses', '%s,%s' % (outs[0]['status'], outs[1]['status']))
            _emit('n10_total_dispatches', total)
            self.assertEqual(total, 1, 'journal must backstop a second actuation')
            for o in outs:
                self.assertIn(o['status'], ('done', 'running'),
                              'no bogus terminal record may be returned')
            stored = W.StateStoreJournal(
                StateStore(os.path.join(shared, 'runtime-state.json'))).get(wid)
            _emit('n10_stored_status', (stored or {}).get('status'))
            self.assertIsNotNone(stored)
            self.assertEqual(stored['status'], 'done')
            failed = False
        finally:
            for p in procs:
                if p.poll() is None:
                    p.kill()
            for log in logs:
                log.close()
            if not failed:
                shutil.rmtree(d, ignore_errors=True)
            else:
                print('NIGHTFALL_KEEP_TMPDIR ' + d, flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
