"""ActiveLook transport core (spec §3.4, CONN-002/003/014): what goes to the glasses, in which order, at what pace.

BLE-agnostic and unit-tested; the Bluetooth links (PC bleak, phone Companion) only move bytes.
- one bounded queue with priorities; a newer full-screen redraw replaces an older one not yet sent (no backlog of
  stale screens); a frame older than its deadline is dropped and counted, never sent late;
- writes are cut to the negotiated MTU (ATT payload = MTU - 3), never larger;
- flow control: nothing is written while the glasses say PAUSE; writing resumes on RESUME. Other status bytes are
  counted as errors and pause briefly. (Byte values follow the ActiveLook API docs as we read them; to be confirmed on
  the real ENGO 3 before claiming them.)
- reconnection with a bounded exponential back-off;
- a single controller: one OpenBridge process at a time owns the glasses; taking over is explicit.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

FLOW_RESUME, FLOW_PAUSE = 0x01, 0x02
PRIORITY = {'critical': 0, 'screen': 1, 'update': 2, 'ambient': 3}
MAX_FRAMES = 64
BACKOFF_S = (1, 2, 4, 8, 16, 30)


class Transport:
    def __init__(self, write, mtu=23, clock=time.monotonic, max_frames=MAX_FRAMES):
        """write(chunk: bytes) -> None sends one BLE write without response."""
        self.write, self.clock, self.max_frames = write, clock, max_frames
        self.set_mtu(mtu)
        self.queue = []                       # [priority, seq, kind, deadline, bytearray remaining]
        self.paused = False
        self._pause_until = 0.0
        self._seq = 0
        self.stats = {'frames': 0, 'chunks': 0, 'bytes': 0, 'dropped_late': 0, 'dropped_full': 0,
                      'superseded': 0, 'flow_errors': 0, 'pauses': 0}

    def set_mtu(self, mtu):
        self.chunk = max(20, int(mtu) - 3)

    def submit(self, data: bytes, kind='screen', max_delay_s=2.0):
        """Queue one frame (or a whole screen). kind 'screen' replaces any queued, not-yet-started screen."""
        if kind not in PRIORITY:
            raise ValueError('kind must be one of %s' % sorted(PRIORITY))
        if kind == 'screen':
            keep = []
            for q in self.queue:
                if q[2] == 'screen' and q[5] == 0:          # never cut a screen already half-sent
                    self.stats['superseded'] += 1
                else:
                    keep.append(q)
            self.queue = keep
        self._seq += 1
        self.queue.append([PRIORITY[kind], self._seq, kind, self.clock() + max_delay_s, bytearray(data), 0])
        self.queue.sort(key=lambda q: (q[0], q[1]))
        while len(self.queue) > self.max_frames:
            worst = max(self.queue, key=lambda q: (q[0], q[1]))
            self.queue.remove(worst)
            self.stats['dropped_full'] += 1

    def on_flow(self, status: int):
        if status == FLOW_PAUSE:
            if not self.paused:
                self.stats['pauses'] += 1
            self.paused = True
        elif status == FLOW_RESUME:
            self.paused = False
        else:
            self.stats['flow_errors'] += 1
            self._pause_until = self.clock() + 0.2

    def pump(self, budget=64):
        """Send up to `budget` chunks. Returns how many were written."""
        sent = 0
        while sent < budget and self.queue and not self.paused and self.clock() >= self._pause_until:
            q = self.queue[0]
            if q[5] == 0 and self.clock() > q[3]:
                self.queue.pop(0)
                self.stats['dropped_late'] += 1
                continue
            piece = bytes(q[4][:self.chunk])
            self.write(piece)
            del q[4][:self.chunk]
            q[5] += len(piece)
            sent += 1
            self.stats['chunks'] += 1
            self.stats['bytes'] += len(piece)
            if not q[4]:
                self.queue.pop(0)
                self.stats['frames'] += 1
        return sent

    def idle(self):
        return not self.queue


class Backoff:
    def __init__(self, schedule=BACKOFF_S, max_attempts=12):
        self.schedule, self.max_attempts, self.attempt = schedule, max_attempts, 0

    def next_delay(self):
        """Seconds to wait before the next attempt, or None when we give up (the owner reconnects by hand)."""
        if self.attempt >= self.max_attempts:
            return None
        d = self.schedule[min(self.attempt, len(self.schedule) - 1)]
        self.attempt += 1
        return d

    def reset(self):
        self.attempt = 0


def controller_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'glasses_controller.json'


class ControllerLock:
    """Only one OpenBridge controller drives the glasses (the ENGO accept one central). Heartbeat-based: a lock not
    refreshed for STALE_S belongs to nobody. Taking over a live lock needs takeover=True (an explicit owner choice)."""
    STALE_S = 15

    def __init__(self, owner, path=None, clock=time.time):
        self.owner, self.path, self.clock = owner, Path(path or controller_path()), clock

    def holder(self):
        try:
            d = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        return d if self.clock() - d.get('beat', 0) <= self.STALE_S else None

    def acquire(self, takeover=False):
        h = self.holder()
        if h and h.get('owner') != self.owner and not takeover:
            return False, h
        self.beat()
        return True, h

    def beat(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps({'owner': self.owner, 'beat': self.clock()}), encoding='utf-8')
        os.replace(tmp, self.path)

    def release(self):
        h = self.holder()
        if h and h.get('owner') == self.owner:
            self.path.write_text(json.dumps({'owner': None, 'beat': 0}), encoding='utf-8')
