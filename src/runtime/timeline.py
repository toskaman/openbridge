"""Cross-transport fact timeline (V4-01).

One ordered, bounded, in-memory record of what each device/source reported and when. It is fed only by read paths
that already exist (read_facts receipts, executor events such as watcher crossings or ADB re-attach, relay route
status). It never triggers a read or a write itself.

Only *transitions* are kept per (device, fact): a value that repeats is folded into `last_confirmed_at` of the
current entry, so a 10-minute capture stays small and every row means "this changed here". Values are the
diagnostic findings already produced by src/runtime/diagnostics.py, which never include serials, MACs, SSIDs,
keys or IP addresses.
"""
import threading
import time
from collections import deque
from datetime import datetime, timezone

MAX_ENTRIES = 4000
# Executor events that are themselves facts about a link or a watch (not receipts of reads).
EVENT_FACTS = ('watch_triggered', 'watch_cleared', 'watch_unavailable', 'reattached')
LINK_ERRORS = ('DEVICE_UNAVAILABLE', 'IDENTITY_CHANGED', 'NOT_READABLE')


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec='seconds')


class Timeline:
    def __init__(self, clock=time.time, max_entries=MAX_ENTRIES):
        self.clock = clock
        self._lock = threading.Lock()
        self.entries = deque(maxlen=max_entries)
        self._seq = 0
        self._current = {}            # (device_key, name) -> entry (latest value)

    # ---------------- ingestion ----------------
    def _add(self, device_key, category, source, name, value, kind, t, prev=None, unit='', fact_kind='OBSERVED'):
        self._seq += 1
        e = {'id': f'f{self._seq}', 't': t, 'at': _iso(t), 'device_key': device_key, 'category': category,
             'source': str(source)[:80], 'name': name, 'value': value, 'unit': unit, 'previous': prev,
             'kind': kind, 'fact_kind': fact_kind, 'last_confirmed_at': _iso(t)}
        self.entries.append(e)
        return e

    def observe(self, device_key, category, name, value, source='', unit='', fact_kind='OBSERVED', t=None):
        """Record one value. Returns the new entry when the value changed (or is first seen), else None."""
        t = self.clock() if t is None else t
        with self._lock:
            cur = self._current.get((device_key, name))
            if cur is not None and cur['value'] == value:
                cur['last_confirmed_at'] = _iso(t)
                return None
            kind = 'first' if cur is None else 'change'
            e = self._add(device_key, category, source, name, value, kind, t, None if cur is None else cur['value'], unit, fact_kind)
            self._current[(device_key, name)] = e
            return e

    def ingest_receipt(self, device_key, category, receipt, t=None):
        """Feed one read_facts receipt. A refused/failed read is itself a fact about the link."""
        t = self.clock() if t is None else t
        state = receipt.get('state')
        if state in ('VERIFIED', 'PARTIAL'):
            for f in (receipt.get('result') or {}).get('facts', []):
                if isinstance(f.get('value'), (dict, list)):
                    continue                       # structured INFERRED summaries are not timeline values
                self.observe(device_key, category, f['name'], f['value'], f.get('source', ''), f.get('unit', ''), f.get('kind', 'OBSERVED'), t)
            lost = bool((receipt.get('result') or {}).get('lost_link'))
            self.observe(device_key, category, 'link', 'lost' if lost else 'up', 'read_facts receipt', t=t)
        else:
            code = next((err.split(':')[0] for err in receipt.get('errors', ())), '')
            if code in LINK_ERRORS:
                self.observe(device_key, category, 'link', 'lost' if code != 'IDENTITY_CHANGED' else 'identity_changed',
                             f'read_facts {code}', t=t)

    def ingest_event(self, event, category='', t=None):
        if event.get('kind') not in EVENT_FACTS:
            return None
        t = self.clock() if t is None else t
        dev = event.get('device_key', '')
        name = 'event_' + event['kind']
        with self._lock:              # events are discrete: always appended, never folded
            return self._add(dev, category, 'executor event', name,
                             {k: v for k, v in event.items() if k in ('finding', 'value', 'op', 'threshold', 'state')} or True,
                             'event', t, fact_kind='OBSERVED')

    def ingest_routes(self, rows, t=None):
        for r in rows:
            self.observe(r.get('device_key', ''), 'relay', f"relay_route_{r.get('relay_id', '')[:16]}", r.get('status'), 'relay ledger', t=t)

    # ---------------- reads ----------------
    def rows(self, device_key=None, since_s=None, limit=500):
        now = self.clock()
        with self._lock:
            es = [dict(e) for e in self.entries]
        if device_key:
            es = [e for e in es if e['device_key'] == device_key]
        if since_s is not None:
            es = [e for e in es if now - e['t'] <= since_s]
        return es[-limit:]

    def current(self, device_key, name):
        e = self._current.get((device_key, name))
        return None if e is None else e['value']
