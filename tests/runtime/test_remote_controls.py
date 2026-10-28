"""B3 remote controls (SIMULATED_VERIFIED: fake Companion mirroring RelayServer.java, fake device runners)."""
import time
import unittest

from src.fabric import relay as R
from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.runtime.api_v2 import executor, remote_controls, router
from src.runtime.primitives import Executor
from src.runtime.remote_controls import RemoteControlError
from src.runtime.routing import RouteError
from tests.runtime.test_routing import Clock, world

KEY = R.derive_key('654321', 'rn', 'pn')


class FakeCompanion:
    """Same rules as RelayServer.java: signed commands only, stores {control_id, label}, queues presses, shows results."""
    def __init__(self):
        self.seen, self.controls, self.queue, self.results, self.ops = {}, [], [], [], []

    def press(self, control_id, request_id=None, **extra):
        rid = request_id or ('%032x' % (len(self.ops) * 7919 + int(time.time() * 1000) % 100000 + len(self.queue)))
        self.queue.append({'request_id': rid, 'control_id': control_id, **extra})
        return rid

    def __call__(self, relay, message):
        msg = R.verify(KEY, message, self.seen)
        self.ops.append(msg['op'])
        params = {}
        if msg['op'] == 'set_controls':
            self.controls = msg['params']['controls']; self.queue = []
        elif msg['op'] == 'get_requests':
            params, self.queue = {'requests': self.queue}, []
        elif msg['op'] == 'report_result':
            self.results.append(msg['params'])
        elif msg['op'] in ('get_status', 'discover_capabilities'):
            params = {'capabilities': ['remote_controls'], 'permissions': {}}
        t = int(time.time())
        reply = {'protocol': R.PROTOCOL, 'relay_id': msg['relay_id'], 'op': 'reply', 'params': params, 'nonce': 'r' + msg['nonce'], 'issued_at': t, 'expires_at': t + 30}
        return {**reply, 'mac': R.sign(KEY, reply)}


class RemoteControls(unittest.TestCase):
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
        self.server.relays.enroll('r-watch', KEY, 'h-watch-1', {'capabilities': ['remote_controls'], 'permissions': {}})
        self.server.relays.relays['r-watch']['send'] = self.companion
        self.calls = []
        def fake(self_, key, params):
            self.calls.append((key, params)); return 'EXECUTED', None, None, True, {}
        ex = executor(self.server)
        ex.RUNNERS = dict(Executor.RUNNERS, device_action=fake)
        router(self.server).clock = self.clock
        self.rc = remote_controls(self.server)
        self.rc.clock = self.clock
        self.rc._ensure_thread = lambda: None          # tests drive poll_once() directly

    def grant(self, controls, consent=True):
        return self.rc.set_controls({'relay_id': 'r-watch', 'controls': controls, 'consent': consent})

    def vol_up(self):
        st = self.grant([{'label': 'TV volume +', 'skill_id': 'tv_volume_step', 'target': self.keys['tv'], 'params': {'direction': 'up'}}])
        return st['controls'][0]['control_id']

    def test_device_receives_labels_only_and_press_runs_once_with_owner_params(self):
        cid = self.vol_up()
        self.assertEqual(self.companion.controls, [{'control_id': cid, 'label': 'TV volume +'}])   # no skill, target or params on the device
        rid = self.companion.press(cid, direction='down', skill_id='pc_job')                          # injected fields are ignored
        self.assertEqual(self.rc.poll_once(), 1)
        self.assertEqual(self.calls, [(self.keys['tv'], {'action': 'key', 'args': {'key': 'volume_up'}})])
        self.assertEqual(self.companion.results[-1]['request_id'], rid)
        self.assertIn('done', self.companion.results[-1]['text'])
        self.clock.t += 2
        self.companion.press(cid, request_id=rid)                                                       # the same press re-sent
        self.rc.poll_once()
        self.assertEqual(len(self.calls), 1)
        self.assertIn('already done', self.companion.results[-1]['text'])
        self.clock.t += 2
        self.companion.press(cid)                                                                       # a new press = a new invocation
        self.rc.poll_once()
        self.assertEqual(len(self.calls), 2)
        events = [e['kind'] for e in executor(self.server).events_since(0)]
        self.assertIn('remote_request', events)

    def test_unknown_control_and_revocation(self):
        cid = self.vol_up()
        self.companion.press('ctl-000000000000')
        self.assertEqual(self.rc.poll_once(), 0)
        self.grant([])                                                                                  # owner removes the controls
        self.assertEqual(self.companion.controls, [])
        self.companion.press(cid)
        self.assertEqual(self.rc.poll_once(), 0)
        self.assertEqual(self.calls, [])
        cid = self.vol_up()
        self.server.relays.revoke('r-watch')                                                            # relay revoked: controls die
        self.assertEqual(self.rc.poll_once(), 0)
        self.assertEqual(self.rc.state()['controls'], [])

    def test_owner_validation(self):
        with self.assertRaises(RemoteControlError):
            self.grant([{'label': 'x', 'skill_id': 'tv_volume_step', 'target': self.keys['tv'], 'params': {'direction': 'up'}}], consent=False)
        for bad in ({'label': 'x', 'skill_id': 'pc_job', 'params': {}},                                       # not a skill
                    {'label': 'x', 'skill_id': 'tv_volume_step', 'params': {'direction': 'up'}},               # target missing
                    {'label': 'x', 'skill_id': 'tv_volume_step', 'target': self.keys['tv'], 'params': {'direction': 'sideways'}},
                    {'label': '', 'skill_id': 'device_facts', 'target': self.keys['tv'], 'params': {}}):
            with self.assertRaises(RemoteControlError):
                self.grant([bad])
        self.server.relays.relays['r-watch']['capabilities'] = {'ble_scan'}
        with self.assertRaises(RemoteControlError):                                                     # old Companion without controls
            self.vol_up()

    def test_unavailable_route_is_reported_not_executed(self):
        cid = self.vol_up()
        for l in self.server.fabric_snapshot['links']:
            if l['child'] == self.keys['tv']:
                l['grants'] = ['observe']
        self.companion.press(cid)
        self.rc.poll_once()
        self.assertEqual(self.calls, [])
        self.assertIn('Unavailable', self.companion.results[-1]['text'])
        self.assertEqual(self.rc.state()['history'][-1]['state'], 'BLOCKED')

    def test_rate_limit_per_control(self):
        cid = self.vol_up()
        self.companion.press(cid); self.companion.press(cid, request_id='%032x' % 99)
        self.rc.poll_once()
        self.assertEqual(len(self.calls), 1)
        self.assertIn('Too fast', self.companion.results[-1]['text'])

    def test_owner_lease_cannot_be_used_by_a_relay_actor(self):
        rt = router(self.server)
        doc = rt.skill_routes('tv_volume_step', self.keys['tv'])
        lease = rt.arm({'skill_id': 'tv_volume_step', 'target': self.keys['tv'], 'route_id': doc['selected_route_id'], 'params': {'direction': 'up'}, 'consent': True})
        body = {k: lease[k] for k in ('invocation_id', 'route_id', 'lease_id', 'graph_revision')}
        body.update(skill_id='tv_volume_step', target=self.keys['tv'], params={'direction': 'up'}, consent=True)
        with self.assertRaises(RouteError):
            rt.invoke(body, actor='relay:r-watch')
        self.assertEqual(self.calls, [])
        rt.invoke(body)                                                                                 # the owner can
        self.assertEqual(len(self.calls), 1)

    def test_protocol_bounds(self):
        with self.assertRaises(R.RelayError):
            R.command(KEY, 'r', 'set_controls', {'controls': [{'control_id': 'BAD ID', 'label': 'x'}]})
        with self.assertRaises(R.RelayError):
            R.command(KEY, 'r', 'set_controls', {'controls': [{'control_id': 'ctl-1234', 'label': 'x', 'skill_id': 'pc_job'}]})
        with self.assertRaises(R.RelayError):
            R.command(KEY, 'r', 'report_result', {'request_id': 'x', 'text': 'ok'})
        self.assertEqual(R.validate_requests({'requests': [{'request_id': 'z' * 32, 'control_id': 'ctl-a'}, {'request_id': 'a' * 32, 'control_id': 'ctl-a', 'params': {'x': 1}}]}, {'ctl-a'}),
                         [{'request_id': 'a' * 32, 'control_id': 'ctl-a'}])


if __name__ == '__main__':
    unittest.main()
