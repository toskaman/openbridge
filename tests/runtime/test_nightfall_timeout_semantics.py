"""NIGHTFALL N-08 verdict: DOCUMENTED (no code change).

A worker that finishes after the primitive timeout leaves the receipt at
UNKNOWN_TIMEOUT; the late result is discarded. Reconciling late results
into receipts would change recovery/backlog semantics (broad, near the
deadline); the re-drive hazard is mitigated (the per-device lock is held
until the worker ends, the command cache returns the cached UNKNOWN for
the same intent, and a re-drive needs a fresh owner approval).

This file PINS the current contract so any future change is deliberate:
the receipt stays UNKNOWN_TIMEOUT after a late VERIFIED finish.

Safety: SIMULATED only (fake runner sleeps; temp state; no devices).
Deterministic: fixed sleeps (timeout 1s, work 2.5s); no randomness.
Seed: 20261102.
"""
import dataclasses
import os
import shutil
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

SEED = 20261102


def _emit(name, value):
    print('NIGHTFALL_COUNT %s=%s' % (name, value), flush=True)


class N08LateResultDiscarded(unittest.TestCase):
    def test_late_result_does_not_update_unknown_timeout_receipt(self):
        import src.runtime.primitives as P
        from src.fabric.session import SessionJournal
        from src.runtime.primitives import Executor
        d = tempfile.mkdtemp(prefix='n08-')
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        sj_path = os.path.join(d, 's.json')
        rp = os.path.realpath(sj_path)
        self.assertEqual(os.path.commonpath([rp, os.path.realpath(d)]),
                         os.path.realpath(d))
        self.assertNotIn('OpenBridge', rp)
        orig = P.PRIMITIVES['read_facts']
        P.PRIMITIVES['read_facts'] = dataclasses.replace(orig, timeout_s=1)
        self.addCleanup(P.PRIMITIVES.__setitem__, 'read_facts', orig)
        late = threading.Event()
        finished = []

        def slow(self_, key, params):
            time.sleep(2.5)
            finished.append(time.monotonic())
            late.set()
            return 'VERIFIED', None, {'ok': True}, True, {'ok': True}

        ex = Executor(SimpleNamespace(session_journal=SessionJournal(sj_path),
                                      fabric_registry=None))
        ex.RUNNERS = dict(Executor.RUNNERS, read_facts=slow)
        t0 = time.monotonic()
        out = ex.execute('read_facts', 'sim-n08', {}, consent=False)
        elapsed = time.monotonic() - t0
        tx = out.get('transaction_id')
        _emit('n08_first_state', out.get('state'))
        _emit('n08_first_elapsed_ms', int(elapsed * 1000))
        self.assertEqual(out.get('state'), 'UNKNOWN_TIMEOUT')
        self.assertLess(elapsed, 5.0)
        self.assertTrue(late.wait(timeout=10), 'late worker never finished')
        time.sleep(0.3)
        rec = ex.receipts.get(tx)
        self.assertIsNotNone(rec)
        _emit('n08_late_worker_finished', int(bool(finished)))
        _emit('n08_receipt_after_late', rec.state)
        self.assertEqual(rec.state, 'UNKNOWN_TIMEOUT')


if __name__ == '__main__':
    unittest.main(verbosity=2)
