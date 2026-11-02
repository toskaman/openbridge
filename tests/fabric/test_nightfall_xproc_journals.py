"""NIGHTFALL N-06 regression: cross-process session/relay journal safety.

Two processes hammer a SHARED session journal + relay store. Temp-state
only (asserted inside workers); never live state. Workers use
single-attempt ops (no retry): any cross-process collision crashes the
worker and fails the test. Expectation: returncode 0 + zero loss.

Seed: 20261102 (op counts fixed; scheduling interleavings vary by design).
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
SESSION_PER_PROC = 50
RELAY_PER_PROC = 40
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WORKER = '''
import json, os, sys, time
def main():
    with open(sys.argv[1], encoding='utf-8') as f:
        args = json.load(f)
    sys.path.insert(0, args['root'])
    t0 = time.time()
    while not os.path.exists(args['gate']):
        if time.time() - t0 > 60:
            raise RuntimeError('gate timeout')
        time.sleep(0.005)
    shared = os.path.realpath(args['shared'])
    tmp = os.path.realpath(args['tmpdir'])
    assert os.path.commonpath([shared, tmp]) == tmp, 'shared outside tmpdir'
    assert 'OpenBridge' not in shared, 'live state touched'
    from src.fabric.session import SessionJournal
    from src.fabric.relay_store import RelayStore
    proc = args['proc']
    class MemVault:
        available = True
        def __init__(self): self.d = {}
        def put(self, k, v): self.d[k] = v
        def get(self, k): return self.d.get(k)
        def delete(self, k): self.d.pop(k, None)
    sj = SessionJournal(os.path.join(shared, 'session.json'))
    for i in range(args['session_n']):
        addr = '10.9.%d.%d' % (proc, i)
        sj.record('adb_network_connected', 'sim-n06', {'address': addr},
                  'down', 'up')
    store = RelayStore(os.path.join(shared, 'relays.json'), MemVault())
    for i in range(args['relay_n']):
        rid = 'relay-%06x' % (proc * 100000 + i)
        serial = 'n06sim-p%d-i%04d' % (proc, i)
        key = bytes([(i + proc) % 256]) * 32
        ok = store.save(rid, serial, key,
                        {'capabilities': ['ble_scan'],
                         'battery_powered': False})
        assert ok, 'relay save refused at i=%d' % i
    with open(args['result_file'], 'w', encoding='utf-8') as f:
        json.dump({'session_ops': args['session_n'],
                   'relay_ops': args['relay_n']}, f)
main()
'''


def _emit(name, value):
    print('NIGHTFALL_COUNT %s=%s' % (name, value), flush=True)


class N06CrossProcessJournals(unittest.TestCase):
    def test_concurrent_append_and_save_lose_nothing(self):
        d = tempfile.mkdtemp(prefix='n06-')
        shared = os.path.join(d, 'shared')
        os.mkdir(shared)
        gate = os.path.join(d, 'gate')
        worker_py = os.path.join(d, 'worker_n06.py')
        with open(worker_py, 'w', encoding='utf-8') as f:
            f.write(WORKER)
        procs, logs = [], []
        results = [os.path.join(d, 'r0.json'), os.path.join(d, 'r1.json')]
        failed = True
        try:
            for i in range(2):
                args = {'root': ROOT, 'shared': shared, 'tmpdir': d,
                        'gate': gate, 'proc': i, 'result_file': results[i],
                        'session_n': SESSION_PER_PROC,
                        'relay_n': RELAY_PER_PROC}
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
            _emit('n06_worker_returncodes', '%s,%s' % tuple(rcs))
            self.assertEqual(rcs, [0, 0], 'worker failed; logs kept at ' + d)
            for rp in results:
                with open(rp, encoding='utf-8') as f:
                    res = json.load(f)
                self.assertEqual(res['session_ops'], SESSION_PER_PROC)
                self.assertEqual(res['relay_ops'], RELAY_PER_PROC)
            with open(os.path.join(shared, 'session.json'),
                      encoding='utf-8') as f:
                session_rows = json.load(f)
            with open(os.path.join(shared, 'relays.json'),
                      encoding='utf-8') as f:
                relay_rows = json.load(f)['relays']
            exp_session = 2 * SESSION_PER_PROC
            exp_relay = 2 * RELAY_PER_PROC
            loss_session = exp_session - len(session_rows)
            loss_relay = exp_relay - len(relay_rows)
            _emit('n06_session_expected', exp_session)
            _emit('n06_session_actual', len(session_rows))
            _emit('n06_session_lost', loss_session)
            _emit('n06_relay_expected', exp_relay)
            _emit('n06_relay_actual', len(relay_rows))
            _emit('n06_relay_lost', loss_relay)
            self.assertEqual(loss_session, 0, 'session entries lost')
            self.assertEqual(loss_relay, 0, 'relay pairings lost')
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


class SessionFileSemantics(unittest.TestCase):
    def test_missing_file_reads_empty_and_roundtrips(self):
        from src.fabric.session import SessionJournal
        d = tempfile.mkdtemp(prefix='n06-sem-')
        try:
            sj = SessionJournal(os.path.join(d, 'session.json'))
            self.assertEqual(sj.open_changes(), [])
            cid = sj.record('adb_network_connected', 'sim', {'address': 'a'},
                            'down', 'up')
            self.assertEqual(len(sj.open_changes()), 1)
            sj.close(cid, 'KEPT', 'test')
            self.assertEqual(sj.open_changes(), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_corrupt_file_read_behavior_pinned(self):
        # Documents CURRENT read contract (residual B-02b, fail-open read):
        # open_changes() on a corrupt file returns []. Desired behavior is
        # fail-closed (raise); change this test deliberately with that fix.
        from src.fabric.session import SessionJournal
        d = tempfile.mkdtemp(prefix='n06-sem-')
        try:
            p = os.path.join(d, 'session.json')
            with open(p, 'w', encoding='utf-8') as f:
                f.write('{not json')
            sj = SessionJournal(p)
            self.assertEqual(sj.open_changes(), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
