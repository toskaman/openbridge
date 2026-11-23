"""Sport engines: activity session (run / ride), structured workouts and Ghost Competition.

Inputs are timestamped GPS points (phone GNSS) and sensor observations; outputs are numbers for the HUD and
HudEvents (lap, step changes, ghost gap). No medical claim, no invented metric: a value the sources do not give
stays None.
"""
from __future__ import annotations

import bisect
import math
import time
from dataclasses import dataclass, field

R_EARTH = 6371008.8


def haversine(a, b):
    """Metres between (lat, lon) points."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(h)))


def bearing(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


@dataclass
class Point:
    t: float                    # epoch seconds
    lat: float
    lon: float
    accuracy_m: float = 5.0
    alt: float | None = None


class Session:
    """One activity. Distance from GPS (points with poor accuracy or impossible jumps are skipped), moving time
    (stopped below MOVING_MPS), smoothed pace / speed, automatic laps every lap_m."""
    MAX_ACCURACY_M = 30.0
    MOVING_MPS = 0.5
    MAX_SPEED_MPS = {'run': 12.0, 'ride': 30.0, 'hike': 4.0}

    def __init__(self, sport='run', lap_m=1000.0, started_at=None):
        self.sport, self.lap_m = sport, lap_m
        self.started_at = started_at
        self.points: list[Point] = []
        self.distance_m = 0.0
        self.moving_s = 0.0
        self.track = []                # (elapsed_s, distance_m): what a ghost replays later
        self.laps = []                 # lap durations (s)
        self._lap_start = (0.0, 0.0)   # (elapsed, distance)
        self._window = []              # recent (t, distance) for smoothing
        self.skipped = 0

    def add(self, p: Point):
        """Returns a list of event dicts (e.g. {'type': 'lap', 'n': 3, 'time_s': 312})."""
        events = []
        if self.started_at is None:
            self.started_at = p.t
        if p.accuracy_m > self.MAX_ACCURACY_M:
            self.skipped += 1
            return events
        if self.points:
            prev = self.points[-1]
            dt = p.t - prev.t
            if dt <= 0:
                return events
            d = haversine((prev.lat, prev.lon), (p.lat, p.lon))
            if d / dt > self.MAX_SPEED_MPS.get(self.sport, 30.0):
                self.skipped += 1          # GPS jump: ignore the point, keep the previous one
                return events
            self.distance_m += d
            if d / dt >= self.MOVING_MPS:
                self.moving_s += dt
        self.points.append(p)
        elapsed = p.t - self.started_at
        self.track.append((elapsed, self.distance_m))
        self._window.append((p.t, self.distance_m))
        while len(self._window) > 2 and self._window[-1][0] - self._window[0][0] > 15:
            self._window.pop(0)
        if self.distance_m - self._lap_start[1] >= self.lap_m:
            lap_time = elapsed - self._lap_start[0]
            self.laps.append(lap_time)
            self._lap_start = (elapsed, self._lap_start[1] + self.lap_m)
            events.append({'type': 'lap', 'n': len(self.laps), 'time_s': lap_time})
        return events

    @property
    def elapsed_s(self):
        return (self.points[-1].t - self.started_at) if self.points else 0.0

    @property
    def speed_mps(self):
        """Smoothed over the last ~15 s."""
        if len(self._window) < 2:
            return None
        (t0, d0), (t1, d1) = self._window[0], self._window[-1]
        return (d1 - d0) / (t1 - t0) if t1 > t0 else None

    @property
    def pace_s_per_km(self):
        v = self.speed_mps
        return 1000.0 / v if v and v >= self.MOVING_MPS else None

    @property
    def avg_pace_s_per_km(self):
        return 1000.0 * self.moving_s / self.distance_m if self.distance_m > 50 else None


def hr_zone(bpm, max_hr):
    """Zone 1-5 by % of the owner's max heart rate (50/60/70/80/90 %). None without both values."""
    if not bpm or not max_hr:
        return None
    pct = bpm / max_hr
    return 1 if pct < 0.6 else 2 if pct < 0.7 else 3 if pct < 0.8 else 4 if pct < 0.9 else 5


# ------------------------------------------------------------------ structured workouts

@dataclass
class Step:
    kind: str                     # warmup | work | recovery | cooldown
    duration_s: float = 0.0       # one of duration_s / distance_m
    distance_m: float = 0.0
    target_pace_s_per_km: float | None = None


@dataclass
class Workout:
    name: str
    steps: list[Step]
    index: int = 0
    _start: tuple = (0.0, 0.0)    # (elapsed, distance) at the start of the current step
    done: bool = False

    @classmethod
    def intervals(cls, name, warmup_s, reps, work_m, recovery_s, cooldown_s, target_pace=None):
        steps = [Step('warmup', duration_s=warmup_s)]
        for i in range(reps):
            steps.append(Step('work', distance_m=work_m, target_pace_s_per_km=target_pace))
            if i < reps - 1:
                steps.append(Step('recovery', duration_s=recovery_s))
        steps.append(Step('cooldown', duration_s=cooldown_s))
        return cls(name, steps)

    @property
    def step(self):
        return None if self.done else self.steps[self.index]

    def remaining(self, elapsed, distance):
        s = self.step
        if s is None:
            return None
        if s.distance_m:
            return ('m', max(0.0, s.distance_m - (distance - self._start[1])))
        return ('s', max(0.0, s.duration_s - (elapsed - self._start[0])))

    def update(self, elapsed, distance):
        """Advance through finished steps; returns events ('step_end' / 'step_start' / 'workout_done')."""
        events = []
        while not self.done:
            unit, left = self.remaining(elapsed, distance)
            if left > 0:
                break
            events.append({'type': 'step_end', 'kind': self.step.kind, 'n': self.index + 1})
            self._start = (elapsed, distance)
            self.index += 1
            if self.index >= len(self.steps):
                self.done = True
                events.append({'type': 'workout_done'})
            else:
                events.append({'type': 'step_start', 'kind': self.step.kind, 'n': self.index + 1})
        return events


# ------------------------------------------------------------------ Ghost Competition

class Ghost:
    """A previous activity replayed against the current one: gap in time at the same distance, and in distance at
    the same time. Positive gap = the wearer is ahead."""

    def __init__(self, track, name='Ghost'):
        pts = sorted((float(t), float(d)) for t, d in track)
        if len(pts) < 2:
            raise ValueError('a ghost needs at least two points')
        self.name = name
        self.times = [t for t, _ in pts]
        self.dists = [d for _, d in pts]
        for i in range(1, len(self.dists)):          # distances never go backwards
            self.dists[i] = max(self.dists[i], self.dists[i - 1])

    @property
    def total_m(self):
        return self.dists[-1]

    @property
    def total_s(self):
        return self.times[-1]

    def time_at(self, distance):
        if distance <= self.dists[0]:
            return self.times[0]
        if distance >= self.dists[-1]:
            return None                               # beyond the ghost's activity
        i = bisect.bisect_left(self.dists, distance)
        d0, d1, t0, t1 = self.dists[i - 1], self.dists[i], self.times[i - 1], self.times[i]
        return t0 + (t1 - t0) * (distance - d0) / (d1 - d0) if d1 > d0 else t0

    def distance_at(self, elapsed):
        if elapsed >= self.times[-1]:
            return self.dists[-1]
        i = bisect.bisect_right(self.times, elapsed)
        if i == 0:
            return self.dists[0]
        t0, t1, d0, d1 = self.times[i - 1], self.times[i], self.dists[i - 1], self.dists[i]
        return d0 + (d1 - d0) * (elapsed - t0) / (t1 - t0) if t1 > t0 else d0

    def compare(self, elapsed, distance):
        g_t = self.time_at(distance)
        gap_s = None if g_t is None else g_t - elapsed
        gap_m = distance - self.distance_at(elapsed)
        projection = None
        if distance > 100 and distance < self.total_m:
            projection = elapsed + (self.total_s - (g_t or elapsed)) if g_t is not None else None
        return {'gap_s': gap_s, 'gap_m': gap_m, 'projected_finish_s': projection, 'ghost_name': self.name}
