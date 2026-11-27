"""Shared local-network host guard: one definition used by every adapter and client."""
import unittest

from src.fabric import netguard as NG


class LocalHost(unittest.TestCase):
    def test_private_loopback_linklocal_ips(self):
        for host in ('192.168.1.10', '10.0.0.2', '172.16.0.1', '172.31.255.255', '127.0.0.1', '::1',
                     'fe80::1', 'fe80::abcd:1234', '169.254.169.254', 'fc00::1', '100.64.0.1', '100.127.255.254'):
            self.assertTrue(NG.local_host(host), host)
        for host in ('8.8.8.8', '1.1.1.1', '100.128.0.1', '2001:4860:4860::8888', '::ffff:8.8.8.8'):
            self.assertFalse(NG.local_host(host), host)

    def test_local_names(self):
        for host in ('localhost', 'LOCALHOST', 'homeassistant', 'box.localhost', 'lamp.local', 'router.lan',
                     'nas.home.arpa', 'pc.tail1234.ts.net', '  lamp.local  ', 'lamp.local.', 'my-box_2'):
            self.assertTrue(NG.local_host(host, bare_names=True), host)
        for host in ('example.com', 'lamp.local.evil.com', 'localhost.evil.com',
                     'a/b', 'a\\b', 'user@host', 'a b', '', '.', None, 42, ['x']):
            self.assertFalse(NG.local_host(host, bare_names=True), host)

    def test_bare_names_opt_in(self):
        self.assertTrue(NG.local_host('lamp', bare_names=True))
        self.assertTrue(NG.local_host('my-box_2', bare_names=True))
        self.assertFalse(NG.local_host('lamp'))
        self.assertFalse(NG.local_host('my-box_2'))
        self.assertFalse(NG.local_host('[fe80::1]', bare_names=True))

    def test_extras(self):
        self.assertTrue(NG.local_host('fritz.box', extra_names=('fritz.box',)))
        self.assertFalse(NG.local_host('fritz.box'))
        self.assertTrue(NG.local_host('x.fritz.box', extra_suffixes=('.fritz.box',)))
        self.assertFalse(NG.local_host('x.fritz.box'))

    def test_extras_case_insensitive(self):
        self.assertTrue(NG.local_host('fritz.box', extra_names=('Fritz.Box',)))
        self.assertTrue(NG.local_host('x.fritz.box', extra_suffixes=('.Fritz.Box',)))

    def test_require_local(self):
        self.assertEqual(NG.require_local('lamp.local', 'light'), 'lamp.local')
        with self.assertRaises(ValueError):
            NG.require_local('8.8.8.8', 'light')


if __name__ == '__main__':
    unittest.main()
