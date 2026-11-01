"""Durable relay pairings (key in the vault only, metadata file atomic, corrupt file fails closed) and restore after
a server restart (signed proof required)."""
import json
import tempfile
import unittest
from pathlib import Path

from src.fabric import aead as A
from src.fabric import relay as R
from src.fabric.relay_store import RelayStore
from tests.runtime.test_remote_controls import FakeCompanion, KEY


class FakeVault:
    available = True

    def __init__(self):
        self.d = {}

    def put(self, n, s): self.d[n] = s
    def get(self, n): return self.d.get(n)
    def delete(self, n): self.d.pop(n, None)


def store():
    d = tempfile.mkdtemp()
    return RelayStore(Path(d) / 'relays.json', FakeVault())


class Store(unittest.TestCase):
    def test_roundtrip_key_only_in_vault(self):
        s = store()
        self.assertTrue(s.save('relay-abc123', 'SER1', KEY, {'capabilities': ['remote_controls', 'aead1']}, 'aead1'))
        self.assertNotIn(KEY.hex(), s.path.read_text(encoding='utf-8'))                      # never on disk in clear
        self.assertEqual(s.load(), [('relay-abc123', 'SER1', KEY, {'capabilities': ['aead1', 'remote_controls'], 'battery_powered': False}, 'aead1')])

    def test_repair_replaces_and_remove_forgets(self):
        s = store()
        s.save('relay-aaa111', 'SER1', KEY, {}, None)
        s.save('relay-bbb222', 'SER1', b'n' * 32, {}, None)                  # same device paired again
        self.assertEqual([r[0] for r in s.load()], ['relay-bbb222'])
        self.assertIsNone(s.vault.get('relay-key-aaa111'))
        s.remove('relay-bbb222')
        self.assertEqual(s.load(), [])
        self.assertEqual(s.vault.d, {})

    def test_corrupt_file_fails_closed_and_is_not_overwritten(self):
        s = store()
        s.path.write_text('{not json', encoding='utf-8')
        self.assertEqual(s.load(), [])
        self.assertIn('unreadable', s.error)
        self.assertFalse(s.save('relay-abc123', 'SER1', KEY, {}, None))
        self.assertEqual(s.path.read_text(encoding='utf-8'), '{not json')

    def test_disabled_without_vault_and_bad_ids(self):
        s = RelayStore(Path(tempfile.mkdtemp()) / 'r.json', None)
        self.assertFalse(s.save('relay-abc123', 'SER1', KEY, {}, None))
        s2 = store()
        self.assertFalse(s2.save('../evil', 'SER1', KEY, {}, None))
        self.assertFalse(s2.save('relay-abc123', 'bad serial!', KEY, {}, None))


class AeadCompanion(FakeCompanion):
    """FakeCompanion that only speaks aead1 after negotiation (mirrors RelayServer.java)."""
    def __init__(self, rid, **kw):
        super().__init__(**kw); self.rid = rid

    def __call__(self, relay, message):
        if message.get('enc') != 'aead1':
            raise OSError('403 encryption required')
        inner = json.loads(A.open_(self.key, A.aad_for(self.rid, 'pc>relay'), message))
        reply = super().__call__(relay, inner)
        return A.seal(self.key, A.aad_for(self.rid, 'relay>pc'), json.dumps(reply).encode())


class Restore(unittest.TestCase):
    def server(self, s, companion, serial_present=True):
        import tempfile as _t
        from src.fabric.session import SessionJournal
        from src.server import create_server
        srv = create_server(0, fabric_salt=b't', session_journal=SessionJournal(_t.mkdtemp() + '/s.json'), relay_store=s)
        srv.android.handle_for = lambda serial: 'android-h1' if serial_present and serial == 'SER1' else None
        srv.android.relay_urls = lambda handle: ['http://127.0.0.1:9']
        self.addCleanup(srv.server_close)
        return srv, srv.restore_relays(transport_factory=lambda url: companion)

    def test_plain_pairing_is_restored_and_proven(self):
        s = store(); s.save('relay-abc123', 'SER1', KEY, {'capabilities': ['remote_controls']}, None)
        srv, out = self.server(s, FakeCompanion())
        self.assertEqual(out, [('relay-abc123', 'RESTORED')])
        r = srv.relays.relays['relay-abc123']
        self.assertTrue(r['online']); self.assertEqual(r['device_key'], 'android-h1')
        self.assertIn('remote_controls', r['capabilities'])

    def test_aead_pairing_is_restored_sealed(self):
        s = store(); s.save('relay-abc123', 'SER1', KEY, {'capabilities': ['remote_controls', 'aead1']}, 'aead1')
        srv, out = self.server(s, AeadCompanion('relay-abc123'))
        self.assertEqual(out, [('relay-abc123', 'RESTORED')])
        self.assertEqual(srv.relays.relays['relay-abc123']['aead'], 'aead1')

    def test_absent_device_is_not_enrolled_and_unprovable_stays_offline(self):
        s = store(); s.save('relay-abc123', 'SER1', KEY, {}, None)
        srv, out = self.server(s, FakeCompanion(), serial_present=False)
        self.assertEqual(out, []); self.assertNotIn('relay-abc123', srv.relays.relays)
        srv2, out2 = self.server(s, FakeCompanion(key=b'x' * 32))         # device was re-paired elsewhere
        self.assertTrue(out2[0][1].startswith('OFFLINE'))
        self.assertFalse(srv2.relays.relays['relay-abc123']['online'])


if __name__ == '__main__':
    unittest.main()
