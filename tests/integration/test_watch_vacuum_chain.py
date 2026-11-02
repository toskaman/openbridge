"""Watch -> vacuum chain (SIMULATED_VERIFIED, no hardware/model calls).

Request: 'Add a button to my watch to start the vacuum'.
Deterministic proposal (no model: device agent owns no model code) ->
real Router over world() -> production set_controls/process/revoke,
FakeCompanion mirroring RelayServer.java, fake tuya_command runner
asserting the typed command.

Chain: compose (real route) -> preview -> consented install on watch
relay -> press runs typed 'start' once -> re-press deduped ->
revoke -> press denied. Physical motion is NOT proven here: that
needs the owner-attended session (see HARDWARE_RUNBOOK.md).
"""
import unittest

from src.fabric import relay as R
from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.runtime import composer as C
from src.runtime.api_v2 import executor, remote_controls, router
from src.runtime.primitives import Executor
from tests.runtime.test_remote_controls import FakeCompanion
from tests.runtime.test_routing import Clock, world

KEY = R.derive_key('654321', 'rn', 'pn')


class WatchVacuumChainTest(unittest.TestCase):
    def test_install_press_revoke(self):
        clock = Clock()
        server, keys = world(clock)
        reg = server.fabric_registry
        w = reg.upsert([Identifier('android_serial', 'watch-1', True)],
                       category='watch', label='SM-L310',
                       observations=[DeviceObservation(
                           'model', 'SM-L310', 'ADB', 'WIFI', now(), True)])
        reg.devices[w]['handles'] = {'WIFI': 'h-watch-1'}
        reg.link(Link('pc', w, 'WIFI', ('observe', 'read', 'control'),
                      'ADB:device'))
        vk = reg.upsert([Identifier('tuya_device_id', 'vac-1', True)],
                        category='vacuum', label='Vacuum',
                        observations=[DeviceObservation(
                            'model', 'Vac', 'TUYA_LOCAL', 'LAN', now(), True)])
        reg.link(Link('pc', vk, 'LAN', ('observe', 'read', 'control'),
                      'TUYA_LOCAL'))
        reg.devices[vk]['handles'] = {'TUYA_LOCAL': 'tuya-local'}
        server.fabric_snapshot = reg.snapshot()
        devices = [{'key': vk, 'label': 'Vacuum', 'category': 'vacuum',
                    'handles': {'TUYA_LOCAL': 'tuya-local'}},
                   {'key': w, 'label': 'Galaxy Watch7', 'category': 'watch',
                    'handles': {'WIFI': 'h-watch-1'}}]

        # 1. deterministic proposal -> real-route compose
        proposal = C.proposal_from_doc({'steps': [
            {'skill_id': 'vacuum_command', 'target': 'Vacuum',
             'params': {'command': 'start'}, 'needs': [], 'on_fail': 'fail'}]})
        composed = C.compose(proposal, devices, router(server))
        self.assertEqual((composed['allowed'], composed['refused']), (1, 0))
        self.assertEqual(composed['steps'][0]['device_key'], vk)

        # 2. consented install on the watch relay
        body = C.to_controls(composed, 'r-watch')
        server.relays.enroll(
            'r-watch', KEY, 'h-watch-1',
            {'capabilities': ['remote_controls'], 'permissions': {}})
        companion = FakeCompanion()
        companion.clock = clock
        server.relays.relays['r-watch']['send'] = companion
        rc = remote_controls(server)
        rc.clock = clock
        rc._ensure_thread = lambda: None
        router(server).clock = clock
        calls = []
        ex = executor(server)

        def fake_tuya(_executor, key, params):
            calls.append((key, params))
            self.assertEqual(params.get('command'), 'start')
            return 'VERIFIED', 'docked', 'cleaning', True, {'command': 'start'}

        ex.RUNNERS = dict(Executor.RUNNERS, tuya_command=fake_tuya)
        st = rc.set_controls({'relay_id': 'r-watch',
                              'controls': body['controls'], 'consent': True})
        self.assertEqual(len(st['controls']), 1)
        cid = st['controls'][0]['control_id']

        # 3. one press runs the typed command once, verified by read-back
        rid = companion.press(cid)
        self.assertEqual(rc.poll_once(), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], vk)
        self.assertIn('done', companion.results[-1]['text'])
        clock.t += 2
        companion.press(cid, request_id=rid)
        rc.poll_once()
        self.assertEqual(len(calls), 1)

        # 4. revoke -> subsequent press denied
        rc.set_controls({'relay_id': 'r-watch', 'controls': [],
                         'consent': True})
        companion.press(cid)
        self.assertEqual(rc.poll_once(), 0)
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
