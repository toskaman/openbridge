"""Ordered relay transports: direct Wi-Fi/LAN first, adb forward last. No device."""
import unittest
from types import SimpleNamespace
from unittest import mock
from src.adapters.android import AndroidAdapter
from src.fabric import relay as R
def _adapter():
    def run(args, **kw):
        a = args[1:]
        if a == ['forward', '--list']:
            return SimpleNamespace(returncode=0, stdout='')
        if a[0] == '-s' and a[2:] == ['forward', 'tcp:0', 'tcp:47800']:
            return SimpleNamespace(returncode=0, stdout='50111\n')
        return SimpleNamespace(returncode=0, stdout='')
    ad = AndroidAdapter(executable='adb', runner=run)
    ad._handles = {'192.168.1.14:37565': 'h-watch', 'BV9300PEEA0004883': 'h-usb'}
    return ad
class DirectUrl(unittest.TestCase):
    def test_wifi_serial_gives_direct_url(self):
        self.assertEqual(_adapter().direct_url('h-watch'), 'http://192.168.1.14:47800')
    def test_usb_serial_gives_none(self):
        self.assertIsNone(_adapter().direct_url('h-usb'))
    def test_unknown_handle_raises(self):
        with self.assertRaises(ValueError):
            _adapter().direct_url('h-nope')
    def test_non_private_ip_gives_none(self):
        ad = _adapter()
        ad._handles['8.8.8.8:5555'] = 'h-pub'
        self.assertIsNone(ad.direct_url('h-pub'))
    def test_loopback_ip_gives_none(self):
        ad = _adapter()
        ad._handles['127.0.0.1:5555'] = 'h-lo'
        self.assertIsNone(ad.direct_url('h-lo'))
class RelayUrls(unittest.TestCase):
    def test_direct_first_then_forward(self):
        urls = _adapter().relay_urls('h-watch')
        self.assertEqual(urls, ['http://192.168.1.14:47800', 'http://127.0.0.1:50111'])
    def test_usb_is_forward_only(self):
        self.assertEqual(_adapter().relay_urls('h-usb'), ['http://127.0.0.1:50111'])
    def test_unknown_raises_without_forward_side_effect(self):
        calls = []
        def run(args, **kw):
            calls.append(args[1:])
            return SimpleNamespace(returncode=0, stdout='')
        ad = AndroidAdapter(executable='adb', runner=run)
        ad._handles = {}
        with self.assertRaises(ValueError):
            ad.relay_urls('h-nope')
        self.assertEqual(calls, [])
class Failover(unittest.TestCase):
    def test_tries_in_order_first_success_wins(self):
        seen = []
        def fake(url, timeout=25):
            seen.append((url, timeout))
            def send(_r, m):
                if url.startswith('http://127.0.0.1'):
                    raise OSError('refused')
                return {'ok': True}
            return send
        with mock.patch.object(R, 'http_transport', side_effect=fake):
            send = R.failover_transport(['http://127.0.0.1:50111', 'http://192.168.1.14:47800'])
            self.assertEqual(send(None, {'op': 'x'}), {'ok': True})
        self.assertEqual([u for u, _ in seen], ['http://127.0.0.1:50111', 'http://192.168.1.14:47800'])
    def test_lan_gets_short_timeout_loopback_gets_full(self):
        seen = {}
        def fake(url, timeout=25):
            seen[url] = timeout
            return lambda _r, m: {'ok': True}
        with mock.patch.object(R, 'http_transport', side_effect=fake):
            R.failover_transport(['http://192.168.1.14:47800', 'http://127.0.0.1:50111'], lan_timeout=3, timeout=25)
        self.assertEqual(seen, {'http://192.168.1.14:47800': 3, 'http://127.0.0.1:50111': 25})
    def test_protocol_refusal_propagates_without_failover(self):
        calls = []
        def fake(url, timeout=25):
            def send(_r, m):
                calls.append(url)
                raise R.RelayError('Relay refused: bad envelope')
            return send
        with mock.patch.object(R, 'http_transport', side_effect=fake):
            send = R.failover_transport(['http://127.0.0.1:1', 'http://127.0.0.1:2'])
            with self.assertRaises(R.RelayError):
                send(None, {'op': 'x'})
        self.assertEqual(calls, ['http://127.0.0.1:1'])
    def test_all_down_reraises_last_oserror(self):
        def fake(url, timeout=25):
            def send(_r, m):
                raise OSError('down ' + url)
            return send
        with mock.patch.object(R, 'http_transport', side_effect=fake):
            send = R.failover_transport(['http://127.0.0.1:1', 'http://127.0.0.1:2'])
            with self.assertRaises(OSError):
                send(None, {'op': 'x'})
    def test_empty_urls_rejected(self):
        with self.assertRaises(R.RelayError):
            R.failover_transport([])
    def test_out_of_scope_rejected_at_construction(self):
        with self.assertRaises(R.RelayError):
            R.failover_transport(['http://8.8.8.8:47800'])
if __name__ == '__main__':
    unittest.main()
