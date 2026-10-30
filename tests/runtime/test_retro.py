"""retro_command primitive + skill (SIMULATED_VERIFIED: fake UDP server)."""
import socket
import threading
import unittest

from tests.runtime.test_primitives import ctx
from tests.runtime.test_routing import Clock, world
from src.runtime.api_v2 import executor
from src.runtime.primitives import Executor


class FakeRetroArch:
    def __init__(self):
        self.seen = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        self.sock.settimeout(0.1)
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            cmd = data.decode().strip()
            self.seen.append(cmd)
            self.sock.sendto(b'1.21.0\n' if cmd == 'VERSION' else b'OK\n', addr)

    def close(self):
        self._stop.set()


class RetroPrimitive(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.c, self.key = ctx(self.tmp)
        self.srv = FakeRetroArch()
        self.c.retro_port = self.srv.port
        self.ex = Executor(self.c)

    def tearDown(self):
        self.srv.close()

    def test_version_returns_reply(self):
        r = self.ex.execute('retro_command', 'fabric', {'command': 'VERSION'}, True)
        self.assertEqual(r['state'], 'EXECUTED')
        self.assertEqual(r['result']['reply'], '1.21.0')

    def test_action_is_executed_unverified(self):
        r = self.ex.execute('retro_command', 'fabric', {'command': 'VOLUME_UP'}, True)
        self.assertEqual(r['state'], 'EXECUTED_UNVERIFIED')
        self.assertFalse(r['verified'])
        self.assertEqual(r['result'], {'sent': 'SENT'})
        self.assertIn('VOLUME_UP', self.srv.seen)

    def test_needs_consent(self):
        r = self.ex.execute('retro_command', 'fabric', {'command': 'VERSION'}, False)
        self.assertEqual(r['state'], 'BLOCKED')

    def test_unreachable_is_failed(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(('127.0.0.1', 0))
        dead_port = probe.getsockname()[1]
        probe.close()
        self.c.retro_port = dead_port
        r = self.ex.execute('retro_command', 'fabric', {'command': 'VERSION'}, True)
        self.assertEqual(r['state'], 'FAILED')
        self.assertIn('RETRO_UNAVAILABLE', r['errors'][0])


class RetroSkill(unittest.TestCase):
    def test_skill_routes_server_side(self):
        import json
        from src.runtime import route_contract as rc
        from src.runtime.api_v2 import router
        clock = Clock()
        server, _ = world(clock)
        rt = router(server)
        doc = rt.skill_routes('retro_command', None)
        self.assertEqual(rc.validate_doc(doc), [], json.dumps(doc)[:1000])
        self.assertEqual(doc['routes'][0]['hops'][0]['device_key'], 'fabric')
        self.assertIsNotNone(doc['selected_route_id'])


if __name__ == '__main__':
    unittest.main()
