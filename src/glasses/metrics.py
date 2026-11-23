"""Normalised observations with source, time, unit, quality and freshness (spec §6.1, §6.4, SENSOR-007/008/011).

Every value shown on the glasses comes from here. A value past its time-to-live is *stale* and is returned as None
(the screen shows "—"), never as if it were current. Impossible values are rejected, not clamped.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

SCHEMA_VERSION = '1.0'

# metric -> (unit, ttl seconds, plausible min, plausible max)
METRICS = {
    'heart_rate_bpm': ('bpm', 5.0, 25, 240),
    'speed_mps': ('m/s', 5.0, 0, 40),
    'cadence_rpm': ('rpm', 3.0, 0, 250),            # cycling crank cadence
    'cadence_spm': ('spm', 3.0, 0, 260),            # running steps per minute
    'power_w': ('W', 3.0, 0, 2500),
    'distance_m': ('m', 10.0, 0, 1_000_000),
    'altitude_m': ('m', 10.0, -500, 9000),
    'latitude_deg': ('deg', 5.0, -90, 90),
    'longitude_deg': ('deg', 5.0, -180, 180),
    'gps_accuracy_m': ('m', 5.0, 0, 5000),
    'battery_pct': ('%', 120.0, 0, 100),
    'stride_length_m': ('m', 5.0, 0, 4),
    'temperature_c': ('°C', 900.0, -60, 70),
}
QUALITIES = ('valid', 'estimated', 'degraded')


@dataclass
class Observation:
    metric: str
    value: float
    source_id: str
    source_type: str
    measured_at: float
    received_at: float = field(default_factory=time.time)
    quality: str = 'valid'
    confidence: float = 1.0
    profile: str = ''
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def unit(self):
        return METRICS[self.metric][0]

    @property
    def ttl_s(self):
        return METRICS[self.metric][1]

    def as_dict(self):
        return {'schema_version': SCHEMA_VERSION, 'event_id': self.event_id, 'kind': 'metric', 'metric': self.metric,
                'value': self.value, 'unit': self.unit, 'source_id': self.source_id, 'source_type': self.source_type,
                'measured_at': self.measured_at, 'received_at': self.received_at, 'quality': self.quality,
                'confidence': self.confidence, 'ttl_ms': int(self.ttl_s * 1000), 'profile': self.profile}


class Rejected(ValueError):
    pass


def validate(o: Observation):
    if o.metric not in METRICS:
        raise Rejected('unknown metric %r' % o.metric)
    if isinstance(o.value, bool) or not isinstance(o.value, (int, float)) or o.value != o.value:
        raise Rejected('value must be a number')
    _, _, lo, hi = METRICS[o.metric]
    if not lo <= o.value <= hi:
        raise Rejected('%s=%s outside plausible range %s..%s' % (o.metric, o.value, lo, hi))
    if o.quality not in QUALITIES:
        raise Rejected('quality must be one of %s' % (QUALITIES,))
    if not 0 <= o.confidence <= 1:
        raise Rejected('confidence must be 0..1')
    return o


class Store:
    """Latest value per metric with source priority. A higher-priority source wins while it is fresh; when it goes
    stale, the next fresh source takes over (SENSOR-008), and the provenance is kept."""

    def __init__(self, priority=('ble_', 'phone_'), clock=time.time):
        self.priority, self.clock = tuple(priority), clock
        self._by = {}            # metric -> {source_id: Observation}
        self._lock = threading.Lock()
        self.rejected = 0

    def _rank(self, o):
        for i, p in enumerate(self.priority):
            if o.source_type.startswith(p):
                return i
        return len(self.priority)

    def put(self, o: Observation):
        try:
            validate(o)
        except Rejected:
            self.rejected += 1
            raise
        with self._lock:
            self._by.setdefault(o.metric, {})[o.source_id] = o
        return o

    def fresh(self, metric):
        """The best fresh observation for a metric, or None."""
        now = self.clock()
        with self._lock:
            obs = [o for o in self._by.get(metric, {}).values() if now - o.measured_at <= o.ttl_s]
        if not obs:
            return None
        return sorted(obs, key=lambda o: (self._rank(o), -o.measured_at))[0]

    def value(self, metric):
        o = self.fresh(metric)
        return None if o is None else o.value

    def state(self, metric):
        """READY | STALE | UNAVAILABLE for a metric."""
        if self.fresh(metric):
            return 'READY'
        with self._lock:
            return 'STALE' if self._by.get(metric) else 'UNAVAILABLE'
