"""§7 capture/transfer store (server-side bytes for captures + pulled files)."""
import hashlib
import os
import unittest
from pathlib import Path
import tempfile

from src.runtime import capture_store as C


class CaptureStoreTest(unittest.TestCase):
    def test_put_get_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            s = C.CaptureStore(d)
            cid = s.put(b'\x89PNG-data', kind='cap')
            self.assertTrue(cid.startswith('cap-'))
            self.assertEqual(s.get(cid), b'\x89PNG-data')
            self.assertEqual(s.sha256(cid), hashlib.sha256(b'\x89PNG-data').hexdigest())

    def test_unknown_id_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(C.StoreError):
                C.CaptureStore(d).get('cap-deadbeefdeadbeef')

    def test_bad_id_format_raises_without_touching_disk(self):
        with tempfile.TemporaryDirectory() as d:
            s = C.CaptureStore(d)
            for bad in ('../x', 'cap-xyz!', '', 'cap-short', 'xfer-' + 'g' * 16):
                with self.assertRaises(C.StoreError, msg=bad):
                    s.get(bad)
            self.assertEqual(os.listdir(d), [])

    def test_put_rejects_empty_and_oversize(self):
        with tempfile.TemporaryDirectory() as d:
            s = C.CaptureStore(d)
            with self.assertRaises(C.StoreError):
                s.put(b'', kind='cap')
            with self.assertRaises(C.StoreError):
                s.put(b'x' * (C.MAX_FILE + 1), kind='cap')

    def test_evicts_oldest_beyond_cap(self):
        with tempfile.TemporaryDirectory() as d:
            s = C.CaptureStore(d, max_files=3)
            ids = [s.put(bytes([i]) * 8, kind='cap') for i in range(4)]
            with self.assertRaises(C.StoreError):
                s.get(ids[0])
            self.assertEqual(s.get(ids[1]), b'\x01' * 8)
            self.assertEqual(s.get(ids[3]), b'\x03' * 8)

    def test_eviction_order_survives_reopen(self):
        with tempfile.TemporaryDirectory() as d:
            s = C.CaptureStore(d, max_files=3)
            ids = [s.put(bytes([i]) * 8, kind='cap') for i in range(3)]
            s2 = C.CaptureStore(d, max_files=3)
            s2.put(b'\x09' * 8, kind='cap')
            with self.assertRaises(C.StoreError):
                s2.get(ids[0])
            self.assertEqual(s2.get(ids[2]), b'\x02' * 8)

    def test_transfer_kind_uses_xfer_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            s = C.CaptureStore(d)
            tid = s.put(b'data', kind='xfer')
            self.assertTrue(tid.startswith('xfer-'))
            self.assertEqual(s.get(tid), b'data')

    def test_ids_are_unique(self):
        with tempfile.TemporaryDirectory() as d:
            s = C.CaptureStore(d)
            self.assertEqual(len({s.put(b'data', kind='cap') for _ in range(50)}), 50)


if __name__ == '__main__':
    unittest.main()
