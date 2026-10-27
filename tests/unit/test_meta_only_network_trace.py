"""Release gate (prep kit JURY_RELEASE_GATES / RUNTIME_META_ONLY_TEST_MATRIX): a runtime network trace, not only a
static scan. Every outgoing TCP connection attempted by each model path is recorded at the socket layer (and then
refused, so no real traffic leaves CI). Allowed destinations: the Meta Model API and the pinned local Meta servers."""
import socket
import unittest
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import mock

ALLOWED = {('api.meta.ai', 443), ('127.0.0.1', 11437), ('127.0.0.1', 11438), ('127.0.0.1', 11439)}


class Trace:
    def __init__(self):
        self.seen = []

    def __enter__(self):
        trace = self
        real_connect = socket.socket.connect

        def connect(sock, address):
            trace.seen.append((str(address[0]), int(address[1])))
            raise ConnectionRefusedError('network blocked in the Meta-only trace test')

        def getaddrinfo(host, port, *a, **k):          # keep the hostname visible to the recorder
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (host, port))]
        self.patches = [mock.patch.object(socket.socket, 'connect', connect),
                        mock.patch('socket.getaddrinfo', getaddrinfo)]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()


class MetaOnlyNetworkTrace(unittest.TestCase):
    def assert_only_meta(self, seen):
        self.assertTrue(seen, 'the model path made no connection attempt; trace proves nothing')
        bad = [d for d in seen if d not in ALLOWED]
        self.assertEqual(bad, [], f'non-Meta destination(s): {bad}')

    def test_hosted_broker_contacts_only_meta_api(self):
        from src.ai.broker import RuntimeModelBroker, MetaTransport, CreditPermit, ModelBlocked
        with TemporaryDirectory() as d, Trace() as t:
            b = RuntimeModelBroker(Path(d) / 'b.sqlite', CreditPermit('trace', datetime.now(timezone.utc), 150, 0.20), MetaTransport('test-key'))
            with self.assertRaises(ModelBlocked):
                b.recommend({'battery_percent': 50})
        self.assert_only_meta(t.seen)

    def test_local_llama_and_glimmer_contact_only_local_meta_servers(self):
        from src.ai.local_meta import LocalMetaBroker
        from src.ai.glimmer import GlimmerBroker
        for cls in (LocalMetaBroker, GlimmerBroker):
            with Trace() as t:
                try:
                    cls().ready()
                except Exception:
                    pass
            self.assert_only_meta(t.seen)

    def test_a_non_meta_destination_would_be_caught(self):
        import urllib.request
        with Trace() as t:
            with self.assertRaises(Exception):
                urllib.request.urlopen('https://api.example-non-meta.test/v1', timeout=1)
        self.assertIn(('api.example-non-meta.test', 443), t.seen)
        self.assertNotIn(('api.example-non-meta.test', 443), ALLOWED)


if __name__ == '__main__':
    unittest.main()
