"""Durable reversible-setting transactions; physical adapters require explicit opt-in."""
from contextlib import contextmanager, closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import threading
import time


class TransactionBlocked(ValueError):
    pass


class TransactionEngine:
    def __init__(self, journal_path, adapter, *, allow_physical=False):
        source=getattr(adapter,'source',None)
        if source != 'SIMULATED' and not (source=='ADB' and allow_physical is True):
            raise TransactionBlocked('Physical adapters require explicit transaction opt-in')
        self.path=Path(journal_path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.adapter=adapter
        self._thread_lock=threading.Lock()
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS transactions (id TEXT PRIMARY KEY, resource TEXT NOT NULL, before_value INTEGER NOT NULL, target INTEGER NOT NULL, snapshot_hash TEXT NOT NULL, state TEXT NOT NULL)')
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS active_resource ON transactions(resource) WHERE state != 'REVERTED'")
            db.execute('CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, transaction_id TEXT, state TEXT, recorded REAL)')

    @contextmanager
    def _db(self):
        with closing(sqlite3.connect(self.path,timeout=5)) as db, db:
            db.row_factory=sqlite3.Row
            yield db

    @contextmanager
    def _exclusive(self):
        # An OS-released lease spans committed journal states and the adapter operation.
        # A database transaction alone would lose exclusivity when the snapshot commits.
        if not self._thread_lock.acquire(blocking=False):
            raise TransactionBlocked('Another transaction operation is running')
        lease=None
        acquired=False
        try:
            lease=self.path.with_suffix('.lock').open('a+b')
            if lease.tell()==0:
                lease.write(b'0');lease.flush()
            lease.seek(0)
            try:
                if sys.platform=='win32':
                    import msvcrt
                    msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                acquired=True
            except OSError:
                raise TransactionBlocked('Another process owns the transaction journal') from None
            yield
        finally:
            if lease:
                if acquired:
                    lease.seek(0)
                    if sys.platform=='win32':
                        import msvcrt
                        msvcrt.locking(lease.fileno(),msvcrt.LK_UNLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(lease.fileno(),fcntl.LOCK_UN)
                lease.close()
            self._thread_lock.release()

    @staticmethod
    def _hash(resource,before,target):
        data={'resource':resource,'field':'screen_timeout_seconds','before':before,'target':target}
        return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

    def get(self,transaction_id):
        with self._db() as db:
            row=db.execute('SELECT * FROM transactions WHERE id=?',(transaction_id,)).fetchone()
        if row is None:
            raise TransactionBlocked('Unknown transaction')
        if row['resource'] != self.adapter.identity or row['snapshot_hash'] != self._hash(row['resource'],row['before_value'],row['target']):
            raise TransactionBlocked('Device identity or snapshot integrity check failed')
        return {'id':row['id'],'source':self.adapter.source,'field':getattr(self.adapter,'field','screen_timeout_seconds'),
                'before':row['before_value'],'target':row['target'],'state':row['state']}

    def _state(self,transaction_id,expected,new_state):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT state FROM transactions WHERE id=?',(transaction_id,)).fetchone()
            if current is None or current['state'] not in expected:
                raise TransactionBlocked('Unexpected transaction state')
            db.execute('UPDATE transactions SET state=? WHERE id=?',(new_state,transaction_id))
            db.execute('INSERT INTO events(transaction_id,state,recorded) VALUES(?,?,?)',(transaction_id,new_state,time.time()))

    def status(self):
        with self._exclusive():
            with self._db() as db:
                row=db.execute("SELECT id FROM transactions WHERE resource=? AND state != 'REVERTED'",(self.adapter.identity,)).fetchone()
            return {'source':self.adapter.source,'field':getattr(self.adapter,'field','screen_timeout_seconds'),
                    'current_value':self.adapter.read_setting(),'active':self.get(row['id']) if row else None}

    def prepare(self,transaction_id,target,*,consent=False):
        if consent is not True or type(target) is not int or target not in getattr(self.adapter,'allowed_targets',(15,30,60,120)):
            raise TransactionBlocked('Explicit consent and an approved target are required')
        if not isinstance(transaction_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',transaction_id):
            raise TransactionBlocked('Invalid transaction identifier')
        with self._exclusive():
            with self._db() as db:
                exists=db.execute('SELECT target FROM transactions WHERE id=?',(transaction_id,)).fetchone()
            if exists:
                result=self.get(transaction_id)
                if result['target'] != target:
                    raise TransactionBlocked('Idempotency key belongs to another proposal')
                if result['state']=='PREPARED':
                    try:
                        if self.adapter.read_setting() != result['before']:
                            raise TransactionBlocked('Original state changed during preparation')
                    except Exception:
                        self._state(transaction_id,{'PREPARED'},'QUARANTINED')
                        raise TransactionBlocked('Interrupted preparation requires inspection') from None
                    self._state(transaction_id,{'PREPARED'},'VERIFIED_BACKUP')
                    return self.get(transaction_id)
                return result
            try:
                before=self.adapter.read_setting()
            except Exception:
                raise TransactionBlocked('Cannot obtain the original setting; no write performed') from None
            if type(before) is not int or not 0 < before <= 86400:
                raise TransactionBlocked('Original setting cannot be safely restored')
            resource=self.adapter.identity
            try:
                with self._db() as db:
                    db.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?)',(transaction_id,resource,before,target,self._hash(resource,before,target),'PREPARED'))
                    db.execute('INSERT INTO events(transaction_id,state,recorded) VALUES(?,?,?)',(transaction_id,'PREPARED',time.time()))
            except sqlite3.IntegrityError:
                raise TransactionBlocked('This resource already has an active transaction') from None
            self._state(transaction_id,{'PREPARED'},'VERIFIED_BACKUP')
            return self.get(transaction_id)

    def apply(self,transaction_id):
        with self._exclusive():
            tx=self.get(transaction_id)
            if tx['state']=='VERIFIED':
                return tx
            if tx['state']!='VERIFIED_BACKUP':
                raise TransactionBlocked('Transaction is not ready to execute')
            try:
                if self.adapter.read_setting() != tx['before']:
                    raise TransactionBlocked('Original setting changed; refusing to overwrite')
                self._state(transaction_id,{'VERIFIED_BACKUP'},'EXECUTING')
                self.adapter.write_setting(tx['target'])
                if self.adapter.read_setting() != tx['target']:
                    raise TransactionBlocked('Read-back did not verify the proposed value')
                self._state(transaction_id,{'EXECUTING'},'VERIFIED')
            except Exception:
                self._state(transaction_id,{'VERIFIED_BACKUP','EXECUTING'},'QUARANTINED')
                raise TransactionBlocked('Transaction quarantined; inspect before recovery') from None
            return self.get(transaction_id)

    def revert(self,transaction_id):
        with self._exclusive():
            tx=self.get(transaction_id)
            if tx['state']=='REVERTED':
                return tx
            expected={'PREPARED','VERIFIED_BACKUP','VERIFIED','QUARANTINED','EXECUTING','REVERTING'}
            if tx['state'] not in expected:
                raise TransactionBlocked('Transaction is not recoverable from this state')
            try:
                current=self.adapter.read_setting()
                if current==tx['before']:
                    self._state(transaction_id,expected,'REVERTED')
                    return self.get(transaction_id)
                if current != tx['target']:
                    raise TransactionBlocked('External setting change detected')
                with self._db() as db:
                    executed=db.execute("SELECT 1 FROM events WHERE transaction_id=? AND state='EXECUTING' LIMIT 1",(transaction_id,)).fetchone()
                if not executed:
                    raise TransactionBlocked('No recorded execution; external state must be preserved')
                self._state(transaction_id,expected,'REVERTING')
                self.adapter.write_setting(tx['before'])
                if self.adapter.read_setting() != tx['before']:
                    raise TransactionBlocked('Restoration read-back did not match the snapshot')
                self._state(transaction_id,{'REVERTING'},'REVERTED')
            except Exception:
                self._state(transaction_id,expected,'QUARANTINED')
                raise TransactionBlocked('Recovery quarantined; external state was not overwritten') from None
            return self.get(transaction_id)
