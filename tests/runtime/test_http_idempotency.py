"""§3.4/§3.5: /api/v2/execute honors idempotency_key (durable journal claim).

A duplicate POST carrying the same key (double-click, retry after a lost
response, crash+restart) must never re-dispatch a physical primitive.
"""
import tempfile
import unittest

from src.fabric.session import SessionJournal
from src.runtime.api_v2 import post
from tests.runtime.test_command_center import FakeServer


class CountingExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, primitive_id, device_key, params, consent=False):
        self.calls.append((primitive_id, device_key, dict(params or {})))
        return {'state': 'EXECUTED', 'transaction_id': 'tx-%d' % len(self.calls),
                'errors': [], 'verified': False}


def keyed_server(path=None):
    srv = FakeServer()
    srv.runtime_executor = CountingExecutor()
    if path is not None:
        srv.session_journal = SessionJournal(path + '/s.json')
    return srv


def body(key='k-1', **kw):
    b = {'primitive_id': 'tuya_command', 'device_key': 'dev-vac1',
         'params': {'command': 'start'}, 'consent': True}
    if key is not None:
        b['idempotency_key'] = key
    b.update(kw)
    return b


class HttpIdempotency(unittest.TestCase):
    def test_same_key_second_post_is_duplicate_no_redispatch(self):
        srv = keyed_server(tempfile.mkdtemp())
        st1, _ = post(srv, '/api/v2/execute', body('k-dup'))
        st2, r2 = post(srv, '/api/v2/execute', body('k-dup'))
        self.assertEqual(st1, 200)
        self.assertEqual(st2, 409)
        self.assertIn('DUPLICATE', r2.get('error', ''))
        self.assertEqual(len(srv.runtime_executor.calls), 1)

    def test_different_keys_dispatch_twice(self):
        srv = keyed_server(tempfile.mkdtemp())
        post(srv, '/api/v2/execute', body('k-a'))
        st, _ = post(srv, '/api/v2/execute', body('k-b'))
        self.assertEqual(st, 200)
        self.assertEqual(len(srv.runtime_executor.calls), 2)

    def test_missing_key_keeps_legacy_behavior(self):
        srv = keyed_server(tempfile.mkdtemp())
        post(srv, '/api/v2/execute', body(None))
        post(srv, '/api/v2/execute', body(None))
        self.assertEqual(len(srv.runtime_executor.calls), 2)

    def test_duplicate_refused_after_restart(self):
        journal = tempfile.mkdtemp()
        srv = keyed_server(journal)
        post(srv, '/api/v2/execute', body('k-restart'))
        fresh = keyed_server(journal)   # restart: empty memory, same journal
        st, r = post(fresh, '/api/v2/execute', body('k-restart'))
        self.assertEqual(st, 409)
        self.assertIn('DUPLICATE', r.get('error', ''))
        self.assertEqual(len(fresh.runtime_executor.calls), 0)

    def test_executing_leftover_is_uncertain(self):
        import time as _time
        from src.runtime.state_store import StateStore
        journal = tempfile.mkdtemp()
        StateStore.for_server(keyed_server(journal)).claim_invocation('http-v2', 'k-crash', _time.time())
        srv = keyed_server(journal)
        st, r = post(srv, '/api/v2/execute', body('k-crash'))
        self.assertEqual(st, 409)
        self.assertIn('UNCERTAIN', r.get('error', ''))
        self.assertEqual(len(srv.runtime_executor.calls), 0)

    def test_bad_key_rejected(self):
        srv = keyed_server(tempfile.mkdtemp())
        for bad in ('', 'x' * 97, 123, ['k']):
            st, _ = post(srv, '/api/v2/execute', body(bad))
            self.assertEqual(st, 400, bad)
        self.assertEqual(len(srv.runtime_executor.calls), 0)

    def test_no_journal_falls_back_to_memory(self):
        srv = keyed_server()   # no session_journal: hermetic in-memory dedup
        st1, _ = post(srv, '/api/v2/execute', body('k-mem'))
        st2, r2 = post(srv, '/api/v2/execute', body('k-mem'))
        self.assertEqual((st1, st2), (200, 409))
        self.assertIn('DUPLICATE', r2.get('error', ''))
        self.assertEqual(len(srv.runtime_executor.calls), 1)


class IntentJournal(unittest.TestCase):
    """§3.5: the direct (non-b2) intent path also claims the durable journal."""

    def server(self, journal):
        from tests.runtime.test_command_center import FakeServer
        srv = FakeServer()
        srv.runtime_executor = CountingExecutor()
        srv.session_journal = SessionJournal(journal + '/s.json')
        return srv

    def test_direct_intent_refused_after_restart(self):
        from src.runtime.command import approve, execute, CommandError
        from tests.runtime.test_command_center import vacuum_intent
        journal = tempfile.mkdtemp()
        srv = self.server(journal)
        doc = vacuum_intent()
        prev = approve(srv, doc)
        execute(srv, doc, consent=True, preview=prev)
        self.assertEqual(len(srv.runtime_executor.calls), 1)
        fresh = self.server(journal)   # restart: empty memory, same journal
        with self.assertRaises(CommandError) as e:
            execute(fresh, doc, consent=True, preview=prev)
        self.assertEqual(e.exception.status, 409)
        self.assertEqual(len(fresh.runtime_executor.calls), 0)

    def test_pre_dispatch_refusal_does_not_poison_journal(self):
        from src.runtime.command import approve, execute, CommandError
        from tests.runtime.test_command_center import vacuum_intent
        srv = self.server(tempfile.mkdtemp())
        doc = vacuum_intent()
        prev = approve(srv, doc)
        bad = dict(prev, fingerprint='0' * 64)
        with self.assertRaises(CommandError):
            execute(srv, doc, consent=True, preview=bad)
        out = execute(srv, doc, consent=True, preview=prev)   # clean retry works
        self.assertEqual(out['state'], 'EXECUTED')
        self.assertEqual(len(srv.runtime_executor.calls), 1)


if __name__ == '__main__':
    unittest.main()
