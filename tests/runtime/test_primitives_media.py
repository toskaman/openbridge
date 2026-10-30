"""§7 media/file primitives (SIMULATED_VERIFIED: fake android + tmp store; no adb calls)."""
import hashlib
import tempfile
import unittest
from types import SimpleNamespace

from tests.runtime.test_primitives import ctx
from src.runtime import montage as M
from src.runtime.primitives import Executor, PRIMITIVES


PNG_2X2_RED = M.encode_png(2, 2, bytes((255, 0, 0, 255)) * 4)


class FakeMediaAndroid:
    def __init__(self):
        self._handles = {'SERIAL1': 'h1'}
        self.files = {'/sdcard/Download/a.bin': b'\x00\x01\x02'}
        self.pushed = {}
        self.identity = 'id-1'

    def stable_identifier(self, handle, salt):
        return self.identity if handle in self._handles.values() else None

    def screencap(self, serial):
        assert serial == 'SERIAL1'
        return PNG_2X2_RED

    def pull_file(self, handle, remote, max_bytes=8 * 1024 * 1024):
        assert handle == 'h1'
        if remote not in self.files or len(self.files[remote]) > max_bytes:
            raise ValueError('File pull unavailable')
        return self.files[remote]

    def push_file(self, handle, data, name):
        assert handle == 'h1'
        remote = '/sdcard/OpenBridge/' + name
        self.pushed[remote] = bytes(data)
        self.files[remote] = bytes(data)
        return remote

    def file_sha256(self, handle, remote):
        assert handle == 'h1'
        return hashlib.sha256(self.files[remote]).hexdigest()


class MediaPrimitives(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.c, self.key = ctx(self.tmp)
        self.c.android = FakeMediaAndroid()
        self.ex = Executor(self.c)

    def run_(self, pid, params=None, consent=True, key=None):
        return self.ex.execute(pid, key or self.key, params or {}, consent)

    def test_screen_capture_stores_png(self):
        r = self.run_('screen_capture', {})
        self.assertEqual(r['state'], 'EXECUTED')
        self.assertTrue(r['result']['capture_id'].startswith('cap-'))
        self.assertEqual(r['result']['sha256'], hashlib.sha256(PNG_2X2_RED).hexdigest())
        self.assertEqual((r['result']['width'], r['result']['height']), (2, 2))
        self.assertTrue(r['verified'])

    def test_screen_capture_needs_consent(self):
        r = self.run_('screen_capture', {}, consent=False)
        self.assertEqual(r['state'], 'BLOCKED')
        self.assertIn('CONSENT_REQUIRED', r['errors'][0])

    def test_screen_capture_rejects_non_png(self):
        self.c.android.screencap = lambda serial: b'garbage-bytes-not-png-padding......'
        r = self.run_('screen_capture', {})
        self.assertEqual(r['state'], 'FAILED')

    def test_capture_send_pushes_and_verifies_hash(self):
        cap = self.run_('screen_capture', {})['result']['capture_id']
        r = self.run_('capture_send', {'capture_id': cap}, key=self.key)
        self.assertEqual(r['state'], 'EXECUTED')
        self.assertEqual(r['result']['remote'], '/sdcard/OpenBridge/' + cap + '.png')
        self.assertEqual(r['result']['sha256'], hashlib.sha256(PNG_2X2_RED).hexdigest())

    def test_capture_send_unknown_capture_blocked(self):
        r = self.run_('capture_send', {'capture_id': 'cap-' + '0' * 16})
        self.assertEqual(r['state'], 'BLOCKED')
        self.assertIn('UNKNOWN_CAPTURE', r['errors'][0])

    def test_capture_send_hash_mismatch_fails(self):
        cap = self.run_('screen_capture', {})['result']['capture_id']
        real = self.c.android.file_sha256
        self.c.android.file_sha256 = lambda h, remote: '0' * 64
        try:
            r = self.run_('capture_send', {'capture_id': cap})
        finally:
            self.c.android.file_sha256 = real
        self.assertEqual(r['state'], 'FAILED')
        self.assertIn('HASH_MISMATCH', r['errors'][0])

    def test_capture_montage_combines_server_side(self):
        a = self.run_('screen_capture', {})['result']['capture_id']
        b = self.run_('screen_capture', {})['result']['capture_id']
        r = self.run_('capture_montage', {'capture_ids': [a, b], 'layout': 'row'}, key='fabric')
        self.assertEqual(r['state'], 'EXECUTED')
        self.assertEqual((r['result']['width'], r['result']['height']), (4, 2))
        self.assertTrue(r['result']['capture_id'].startswith('cap-'))

    def test_file_pull_stores_transfer(self):
        r = self.run_('file_pull', {'remote': '/sdcard/Download/a.bin'})
        self.assertEqual(r['state'], 'EXECUTED')
        self.assertTrue(r['result']['transfer_id'].startswith('xfer-'))
        self.assertEqual(r['result']['sha256'], hashlib.sha256(b'\x00\x01\x02').hexdigest())

    def test_file_pull_rejects_traversal(self):
        r = self.run_('file_pull', {'remote': '/etc/hosts'})
        self.assertEqual(r['state'], 'BLOCKED')

    def test_file_push_round_trip_verifies_hash(self):
        tid = self.run_('file_pull', {'remote': '/sdcard/Download/a.bin'})['result']['transfer_id']
        r = self.run_('file_push', {'transfer_id': tid, 'name': 'relay.bin'})
        self.assertEqual(r['state'], 'EXECUTED')
        self.assertEqual(r['result']['remote'], '/sdcard/OpenBridge/relay.bin')
        self.assertEqual(self.c.android.pushed['/sdcard/OpenBridge/relay.bin'], b'\x00\x01\x02')

    def test_descriptors_are_complete(self):
        for pid in ('screen_capture', 'capture_send', 'capture_montage', 'file_pull', 'file_push'):
            self.assertIn(pid, PRIMITIVES)
            self.assertIn(pid, Executor.RUNNERS)


if __name__ == '__main__':
    unittest.main()
