"""V4-S1 (audit): concurrent retries of one approved intent dispatch at most once."""
import threading
import time
import unittest

from tests.runtime.test_command_center import FakeServer, vacuum_intent


class SlowExecutor:
    def __init__(self, delay=0.2, error=None):
        self.calls, self.delay, self.error = [], delay, error
        self.lock = threading.Lock()

    def execute(self, primitive_id, device_key, params, consent=False):
        with self.lock:
            self.calls.append(primitive_id)
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return {'state': 'VERIFIED', 'transaction_id': 'tx-%d' % len(self.calls)}


def run_parallel(n, fn):
    out, threads = [], []
    for _ in range(n):
        def w():
            try:
                out.append(fn())
            except Exception as e:   # noqa: BLE001
                out.append(e)
        threads.append(threading.Thread(target=w))
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    return out


class CommandConcurrency(unittest.TestCase):
    def setUp(self):
        from src.runtime.command import approve
        self.srv = FakeServer()
        self.srv.runtime_executor = SlowExecutor()
        self.doc = vacuum_intent()
        self.prev = approve(self.srv, self.doc)

    def ex(self, doc=None):
        from src.runtime.command import execute
        return execute(self.srv, doc or self.doc, consent=True, preview=self.prev)

    def test_simultaneous_retries_one_effect_same_receipt(self):
        out = run_parallel(5, self.ex)
        self.assertEqual(len(self.srv.runtime_executor.calls), 1)
        self.assertEqual({o['transaction_id'] for o in out}, {'tx-1'})

    def test_completed_retry_returns_cached(self):
        self.ex()
        self.ex()
        self.assertEqual(len(self.srv.runtime_executor.calls), 1)

    def test_unknown_outcome_is_never_redispatched(self):
        self.srv.runtime_executor.error = RuntimeError('link dropped mid-dispatch')
        out = run_parallel(3, self.ex)
        self.assertEqual(len(self.srv.runtime_executor.calls), 1)
        self.assertTrue(any(isinstance(o, RuntimeError) for o in out))
        self.assertEqual(self.ex()['state'], 'INCONCLUSIVE')
        self.assertEqual(len(self.srv.runtime_executor.calls), 1)

    def test_pre_dispatch_refusal_is_not_cached(self):
        from src.runtime.command import CommandError
        devs = self.srv.reg.devices
        self.srv.reg.devices = {}
        with self.assertRaises(CommandError):
            self.ex()
        self.srv.reg.devices = devs
        self.assertEqual(self.ex()['state'], 'VERIFIED')
        self.assertEqual(len(self.srv.runtime_executor.calls), 1)

    def test_distinct_intents_both_execute(self):
        other = vacuum_intent(intent_id='int-other-0001') if 'intent_id' in self.doc else None
        if other is None:
            self.skipTest('intent_id not in draft')
        out = run_parallel(1, self.ex) + run_parallel(1, lambda: self.ex(other))
        self.assertEqual(len(self.srv.runtime_executor.calls), 2, out)


if __name__ == '__main__':
    unittest.main()
