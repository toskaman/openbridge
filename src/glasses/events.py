"""HUD events and their scheduler (spec §6.2, §6.3, HUD-005).

Engines publish short events (message key + typed params, a priority, an expiry); the scheduler decides which one
is on the glasses. Rules:
- priority order CRITICAL > ACTION_RECEIPT > INTERACTION > SPORT > AMBIENT; a higher priority pre-empts;
- an expired event is dropped, never shown late;
- a new event with the same (event_type, source_id) replaces the previous one (coalescing, no pile-up);
- the queue is bounded; when full, the lowest-priority / oldest event is dropped and counted;
- when the current event ends, the screen underneath comes back.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

PRIORITIES = ('CRITICAL', 'ACTION_RECEIPT', 'INTERACTION', 'SPORT', 'AMBIENT')
MAX_QUEUE = 32


@dataclass
class HudEvent:
    event_type: str
    message_key: str
    priority: str = 'AMBIENT'
    params: dict = field(default_factory=dict)
    ttl_s: float = 8.0
    source_id: str = ''
    dismissible: bool = True
    requires_ack: bool = False
    created_at: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        if self.priority not in PRIORITIES:
            raise ValueError('priority must be one of %s' % (PRIORITIES,))

    @property
    def expires_at(self):
        return self.created_at + self.ttl_s

    @property
    def rank(self):
        return PRIORITIES.index(self.priority)

    def as_dict(self, locale_code=''):
        return {'schema_version': '1.0', 'event_id': self.event_id, 'event_type': self.event_type,
                'priority': self.priority, 'message_key': self.message_key, 'params': dict(self.params),
                'created_at': self.created_at, 'expires_at': self.expires_at, 'source_id': self.source_id,
                'dismissible': self.dismissible, 'requires_ack': self.requires_ack, 'locale': locale_code}


class Scheduler:
    def __init__(self, clock=time.time, max_queue=MAX_QUEUE):
        self.clock, self.max_queue = clock, max_queue
        self.queue: list[HudEvent] = []
        self.current: HudEvent | None = None
        self.dropped = 0
        self._lock = threading.Lock()

    def publish(self, ev: HudEvent):
        with self._lock:
            key = (ev.event_type, ev.source_id)
            if self.current and (self.current.event_type, self.current.source_id) == key:
                self.current = ev                     # refresh what is on screen in place
                return ev
            self.queue = [q for q in self.queue if (q.event_type, q.source_id) != key]
            self.queue.append(ev)
            while len(self.queue) > self.max_queue:
                worst = max(self.queue, key=lambda q: (q.rank, -q.created_at))
                self.queue.remove(worst)
                self.dropped += 1
            if self.current and ev.rank < self.current.rank:   # pre-emption: put the current one back
                self.queue.append(self.current)
                self.current = None
        return ev

    def ack(self, event_id=None):
        """Dismiss the event on screen (gesture). Events that require an explicit ack only go away here."""
        with self._lock:
            if self.current and (event_id is None or self.current.event_id == event_id):
                self.current = None

    def tick(self):
        """Expire, then pick what is shown now. Returns the current event or None (= show the normal screen)."""
        now = self.clock()
        with self._lock:
            if self.current and now >= self.current.expires_at and not self.current.requires_ack:
                self.current = None
            before = len(self.queue)
            self.queue = [q for q in self.queue if now < q.expires_at or q.requires_ack]
            self.dropped += before - len(self.queue)
            if self.current is None and self.queue:
                nxt = min(self.queue, key=lambda q: (q.rank, q.created_at))
                self.queue.remove(nxt)
                self.current = nxt
            return self.current
