"""Coordinated, atomic local runtime state. Existing unreadable state never means first run.

All readers/writers cooperate through a path-scoped thread lock and OS file lock.
Unique temporary files are flushed before replacement. No automatic corruption reset.
Receipt merges retain other writers and acknowledgement tombstones prevent resurrection.
This stores completed unresolved outcomes plus a pre-dispatch invocation journal: an id is
claimed EXECUTING before any dispatch and marked DONE after, so a crash or a second process
can never cause a blind re-execution of the same id (DONE refuses as duplicate, a leftover
EXECUTING refuses as uncertain).
"""
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

VERSION = 1
MAX_BYTES = 16 * 1024 * 1024
INVOCATION_DONE_TTL_S = 600          # mirrors InvocationLedger.ttl_s: finished ids stay refused that long
INVOCATION_EXECUTING_TTL_S = 86400   # a leftover EXECUTING row refuses re-execution for a day (ids are single-use)
MAX_INVOCATIONS = 4096               # mirrors the in-memory caps; beyond this new claims fail closed
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()

class StateError(OSError):
    def __init__(self, code, detail):
        super().__init__(f'{code}: {detail}')
        self.code = code

class StateStore:
    def __init__(self, path):
        self.path = Path(path).resolve()
        with _LOCKS_GUARD:
            self._lock = _LOCKS.setdefault(os.path.normcase(str(self.path)), threading.Lock())

    @classmethod
    def for_server(cls, server):
        p = getattr(getattr(server, 'session_journal', None), 'path', None)
        return cls(Path(p).with_name('runtime-state.json')) if p else None

    @contextmanager
    def _locked(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.with_suffix('.lock').open('a+b') as handle:
                if os.fstat(handle.fileno()).st_size == 0:
                    handle.write(b'0'); handle.flush()
                deadline = time.monotonic() + 5
                while True:
                    try:
                        handle.seek(0)
                        if os.name == 'nt':
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise StateError('STATE_LOCK_FAILED', 'Runtime state is busy; operations are blocked') from None
                        time.sleep(.01)
                try:
                    yield
                finally:
                    handle.seek(0)
                    if os.name == 'nt':
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _validate(d):
        from src.runtime.routing import SKILLS
        from src.runtime.primitives import PRIMITIVES, Executor
        if not isinstance(d, dict) or type(d.get('version')) is not int or d['version'] != VERSION:
            raise ValueError('unsupported version')
        policies = d.get('policies', {})
        if not isinstance(policies, dict): raise ValueError('invalid policies')
        for sid, p in policies.items():
            if sid not in SKILLS or not isinstance(p, dict): raise ValueError('invalid policy')
            mode, failover = p.get('mode'), p.get('failover')
            if mode not in ('AUTO', 'PREFERRED', 'PINNED') or failover not in ('none', 'idempotent_read_retry'):
                raise ValueError('invalid policy')
            if failover != 'none' and not (SKILLS[sid]['idempotent'] and SKILLS[sid]['reversibility'] == 'NONE'):
                raise ValueError('invalid failover')
            if mode == 'PINNED' and not (isinstance(p.get('pinned_route_id'), str) and p['pinned_route_id'].startswith('rt-')):
                raise ValueError('invalid pinned route')
            preferred = p.get('preferred', [])
            if not isinstance(preferred, list) or len(preferred) > 32 or not all(isinstance(x, str) for x in preferred):
                raise ValueError('invalid preferences')
        rows = d.get('unresolved', [])
        if not isinstance(rows, list): raise ValueError('invalid unresolved receipts')
        seen = set()
        for r in rows:
            if not isinstance(r, dict): raise ValueError('invalid receipt')
            tx, primitive = r.get('transaction_id'), r.get('primitive_id')
            if not isinstance(tx, str) or not tx or len(tx) > 96 or tx in seen: raise ValueError('invalid receipt id')
            seen.add(tx)
            if primitive not in PRIMITIVES or PRIMITIVES[primitive].reversibility == 'NONE' or r.get('state') not in Executor.UNRESOLVED:
                raise ValueError('invalid unresolved state')
            for field in ('before', 'after', 'device_key', 'verified', 'started_at', 'finished_at'):
                if field not in r: raise ValueError('incomplete receipt')
            if not isinstance(r['device_key'], str) or not r['device_key'] or len(r['device_key']) > 64 or r['verified'] is not False:
                raise ValueError('invalid receipt fields')
            if not all(isinstance(r[k], str) and r[k] for k in ('started_at','finished_at')):
                raise ValueError('invalid receipt times')
            if not isinstance(r.get('errors', []), list) or not all(isinstance(x, str) for x in r.get('errors', [])):
                raise ValueError('invalid receipt errors')
        ack = d.get('acknowledged', [])
        if not isinstance(ack, list) or not all(isinstance(x, str) and x and len(x) <= 96 for x in ack):
            raise ValueError('invalid acknowledgements')
        invs = d.get('invocations', [])
        if not isinstance(invs, list) or len(invs) > MAX_INVOCATIONS:
            raise ValueError('invalid invocations')
        seen_inv = set()
        for r in invs:
            if not isinstance(r, dict):
                raise ValueError('invalid invocation')
            actor, iid = r.get('actor'), r.get('invocation_id')
            if not isinstance(actor, str) or not actor or len(actor) > 128:
                raise ValueError('invalid invocation actor')
            if not isinstance(iid, str) or not iid or len(iid) > 96 or (actor, iid) in seen_inv:
                raise ValueError('invalid invocation id')
            seen_inv.add((actor, iid))
            fp = r.get('fingerprint')
            if fp is not None and (not isinstance(fp, str) or len(fp) != 64):
                raise ValueError('invalid invocation fingerprint')
            if r.get('state') not in ('EXECUTING', 'DONE'):
                raise ValueError('invalid invocation state')
            if r.get('state') == 'DONE' and (fp is None or not isinstance(r.get('finished_at'), (int, float))
                                             or isinstance(r.get('finished_at'), bool)):
                raise ValueError('finished invocation needs a fingerprint and finish time')
            if not isinstance(r.get('started_at'), (int, float)) or isinstance(r.get('started_at'), bool):
                raise ValueError('invalid invocation time')
            fa = r.get('finished_at')
            if fa is not None and (not isinstance(fa, (int, float)) or isinstance(fa, bool)):
                raise ValueError('invalid invocation time')
        return d

    def _read(self):
        try:
            with self.path.open('rb') as handle:
                raw = handle.read(MAX_BYTES + 1)
        except FileNotFoundError:
            return {'version': VERSION}
        if len(raw) > MAX_BYTES: raise ValueError('state size limit')
        return self._validate(json.loads(raw.decode('utf-8')))

    def load(self):
        try:
            with self._locked(): return self._read()
        except StateError: raise
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise StateError('STATE_UNREADABLE', f'Cannot verify saved runtime state ({type(error).__name__}); preserve the file for review') from None

    def _write(self, d):
        self._validate(d)
        raw = json.dumps(d, sort_keys=True, allow_nan=False).encode('utf-8')
        if len(raw) > MAX_BYTES: raise OSError('state size limit')
        name = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix=self.path.name+'.', suffix='.tmp', delete=False) as handle:
                name = handle.name; handle.write(raw); handle.flush(); os.fsync(handle.fileno())
            os.replace(name, self.path)
            if os.name != 'nt':
                fd = os.open(self.path.parent, os.O_RDONLY)
                try: os.fsync(fd)
                finally: os.close(fd)
        finally:
            if name and os.path.exists(name): os.unlink(name)

    def _mutate(self, change):
        try:
            with self._locked():
                try: d = self._read()
                except (OSError, ValueError, TypeError, KeyError):
                    raise StateError('STATE_UNREADABLE', 'Saved runtime state cannot be verified; no update was applied') from None
                change(d)
                self._write(d)
        except StateError: raise
        except (OSError, ValueError, TypeError) as error:
            raise StateError('STATE_WRITE_FAILED', f'Runtime state was not confirmed durable ({type(error).__name__})') from None

    def update(self, **fields):
        self._mutate(lambda d: d.update(fields, version=VERSION))

    def set_policy(self, skill_id, policy):
        self._mutate(lambda d: d.setdefault('policies', {}).__setitem__(skill_id, policy))

    def update_layouts(self, fn):
        def change(d):
            fn(d.setdefault('explorer_layouts', {}))
        self._mutate(change)

    def save_unresolved(self, rows, acknowledged=()):
        def change(d):
            ack = set(d.get('acknowledged', [])) | set(acknowledged)
            saved = {r['transaction_id']: r for r in d.get('unresolved', [])}
            saved.update({r['transaction_id']: r for r in rows})
            d['unresolved'] = [r for tx, r in saved.items() if tx not in ack]
            d['acknowledged'] = sorted(ack)
        self._mutate(change)

    @staticmethod
    def _prune_invocations(invs, now):
        return [r for r in invs
                if not (r['state'] == 'DONE' and now - r['finished_at'] > INVOCATION_DONE_TTL_S)
                and not (r['state'] == 'EXECUTING' and now - r['started_at'] > INVOCATION_EXECUTING_TTL_S)]

    def claim_invocation(self, actor, invocation_id, now):
        """Pre-dispatch journal claim: the atomic cross-process admission for an invocation id.

        Returns (True, None) when this call inserted the EXECUTING row and the caller may dispatch,
        else (False, row) with the existing DONE/EXECUTING entry and the caller must refuse."""
        out = {}

        def change(d):
            invs = self._prune_invocations(d.get('invocations', []), now)
            for r in invs:
                if r['actor'] == actor and r['invocation_id'] == invocation_id:
                    d['invocations'] = invs
                    out['row'] = r
                    return
            if len(invs) >= MAX_INVOCATIONS:
                d['invocations'] = invs
                raise StateError('STATE_JOURNAL_FULL', 'invocation journal is full; retry after entries expire')
            d['invocations'] = invs + [{'actor': actor, 'invocation_id': invocation_id, 'fingerprint': None,
                                        'state': 'EXECUTING', 'started_at': now, 'finished_at': None}]
            out['row'] = None
        self._mutate(change)
        return (out['row'] is None), out['row']

    def finish_invocation(self, actor, invocation_id, fingerprint, now):
        """EXECUTING -> DONE compare-and-set. True iff this call transitioned the row; a missing or
        already-DONE row is left untouched (another joiner of the same invocation finished it)."""
        out = {}

        def change(d):
            invs = self._prune_invocations(d.get('invocations', []), now)
            out['done'] = False
            for r in invs:
                if r['actor'] == actor and r['invocation_id'] == invocation_id and r['state'] == 'EXECUTING':
                    r['fingerprint'], r['state'], r['finished_at'] = fingerprint, 'DONE', now
                    out['done'] = True
            d['invocations'] = invs
        self._mutate(change)
        return out['done']

    def load_invocations(self, now):
        """Pruned journal view for boot load (read-only; pruning is persisted by the next write)."""
        return list(self._prune_invocations(self.load().get('invocations', []), now))
