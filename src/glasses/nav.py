"""Navigation for the glasses: GPX routes, turn detection, route following, off-route, remaining distance and ETA.

HUD rule (spec §5.3): arrow + distance + short instruction. No map. Directions come from the route geometry;
street names are not invented when the route file has none.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from src.glasses.sport import bearing, haversine

MAX_GPX_BYTES = 5 * 1024 * 1024
OFF_ROUTE_M = 40.0
BACK_ON_ROUTE_M = 25.0
TURN_MIN_DEG = 30.0
TURN_WINDOW_M = 25.0


class GpxError(ValueError):
    pass


@dataclass
class Route:
    name: str
    points: list                      # [(lat, lon)]
    pois: list = field(default_factory=list)      # [{'name', 'lat', 'lon', 'kind'}]
    cum: list = field(default_factory=list)       # cumulative distance at each point
    turns: list = field(default_factory=list)     # [{'at_m', 'direction', 'angle'}]

    def __post_init__(self):
        if len(self.points) < 2:
            raise GpxError('a route needs at least two points')
        self.cum = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            self.cum.append(self.cum[-1] + haversine(a, b))
        self.turns = detect_turns(self.points, self.cum)

    @property
    def length_m(self):
        return self.cum[-1]

    def reversed(self):
        """Return-to-start: the same route, backwards (NAV-011)."""
        return Route(self.name + ' (return)', list(reversed(self.points)), list(self.pois))


def parse_gpx(data: bytes, name='Route') -> Route:
    """Track points (trkpt) or route points (rtept), plus waypoints as POIs. Entity declarations are refused
    (no DTD processing), the size is bounded."""
    if len(data) > MAX_GPX_BYTES:
        raise GpxError('GPX file larger than 5 MB')
    head = data[:4096].lower()
    if b'<!doctype' in head or b'<!entity' in data.lower():
        raise GpxError('GPX with a DTD or entities is refused')
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise GpxError('not a GPX file: %s' % e) from None
    pts, pois, title = [], [], None
    for el in root.iter():
        tag = el.tag.rsplit('}', 1)[-1]
        if tag in ('trkpt', 'rtept', 'wpt'):
            try:
                lat, lon = float(el.get('lat')), float(el.get('lon'))
            except (TypeError, ValueError):
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            if tag == 'wpt':
                nm = next((c.text for c in el if c.tag.rsplit('}', 1)[-1] == 'name'), None)
                kind = next((c.text for c in el if c.tag.rsplit('}', 1)[-1] in ('type', 'sym')), None)
                pois.append({'name': (nm or 'Waypoint')[:40], 'lat': lat, 'lon': lon, 'kind': (kind or '')[:20]})
            else:
                pts.append((lat, lon))
        elif tag == 'name' and title is None and el.text:
            title = el.text.strip()[:60]
    deduped = [p for i, p in enumerate(pts) if i == 0 or haversine(pts[i - 1], p) > 0.5]
    return Route(title or name, deduped, pois)


def _turn_name(delta):
    a = abs(delta)
    side = 'right' if delta > 0 else 'left'
    if a >= 150:
        return 'u_turn'
    if a >= 110:
        return 'sharp_' + side
    if a >= 50:
        return side
    return 'slight_' + side


def detect_turns(points, cum):
    """Heading change between the TURN_WINDOW_M before and after each point; local peaks above TURN_MIN_DEG."""
    n = len(points)
    cand = []
    for i in range(1, n - 1):
        j = i
        while j > 0 and cum[i] - cum[j] < TURN_WINDOW_M:
            j -= 1
        k = i
        while k < n - 1 and cum[k] - cum[i] < TURN_WINDOW_M:
            k += 1
        if j == i or k == i:
            continue
        b_in, b_out = bearing(points[j], points[i]), bearing(points[i], points[k])
        delta = (b_out - b_in + 540) % 360 - 180
        if abs(delta) >= TURN_MIN_DEG:
            cand.append((i, delta))
    turns = []
    for i, delta in cand:                              # keep the strongest point of each bend
        if turns and cum[i] - turns[-1]['at_m'] < TURN_WINDOW_M:
            if abs(delta) > abs(turns[-1]['angle']):
                turns[-1] = {'at_m': cum[i], 'direction': _turn_name(delta), 'angle': round(delta)}
            continue
        turns.append({'at_m': cum[i], 'direction': _turn_name(delta), 'angle': round(delta)})
    return turns


def _project(p, a, b):
    """Closest point of segment a-b to p, in a local flat frame (fine at these distances). Returns (t, dist_m)."""
    lat0 = math.radians(p[0])
    kx, ky = math.cos(lat0) * 111320.0, 110540.0
    ax, ay = (a[1] - p[1]) * kx, (a[0] - p[0]) * ky
    bx, by = (b[1] - p[1]) * kx, (b[0] - p[0]) * ky
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
    return t, math.hypot(ax + t * dx, ay + t * dy)


class Follower:
    """Where the wearer is on the route: along-route distance, next turn, off-route state, remaining, ETA."""

    def __init__(self, route: Route):
        self.route = route
        self.along = 0.0
        self.off_route = False
        self.arrived = False
        self._seg = 0

    def update(self, lat, lon, speed_mps=None):
        r, p = self.route, (lat, lon)
        cands = []
        for i in range(len(r.points) - 1):
            t, d = _project(p, r.points[i], r.points[i + 1])
            cands.append((d, i, t))
        best_d = min(c[0] for c in cands)
        # Loops and out-and-back routes pass the same place twice: among the segments about as close as the best,
        # keep the one nearest to where we were along the route, so progress never jumps to the end.
        near = [c for c in cands if c[0] <= best_d + 15.0]
        d_, i_, t_ = min(near, key=lambda c: abs(r.cum[c[1]] + c[2] * (r.cum[c[1] + 1] - r.cum[c[1]]) - self.along))
        best = (i_, d_, t_)
        i, dist, t = best
        self._seg = i
        self.along = r.cum[i] + t * (r.cum[i + 1] - r.cum[i])
        events = []
        if not self.off_route and dist > OFF_ROUTE_M:
            self.off_route = True
            events.append({'type': 'off_route', 'distance_m': dist})
        elif self.off_route and dist < BACK_ON_ROUTE_M:
            self.off_route = False
            events.append({'type': 'back_on_route'})
        remaining = max(0.0, r.length_m - self.along)
        if not self.arrived and remaining < 20 and self.along > 0.8 * r.length_m:
            self.arrived = True
            events.append({'type': 'arrival'})
        nxt = next((tr for tr in r.turns if tr['at_m'] > self.along + 3), None)
        nearest_poi = None
        for poi in r.pois:
            d = haversine(p, (poi['lat'], poi['lon']))
            if nearest_poi is None or d < nearest_poi[1]:
                nearest_poi = (poi, d)
        return {
            'along_m': self.along, 'off_route': self.off_route, 'off_by_m': dist, 'remaining_m': remaining,
            'eta_s': remaining / speed_mps if speed_mps and speed_mps > 0.3 else None,
            'next_turn': None if nxt is None else {'direction': nxt['direction'], 'in_m': nxt['at_m'] - self.along},
            'nearest_poi': None if nearest_poi is None else {'name': nearest_poi[0]['name'], 'distance_m': nearest_poi[1]},
            'events': events,
        }


def simulate(route: Route, speed_mps, t0, step_s=1.0, accuracy_m=4.0, jitter_m=0.0, seed=7):
    """Points moving along a route at a constant speed: for demos and tests, labelled SIMULATED wherever shown."""
    import random
    from src.glasses.sport import Point
    rng = random.Random(seed)
    d, t, i = 0.0, t0, 0
    while d <= route.length_m:
        while i < len(route.cum) - 2 and route.cum[i + 1] < d:
            i += 1
        a, b = route.points[i], route.points[i + 1]
        seg = route.cum[i + 1] - route.cum[i]
        f = 0.0 if seg == 0 else (d - route.cum[i]) / seg
        lat, lon = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        if jitter_m:
            lat += rng.gauss(0, jitter_m) / 111320.0
            lon += rng.gauss(0, jitter_m) / (111320.0 * max(0.2, math.cos(math.radians(lat))))
        yield Point(t, lat, lon, accuracy_m)
        d += speed_mps * step_s
        t += step_s
