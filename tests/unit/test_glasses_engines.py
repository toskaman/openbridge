"""Glasses engines: i18n, observations and freshness, HUD event scheduling, BLE sport sensors, sport sessions,
workouts, Ghost, GPX navigation and the ActiveLook transport core."""
import struct
import unittest

from src.glasses import i18n
from src.glasses import sport as S
from src.glasses.events import HudEvent, Scheduler
from src.glasses.metrics import Observation, Rejected, Store
from src.glasses.nav import Follower, GpxError, Route, parse_gpx, simulate
from src.glasses.sensors import CSC, CyclingPower, Sensor, battery, heart_rate, indoor_bike, rsc
from src.glasses.transport import Backoff, ControllerLock, FLOW_PAUSE, FLOW_RESUME, Transport


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class I18nTests(unittest.TestCase):
    def test_every_key_in_both_languages(self):
        self.assertEqual(i18n.missing(), {'fr': [], 'en': []})

    def test_spec_minimum_keys_exist(self):
        for k in ('common.ok', 'common.cancel', 'common.back', 'common.next', 'common.retry', 'common.connected',
                  'common.disconnected', 'common.unknown', 'common.unavailable', 'hud.battery', 'hud.gps_lost',
                  'hud.sensor_lost', 'hud.navigation.next_turn', 'hud.navigation.off_route', 'hud.navigation.arrival',
                  'hud.training.interval_start', 'hud.training.interval_end', 'hud.training.target_pace',
                  'hud.ghost.ahead', 'hud.ghost.behind', 'hud.safety.confirm', 'hud.safety.cancel',
                  'hud.safety.sos_pending', 'hud.action.verified', 'hud.action.unverified', 'hud.action.refused',
                  'settings.language', 'settings.hud_language', 'settings.units', 'voice.listening', 'voice.not_understood'):
            self.assertIn(k, i18n.table('en'), k)

    def test_resolve_and_format(self):
        self.assertEqual(i18n.resolve({'language': 'fr'}), ('fr', 'fr'))
        self.assertEqual(i18n.resolve({'language': 'fr', 'hud_language': 'en'}), ('fr', 'en'))
        self.assertEqual(i18n.t('hud.ghost.ahead', 'fr', gap='12 s'), "12 s d'avance")
        self.assertEqual(i18n.t('no.such.key', 'fr'), 'no.such.key')
        self.assertEqual(i18n.fmt_distance(1530, lang='fr'), '1,5 km')
        self.assertEqual(i18n.fmt_distance(152), '150 m')
        self.assertEqual(i18n.fmt_pace(303), '5:03')
        self.assertEqual(i18n.fmt_duration(3725), '1:02:05')
        self.assertEqual(i18n.fmt_distance(30, units='imperial'), '100 ft')

    def test_every_screen_fits_in_french(self):
        from src.glasses import preview
        names = [n for n, _ in preview.gallery(lang='fr')]
        self.assertIn('sport_nav_fr', names)


class MetricsTests(unittest.TestCase):
    def test_impossible_values_are_rejected(self):
        st = Store(clock=Clock())
        with self.assertRaises(Rejected):
            st.put(Observation('heart_rate_bpm', 400, 'hrm', 'ble_heart_rate', Clock()()))
        with self.assertRaises(Rejected):
            st.put(Observation('unknown_metric', 1, 'x', 'ble_x', Clock()()))
        self.assertEqual(st.rejected, 2)

    def test_stale_values_disappear_and_priority_falls_back(self):
        c = Clock()
        st = Store(clock=c)
        st.put(Observation('speed_mps', 3.0, 'pod', 'ble_rsc', c.t))
        st.put(Observation('speed_mps', 2.8, 'gnss', 'phone_gnss', c.t))
        self.assertEqual(st.value('speed_mps'), 3.0)          # BLE sensor first
        c.t += 6
        self.assertIsNone(st.value('speed_mps'))              # both stale: never shown as current
        self.assertEqual(st.state('speed_mps'), 'STALE')
        st.put(Observation('speed_mps', 2.9, 'gnss', 'phone_gnss', c.t))
        self.assertEqual(st.value('speed_mps'), 2.9)
        self.assertEqual(st.fresh('speed_mps').as_dict()['unit'], 'm/s')


class SchedulerTests(unittest.TestCase):
    def test_priority_expiry_coalescing(self):
        c = Clock()
        s = Scheduler(clock=c)
        s.publish(HudEvent('weather', 'hud.battery', 'AMBIENT', ttl_s=10, created_at=c.t))
        self.assertEqual(s.tick().event_type, 'weather')
        s.publish(HudEvent('nav.turn', 'hud.navigation.next_turn', 'INTERACTION', ttl_s=5, created_at=c.t))
        self.assertEqual(s.tick().event_type, 'nav.turn')     # pre-empts the ambient card
        s.publish(HudEvent('nav.turn', 'hud.navigation.next_turn', 'INTERACTION', {'distance': '50 m'}, ttl_s=5, created_at=c.t))
        self.assertEqual(s.current.params, {'distance': '50 m'})   # refreshed in place, no pile-up
        c.t += 6
        self.assertEqual(s.tick().event_type, 'weather')      # back to what was underneath
        c.t += 10
        self.assertIsNone(s.tick())                           # expired events are never shown late

    def test_bounded_and_ack(self):
        c = Clock()
        s = Scheduler(clock=c, max_queue=3)
        for i in range(6):
            s.publish(HudEvent('e%d' % i, 'common.ok', 'AMBIENT', created_at=c.t))
        self.assertEqual(len(s.queue), 3)
        self.assertEqual(s.dropped, 3)
        s.publish(HudEvent('sos', 'hud.safety.sos_pending', 'CRITICAL', {'n': 5}, requires_ack=True, created_at=c.t))
        self.assertEqual(s.tick().priority, 'CRITICAL')
        c.t += 100
        self.assertEqual(s.tick().event_type, 'sos')          # requires an explicit acknowledgement
        s.ack()
        self.assertIsNone(s.current)


class SensorTests(unittest.TestCase):
    def test_heart_rate_uint8_uint16_rr(self):
        self.assertEqual(heart_rate(bytes([0x00, 72]))['heart_rate_bpm'], 72)
        self.assertEqual(heart_rate(bytes([0x01]) + struct.pack('<H', 301))['heart_rate_bpm'], 301)
        d = heart_rate(bytes([0x16, 80]) + struct.pack('<HH', 1024, 512))
        self.assertEqual((d['rr_s'], d['contact']), ([1.0, 0.5], True))

    def test_rsc(self):
        d = rsc(bytes([0x07]) + struct.pack('<HB', 768, 170) + struct.pack('<H', 115) + struct.pack('<I', 12345))
        self.assertEqual(d, {'speed_mps': 3.0, 'cadence_spm': 170, 'running': True, 'stride_length_m': 1.15,
                             'distance_m': 1234.5})

    def test_csc_speed_cadence_and_rollover(self):
        c = CSC(wheel_circumference_m=2.0)
        pkt = lambda wr, wt, cr, ct: bytes([0x03]) + struct.pack('<IHHH', wr, wt, cr, ct)
        self.assertEqual(c.feed(pkt(100, 1000, 50, 1000)), {})
        d = c.feed(pkt(105, 2024, 51, 2024))                 # 5 revs x 2 m in 1 s; 1 crank rev in 1 s
        self.assertAlmostEqual(d['speed_mps'], 10.0)
        self.assertAlmostEqual(d['cadence_rpm'], 60.0)
        d = c.feed(pkt(110, (2024 + 1024) & 0xFFFF, 52, 65535))   # crank time wraps
        self.assertAlmostEqual(d['speed_mps'], 10.0)

    def test_power_ftms_battery_and_bad_bytes(self):
        cp = CyclingPower()
        self.assertEqual(cp.feed(struct.pack('<Hh', 0, 245))['power_w'], 245)
        flags = 0x0004 | 0x0040 | 0x0200                     # cadence, power, HR (speed present: bit 0 clear)
        d = indoor_bike(struct.pack('<HHHhB', flags, 3000, 180, 210, 150))
        self.assertAlmostEqual(d['speed_mps'], 30 / 3.6)
        self.assertEqual((d['cadence_rpm'], d['power_w'], d['heart_rate_bpm']), (90.0, 210, 150))
        self.assertEqual(battery(bytes([87])), {'battery_pct': 87})
        s = Sensor('heart_rate', 'hrm-1', clock=Clock())
        self.assertEqual(s.feed(b''), [])
        self.assertEqual(s.errors, 1)
        obs = s.feed(bytes([0x00, 140]))
        self.assertEqual((obs[0].metric, obs[0].value, obs[0].source_type), ('heart_rate_bpm', 140, 'ble_heart_rate'))


def square_route(side_m=300):
    lat0, lon0 = 45.0, 6.0
    mlat, mlon = 1 / 111320.0, 1 / (111320.0 * 0.7071)
    pts = []
    for dy, dx in ((0, 1), (1, 0), (0, -1)):
        start = pts[-1] if pts else (lat0, lon0)
        if not pts:
            pts.append(start)
        for k in range(1, 16):
            pts.append((start[0] + dy * side_m * k / 15 * mlat, start[1] + dx * side_m * k / 15 * mlon))
    return Route('U', pts)


class SportTests(unittest.TestCase):
    def test_session_distance_pace_laps_and_gps_jump(self):
        s = S.Session('run', lap_m=200)
        r = square_route()
        laps = []
        for p in simulate(r, 3.0, 0, 1.0):
            laps += s.add(p)
        self.assertAlmostEqual(s.distance_m, r.length_m, delta=5)
        self.assertAlmostEqual(s.pace_s_per_km, 1000 / 3.0, delta=5)
        self.assertEqual(len(laps), int(r.length_m // 200))
        before = s.distance_m
        s.add(S.Point(s.points[-1].t + 1, s.points[-1].lat + 0.01, s.points[-1].lon))   # 1.1 km in 1 s
        self.assertEqual(s.distance_m, before)
        s.add(S.Point(s.points[-1].t + 1, s.points[-1].lat, s.points[-1].lon, accuracy_m=80))
        self.assertEqual(s.skipped, 2)

    def test_workout_steps(self):
        w = S.Workout.intervals('2x400', 60, 2, 400, 30, 60, target_pace=240)
        self.assertEqual([x.kind for x in w.steps], ['warmup', 'work', 'recovery', 'work', 'cooldown'])
        ev = w.update(61, 150)
        self.assertEqual([e['type'] for e in ev], ['step_end', 'step_start'])
        self.assertEqual(w.remaining(100, 350), ('m', 200))
        w.update(200, 551)
        self.assertEqual(w.step.kind, 'recovery')

    def test_ghost(self):
        g = S.Ghost([(t, t * 3.0) for t in range(0, 1001, 10)], 'PB')
        c = g.compare(100, 330)                              # ghost needed 110 s for 330 m
        self.assertAlmostEqual(c['gap_s'], 10)
        self.assertAlmostEqual(c['gap_m'], 30)
        self.assertAlmostEqual(c['projected_finish_s'], 100 + (1000 - 110))
        self.assertIsNone(g.compare(2000, 5000)['gap_s'])
        self.assertEqual(S.hr_zone(165, 190), 4)
        self.assertIsNone(S.hr_zone(None, 190))


class NavTests(unittest.TestCase):
    def test_turns_follow_and_off_route(self):
        r = square_route()
        self.assertEqual([t['direction'] for t in r.turns], ['left', 'left'])
        f = Follower(r)
        out = f.update(*r.points[2], speed_mps=3)
        self.assertEqual(out['next_turn']['direction'], 'left')
        self.assertAlmostEqual(out['next_turn']['in_m'], 300 - 40, delta=6)
        self.assertAlmostEqual(out['eta_s'], out['remaining_m'] / 3)
        lat, lon = r.points[5]
        out = f.update(lat + 80 / 111320.0, lon)
        self.assertTrue(out['off_route'])
        self.assertEqual(out['events'][0]['type'], 'off_route')
        out = f.update(lat, lon)
        self.assertEqual(out['events'][0]['type'], 'back_on_route')

    def test_loop_does_not_jump_to_the_end(self):
        from src.glasses.preview import sample_route
        r = sample_route()
        f = Follower(r)
        arrivals = [i for i, p in enumerate(simulate(r, 3.3, 0, 1.0)) if f.update(p.lat, p.lon, 3.3)['events'][:1] == [{'type': 'arrival'}]]
        self.assertEqual(len(arrivals), 1)
        self.assertGreater(arrivals[0], 800)

    def test_gpx_parse_and_refusals(self):
        gpx = (b'<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><metadata><name>Tour</name></metadata>'
               b'<wpt lat="45.001" lon="6.001"><name>Eau</name><type>water</type></wpt><trk><trkseg>'
               b'<trkpt lat="45.0" lon="6.0"/><trkpt lat="45.0" lon="6.01"/><trkpt lat="45.01" lon="6.01"/></trkseg></trk></gpx>')
        r = parse_gpx(gpx)
        self.assertEqual((r.name, len(r.points), r.pois[0]['name']), ('Tour', 3, 'Eau'))
        self.assertEqual(r.reversed().points[0], r.points[-1])
        with self.assertRaises(GpxError):
            parse_gpx(b'<!DOCTYPE x [<!ENTITY a "aaaa">]><gpx>&a;</gpx>')
        with self.assertRaises(GpxError):
            parse_gpx(b'not xml')
        with self.assertRaises(GpxError):
            parse_gpx(b'<gpx><trk><trkseg><trkpt lat="45" lon="6"/></trkseg></trk></gpx>')


class TransportTests(unittest.TestCase):
    def test_mtu_flow_control_and_supersede(self):
        sent, c = [], Clock(0)
        tr = Transport(sent.append, mtu=23, clock=c)
        tr.submit(bytes(50), 'screen')
        tr.submit(bytes(10), 'update')
        tr.on_flow(FLOW_PAUSE)
        self.assertEqual(tr.pump(), 0)                       # nothing written while paused
        tr.on_flow(FLOW_RESUME)
        self.assertEqual(tr.pump(budget=1), 1)
        self.assertEqual(len(sent[0]), 20)                   # MTU 23 -> 20-byte ATT payload
        tr.submit(bytes([1]) * 30, 'screen')                 # the half-sent screen is not cut
        tr.submit(bytes([2]) * 30, 'screen')                 # but the queued one is replaced
        tr.pump()
        self.assertEqual(tr.stats['superseded'], 1)
        self.assertEqual(b''.join(sent), bytes(50) + bytes([2]) * 30 + bytes(10))
        self.assertTrue(tr.idle())

    def test_late_frames_are_dropped_and_queue_bounded(self):
        sent, c = [], Clock(0)
        tr = Transport(sent.append, clock=c, max_frames=4)
        tr.submit(b'x', 'ambient', max_delay_s=1)
        c.t = 5
        tr.pump()
        self.assertEqual((sent, tr.stats['dropped_late']), ([], 1))
        for _ in range(6):
            tr.submit(b'y', 'update')
        self.assertEqual(len(tr.queue), 4)
        tr.on_flow(0x03)                                     # unknown status: counted, short pause
        self.assertEqual(tr.stats['flow_errors'], 1)

    def test_backoff_and_single_controller(self):
        import tempfile
        from pathlib import Path
        b = Backoff(max_attempts=8)
        self.assertEqual([b.next_delay() for _ in range(9)], [1, 2, 4, 8, 16, 30, 30, 30, None])
        with tempfile.TemporaryDirectory() as d:
            c = Clock(1000)
            pc = ControllerLock('pc', Path(d) / 'lock.json', clock=c)
            phone = ControllerLock('phone', Path(d) / 'lock.json', clock=c)
            self.assertTrue(pc.acquire()[0])
            ok, holder = phone.acquire()
            self.assertFalse(ok)
            self.assertEqual(holder['owner'], 'pc')
            self.assertTrue(phone.acquire(takeover=True)[0])   # explicit switch
            c.t += 60
            self.assertTrue(pc.acquire()[0])                   # a silent holder expires


class LiveTests(unittest.TestCase):
    def test_engine_publishes_turns_laps_and_snapshot(self):
        from src.glasses.live import SportEngine
        c = Clock(0)
        eng = SportEngine('run', clock=c, max_hr=190)
        r = square_route()
        eng.set_route(r)
        eng.set_ghost(S.Ghost([(t, t * 2.5) for t in range(0, 600, 5)]))
        seen = set()
        for p in simulate(r, 3.0, 0, 1.0):
            c.t = p.t
            eng.gps(p)
            ev = eng.scheduler.tick()
            if ev:
                seen.add(ev.message_key)
        self.assertIn('hud.navigation.next_turn', seen)
        self.assertIn('hud.navigation.arrival', seen)
        snap = eng.snapshot()
        self.assertGreater(snap['ghost']['gap_s'], 0)         # faster than a 2.5 m/s ghost
        self.assertIsNone(snap['heart_rate'])                 # no sensor: no invented value


if __name__ == '__main__':
    unittest.main()
