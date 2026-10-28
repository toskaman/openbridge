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
        self.assertNotIn(ok['transaction_id'], json.dumps(json.loads((Path(d) / 'runtime-state.json').read_text())))

    def test_policies_survive_restart(self):
        d = tempfile.mkdtemp()
        c = ctx(d)
        Router(c).set_policy({'skill_id': 'device_facts', 'mode': 'AUTO', 'failover': 'idempotent_read_retry'})
        Router(c).set_policy({'skill_id': 'ble_scan_room', 'mode': 'PINNED', 'route_id': 'rt-0123456789abcdef'})
        fresh = Router(ctx(d))
        self.assertEqual(fresh.policy('device_facts')['failover'], 'idempotent_read_retry')
        self.assertEqual(fresh.policy('ble_scan_room')['pinned_route_id'], 'rt-0123456789abcdef')

    def test_corrupt_or_foreign_state_is_ignored_safely(self):
        d = tempfile.mkdtemp()
        p = Path(d) / 'runtime-state.json'
        p.write_text('{not json')
        self.assertEqual(Router(ctx(d)).policy('device_facts')['mode'], 'AUTO')
        p.write_text(json.dumps({'version': 1, 'policies': {'device_facts': {'mode': 'EVIL', 'failover': 'none'}, 'nope': {}},
                                 'unresolved': [{'transaction_id': 'x'}, 'junk']}))
        self.assertEqual(Router(ctx(d)).policy('device_facts')['mode'], 'AUTO')
        self.assertEqual(Executor(ctx(d)).recovery().pending_transactions, ())


if __name__ == '__main__':
    unittest.main()
