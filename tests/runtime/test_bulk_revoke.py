"""Scenario C: bulk revoke semantics (SIMULATED_VERIFIED, FakeCompanion).

"Remove all OpenBridge controls from my watch" = set_controls([]):
grants die server-side under a generation guard, the device is told
to clear its UI, and stale presses can never dispatch afterwards.
"""
import unittest

from src.fabric import relay as R
from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.runtime.api_v2 import executor, remote_controls, router
from src.runtime.primitives import Executor
from tests.runtime.test_remote_controls import FakeCompanion
from tests.runtime.test_routing import Clock, world

KEY = R.derive_key('654321', 'rn', 'pn')
VOL = {'label': 'TV volume +', 'skill_id': 'tv_volume_step',
       'params': {'direction': 'up'}}


class BulkRevoke(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        reg = self.server.fabric_registry
        w = reg.upsert([Identifier('android_serial', 'watch-1', True)],
                       category='watch', label='SM-L310',
                       observations=[DeviceObservation(
                           'model', 'SM-L310', 'ADB', 'WIFI', now(), True)])
        reg.devices[w]['handles'] = {'WIFI': 'h-watch-1'}
        reg.link(Link('pc', w, 'WIFI', ('observe', 'read', 'control'),
                      'ADB:device'))
        self.server.fabric_snapshot = reg.snapshot()
        self.companion = FakeCompanion()
        self.companion.clock = self.clock
        self.server.relays.enroll('r-watch', KEY, 'h-watch-1',
                                  {'capabilities': ['remote_controls'],
                                   'permissions': {}})
        self.server.relays.relays['r-watch']['send'] = self.companion
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

    def _grant(self, controls):
        body = {'relay_id': 'r-watch', 'consent': True, 'controls': [
            dict(c, target=self.keys['tv']) for c in controls]}
        return self.rc.set_controls(body)['controls']

    def test_empty_panel_revoke_is_clean(self):
        st = self.rc.set_controls({'relay_id': 'r-watch', 'controls': [],
                                   'consent': True})
        self.assertEqual(st['controls'], [])
        self.assertEqual(self.companion.controls, [])

    def test_duplicate_definitions_collapse_to_one_grant(self):
        got = self._grant([VOL, dict(VOL)])
        self.assertEqual(len(got), 1)
        self.assertEqual(self.rc.state()['controls'][0]['label'],
                         'TV volume +')

    def test_offline_revoke_kills_grants_and_stays_loud(self):
        got = self._grant([VOL])
        cid = got[0]['control_id']

        def down(relay, message):
            raise R.RelayError('unreachable')

        self.server.relays.relays['r-watch']['send'] = down
        with self.assertRaises(R.RelayError):
            self.rc.set_controls({'relay_id': 'r-watch', 'controls': [],
                                  'consent': True})
        self.assertEqual(self.rc.state()['controls'], [])
        # reconnect: the stale on-device button still cannot dispatch
        self.server.relays.relays['r-watch']['send'] = self.companion
        self.companion.press(cid)
        self.assertEqual(self.rc.poll_once(), 0)
        self.assertEqual(self.calls, [])

    def test_repeat_revoke_is_idempotent(self):
        self._grant([VOL])
        for _ in range(2):
            st = self.rc.set_controls({'relay_id': 'r-watch',
                                       'controls': [], 'consent': True})
            self.assertEqual(st['controls'], [])
        self.assertEqual(self.companion.controls, [])


if __name__ == '__main__':
    unittest.main()
