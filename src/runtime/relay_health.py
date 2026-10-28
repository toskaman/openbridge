"""Relay observation ledger: provenance, freshness, staleness, rotating-address policy and anti-spoofing flags.

Relay reports are untrusted. Nothing here decides anything: it annotates observations with where/when they came from
and raises INFERRED flags (with their basis) that the UI and the policy engine can show or use to refuse."""
import hashlib
import threading
import time
from collections import deque
from statistics import median

STALE_S = 120            # an advertiser not re-seen for 2 min is stale
ROUTE_STALE_S = 300      # a relay without a successful scan for 5 min is a stale route
RSSI_JUMP_DB = 40        # jump between two scans of the same relay < 30 s apart
ROTATING = ('resolvable_private', 'non_resolvable', 'random', 'unknown')
MAX_ENTRIES = 2000


def _fp(o):
    """Payload fingerprint used to group a rotating-address device across rotations (weak hint only)."""
    raw = f"{sorted(o['company_ids'])}|{sorted(o['service_uuids'])}|{o['name']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


class RelayLedger:
    def __init__(self, clock=time.time):
        self.clock = clock
        self._lock = threading.Lock()
        self.entries = deque(maxlen=MAX_ENTRIES)       # (t, relay_id, addr_hash, fp, rssi, kind, name, company_ids)
        self.routes = {}                               # relay_id -> {'last_success_at', 'scans', 'failures'}

    @staticmethod
    def _addr(address):
        return hashlib.sha256(address.lower().encode()).hexdigest()[:16]

    def record(self, relay_id, observations):
        t = self.clock()
        with self._lock:
            for o in observations:
                self.entries.append((t, relay_id, self._addr(o['address']), _fp(o), o.get('rssi'), o.get('address_kind', 'unknown'),
                                     o.get('name', ''), tuple(o.get('company_ids') or ())))
            r = self.routes.setdefault(relay_id, {'last_success_at': None, 'scans': 0, 'failures': 0})
            r['last_success_at'], r['scans'] = t, r['scans'] + 1

    def proved(self, relay_id):
        """A signed reply from the relay (pairing confirmation or status read-back) re-proves the route without a scan."""
        with self._lock:
            self.routes.setdefault(relay_id, {'last_success_at': None, 'scans': 0, 'failures': 0})['last_proof_at'] = self.clock()

    def failure(self, relay_id):
        with self._lock:
            self.routes.setdefault(relay_id, {'last_success_at': None, 'scans': 0, 'failures': 0})['failures'] += 1

    def route_status(self, relay_id, online=True):
        r = self.routes.get(relay_id)
        if not online:
            return 'OFFLINE'
        if not r or r['last_success_at'] is None:
            return 'NEVER_SUCCEEDED'
        return 'STALE' if self.clock() - r['last_success_at'] > ROUTE_STALE_S else 'FRESH'

    def advertisers(self, known_names=()):
        """One row per address (static) or per payload fingerprint (rotating), with provenance and flags."""
        now = self.clock()
        with self._lock:
            entries = list(self.entries)
        groups = {}
        for e in entries:
            t, rid, addr, fp, rssi, kind, name, cids = e
            gid = ('addr:' + addr) if kind in ('public', 'static_random') else ('rot:' + fp)
            groups.setdefault(gid, []).append(e)
        out = []
        known = {n.lower() for n in known_names if n}
        for gid, es in groups.items():
            last = max(x[0] for x in es)
            rssis = [x[4] for x in es if x[4] is not None]
            flags = []
            by_relay = {}
            for x in sorted(es):
                by_relay.setdefault(x[1], []).append(x)
            for rid, xs in by_relay.items():
                for a, b in zip(xs, xs[1:]):
                    if a[4] is not None and b[4] is not None and b[0] - a[0] < 30 and abs(a[4] - b[4]) >= RSSI_JUMP_DB:
                        flags.append({'flag': 'rssi_jump', 'basis': f'{abs(a[4]-b[4])} dB in {round(b[0]-a[0])} s from one relay'}); break
            if gid.startswith('addr:') and len({x[7] for x in es}) > 1:
                flags.append({'flag': 'inconsistent_payload', 'basis': 'same static address advertised different company ids'})
            names = {x[6].lower() for x in es if x[6]}
            if gid.startswith('rot:') and names & known:
                flags.append({'flag': 'name_collision', 'basis': 'rotating advertiser uses the name of a strongly identified device'})
            rotating = gid.startswith('rot:')
            out.append({'id': gid, 'rotating': rotating, 'addresses_seen': len({x[2] for x in es}),
                        'identity': 'weak (rotating address, grouped by payload)' if rotating else 'address',
                        'relays': sorted(by_relay), 'first_seen_s_ago': round(now - min(x[0] for x in es)),
                        'last_seen_s_ago': round(now - last), 'stale': now - last > STALE_S,
                        'rssi_median': median(rssis) if rssis else None, 'samples': len(es),
                        'flags': [dict(f, kind='INFERRED') for f in flags]})
        return sorted(out, key=lambda a: (a['stale'], a['last_seen_s_ago']))

    def samples(self, group_id, since_s=None):
        """Per-relay RSSI samples of ONE advertiser group the owner selected (calibration / zone estimate only)."""
        now = self.clock()
        with self._lock:
            entries = list(self.entries)
        out = []
        for t, rid, addr, fp, rssi, kind, name, cids in entries:
            gid = ('addr:' + addr) if kind in ('public', 'static_random') else ('rot:' + fp)
            if gid == group_id and rssi is not None and (since_s is None or now - t <= since_s):
                out.append({'t': t, 'relay_id': rid, 'rssi': rssi})
        return out
