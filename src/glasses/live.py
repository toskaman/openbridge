"""Live sport engine: turns GPS points and sensor observations into what the sport screens show, and into HUD
events (laps, workout steps, navigation turns, off-route, ghost overtakes) for the scheduler.

Sources (spec §2, PHONE-001, SENSOR-*): phone GNSS through the Companion, BLE sensors through the phone or this PC,
or a simulation (a GPX replayed at a chosen speed, always labelled SIMULATED in evidence).
"""
from __future__ import annotations

import time

from src.glasses import sport as S
from src.glasses.events import HudEvent, Scheduler
from src.glasses.metrics import Observation, Rejected, Store
from src.glasses.nav import Follower, Route
from src.glasses.i18n import fmt_distance, fmt_duration

TURN_ANNOUNCE_M = (200, 50)


class SportEngine:
    def __init__(self, sport='run', clock=time.time, scheduler=None, max_hr=None, units='metric', lang='en'):
        self.clock = clock
        self.store = Store(clock=clock)
        self.session = S.Session(sport)
        self.scheduler = scheduler or Scheduler(clock=clock)
        self.workout: S.Workout | None = None
        self.ghost: S.Ghost | None = None
        self.follower: Follower | None = None
        self.max_hr, self.units, self.lang = max_hr, units, lang
        self.nav = {}
        self._announced = set()
        self._ghost_ahead = None

    # ---- setup
    def set_route(self, route: Route):
        self.follower = Follower(route)
        self._announced.clear()

    def set_workout(self, workout: S.Workout):
        self.workout = workout

    def set_ghost(self, ghost: S.Ghost):
        self.ghost = ghost
        self._ghost_ahead = None

    # ---- inputs
    def observe(self, o: Observation):
        try:
            self.store.put(o)
        except Rejected:
            return False
        return True

    def gps(self, p: S.Point):
        for name, val in (('latitude_deg', p.lat), ('longitude_deg', p.lon), ('gps_accuracy_m', min(p.accuracy_m, 5000))):
            self.observe(Observation(name, val, 'phone-gnss', 'phone_gnss', p.t))
        for ev in self.session.add(p):
            if ev['type'] == 'lap':
                self._pub('sport.lap', 'hud.training.interval_end', 'SPORT',
                          {'step': '%s %d · %s' % ('Km' if self.session.lap_m == 1000 else 'Lap', ev['n'], fmt_duration(ev['time_s']))})
        if self.session.speed_mps is not None:
            self.observe(Observation('speed_mps', self.session.speed_mps, 'phone-gnss', 'phone_gnss', p.t, quality='estimated'))
        if self.follower:
            self.nav = self.follower.update(p.lat, p.lon, self.session.speed_mps)
            self.nav['arrived'] = self.follower.arrived
            self._nav_events(self.nav)
        if self.workout:
            for ev in self.workout.update(self.session.elapsed_s, self.session.distance_m):
                if ev['type'] == 'step_start':
                    self._pub('training.step', 'hud.training.interval_start', 'INTERACTION',
                              {'step': self._step_name(ev['kind'])}, ttl=6)
                elif ev['type'] == 'workout_done':
                    self._pub('training.step', 'hud.training.done', 'INTERACTION', {}, ttl=10)
        if self.ghost:
            g = self.ghost.compare(self.session.elapsed_s, self.session.distance_m)
            if g['gap_s'] is not None:
                ahead = g['gap_s'] >= 0
                if self._ghost_ahead is not None and ahead != self._ghost_ahead and abs(g['gap_s']) >= 2:
                    self._pub('ghost.cross', 'hud.ghost.ahead' if ahead else 'hud.ghost.behind', 'SPORT',
                              {'gap': fmt_duration(abs(g['gap_s']))})
                if abs(g['gap_s']) >= 2:
                    self._ghost_ahead = ahead

    def _step_name(self, kind):
        from src.glasses.i18n import t
        return t('hud.training.' + kind, self.lang)

    def _nav_events(self, nav):
        from src.glasses.i18n import t
        for ev in nav.get('events', ()):
            if ev['type'] == 'off_route':
                self._pub('nav.route', 'hud.navigation.off_route', 'INTERACTION', {}, ttl=6)
            elif ev['type'] == 'back_on_route':
                self._pub('nav.route', 'hud.navigation.back_on_route', 'INTERACTION', {}, ttl=4)
            elif ev['type'] == 'arrival':
                self._pub('nav.route', 'hud.navigation.arrival', 'INTERACTION', {}, ttl=8)
        turn = nav.get('next_turn')
        if turn and not nav.get('off_route'):
            for limit in TURN_ANNOUNCE_M:
                key = (round(self.follower.along + turn['in_m']), limit)
                if turn['in_m'] <= limit and key not in self._announced:
                    self._announced.add(key)
                    self._pub('nav.turn', 'hud.navigation.next_turn', 'INTERACTION',
                              {'direction': t('hud.dir.' + turn['direction'], self.lang),
                               'distance': fmt_distance(turn['in_m'], self.units, self.lang)}, ttl=5)
                    break

    def _pub(self, etype, key, prio, params, ttl=4.0):
        self.scheduler.publish(HudEvent(etype, key, prio, params, ttl_s=ttl, source_id='sport',
                                        created_at=self.clock()))

    # ---- output for the screens
    def snapshot(self):
        st = self.store
        hr = st.value('heart_rate_bpm')
        out = {
            'gps': st.state('latitude_deg'),
            'distance_m': self.session.distance_m if self.session.points else None,
            'elapsed_s': self.session.elapsed_s if self.session.points else None,
            'speed_mps': st.value('speed_mps'),
            'pace_s_per_km': self.session.pace_s_per_km if st.value('speed_mps') is not None else None,
            'heart_rate': hr, 'hr_zone': S.hr_zone(hr, self.max_hr),
            'cadence': st.value('cadence_spm') if self.session.sport == 'run' else st.value('cadence_rpm'),
            'power': st.value('power_w'),
            'lap_n': len(self.session.laps) or None,
            'last_lap_s': self.session.laps[-1] if self.session.laps else None,
        }
        if self.follower:
            out['nav'] = self.nav
        if self.ghost:
            g = self.ghost.compare(self.session.elapsed_s, self.session.distance_m)
            g.update(total_m=self.ghost.total_m, ghost_m=self.ghost.distance_at(self.session.elapsed_s))
            out['ghost'] = g
        if self.workout:
            w = self.workout
            if w.done:
                out['workout'] = {'done': True}
            else:
                out['workout'] = {'kind': w.step.kind, 'n': w.index + 1, 'total': len(w.steps),
                                  'remaining': w.remaining(self.session.elapsed_s, self.session.distance_m),
                                  'target_pace': w.step.target_pace_s_per_km}
        return out
