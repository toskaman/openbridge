"""NIGHTFALL N-03 regression: b2 cross-process double-dispatch.

Two processes run command.execute() on the SAME (intent_id, fingerprint)
through the b2 path against a SIMULATED adapter with a SHARED journal.
Exactly one process may dispatch; the loser must be refused (409
DUPLICATE_REQUEST or UNCERTAIN_OUTCOME, scheduling decides which).

Safety: SIMULATED only (synthetic registry + fake read_facts; temp state,
asserted in workers; never live state).
Determinism: uuid4 patched to a counter in workers so both processes
approve identical fingerprints; winner/loser assertions are order-agnostic.
Seed: 20261102.
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
INTENT_ID = 'int-nightfall-n03'
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
        time.sleep(0.01)
    shared = os.path.realpath(args['shared'])
    tmp = os.path.realpath(args['tmpdir'])
    assert os.path.commonpath([shared, tmp]) == tmp, 'shared outside tmpdir'
    assert 'OpenBridge' not in shared, 'live state touched'
    from tests.runtime.test_routing import world, Clock
    from src.fabric.session import SessionJournal
    from src.runtime import command as CMD
    from src.runtime.api_v2 import executor, router
    from src.runtime.primitives import Executor
    server, keys = world(Clock(1793100000.0))
    server.session_journal = SessionJournal(os.path.join(shared, 's.json'))
    n = [0]
    def fake(self_, key, params):
        n[0] += 1
        return 'VERIFIED', None, {'ok': True}, True, {'ok': True}
    ex = executor(server)
    ex.RUNNERS = dict(Executor.RUNNERS, read_facts=fake)
    router(server)
    doc = {'intent_id': 'INTENT', 'version': 1, 'raw_text': 'read the tv facts',
           'lang': 'en', 'outcome': 'read facts',
           'targets': [{'kind': 'device', 'ref': 'Android TV'}],
           'skill_id': 'device_facts', 'params': {}, 'confidence': 0.9,
           'ambiguities': [], 'clarifying_question': None,
           'risk_level': 'low', 'status': 'resolved',
           'provenance': {'parser': 'rules', 'model_id': None}}
    prev = CMD.approve(server, doc)
    out = {'fingerprint': prev['fingerprint'],
           'approved_targets': prev['approved_targets'],
           'invocation_id': None, 'state': None, 'dispatches': 0,
           'refused': False, 'refuse_status': None, 'refuse_message': None}
    try:
        rc = CMD.execute(server, doc, consent=True, preview=prev)
    except CMD.CommandError as e:
        out['refused'] = True
        out['refuse_status'] = e.status
        out['refuse_message'] = getattr(e, 'message', str(e))
        out['state'] = 'REFUSED'
    else:
        out['invocation_id'] = rc.get('invocation_id')
        out['state'] = rc.get('state')
    out['dispatches'] = n[0]
    with open(args['result_file'], 'w', encoding='utf-8') as f:
        json.dump(out, f)

main()
'''.replace('INTENT', INTENT_ID)


def _emit(name, value):
    print('NIGHTFALL_COUNT %s=%s' % (name, value), flush=True)


class N03B2DoubleDispatch(unittest.TestCase):
    def test_same_intent_dispatches_once_across_processes(self):
        d = tempfile.mkdtemp(prefix='n03-')
        shared = os.path.join(d, 'shared')
        os.mkdir(shared)
        gate = os.path.join(d, 'gate')
        worker_py = os.path.join(d, 'worker_n03.py')
        with open(worker_py, 'w', encoding='utf-8') as f:
            f.write(WORKER)
        procs, logs = [], []
        results = [os.path.join(d, 'r0.json'), os.path.join(d, 'r1.json')]
        failed = True
        try:
            for i in range(2):
                args = {'root': ROOT, 'shared': shared, 'tmpdir': d,
                        'gate': gate, 'result_file': results[i]}
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
            _emit('n03_worker_returncodes', '%s,%s' % tuple(rcs))
            self.assertEqual(rcs, [0, 0], 'worker failed; logs kept at ' + d)
            outs = []
            for rp in results:
                with open(rp, encoding='utf-8') as f:
                    outs.append(json.load(f))
            same_fp = outs[0]['fingerprint'] == outs[1]['fingerprint']
            _emit('n03_same_fingerprint', int(same_fp))
            self.assertTrue(same_fp, 'workers must approve the same fingerprint')
            total = outs[0]['dispatches'] + outs[1]['dispatches']
            _emit('n03_total_dispatches', total)
            self.assertEqual(total, 1, 'exactly one process may dispatch')
            winners = [o for o in outs if not o['refused']]
            losers = [o for o in outs if o['refused']]
            self.assertEqual(len(winners), 1)
            self.assertEqual(len(losers), 1)
            self.assertEqual(winners[0]['state'], 'VERIFIED')
            self.assertEqual(losers[0]['refuse_status'], 409)
            # Scheduling decides which honest refusal the loser sees: DONE
            # (duplicate) or still-EXECUTING (uncertain). CommandError carries
            # status + message only (RouteError code is not forwarded).
            self.assertIn(losers[0]['refuse_message'], (
                'This request was already handled',
                'An invocation with this id is already running elsewhere or was interrupted; use a fresh invocation id'))
            from src.runtime.command import _b2_invocation_id
            expect = _b2_invocation_id(INTENT_ID, outs[0]['fingerprint'])
            _emit('n03_derived_id_stable', int(winners[0]['invocation_id'] == expect))
            self.assertEqual(winners[0]['invocation_id'], expect)
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
