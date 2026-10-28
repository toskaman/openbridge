"""Device registry with conservative identity resolution.

Rules: observations merge into one device only when they share a STRONG identifier of the same kind.
Weak signals (same IP, same name, randomized MAC) only create a 'possible_same' hint; they never merge
and never let an action target a different device."""
import threading
import uuid
from src.fabric.contracts import DeviceObservation, Identifier, Capability, Link, LINK_GRANTS, now

MAX_DEVICES = 2000
# More specific evidence wins: a TV that also speaks HomeKit stays a TV.
CATEGORY_RANK = {'unknown': 0, 'ble': 1, 'iot': 2, 'nas': 3, 'printer': 3, 'media': 4, 'computer': 5, 'hub': 5, 'android': 5,
                 'network': 5, 'apple': 5, 'vacuum': 6, 'phone': 6, 'watch': 6, 'tv': 6, 'router': 7}
MAX_OBSERVATIONS_PER_DEVICE = 200


class Registry:
    def __init__(self):
        self._lock = threading.RLock()
        self.devices = {}        # key -> {'key','category','label','identifiers':set,'observations':{},'capabilities':{},'last_seen'}
        self.links = {}          # (parent, child, transport, source) -> Link
        self.hints = set()       # frozenset({key_a, key_b}) weak possible-same pairs

    def _by_identifier(self, ident):
        for key, dev in self.devices.items():
            if ident in dev['identifiers']:
                return key
        return None

    def upsert(self, identifiers, *, category='unknown', label='Device', observations=(), weak=()):
        """Return the device key. `weak` are (kind, value) hints such as IP or announced name."""
        with self._lock:
            strong = [i for i in identifiers if i.strong]
            matches = {self._by_identifier(i) for i in strong} - {None}
            if len(matches) > 1:
                # Strong identifiers disagree: refuse to merge; record a new device and hint the conflict.
                key = self._new(category, label)
                for other in matches:
                    self.hints.add(frozenset((key, other)))
            elif matches:
                key = matches.pop()
            else:
                key = self._new(category, label)
            dev = self.devices[key]
            dev['identifiers'].update(identifiers)
            if CATEGORY_RANK.get(category, 0) > CATEGORY_RANK.get(dev['category'], 0):
                dev['category'] = category
            if label and dev['label'] in ('Device', '') :
                dev['label'] = label
            for obs in observations:
                self.observe(key, obs)
            for kind, value in weak:
                for other, odev in self.devices.items():
                    if other != key and (kind, value) in odev['weak']:
                        self.hints.add(frozenset((key, other)))
                dev['weak'].add((kind, value))
            dev['last_seen'] = now()
            return key

    def _new(self, category, label):
        if len(self.devices) >= MAX_DEVICES:
            raise OverflowError('Device registry limit reached')
        key = 'dev-' + uuid.uuid4().hex[:12]
        self.devices[key] = {'key': key, 'category': category, 'label': label, 'identifiers': set(),
                             'weak': set(), 'observations': {}, 'capabilities': {}, 'last_seen': now()}
        return key

    def observe(self, key, obs: DeviceObservation):
        with self._lock:
            dev = self.devices[key]
            bucket = dev['observations'].setdefault(obs.key, {})
            bucket[obs.source] = obs        # keep distinct sources; never overwrite another source's view
            if sum(len(b) for b in dev['observations'].values()) > MAX_OBSERVATIONS_PER_DEVICE:
                raise OverflowError('Too many observations for one device')

    def capability(self, key, cap: Capability):
        with self._lock:
            self.devices[key]['capabilities'][(cap.name, cap.via)] = cap

    def link(self, link: Link):
        if not set(link.grants) <= set(LINK_GRANTS):
            raise ValueError('Unknown link grant')
        with self._lock:
            self.links[(link.parent, link.child, link.transport, link.source)] = link

    def best_value(self, key, field):
        """Prefer verified direct reads over third-party reports; never invent missing fields."""
        obs = self.devices[key]['observations'].get(field)
        if not obs:
            return None
        return sorted(obs.values(), key=lambda o: (o.verified, o.confidence, o.observed_at), reverse=True)[0]

    def snapshot(self):
        with self._lock:
            devices = []
            for dev in self.devices.values():
                devices.append({'key': dev['key'], 'category': dev['category'], 'label': dev['label'],
                    'identifier_kinds': sorted({i.kind for i in dev['identifiers']}),
                    'facts': {f: {'value': self.best_value(dev['key'], f).value,
                                  'sources': sorted(o.source for o in obs.values()),
                                  'verified': self.best_value(dev['key'], f).verified,
                                  'observed_at': self.best_value(dev['key'], f).observed_at}
                              for f, obs in dev['observations'].items()},
                    'capabilities': [vars(c) for c in dev['capabilities'].values()],
                    'handles': dict(dev.get('handles', {})), 'last_seen': dev['last_seen']})
            links = [vars(l) | {'grants': list(l.grants)} for l in self.links.values()]
            hints = [sorted(h) for h in self.hints]
            for d in devices:
                d['possibly_same_as'] = sorted(o for h in self.hints if d['key'] in h for o in h if o != d['key'])
            return {'schema_version': 1, 'devices': devices, 'links': links, 'possible_duplicates': hints}
