"""Multi-interface mDNS browse: explicit extra interfaces only (P2P/hotspot subnets)."""
import socket
import unittest
from unittest import mock

from src.fabric import mdns
from tests.fabric.test_mdns import FakeSock, companion_packet


class BrowseIfaces(unittest.TestCase):
    def test_default_is_single_browse(self):
        seen = []

        def factory(*a, **k):
            seen.append(1)
            return FakeSock([(companion_packet(), '192.168.1.14')])

        out = mdns.browse_interfaces(sock_factory=factory)
        self.assertEqual(len(out['instances']), 1)
        self.assertEqual(len(seen), 1)

    def test_extra_ifaces_browsed_and_merged(self):
        calls = []

        def factory(*a, **k):
            return FakeSock([])

        real = mdns.discover

        def spy(timeout=2.5, scope=None, services=None, sock_factory=None, interface_ip=None):
            calls.append(interface_ip)
            if interface_ip == '192.168.49.1':
                return {'status': 'READY', 'instances': [{'service': 'x', 'addresses': ['192.168.49.5']}],
                        'ignored_out_of_scope': 0, 'packets': 1}
            return {'status': 'READY', 'instances': [], 'ignored_out_of_scope': 0, 'packets': 0}

        with mock.patch.object(mdns, 'discover', side_effect=spy):
            with mock.patch.object(mdns, 'lan_interface_ip', return_value='192.168.1.2'):
                out = mdns.browse_interfaces(extra_ifaces=['192.168.49.1'], sock_factory=factory)
        self.assertEqual(sorted(calls), ['192.168.1.2', '192.168.49.1'])
        self.assertEqual(len(out['instances']), 1)

    def test_non_private_and_junk_ifaces_rejected(self):
        calls = []

        def spy(timeout=2.5, scope=None, services=None, sock_factory=None, interface_ip=None):
            calls.append(interface_ip)
            return {'status': 'READY', 'instances': [], 'ignored_out_of_scope': 0, 'packets': 0}

        with mock.patch.object(mdns, 'discover', side_effect=spy):
            with mock.patch.object(mdns, 'lan_interface_ip', return_value='192.168.1.2'):
                mdns.browse_interfaces(extra_ifaces=['8.8.8.8', '127.0.0.1', 'nope',
                                                     '192.168.1.300', None, 42],
                                       sock_factory=lambda *a, **k: FakeSock([]))
        self.assertEqual(calls, ['192.168.1.2'])

    def test_bounded_to_four_extra(self):
        calls = []

        def spy(timeout=2.5, scope=None, services=None, sock_factory=None, interface_ip=None):
            calls.append(interface_ip)
            return {'status': 'READY', 'instances': [], 'ignored_out_of_scope': 0, 'packets': 0}

        ifaces = ['192.168.%d.1' % i for i in range(10)]
        with mock.patch.object(mdns, 'discover', side_effect=spy):
            with mock.patch.object(mdns, 'lan_interface_ip', return_value='192.168.1.2'):
                mdns.browse_interfaces(extra_ifaces=ifaces, sock_factory=lambda *a, **k: FakeSock([]))
        self.assertEqual(len(calls), 5)  # default + 4

    def test_env_provides_extra_ifaces(self):
        import os
        calls = []

        def spy(timeout=2.5, scope=None, services=None, sock_factory=None, interface_ip=None):
            calls.append(interface_ip)
            return {'status': 'READY', 'instances': [], 'ignored_out_of_scope': 0, 'packets': 0}

        with mock.patch.object(mdns, 'discover', side_effect=spy):
            with mock.patch.object(mdns, 'lan_interface_ip', return_value='192.168.1.2'):
                with mock.patch.dict(os.environ, {'OPENBRIDGE_MDNS_IFACES': '192.168.49.1, 8.8.8.8'}):
                    mdns.browse_interfaces(sock_factory=lambda *a, **k: FakeSock([]))
        self.assertEqual(sorted(calls), ['192.168.1.2', '192.168.49.1'])


if __name__ == '__main__':
    unittest.main()
