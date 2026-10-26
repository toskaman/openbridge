from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from src.core.transactions import TransactionEngine, TransactionBlocked


class Setting:
    identity='simulated-screen-setting'
    source='SIMULATED'
    def __init__(self):
        self.value=30
        self.writes=[]
        self.fail_after_write=False
    def read_setting(self): return self.value
    def write_setting(self,value):
        self.value=value
        self.writes.append(value)
        if self.fail_after_write:
            self.fail_after_write=False
            raise OSError('Disconnected after the operation')


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'journal.sqlite'
        self.adapter=Setting()
        self.engine=TransactionEngine(self.path,self.adapter)

    def prepare(self,tx='example-transaction',target=60,consent=True):
        return self.engine.prepare(tx,target,consent=consent)

    def test_exact_snapshot_apply_and_restore(self):
        tx=self.prepare()
        self.assertEqual(tx['before'],30)
        self.assertEqual(tx['state'],'VERIFIED_BACKUP')
        self.assertEqual(self.engine.apply(tx['id'])['state'],'VERIFIED')
        self.assertEqual(self.adapter.value,60)
        self.assertEqual(self.engine.revert(tx['id'])['state'],'REVERTED')
        self.assertEqual(self.adapter.value,30)

    def test_consent_and_safe_target_required(self):
        for value,consent in ((60,False),(0,True),(999,True),(True,True)):
            with self.assertRaises(TransactionBlocked):
                self.prepare(target=value,consent=consent)
        self.assertFalse(self.adapter.writes)

    def test_physical_adapter_requires_explicit_opt_in(self):
        self.adapter.source='ADB'
        with self.assertRaises(TransactionBlocked):TransactionEngine(self.path,self.adapter)
        engine=TransactionEngine(self.path,self.adapter,allow_physical=True)
        self.assertEqual(engine.prepare('physical-test',60,consent=True)['source'],'ADB')

    def test_backup_is_durable_before_write(self):
        self.prepare()
        def write(value):
            recovered=TransactionEngine(self.path,self.adapter).get('example-transaction')
            self.assertEqual(recovered['before'],30)
            self.assertEqual(recovered['state'],'EXECUTING')
            self.adapter.value=value
        self.adapter.write_setting=write
        self.engine.apply('example-transaction')

    def test_external_change_before_apply_blocks_without_overwrite(self):
        self.prepare()
        self.adapter.value=120
        with self.assertRaises(TransactionBlocked): self.engine.apply('example-transaction')
        self.assertFalse(self.adapter.writes)
        self.assertEqual(self.engine.get('example-transaction')['state'],'QUARANTINED')

    def test_external_change_before_undo_is_preserved(self):
        self.prepare();self.engine.apply('example-transaction');self.adapter.value=120
        with self.assertRaises(TransactionBlocked): self.engine.revert('example-transaction')
        self.assertEqual(self.adapter.value,120)

    def test_ambiguous_write_is_quarantined_then_recovered(self):
        self.prepare();self.adapter.fail_after_write=True
        with self.assertRaises(TransactionBlocked): self.engine.apply('example-transaction')
        self.assertEqual(self.engine.get('example-transaction')['state'],'QUARANTINED')
        self.assertEqual(self.engine.revert('example-transaction')['state'],'REVERTED')
        self.assertEqual(self.adapter.value,30)

    def test_restart_uses_saved_original(self):
        self.prepare();self.engine.apply('example-transaction')
        restarted=TransactionEngine(self.path,self.adapter)
        self.assertEqual(restarted.revert('example-transaction')['before'],30)
        self.assertEqual(self.adapter.value,30)

    def test_restart_between_snapshot_commit_and_backup_verification(self):
        self.prepare()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE transactions SET state='PREPARED'")
        db.close()
        restarted=TransactionEngine(self.path,self.adapter)
        self.assertEqual(restarted.prepare('example-transaction',60,consent=True)['state'],'VERIFIED_BACKUP')
        self.assertEqual(restarted.apply('example-transaction')['state'],'VERIFIED')
        restarted.revert('example-transaction')
        self.assertEqual(self.adapter.value,30)

    def test_unexecuted_snapshot_can_be_cancelled_by_revert(self):
        self.prepare()
        self.assertEqual(self.engine.revert('example-transaction')['state'],'REVERTED')
        self.assertFalse(self.adapter.writes)

    def test_never_executed_transaction_cannot_overwrite_external_target(self):
        self.prepare();self.adapter.value=60
        for _ in range(2):
            with self.assertRaises(TransactionBlocked): self.engine.revert('example-transaction')
        self.assertEqual(self.adapter.value,60)
        self.assertFalse(self.adapter.writes)

    def test_repeated_requests_do_not_repeat_writes(self):
        self.prepare();self.prepare();self.engine.apply('example-transaction');self.engine.apply('example-transaction')
        self.engine.revert('example-transaction');self.engine.revert('example-transaction')
        self.assertEqual(self.adapter.writes,[60,30])

    def test_corrupt_snapshot_blocks_recovery(self):
        self.prepare();self.engine.apply('example-transaction')
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE transactions SET before_value=90')
        with self.assertRaises(TransactionBlocked): self.engine.revert('example-transaction')
        self.assertEqual(self.adapter.value,60)
        db.close()

    def test_device_identity_change_blocks_writes(self):
        self.prepare();self.adapter.identity='other-device'
        with self.assertRaises(TransactionBlocked): self.engine.apply('example-transaction')
        self.assertFalse(self.adapter.writes)

    def test_concurrent_prepare_allows_one_active_transaction(self):
        def prepare(index):
            try:
                TransactionEngine(self.path,self.adapter).prepare(f'tx-{index}',60,consent=True)
                return True
            except TransactionBlocked: return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(prepare,range(4))),1)
