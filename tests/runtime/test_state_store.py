"""Durable runtime state: routing policies and the unresolved-receipt backlog survive a restart."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.fabric.session import SessionJournal
from src.runtime.contract import TransactionReceipt
from src.runtime.primitives import Executor
from src.runtime.routing import Router, RouteError
from src.runtime.state_store import StateError, StateStore


def ctx(d):
    return SimpleNamespace(fabric_registry=None, fabric_snapshot=None, relays=SimpleNamespace(relays={}), relay_ledger=None,
                           session_journal=SessionJournal(str(Path(d) / 's.json')), runtime_executor=None, skill_router=None)


class Persistence(unittest.TestCase):
    def test_unresolved_backlog_survives_restart_and_acknowledge_persists(self):
        d = tempfile.mkdtemp()
        ex = Executor(ctx(d))
        def fail(self_, key, params):
            raise RuntimeError('adapter lost mid-operation')
        ex.RUNNERS = dict(Executor.RUNNERS, relay_revoke=fail)
        r = ex.execute('relay_revoke', 'dev-1', {'relay_id': 'r'}, consent=True)
        self.assertEqual(r['state'], 'FAILED')
        again = Executor(ctx(d))                                    # server restart
        self.assertIn(r['transaction_id'], again.recovery().pending_transactions)
        self.assertTrue(again.acknowledge(r['transaction_id']))
        third = Executor(ctx(d))
        self.assertNotIn(r['transaction_id'], third.recovery().pending_transactions)
        ok = ex.execute('no-such-primitive', 'dev-1', {})           # resolved outcomes are not persisted
        self.assertNotIn(ok['transaction_id'], json.dumps(json.loads((Path(d) / 'runtime-state.json').read_text(encoding='utf-8'))))

    def test_policies_survive_restart(self):
        d = tempfile.mkdtemp()
        c = ctx(d)
        Router(c).set_policy({'skill_id': 'device_facts', 'mode': 'AUTO', 'failover': 'idempotent_read_retry'})
        Router(c).set_policy({'skill_id': 'ble_scan_room', 'mode': 'PINNED', 'route_id': 'rt-0123456789abcdef'})
        fresh = Router(ctx(d))
        self.assertEqual(fresh.policy('device_facts')['failover'], 'idempotent_read_retry')
        self.assertEqual(fresh.policy('ble_scan_room')['pinned_route_id'], 'rt-0123456789abcdef')

    def test_corrupt_or_foreign_state_blocks_recovery_and_routing(self):
        d = tempfile.mkdtemp()
        p = Path(d) / 'runtime-state.json'
        p.write_text('{not json', encoding='utf-8')
        with self.assertRaises(RouteError):
            Router(ctx(d)).skill_routes('device_facts', 'dev-1')
        p.write_text(json.dumps({'version': 1, 'policies': {'device_facts': {'mode': 'EVIL', 'failover': 'none'}, 'nope': {}},
                                 'unresolved': [{'transaction_id': 'x'}, 'junk']}), encoding='utf-8')
        with self.assertRaises(RouteError):
            Router(ctx(d)).skill_routes('device_facts', 'dev-1')
        self.assertIn('STATE_UNREADABLE', Executor(ctx(d)).recovery().blocked_reason)


class InvocationJournal(unittest.TestCase):
    def test_claim_is_exclusive_and_finish_records_done(self):
        # §3.5: pre-dispatch claim is the cross-process admission; finish marks DONE.
        import time
        d = tempfile.mkdtemp()
        store = StateStore(str(Path(d) / 'runtime-state.json'))
        now = time.time()
        claimed, row = store.claim_invocation('owner', 'inv-1', now)
        self.assertTrue(claimed)
        self.assertIsNone(row)
        claimed, row = store.claim_invocation('owner', 'inv-1', now)
        self.assertFalse(claimed)
        self.assertEqual(row['state'], 'EXECUTING')
        self.assertTrue(store.finish_invocation('owner', 'inv-1', 'f' * 64, now))
        self.assertFalse(store.finish_invocation('owner', 'inv-1', 'f' * 64, now))   # already DONE: no-op
        rows = store.load_invocations(now)
        self.assertEqual([(r['invocation_id'], r['state'], r['fingerprint']) for r in rows], [('inv-1', 'DONE', 'f' * 64)])
        self.assertEqual(store.load_invocations(now + 601), [])                       # DONE prunes after the ledger TTL
        store.claim_invocation('owner', 'inv-2', now + 601)                           # the next write prunes the file
        raw = json.loads((Path(d) / 'runtime-state.json').read_text(encoding='utf-8'))['invocations']
        self.assertEqual([r['invocation_id'] for r in raw], ['inv-2'])

    def test_malformed_journal_rows_are_rejected(self):
        d = tempfile.mkdtemp()
        p = Path(d) / 'runtime-state.json'
        p.write_text(json.dumps({'version': 1, 'invocations': [{'actor': 'owner'}]}), encoding='utf-8')
        with self.assertRaises(StateError):
            StateStore(str(p)).load_invocations(0)


if __name__ == '__main__':
    unittest.main()
