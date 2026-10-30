"""Onboarding API: hardware matrix payload + artifact portal (SIMULATED_VERIFIED)."""
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import ProxyHandler, build_opener

from src.fabric import apk_portal as ap
from src.fabric.registry import Registry
from src.runtime import api_v2


def srv(apk, agent_dir, reg=None):
    reg = reg if reg is not None else Registry()
    return SimpleNamespace(fabric_snapshot=reg.snapshot(), fabric_registry=reg,
                           companion_apk=apk, agent_dir=agent_dir,
                           runtime_executor=SimpleNamespace(), apk_portal=None)


class Timer:
    def __init__(self, interval, callback):
        self.cancelled = False
        self.daemon = False
    def start(self): pass
    def cancel(self): self.cancelled = True


class MatrixPayload(unittest.TestCase):
    def test_get_onboarding_lists_matrix(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'agent_x64.exe').write_bytes(b'fixture-only')
            code, body = api_v2.get(srv(Path(d) / 'no.apk', Path(d)), '/api/v2/onboarding', '')
            self.assertEqual(code, 200)
            by_id = {m['id']: m for m in body['agent_matrix']}
            self.assertEqual(by_id['windows-x64']['status'], 'READY')
            self.assertEqual(by_id['linux-x64']['status'], 'NEEDS_STEP')
            self.assertNotIn('path', by_id['windows-x64'])
            self.assertIn('candidates', body)


class ArtifactEndpoint(unittest.TestCase):
    def test_unknown_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            code, body = api_v2.apk_portal(srv(Path(d) / 'no.apk', Path(d)), {'artifact': '../../x'})
            self.assertEqual(code, 400)

    def test_missing_artifact_file_is_honest(self):
        with tempfile.TemporaryDirectory() as d:
            code, body = api_v2.apk_portal(srv(Path(d) / 'no.apk', Path(d)), {'artifact': 'windows-x64'})
            self.assertEqual(code, 409)
            self.assertIn('agent_x64.exe', body['error'])

    def test_artifact_is_served(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'agent_x64.exe').write_bytes(b'MZfixture')
            s = srv(Path(d) / 'no.apk', Path(d))
            with patch('src.fabric.mdns.lan_interface_ip', lambda scope: '192.168.1.20'), \
                 patch.object(ap, 'ThreadingHTTPServer', lambda address, handler: ThreadingHTTPServer(('127.0.0.1', 0), handler)), \
                 patch.object(ap.threading, 'Timer', Timer):
                code, state = api_v2.apk_portal(s, {'artifact': 'windows-x64', 'minutes': 10})
                try:
                    self.assertEqual(code, 200)
                    self.assertTrue(state['url'].endswith('/agent_x64.exe'))
                    self.assertEqual(state['filename'], 'agent_x64.exe')
                    r = build_opener(ProxyHandler({})).open(
                        f"http://127.0.0.1:{s.apk_portal._srv.server_port}/agent_x64.exe")
                    self.assertEqual(r.read(), b'MZfixture')
                    r.close()
                finally:
                    s.apk_portal.stop()


if __name__ == '__main__':
    unittest.main()
