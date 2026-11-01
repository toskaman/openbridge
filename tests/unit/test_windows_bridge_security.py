"""F30 sec-code: bridge PSK strength, v4 plaintext warning, relay enroll validation."""
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from src.adapters import windows_bridge
from src.adapters.windows_bridge import WindowsBridge, BridgeUnavailable, MIN_PSK_LENGTH
from src.fabric import relay as R


class PskStrengthTests(unittest.TestCase):
    def test_threshold_is_documented(self):
        self.assertIsInstance(MIN_PSK_LENGTH, int)
        self.assertGreaterEqual(MIN_PSK_LENGTH, 16)

    def test_rejects_empty_short_and_non_string_psk(self):
        for bad in ('', 'x' * (MIN_PSK_LENGTH - 1), None, b'x' * 32, 12345):
            with self.assertRaises(BridgeUnavailable, msg=repr(bad)):
                WindowsBridge(bad, '127.0.0.1')

    def test_accepts_threshold_psk(self):
        b = WindowsBridge('x' * MIN_PSK_LENGTH, '127.0.0.1')
        b.close()
        self.assertFalse(b.connected())

    def test_short_psk_message_names_threshold_without_echoing_key(self):
        with self.assertRaises(BridgeUnavailable) as ctx:
            WindowsBridge('short', '127.0.0.1')
        self.assertIn(str(MIN_PSK_LENGTH), str(ctx.exception))
        self.assertNotIn('short', str(ctx.exception))


class PlaintextWarningTests(unittest.TestCase):
    def test_start_warns_v4_is_plaintext(self):
        import src.server as server
        made = {}

        class FakeBridge:
            def __init__(self, psk, bind_ip, port):
                made.update(psk=psk, bind_ip=bind_ip, port=port)

            def start(self):
                return self

        class NoVault:
            def get(self, name):
                return None

        with mock.patch.object(windows_bridge, 'WindowsBridge', FakeBridge), \
                mock.patch('src.fabric.mdns.lan_interface_ip', return_value='192.168.1.10'), \
                mock.patch('src.fabric.mdns.default_scope', return_value='lan'), \
                mock.patch('src.fabric.credential_vault.Vault', NoVault), \
                mock.patch.dict(os.environ, {'OPENBRIDGE_WINDOWS_PSK': 'env_psk_0123456789abcdef'}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                out = server.start_windows_bridge(9999)
        self.assertIsInstance(out, FakeBridge)
        self.assertEqual(made['psk'], 'env_psk_0123456789abcdef')
        self.assertEqual((made['bind_ip'], made['port']), ('192.168.1.10', 9999))
        self.assertIn('NOT encrypted', buf.getvalue())
        self.assertIn('v4', buf.getvalue())

    def test_vault_psk_wins_over_env(self):
        import src.server as server
        made = {}

        class FakeBridge:
            def __init__(self, psk, bind_ip, port):
                made['psk'] = psk

            def start(self):
                return self

        class VaultWithPsk:
            def get(self, name):
                return 'vault_psk_0123456789abcdef' if name == 'windows-bridge-psk' else None

        with mock.patch.object(windows_bridge, 'WindowsBridge', FakeBridge), \
                mock.patch('src.fabric.mdns.lan_interface_ip', return_value='192.168.1.10'), \
                mock.patch('src.fabric.mdns.default_scope', return_value='lan'), \
                mock.patch('src.fabric.credential_vault.Vault', VaultWithPsk), \
                mock.patch.dict(os.environ, {'OPENBRIDGE_WINDOWS_PSK': 'env_psk_0123456789abcdef'}):
            with redirect_stdout(io.StringIO()):
                server.start_windows_bridge()
        self.assertEqual(made['psk'], 'vault_psk_0123456789abcdef')

    def test_no_warning_when_psk_rejected(self):
        import src.server as server
        with mock.patch('src.fabric.mdns.lan_interface_ip', return_value='127.0.0.1'), \
                mock.patch('src.fabric.mdns.default_scope', return_value='lan'), \
                mock.patch('src.fabric.credential_vault.Vault') as vault_cls, \
                mock.patch.dict(os.environ, {'OPENBRIDGE_WINDOWS_PSK': 'short'}):
            vault_cls.return_value.get.return_value = None
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(BridgeUnavailable):
                    server.start_windows_bridge()
        self.assertNotIn('NOT encrypted', buf.getvalue())


class EnrollValidationTests(unittest.TestCase):
    KEY = R.derive_key('123456', 'rn', 'pn')

    def _declared(self):
        return {'capabilities': ['ble_scan'],
                'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}}

    def test_accepts_real_and_simulated_ids(self):
        m = R.RelayManager(lambda r, msg: {})
        for rid in ('relay-abcdef012345', 'tv', 'phone', 'r-watch', 'r-tv-sim', 'relay-draintest1'):
            m.enroll(rid, self.KEY, 'dev-1', self._declared())
            self.assertIn(rid, m.relays)

    def test_length_boundary(self):
        m = R.RelayManager(lambda r, msg: {})
        m.enroll('a' * 60, self.KEY, 'dev-1', self._declared())
        with self.assertRaises(R.RelayError):
            m.enroll('a' * 61, self.KEY, 'dev-1', self._declared())

    def test_rejects_vault_unsafe_ids(self):
        m = R.RelayManager(lambda r, msg: {})
        for bad in ('', None, 12345, ['x'], 'has space', 'a/b', '..', 'relay-ABC!', '-lead'):
            with self.assertRaises(R.RelayError, msg=repr(bad)):
                m.enroll(bad, self.KEY, 'dev-1', self._declared())
        self.assertEqual(m.relays, {})

    def test_enrolled_id_is_revoke_safe(self):
        # Regression: an enroll-accepted id must survive the revoke path's vault lookup
        # (RelayStore.remove -> Vault._path raised an uncaught ValueError for rogue ids).
        from src.fabric.credential_vault import Vault
        m = R.RelayManager(lambda r, msg: (_ for _ in ()).throw(OSError('down')))
        m.enroll('relay-abcdef012345', self.KEY, 'dev-1', self._declared())
        Vault()._path('relay-key-' + 'relay-abcdef012345'[6:])
        m.revoke('relay-abcdef012345')
        self.assertNotIn('relay-abcdef012345', m.relays)


if __name__ == '__main__':
    unittest.main()