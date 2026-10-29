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
    def __init__(self, key=KEY):
        self.key, self.seen, self.controls, self.queue, self.results, self.ops = key, {}, [], [], [], []
        self.clock = time.time
        self.pending = {}
        self.revision, self.status = 0, {}       # layout v2: applied revision (ACK) and status values

    def press(self, control_id, request_id=None, **extra):
        rid = request_id or ('%032x' % (len(self.ops) * 7919 + int(time.time() * 1000) % 100000 + len(self.queue)))
        self.queue.append({'request_id': rid, 'control_id': control_id, 'pressed_at': int(self.clock() * 1000), **extra})
        return rid

    def __call__(self, relay, message):
        msg = R.verify(self.key, message, self.seen)
        self.ops.append(msg['op'])
        params = {}
        if msg['op'] == 'set_controls':
            self.controls = msg['params']['controls']; self.queue = []
            self.revision = msg['params'].get('revision', 0)
            self.status = {c['control_id']: c.get('value', '') for c in self.controls if c.get('kind') == 'status'}
        elif msg['op'] == 'update_status':
            self.status.update({k: v for k, v in msg['params']['values'].items() if k in self.status})   # queue untouched
        elif msg['op'] == 'get_requests':
            params, self.queue = {'requests': self.queue, 'applied_revision': self.revision}, []
            self.pending.update({r['request_id']: True for r in params['requests']})
        elif msg['op'] == 'report_result':
            if self.pending.pop(msg['params']['request_id'], None):     # unknown or late results are ignored, like the Java
                self.results.append(msg['params'])
        elif msg['op'] in ('get_status', 'discover_capabilities'):
            params = {'capabilities': ['remote_controls'], 'permissions': {}}
        t = int(time.time())
        reply = {'protocol': R.PROTOCOL, 'relay_id': msg['relay_id'], 'op': 'reply', 'params': params, 'nonce': 'r' + msg['nonce'], 'issued_at': t, 'expires_at': t + 30}
        return {**reply, 'mac': R.sign(self.key, reply)}


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
        self.companion = FakeCompanion(); self.companion.clock = self.clock
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


class Burst(unittest.TestCase):
    setUp = RemoteControls.setUp
    grant = RemoteControls.grant
    vol_up = RemoteControls.vol_up

    def test_unusual_burst_suspends_until_regrant(self):
        cid = self.vol_up()
        for i in range(6):
            self.clock.t += 0.6
            self.companion.press(cid, request_id='%032x' % (1000 + i))
            self.rc.poll_once()
        self.assertEqual(len(self.calls), 3)                              # 4th press inside 10 s suspends the control
        self.assertIn('paused', self.companion.results[-1]['text'])
        self.assertTrue(self.rc.state()['suspended'])
        self.clock.t += 60
        self.companion.press(cid, request_id='%032x' % 2000); self.rc.poll_once()
        self.assertEqual(len(self.calls), 3)                              # still suspended: only the owner re-enables
        cid = self.vol_up()                                               # explicit re-grant
        self.companion.press(cid, request_id='%032x' % 3000); self.rc.poll_once()
        self.assertEqual(len(self.calls), 4)


class ReviewFailures(unittest.TestCase):
    """Codex review of PR #54 (head 581825a): each test failed on that head."""
    setUp = RemoteControls.setUp
    grant = RemoteControls.grant
    vol_up = RemoteControls.vol_up

    def test_revocation_during_inflight_get_requests_never_dispatches(self):
        cid = self.vol_up()
        self.companion.press(cid, request_id='%032x' % 1)
        real = self.companion.__call__
        def revoke_mid_flight(relay, message):
            reply = real(relay, message)
            if R.verify(KEY, message, {})['op'] == 'get_requests':
                self.rc.grants.pop('r-watch', None)            # owner revokes while the reply is on the wire
            return reply
        self.server.relays.relays['r-watch']['send'] = revoke_mid_flight
        self.rc.poll_once()
        self.assertEqual(self.calls, [])

    def test_regrant_with_same_definition_does_not_honour_old_requests(self):
        cid = self.vol_up()
        self.grant([])
        cid2 = self.vol_up()                                   # identical control re-granted
        self.assertNotEqual(cid, cid2)                         # new generation, new id on the device
        self.companion.queue.append({'request_id': '%032x' % 7, 'control_id': cid, 'pressed_at': int(self.clock.t * 1000)})
        self.rc.poll_once()
        self.assertEqual(self.calls, [])

    def test_close_stops_poller_and_late_dispatch(self):
        import threading
        cid = self.vol_up()
        gate, entered = threading.Event(), threading.Event()
        real = self.companion.__call__
        def slow(relay, message):
            if R.verify(KEY, dict(message), {})['op'] == 'get_requests':
                entered.set(); gate.wait(5)
            return real(relay, message)
        self.server.relays.relays['r-watch']['send'] = slow
        self.companion.press(cid, request_id='%032x' % 2)
        t = threading.Thread(target=self.rc.poll_once); t.start()
        entered.wait(5)
        self.rc.close()                                        # server shutting down while the fetch is pending
        gate.set(); t.join(5)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.rc.state()['controls'], [])

    def test_stale_or_future_request_is_refused(self):
        cid = self.vol_up()
        now_ms = int(self.clock.t * 1000)
        self.companion.queue.append({'request_id': '%032x' % 3, 'control_id': cid, 'pressed_at': now_ms - 120_000})
        self.companion.queue.append({'request_id': '%032x' % 4, 'control_id': cid, 'pressed_at': now_ms + 120_000})
        self.rc.poll_once()
        self.assertEqual(self.calls, [])
        self.assertEqual([h['state'] for h in self.rc.state()['history']], ['EXPIRED', 'EXPIRED'])

    def test_repair_with_new_key_invalidates_controls(self):
        cid = self.vol_up()
        k2 = R.derive_key('111111', 'a', 'b')                  # owner re-paired the watch: new key on both sides
        self.server.relays.enroll('r-watch', k2, 'h-watch-1', {'capabilities': ['remote_controls'], 'permissions': {}})
        self.companion.key = k2
        self.server.relays.relays['r-watch']['send'] = self.companion
        self.companion.press(cid, request_id='%032x' % 5)
        self.rc.poll_once()
        self.assertEqual(self.calls, [])

    def test_evidence_chain_is_recorded(self):
        cid = self.vol_up()
        self.companion.queue.append({'request_id': '%032x' % 6, 'control_id': cid, 'pressed_at': int(self.clock.t * 1000), 'seq': 41,
                                     'gesture': 'long_press', 'touch': {'tool': 1, 'pressure': 0.5, 'size': 0.1}})
        self.rc.poll_once()
        h = self.rc.state()['history'][-1]
        self.assertEqual((h['seq'], h['gesture'], h['touch']['tool']), (41, 'long_press', 1))
        self.assertTrue(h['invocation_id'].startswith('inv-')); self.assertTrue(h['transaction_id'].startswith('tx-'))


class Shutdown(unittest.TestCase):
    def test_server_close_stops_remote_controls(self):
        import tempfile
        from src.server import create_server
        from src.fabric.session import SessionJournal
        s = create_server(0, fabric_salt=b's', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        rc = remote_controls(s)
        s.server_close()
        self.assertTrue(rc.state()['closed'])
        with self.assertRaises(RemoteControlError):
            rc.set_controls({'relay_id': 'x', 'controls': [], 'consent': True})


class PendingAck(unittest.TestCase):
    setUp = RemoteControls.setUp
    grant = RemoteControls.grant
    vol_up = RemoteControls.vol_up

    def test_every_fetched_request_is_acknowledged_whatever_the_outcome(self):
        cid = self.vol_up()
        now_ms = int(self.clock.t * 1000)
        self.companion.queue += [{'request_id': '%032x' % 1, 'control_id': cid, 'pressed_at': now_ms},
                                 {'request_id': '%032x' % 2, 'control_id': cid, 'pressed_at': now_ms - 600_000}]   # executed + expired
        self.rc.poll_once()
        self.assertEqual(self.companion.pending, {})
        self.assertEqual(len(self.companion.results), 2)

    def test_closed_pc_leaves_request_pending_for_the_device_timeout(self):
        cid = self.vol_up()
        self.companion.press(cid, request_id='%032x' % 3)
        real = self.companion.__call__
        def close_after_fetch(relay, message):
            reply = real(relay, message)
            if R.verify(self.companion.key, dict(message), {})['op'] == 'get_requests':
                self.rc.close()
            return reply
        self.server.relays.relays['r-watch']['send'] = close_after_fetch
        self.rc.poll_once()
        self.assertEqual(self.calls, [])
        self.assertIn('%032x' % 3, self.companion.pending)   # device shows "Not confirmed" after 20 s; never re-sent
