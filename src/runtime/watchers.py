"""Safe automation: read-only watchers.

A watch re-runs the `read_facts` primitive on one device at a bounded interval and emits an event when a finding
crosses an owner-set threshold. Watchers never write, never chain into actions, and go through the Executor (schema,
identity re-check, per-device concurrency). They are session-scoped: stopped on server shutdown, capped in number,
interval and lifetime."""
import secrets
import threading
import time

OPS = {'lt': lambda a, b: a < b, 'le': lambda a, b: a <= b, 'gt': lambda a, b: a > b, 'ge': lambda a, b: a >= b,
       'eq': lambda a, b: a == b, 'ne': lambda a, b: a != b}
MAX_WATCHES = 16
MIN_INTERVAL_S = 30
MAX_INTERVAL_S = 3600
MAX_LIFETIME_S = 24 * 3600


class WatchError(ValueError):
    pass


class Watchers:
    def __init__(self, executor, clock=time.monotonic, sleep=None):
        self.ex = executor
        self.clock = clock
        self._stop = {}
        self.watches = {}
        self._lock = threading.Lock()
        self._sleep = sleep

    def start(self, device_key, finding, op, threshold, interval_s, lifetime_s=3600):
        if op not in OPS:
            raise WatchError('unknown comparison')
        if not isinstance(finding, str) or not finding.replace('_', '').isalnum() or len(finding) > 48:
            raise WatchError('invalid finding name')
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float, str)):
            raise WatchError('threshold must be a number or short text')
        if isinstance(threshold, str) and (len(threshold) > 32 or op not in ('eq', 'ne')):
            raise WatchError('text thresholds support eq/ne only')
        if not MIN_INTERVAL_S <= interval_s <= MAX_INTERVAL_S or not interval_s <= lifetime_s <= MAX_LIFETIME_S:
            raise WatchError('interval or lifetime out of bounds')
        with self._lock:
            if len([w for w in self.watches.values() if w['state'] == 'RUNNING']) >= MAX_WATCHES:
                raise WatchError('too many watches')
            wid = 'watch-' + secrets.token_hex(6)
            stop = threading.Event()
            self._stop[wid] = stop
            self.watches[wid] = {'watch_id': wid, 'device_key': device_key, 'finding': finding, 'op': op, 'threshold': threshold,
                                 'interval_s': interval_s, 'lifetime_s': lifetime_s, 'state': 'RUNNING', 'runs': 0,
                                 'last_value': None, 'last_state': None, 'triggered': 0, 'active': False}
        threading.Thread(target=self._loop, args=(wid, stop), daemon=True).start()
        return dict(self.watches[wid])

    def check_once(self, wid):
        w = self.watches[wid]
        r = self.ex.execute('read_facts', w['device_key'], {})
        w['runs'] += 1
        w['last_state'] = r['state']
        if r['state'] != 'VERIFIED':
            self.ex.emit('watch_unavailable', watch_id=wid, state=r['state'], errors=r['errors'][:1])
            return
        f = next((x for x in r['result'].get('facts', []) if x['name'] == w['finding']), None)
        if f is None:
            self.ex.emit('watch_unavailable', watch_id=wid, state='FINDING_ABSENT', errors=[])
            return
        w['last_value'] = f['value']
        try:
            hit = OPS[w['op']](f['value'], w['threshold'])
        except TypeError:
            hit = False
        if hit and not w['active']:            # edge-triggered: one event per crossing, not per poll
            w['triggered'] += 1
            self.ex.emit('watch_triggered', watch_id=wid, device_key=w['device_key'], finding=w['finding'],
                         value=f['value'], unit=f.get('unit', ''), op=w['op'], threshold=w['threshold'], finding_kind=f['kind'])
        elif not hit and w['active']:
            self.ex.emit('watch_cleared', watch_id=wid, finding=w['finding'], value=f['value'])
        w['active'] = hit

    def _loop(self, wid, stop):
        w = self.watches[wid]
        end = self.clock() + w['lifetime_s']
        while not stop.is_set() and self.clock() < end:
            try:
                self.check_once(wid)
            except Exception as e:      # a watcher must never crash the server
                self.ex.emit('watch_unavailable', watch_id=wid, state='ERROR', errors=[type(e).__name__])
            if (self._sleep or stop.wait)(w['interval_s']):
                break
        if w['state'] == 'RUNNING':
            w['state'] = 'STOPPED' if stop.is_set() else 'EXPIRED'

    def stop(self, wid):
        with self._lock:
            if wid not in self.watches:
                raise WatchError('unknown watch')
            self._stop[wid].set()
            self.watches[wid]['state'] = 'STOPPED'
        return dict(self.watches[wid])

    def stop_all(self):
        for wid in list(self.watches):
            if self.watches[wid]['state'] == 'RUNNING':
                self.stop(wid)

    def list(self):
        return [dict(w) for w in self.watches.values()]
