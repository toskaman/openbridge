"""Temporary-file persistence regressions; no hardware or hosted calls."""
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.runtime.test_state_store import ctx
from src.runtime.primitives import Executor
from src.runtime.routing import Router, RouteError
from src.runtime.state_store import StateStore

class StateSafety(unittest.TestCase):
    def test_missing_is_first_run_but_corruption_blocks_changes(self):
        with tempfile.TemporaryDirectory() as d:
            c=ctx(d);self.assertEqual(Executor(c).recovery().blocked_reason,'')
            p=Path(d)/'runtime-state.json';p.write_text('{bad')
            ex=Executor(ctx(d));calls=[]
            ex.RUNNERS=dict(Executor.RUNNERS,relay_revoke=lambda *a:calls.append(a))
            self.assertIn('STATE_UNREADABLE',ex.recovery().blocked_reason)
            r=ex.execute('relay_revoke','dev-1',{'relay_id':'r'},consent=True)
            self.assertEqual(r['state'],'BLOCKED');self.assertEqual(calls,[])
            with self.assertRaises(RouteError) as cm:
                Router(ctx(d)).skill_routes('ble_scan_room')
            self.assertEqual(cm.exception.code,'STATE_UNREADABLE')
            self.assertEqual(p.read_text(),'{bad')

    def test_malformed_rows_and_foreign_version_are_not_empty_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'runtime-state.json'
            for body in ({'version':99},{'version':1,'unresolved':[{'transaction_id':'x'}]},
                         {'version':1,'policies':{'device_facts':{'mode':'EVIL'}}}):
                p.write_text(json.dumps(body))
                self.assertTrue(Executor(ctx(d)).recovery().blocked_reason)
                with self.assertRaises(RouteError):Router(ctx(d)).skill_routes('ble_scan_room')

    def test_policy_save_failure_is_reported_and_does_not_publish_success(self):
        with tempfile.TemporaryDirectory() as d:
            r=Router(ctx(d));before=r.policy('ble_scan_room').copy()
            with patch('os.replace',side_effect=OSError('disk unavailable')):
                with self.assertRaises(RouteError) as cm:
                    r.set_policy({'skill_id':'ble_scan_room','mode':'PINNED','route_id':'rt-test'})
            self.assertEqual(cm.exception.code,'STATE_WRITE_FAILED')
            self.assertEqual(r.policy('ble_scan_room'),before)

    def test_unresolved_save_failure_blocks_next_change_and_ack_is_not_success(self):
        with tempfile.TemporaryDirectory() as d:
            ex=Executor(ctx(d));calls=[]
            def fail(*args):calls.append(1);raise RuntimeError('lost adapter')
            ex.RUNNERS=dict(Executor.RUNNERS,relay_revoke=fail)
            with patch('os.replace',side_effect=OSError('disk unavailable')):
                receipt=ex.execute('relay_revoke','dev-1',{'relay_id':'r'},consent=True)
                self.assertIn('STATE_WRITE_FAILED',ex.recovery().blocked_reason)
                self.assertFalse(ex.acknowledge(receipt['transaction_id']))
                self.assertIn(receipt['transaction_id'],ex.recovery().pending_transactions)
                self.assertEqual(ex.execute('relay_revoke','dev-2',{'relay_id':'r'},consent=True)['state'],'BLOCKED')
            self.assertEqual(len(calls),1)

    def test_process_writers_preserve_unrelated_fields_and_leave_no_shared_temp(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'runtime-state.json'
            code="from src.runtime.state_store import StateStore;import sys; s=StateStore(sys.argv[1]);[(s.update(**{sys.argv[2]:n})) for n in range(25)]"
            workers=[subprocess.Popen([sys.executable,'-c',code,str(path),f'writer{i}'],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for i in range(4)]
            outputs=[(w.communicate(timeout=30),w.returncode) for w in workers]
            self.assertTrue(all(rc==0 for _,rc in outputs),outputs)
            result=StateStore(path).load()
            self.assertEqual([result.get(f'writer{i}') for i in range(4)],[24]*4)
            self.assertEqual(list(Path(d).glob('*.tmp')),[])

    def test_acknowledgement_api_surfaces_storage_failure(self):
        from src.runtime import api_v2
        with tempfile.TemporaryDirectory() as d:
            c=ctx(d);ex=api_v2.executor(c)
            def fail(*args):raise RuntimeError('lost adapter')
            ex.RUNNERS=dict(Executor.RUNNERS,relay_revoke=fail)
            row=ex.execute('relay_revoke','dev-1',{'relay_id':'r'},consent=True)
            with patch('os.replace',side_effect=OSError('disk unavailable')):
                status,body=api_v2.post(c,'/api/v2/recovery/acknowledge',{'transaction_id':row['transaction_id'],'consent':True})
            self.assertEqual(status,503)
            self.assertIn('STATE_WRITE_FAILED',body['error'])

    def test_two_policy_owners_and_receipt_owners_preserve_each_other(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Router(ctx(d)),Router(ctx(d))
            a.set_policy({'skill_id':'ble_scan_room','mode':'PINNED','route_id':'rt-tv'})
            b.set_policy({'skill_id':'device_facts','mode':'AUTO'})
            self.assertEqual(Router(ctx(d)).policy('ble_scan_room')['pinned_route_id'],'rt-tv')
            x,y=Executor(ctx(d)),Executor(ctx(d))
            def fail(*args):raise RuntimeError('lost adapter')
            for ex in (x,y):ex.RUNNERS=dict(Executor.RUNNERS,relay_revoke=fail)
            rx=x.execute('relay_revoke','dev-1',{'relay_id':'r'},consent=True)
            ry=y.execute('relay_revoke','dev-2',{'relay_id':'r'},consent=True)
            self.assertTrue(x.acknowledge(rx['transaction_id']))
            self.assertTrue(y._persist())  # stale peer must not resurrect acknowledged receipt
            pending=Executor(ctx(d)).recovery().pending_transactions
            self.assertNotIn(rx['transaction_id'],pending);self.assertIn(ry['transaction_id'],pending)

    def test_slow_snapshot_cannot_resurrect_acknowledged_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            ex=Executor(ctx(d))
            def fail(*args):raise RuntimeError('lost adapter')
            ex.RUNNERS=dict(Executor.RUNNERS,relay_revoke=fail)
            row=ex.execute('relay_revoke','dev-1',{'relay_id':'r'},consent=True)
            started,release=threading.Event(),threading.Event();original=ex._store.save_unresolved
            def slow(rows,ack=()):
                if not started.is_set():started.set();release.wait(2)
                return original(rows,ack)
            ex._store.save_unresolved=slow
            writer=threading.Thread(target=ex._persist);writer.start();self.assertTrue(started.wait(1))
            done=[];ack=threading.Thread(target=lambda:done.append(ex.acknowledge(row['transaction_id'])))
            ack.start();release.set();writer.join(3);ack.join(3)
            self.assertFalse(writer.is_alive());self.assertFalse(ack.is_alive());self.assertEqual(done,[True])
            self.assertNotIn(row['transaction_id'],Executor(ctx(d)).recovery().pending_transactions)
