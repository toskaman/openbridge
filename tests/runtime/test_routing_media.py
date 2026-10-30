"""§7 media/file routable skills (SIMULATED_VERIFIED: synthetic registry, fake runners)."""
import json
import unittest
from types import SimpleNamespace

from tests.runtime.test_routing import Clock, world
from src.runtime import route_contract as rc
from src.runtime.api_v2 import executor, router
from src.runtime.primitives import Executor
from src.runtime.routing import RouteError


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        ex = executor(self.server)

        def fake(result):
            def run(self_, key, params):
                return 'EXECUTED', None, 'ok', True, dict(result)
            return run

        ex.RUNNERS = dict(
            Executor.RUNNERS,
            screen_capture=fake({'capture_id': 'cap-1', 'sha256': 's', 'bytes': 8, 'width': 2, 'height': 2}),
            capture_send=fake({'remote': '/sdcard/OpenBridge/cap-1.png', 'sha256': 's', 'bytes': 8}),
            capture_montage=fake({'capture_id': 'cap-2', 'sha256': 'm', 'width': 4, 'height': 2, 'inputs': 2}),
            file_pull=fake({'transfer_id': 'xfer-1', 'sha256': 't', 'bytes': 3, 'remote': '/sdcard/Download/a.bin'}),
            file_push=fake({'remote': '/sdcard/OpenBridge/relay.bin', 'sha256': 't', 'bytes': 3}),
        )
        self.router = router(self.server)
        self.router.clock = self.clock

    def routes(self, skill, target=None):
        doc = self.router.skill_routes(skill, target)
        self.assertEqual(rc.validate_doc(doc), [], json.dumps(doc, indent=1)[:2000])
        return doc

    def arm_invoke(self, skill, target, params):
        doc = self.routes(skill, target)
        self.assertIsNotNone(doc['selected_route_id'])
        lease = self.router.arm({'skill_id': skill, 'target': target, 'route_id': doc['selected_route_id'],
                                 'params': params, 'consent': True})
        body = {'invocation_id': lease['invocation_id'], 'skill_id': skill,
                'route_id': lease['route_id'], 'lease_id': lease['lease_id'],
                'graph_revision': lease['graph_revision'], 'params': params, 'consent': True}
        if target:
            body['target'] = target
        return self.router.invoke(body)


class MediaSkills(Base):
    def test_screen_capture_ready_and_dispatches(self):
        r = self.arm_invoke('screen_capture', self.keys['phone'], {})
        self.assertEqual(r['state'], 'EXECUTED')
        self.assertEqual(r['result']['capture_id'], 'cap-1')
        self.assertEqual(r['skill_id'], 'screen_capture')

    def test_capture_send_ready_and_dispatches(self):
        r = self.arm_invoke('capture_send', self.keys['phone'], {'capture_id': 'cap-1'})
        self.assertEqual(r['state'], 'EXECUTED')
        self.assertTrue(r['result']['remote'].endswith('.png'))

    def test_capture_montage_is_server_side_untargeted(self):
        doc = self.routes('capture_montage')
        self.assertEqual(len(doc['routes']), 1)
        self.assertEqual(doc['routes'][0]['hops'][0]['device_key'], 'fabric')
        r = self.arm_invoke('capture_montage', None, {'capture_ids': ['cap-1', 'cap-2'], 'layout': 'grid'})
        self.assertEqual(r['result']['inputs'], 2)

    def test_file_pull_and_push_round_trip(self):
        pulled = self.arm_invoke('file_pull', self.keys['phone'], {'remote': '/sdcard/Download/a.bin'})
        self.assertEqual(pulled['result']['transfer_id'], 'xfer-1')
        pushed = self.arm_invoke('file_push', self.keys['phone'], {'transfer_id': 'xfer-1', 'name': 'relay.bin'})
        self.assertEqual(pushed['result']['remote'], '/sdcard/OpenBridge/relay.bin')

    def test_link_down_is_honest_unavailable(self):
        self.server.fabric_snapshot['links'] = [l for l in self.server.fabric_snapshot['links']
                                                if l['child'] != self.keys['phone']]
        doc = self.routes('screen_capture', self.keys['phone'])
        self.assertEqual(doc['routes'][0]['state'], 'UNAVAILABLE')
        self.assertEqual(doc['routes'][0]['reason'], 'link_down')
        self.assertIsNone(doc['selected_route_id'])

    def test_missing_capture_id_rejected(self):
        doc = self.routes('capture_send', self.keys['phone'])
        with self.assertRaises(RouteError):
            self.router.arm({'skill_id': 'capture_send', 'target': self.keys['phone'],
                             'route_id': doc['selected_route_id'], 'params': {}, 'consent': True})


class GroundedSkills(Base):
    def setUp(self):
        super().setUp()
        from src.fabric.contracts import DeviceObservation, Identifier, Link, now
        reg = self.server.fabric_registry
        vk = reg.upsert([Identifier('tuya_device_id', 'vac-1', True)], category='vacuum', label='Vacuum',
                        observations=[DeviceObservation('model', 'Vac', 'TUYA_LOCAL', 'LAN', now(), True)])
        reg.link(Link('pc', vk, 'LAN', ('observe', 'read', 'control'), 'TUYA_LOCAL'))
        ck = reg.upsert([Identifier('windows_machine_guid', 'pc-1', True)], category='computer', label='PC2',
                        observations=[DeviceObservation('os_build', 'Win11', 'WINDOWS_AGENT', 'LAN', now(), True)])
        reg.devices[ck]['handles'] = {'WINDOWS_AGENT': 'windows-agent'}
        reg.link(Link('pc', ck, 'LAN', ('observe', 'read'), 'WINDOWS_AGENT'))
        self.server.fabric_snapshot = reg.snapshot()
        self.keys['vacuum'] = vk
        self.keys['computer'] = ck
        ex = executor(self.server)

        def fake(result):
            def run(self_, key, params):
                return 'EXECUTED', None, 'ok', True, dict(result)
            return run

        ex.RUNNERS = dict(ex.RUNNERS, device_action=fake({'acted': True}),
                          device_capabilities=fake({'actions': ['key']}),
                          tuya_command=fake({'command': 'dock'}),
                          pc_job=fake({'exit_code': 0}))

    def test_app_launch_dispatches_launch_app(self):
        calls = []
        ex = executor(self.server)
        real = ex.RUNNERS['device_action']

        def spy(self_, key, params):
            calls.append(params)
            return real(self_, key, params)

        ex.RUNNERS = dict(ex.RUNNERS, device_action=spy)
        r = self.arm_invoke('app_launch', self.keys['tv'], {'package': 'com.google.android.youtube.tv'})
        self.assertEqual(r['state'], 'EXECUTED')
        self.assertEqual(calls[0]['action'], 'launch_app')
        self.assertEqual(calls[0]['args'], {'package': 'com.google.android.youtube.tv'})

    def test_capability_probe_is_read_only(self):
        doc = self.routes('capability_probe', self.keys['phone'])
        self.assertEqual(doc['skill']['reversibility'], 'NONE')
        self.assertEqual(doc['skill']['consent'], 'none')
        r = self.arm_invoke('capability_probe', self.keys['phone'], {})
        self.assertEqual(r['result'], {'actions': ['key']})

    def test_vacuum_command_needs_control_grant(self):
        doc = self.routes('vacuum_command', self.keys['vacuum'])
        self.assertEqual(doc['routes'][0]['hops'][0]['required_grant'], 'control')
        r = self.arm_invoke('vacuum_command', self.keys['vacuum'], {'command': 'dock'})
        self.assertEqual(r['state'], 'EXECUTED')

    def test_vacuum_without_control_is_unavailable(self):
        snap = self.server.fabric_snapshot
        snap['links'] = [l if l['child'] != self.keys['vacuum'] else dict(l, grants=('observe', 'read'))
                         for l in snap['links']]
        doc = self.routes('vacuum_command', self.keys['vacuum'])
        self.assertEqual(doc['routes'][0]['state'], 'UNAVAILABLE')
        self.assertEqual(doc['routes'][0]['reason'], 'grant_insufficient')

    def test_pc_run_routes_over_read_link_with_consent(self):
        doc = self.routes('pc_run', self.keys['computer'])
        hop = doc['routes'][0]['hops'][0]
        self.assertEqual((hop['required_grant'], doc['skill']['consent']),
                         ('read', 'per_invocation'))
        self.assertEqual(doc['routes'][0]['state'], 'READY')
        r = self.arm_invoke('pc_run', self.keys['computer'],
                            {'command': 'shutdown /s /t 60', 'shell': 'cmd'})
        self.assertEqual(r['result'], {'exit_code': 0})

    def test_pc_run_without_agent_handle_is_link_down(self):
        del self.server.fabric_registry.devices[self.keys['computer']]['handles']['WINDOWS_AGENT']
        self.server.fabric_snapshot = self.server.fabric_registry.snapshot()
        doc = self.routes('pc_run', self.keys['computer'])
        self.assertEqual(doc['routes'][0]['reason'], 'link_down')


if __name__ == '__main__':
    unittest.main()
