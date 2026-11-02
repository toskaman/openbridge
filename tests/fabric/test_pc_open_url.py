"""pc_open_url primitive + skill (scenario F): strict URL, fixed command shape.

The runner builds ONE fixed PowerShell template from a strictly
validated URL; no model text ever reaches a shell. Only process
launch is verified — page load is never claimed.
"""
import base64
import unittest
from types import SimpleNamespace

from src.adapters.windows_bridge import BridgeUnavailable
from src.fabric.contracts import Identifier
from src.fabric.registry import Registry
from src.runtime.primitives import Executor


class FakeBridge:
    ident = 'id-pc1'

    def __init__(self):
        self.jobs = []

    def connected(self):
        return True

    def identity(self, _salt):
        return self.ident

    def run_job(self, command, shell, timeout_s):
        self.jobs.append((command, shell, timeout_s))
        return {'exit_code': 0, 'timed_out': False,
                'stdout_b64': base64.b64encode(b''),
                'stderr_b64': base64.b64encode(b'')}


def rig():
    reg = Registry()
    key = reg.upsert([Identifier('windows_machine_guid', 'id-pc1', True)],
                     category='computer', label='PC 1')
    bridge = FakeBridge()
    ex = Executor(SimpleNamespace(fabric_registry=reg, fabric_salt=b's',
                                  fabric_adapters=lambda _p=None: {'windows': bridge}))
    return ex, key, bridge


class PcOpenUrl(unittest.TestCase):
    def test_youtube_opens_with_fixed_shape(self):
        ex, key, bridge = rig()
        r = ex.execute('pc_open_url', key,
                       {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
                       consent=True)
        self.assertEqual(r['state'], 'VERIFIED')
        self.assertTrue(r['result']['launched_only'])
        self.assertEqual(bridge.jobs,
                         [('Start-Process "https://www.youtube.com/watch?v=dQw4w9WgXcQ"',
                           'powershell', 60)])

    def test_injection_urls_rejected_before_sending(self):
        ex, key, bridge = rig()
        bad = ['https://x.com/$(calc)', 'https://x.com/`calc`',
               'https://x.com/a"b', 'file:///C:/x', 'javascript:alert(1)',
               'https://x.com/a b', 'https://x com/', 'not a url', '',
               'https://x.com/\x00', 'ftp://x.com/f']
        for url in bad:
            with self.subTest(url=url):
                r = ex.execute('pc_open_url', key, {'url': url}, consent=True)
                self.assertEqual(r['state'], 'BLOCKED')
                self.assertIn('BAD_URL', r['errors'][0])
        self.assertEqual(bridge.jobs, [])

    def test_agent_failure_is_failed_never_verified(self):
        ex, key, bridge = rig()

        def dead(_c, _sh, _t):
            raise BridgeUnavailable('gone')

        bridge.run_job = dead
        r = ex.execute('pc_open_url', key, {'url': 'https://example.org/'},
                       consent=True)
        self.assertNotEqual(r['state'], 'VERIFIED')
        self.assertFalse(r['verified'])
        self.assertTrue(r['errors'][0].startswith('FAILED:'), r['errors'])

    def test_managed_skills_route_to_bridged_pc(self):
        from src.fabric.contracts import Link
        from src.runtime.api_v2 import router
        from tests.runtime.test_routing import Clock, world
        clock = Clock()
        server, keys = world(clock)
        reg = server.fabric_registry
        ck = reg.upsert([Identifier('windows_machine_guid', 'pc-9', True)],
                        category='computer', label='PC9')
        reg.devices[ck]['handles'] = {'WINDOWS_AGENT': 'windows-agent'}
        reg.link(Link('pc', ck, 'LAN', ('observe', 'read'), 'WINDOWS_AGENT'))
        server.fabric_snapshot = reg.snapshot()
        for sid, prim in (('pc_place_file', 'pc_place_file'),
                          ('pc_wallpaper', 'pc_wallpaper')):
            with self.subTest(skill=sid):
                doc = router(server).skill_routes(sid, ck)
                self.assertIsNotNone(doc['selected_route_id'])
                self.assertEqual(doc['routes'][0]['hops'][0]['primitive_id'], prim)
                self.assertIsNone(router(server).skill_routes(sid, keys['tv'])
                                  ['selected_route_id'])

    def test_skill_routes_to_bridged_pc(self):
        from src.fabric.contracts import Link
        from src.runtime.api_v2 import router
        from tests.runtime.test_routing import Clock, world
        clock = Clock()
        server, keys = world(clock)
        reg = server.fabric_registry
        ck = reg.upsert([Identifier('windows_machine_guid', 'pc-9', True)],
                        category='computer', label='PC9')
        reg.devices[ck]['handles'] = {'WINDOWS_AGENT': 'windows-agent'}
        reg.link(Link('pc', ck, 'LAN', ('observe', 'read'), 'WINDOWS_AGENT'))
        server.fabric_snapshot = reg.snapshot()
        doc = router(server).skill_routes('pc_open_url', ck)
        self.assertIsNotNone(doc['selected_route_id'])
        self.assertEqual(doc['routes'][0]['hops'][0]['primitive_id'], 'pc_open_url')
        self.assertIsNone(router(server).skill_routes('pc_open_url', keys['tv'])
                          ['selected_route_id'])


if __name__ == '__main__':
    unittest.main()
