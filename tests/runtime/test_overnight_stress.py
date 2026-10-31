"""ON §10 bounded idempotency/reconnect stress (SIMULATED_VERIFIED: fakes + tmp journal).

1. 100 concurrent invokes of one armed id dispatch exactly once, share one
   transaction id, and stay refused after a Router restart (same journal file).
2. 100 distinct live presses suspend at 3 (sticky); 50 stale/duplicate replays
   must not pollute the burst window (gap-3 regression).
3. 50 offline/online cycles each deliver exactly one queued press, no dup/loss.
No hardware, no model, no sleeps (clock jumps + bounded thread gates only).
"""
import threading
import unittest

from src.runtime.api_v2 import executor, remote_controls, router
from src.runtime.primitives import Executor
from src.runtime.remote_controls import BURST_WINDOW_S, RECONNECT_PROBE_S
from src.runtime.routing import RouteError, Router
from tests.runtime.test_remote_controls import KEY, FakeCompanion
from tests.runtime.test_routing import Base as RoutingBase
from tests.runtime.test_routing import Clock, world


class ConcurrentSameId(RoutingBase):
    def test_100_concurrent_same_id_dispatches_once_then_survives_restart(self):
        lease = self.router.arm({'skill_id': 'ble_scan_room',
                                 'route_id': self.routes()['selected_route_id'],
                                 'params': {'seconds': 8}, 'consent': True},
                                invocation_id='inv-' + 'f' * 32)
        gate = threading.Event()
        ex = executor(self.server)

        def slow(self_, key, params):
            gate.wait(10)
            self.calls.append('scan')
            return 'VERIFIED', None, {}, True, {}

        ex.RUNNERS = dict(ex.RUNNERS, relay_ble_scan=slow)
        out, errs = [], []

        def run():
            try:
                out.append(self.invoke(lease))
            except Exception as e:  # noqa: BLE001 - collected, asserted below
                errs.append(e)

        ths = [threading.Thread(target=run) for _ in range(100)]
        for t in ths:
            t.start()
        threading.Event().wait(0.3)
        gate.set()
        for t in ths:
            t.join(10)
        self.assertEqual(errs, [])
        self.assertEqual(self.calls, ['scan'])
        self.assertEqual(len(out), 100)
        self.assertEqual(len({o['transaction_id'] for o in out}), 1)
        fresh = Router(self.server)
        fresh.clock = self.clock
        with self.assertRaises(RouteError) as e:
            fresh.arm({'skill_id': 'ble_scan_room',
                       'route_id': self.routes()['selected_route_id'],
                       'params': {'seconds': 8}, 'consent': True},
                      invocation_id='inv-' + 'f' * 32)
        self.assertEqual(e.exception.code, 'DUPLICATE_REQUEST')
        self.assertEqual(self.calls, ['scan'])


class PressBurst(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        self.companion = FakeCompanion()
        self.companion.clock = self.clock
        self.server.relays.enroll('r-burst', KEY, 'h-tv-1',
                                  {'capabilities': ['remote_controls'], 'permissions': {}})
        self.server.relays.relays['r-burst']['send'] = self.companion
        self.calls = []

        def fake(self_, key, params):
            self.calls.append((key, params))
            return 'EXECUTED', None, None, True, {}

        ex = executor(self.server)
        ex.RUNNERS = dict(Executor.RUNNERS, device_action=fake)
        router(self.server).clock = self.clock
        self.rc = remote_controls(self.server)
        self.rc.clock = self.clock
        self.rc._ensure_thread = lambda: None
        st = self.rc.set_controls({'relay_id': 'r-burst', 'controls': [
            {'label': 'TV volume +', 'skill_id': 'tv_volume_step',
             'target': self.keys['tv'], 'params': {'direction': 'up'}}], 'consent': True})
        self.cid = st['controls'][0]['control_id']
        self.key = ('r-burst', self.cid)

    def live_press(self, rid):
        self.rc.process('r-burst', {'request_id': rid, 'control_id': self.cid,
                                    'pressed_at': int(self.clock() * 1000)})

    def test_100_distinct_presses_cap_at_3_and_replays_do_not_pollute(self):
        for i in range(100):
            self.live_press('%032x' % (i + 1))
            self.clock.t += 0.6
        self.assertEqual(len(self.calls), 3)                  # BURST=3, 4th suspends
        self.assertIn(self.key, self.rc.suspended)
        self.clock.t += 60                                    # window slides fully
        self.live_press('%032x' % 100001)
        self.assertEqual(len(self.calls), 3)                  # suspension is sticky
        before = list(self.rc._recent.get(self.key, []))
        for i in range(25):                                   # stale replays
            self.rc.process('r-burst', {'request_id': '%032x' % (200001 + i),
                                        'control_id': self.cid,
                                        'pressed_at': int((self.clock() - 61) * 1000)})
        for i in range(25):                                   # duplicate replays
            self.rc.process('r-burst', {'request_id': '%032x' % (i % 3 + 1),
                                        'control_id': self.cid,
                                        'pressed_at': int(self.clock() * 1000)})
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.rc._recent.get(self.key, []), before)
        bad = [e for e in self.rc.history if e['state'] in ('EXPIRED', 'DUPLICATE')]
        self.assertEqual(len(bad), 50)


class ReconnectStorm(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        self.companion = FakeCompanion()
        self.companion.clock = self.clock
        self.server.relays.enroll('r-flap', KEY, 'h-tv-1',
                                  {'capabilities': ['remote_controls'], 'permissions': {}})
        self.server.relays.relays['r-flap']['send'] = self.companion
        self.calls = []

        def fake(self_, key, params):
            self.calls.append((key, params))
            return 'EXECUTED', None, None, True, {}

        ex = executor(self.server)
        ex.RUNNERS = dict(Executor.RUNNERS, device_action=fake)
        router(self.server).clock = self.clock
        self.rc = remote_controls(self.server)
        self.rc.clock = self.clock
        self.rc._ensure_thread = lambda: None
        st = self.rc.set_controls({'relay_id': 'r-flap', 'controls': [
            {'label': 'TV volume +', 'skill_id': 'tv_volume_step',
             'target': self.keys['tv'], 'params': {'direction': 'up'}}], 'consent': True})
        self.cid = st['controls'][0]['control_id']

    def test_50_reconnect_cycles_no_dup_no_loss(self):
        relay = self.server.relays.relays['r-flap']
        for i in range(50):
            relay['online'] = False
            self.clock.t += RECONNECT_PROBE_S + 1
            rid = self.companion.press(self.cid)
            self.assertEqual(self.rc.poll_once(), 1)
            self.assertTrue(relay['online'])
            self.assertEqual(self.companion.results[-1]['request_id'], rid)
        self.assertEqual(len(self.calls), 50)
        self.assertLessEqual(len(self.rc.history), 100)
        states = {e['state'] for e in self.rc.history}
        self.assertFalse(states & {'DUPLICATE', 'UNCERTAIN', 'EXPIRED', 'SUSPENDED', 'REVOKED'})
        self.assertTrue(relay['online'])


if __name__ == '__main__':
    unittest.main()
