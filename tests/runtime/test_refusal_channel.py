"""§9 refusal channel: every refused press lands in state()['history'] with a
server-composed 'reason', exposed by GET /api/v2/remote_controls for the dashboard.

RED: history entries carry 'state' but no human-readable reason; the dashboard
cannot show WHY a press was refused (revoked? expired? suspended?).
"""
import unittest

from src.runtime import api_v2
from src.runtime.api_v2 import executor, remote_controls, router
from src.runtime.primitives import Executor
from src.runtime.remote_controls import REQUEST_TTL_S
from tests.runtime.test_remote_controls import KEY, FakeCompanion
from tests.runtime.test_routing import Clock, world
from src.fabric import relay as R
from src.fabric.contracts import DeviceObservation, Identifier, Link, now


class RefusalChannel(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        reg = self.server.fabric_registry
        w = reg.upsert([Identifier('android_serial', 'watch-1', True)], category='watch', label='SM-L310',
                       observations=[DeviceObservation('model', 'SM-L310', 'ADB', 'WIFI', now(), True)])
        reg.devices[w]['handles'] = {'WIFI': 'h-watch-1'}
        reg.link(Link('pc', w, 'WIFI', ('observe', 'read', 'control'), 'ADB:device'))
        self.server.fabric_snapshot = reg.snapshot()
        self.companion = FakeCompanion()
        self.companion.clock = self.clock
        self.server.relays.enroll('r-watch', KEY, 'h-watch-1', {'capabilities': ['remote_controls'], 'permissions': {}})
        self.server.relays.relays['r-watch']['send'] = self.companion
        router(self.server).clock = self.clock
        self.rc = remote_controls(self.server)
        self.rc.clock = self.clock
        self.rc._ensure_thread = lambda: None
        st = self.rc.set_controls({'relay_id': 'r-watch', 'controls': [
            {'label': 'TV volume +', 'skill_id': 'tv_volume_step', 'target': self.keys['tv'],
             'params': {'direction': 'up'}}], 'consent': True})
        self.cid = st['controls'][0]['control_id']

    def test_expired_press_records_structured_reason(self):
        rid = self.companion.press(self.cid)
        self.companion.queue[-1]['pressed_at'] -= (REQUEST_TTL_S + 5) * 1000
        self.assertEqual(self.rc.poll_once(), 1)
        entry = self.rc.state()['history'][-1]
        self.assertEqual(entry['state'], 'EXPIRED')
        self.assertEqual(entry['request_id'], rid)
        self.assertIn('reason', entry)                       # RED: missing today
        self.assertIn('too old', entry['reason'])
        self.assertLessEqual(len(entry['reason']), 80)

    def test_route_exposes_refusal_reason(self):
        self.companion.press(self.cid)
        self.companion.queue[-1]['pressed_at'] -= (REQUEST_TTL_S + 5) * 1000
        self.rc.poll_once()
        code, payload = api_v2.get(self.server, '/api/v2/remote_controls', {})
        self.assertEqual(code, 200)
        entry = payload['history'][-1]
        self.assertEqual(entry['state'], 'EXPIRED')
        self.assertIn('reason', entry)                       # RED: missing today

    def test_reason_never_carries_device_free_text(self):
        rid = self.companion.press(self.cid, label='PWNED <script>', skill_id='pc_job')
        self.companion.queue[-1]['pressed_at'] -= (REQUEST_TTL_S + 5) * 1000
        self.rc.poll_once()
        entry = self.rc.state()['history'][-1]
        self.assertEqual(entry['request_id'], rid)
        self.assertNotIn('PWNED', entry.get('reason', ''))
        self.assertNotIn('pc_job', entry.get('reason', ''))


if __name__ == '__main__':
    unittest.main()
