"""Unit tests for ENGO / ActiveLook by Microoled firmware metadata & config backup."""
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.adapters import activelook as AL
from src.glasses.backup import (
    backup_glasses,
    build_restore_frames,
    decode_payload,
    decode_tx_frame,
    reassemble_tx_frames,
    write_backup_archive,
)


class GlassesBackupTests(unittest.TestCase):
    def test_decode_tx_frame_and_payloads(self):
        # vers (0x06): fw 4.7.2.0, year 2026 (26), week 45, serial 0x010203
        vers_pkt = AL.encode_packet(0x06, bytes([4, 7, 2, 0, 26, 45, 0x01, 0x02, 0x03]))
        cmd, qid, data = decode_tx_frame(vers_pkt)
        self.assertEqual(cmd, 0x06)
        self.assertEqual(qid, b'')
        info = decode_payload(cmd, data)
        self.assertEqual(info['fw_version'], '4.7.2.0')
        self.assertEqual(info['build_year'], 2026)
        self.assertEqual(info['serial_hex'], '010203')

        # settings (0x0A): 5-byte form (x=-4, y=2, luma=12, als=1, gesture=1)
        st_pkt = AL.encode_packet(0x0A, struct.pack('>bbBBB', -4, 2, 12, 1, 1))
        _, _, st_data = decode_tx_frame(st_pkt)
        st = decode_payload(0x0A, st_data)
        self.assertEqual((st['shift_x'], st['shift_y'], st['luma']), (-4, 2, 12))
        self.assertTrue(st['als'] and st['gesture'])

        # cfgFreeSpace (0xD7) + layoutList (0x64) + fontList (0x50) + imgList (0x47)
        self.assertEqual(decode_payload(0xD7, struct.pack('>I', 2097152))['free_space_bytes'], 2097152)
        self.assertEqual(decode_payload(0x64, bytes([1, 2, 9]))['layout_ids'], [1, 2, 9])
        self.assertEqual(decode_payload(0x50, bytes([0, 12, 1, 18]))['fonts'], [{'id': 0, 'height': 12}, {'id': 1, 'height': 18}])
        imgs = decode_payload(0x47, struct.pack('>BHH', 3, 64, 48))['images']
        self.assertEqual(imgs, [{'id': 3, 'width': 64, 'height': 48}])

    def test_build_restore_frames_and_write_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_fw = tmp_path / 'engo3_fw_4.7.2.img'
            fake_fw.write_bytes(b'SUOTA-FW-TEST-IMAGE-BYTES')

            tx = [
                AL.encode_packet(0x06, bytes([4, 7, 2, 0, 26, 45, 0xAA, 0xBB, 0xCC])),
                AL.encode_packet(0x0A, struct.pack('>bbBBB', 3, -2, 10, 1, 1)),
                AL.encode_packet(0x64, bytes([1, 2, 7, 9])),
                AL.encode_packet(0xD7, struct.pack('>I', 1500000)),
            ]
            dis = {
                'manufacturer': 'ENGO / Microoled',
                'model_number': 'ENGO 3 Photochromic',
                'firmware_revision': '4.7.2',
            }
            res = write_backup_archive(
                tmp_path / 'backups',
                dis=dis,
                tx_frames=tx,
                device_meta={'name': 'ENGO 3', 'address': 'AA:BB:CC:DD:EE:FF', 'suota_present': True},
                fw_package=fake_fw,
            )
            self.assertEqual(res['partners'], ['ENGO', 'ActiveLook by Microoled'])
            self.assertTrue(Path(res['archive_zip']).is_file())
            self.assertEqual(res['firmware_revision'], '4.7.2')
            self.assertTrue(res['suota_present'])
            self.assertGreater(res['settings_restore_bytes'], 0)

            with zipfile.ZipFile(res['archive_zip'], 'r') as zf:
                names = set(zf.namelist())
                self.assertIn('manifest.json', names)
                self.assertIn('raw_frames.jsonl', names)
                self.assertIn('settings_restore.bin', names)
                self.assertIn('engo3_fw_4.7.2.img', names)
                manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
                self.assertEqual(manifest['partners'], ['ENGO', 'ActiveLook by Microoled'])
                self.assertEqual(manifest['activelook']['layout_ids'], [1, 2, 7, 9])

    def test_build_restore_frames_roundtrip(self):
        raw = build_restore_frames({'shift_x': -5, 'shift_y': 4, 'luma': 11, 'gesture': True, 'als': False})
        self.assertIn(b'\xFF\x09', raw)
        self.assertIn(b'\xFF\x10', raw)
        self.assertIn(b'\xFF\x21', raw)
        self.assertIn(b'\xFF\x22', raw)

    def test_reassemble_wide_tx_frames_and_cfg_list(self):
        # Wide 0x10 imgList frame split across two BLE notification chunks (>244 B)
        imgs_payload = b''.join(struct.pack('>BHH', i, 26, 26) for i in range(60))
        total_len = 6 + len(imgs_payload)
        wide_frame = b'\xFF\x47\x10' + struct.pack('>H', total_len) + imgs_payload + b'\xAA'
        c1, c2 = wide_frame[:244], wide_frame[244:]
        assembled = reassemble_tx_frames([c1, c2])
        self.assertEqual(assembled, [wide_frame])
        cmd, _, data = decode_tx_frame(assembled[0])
        self.assertEqual(cmd, 0x47)
        self.assertEqual(len(decode_payload(0x47, data)['images']), 60)

        # cfgList (0xD3) + 8-byte cfgFreeSpace (0xD7)
        cfg_bytes = b'ALooK\x00' + struct.pack('>IIBBB', 626730, 24, 0, 2, 1)
        cfgs = decode_payload(0xD3, cfg_bytes)['configs']
        self.assertEqual(cfgs[0]['name'], 'ALooK')
        self.assertEqual(cfgs[0]['size_bytes'], 626730)
        self.assertTrue(cfgs[0]['is_system'])
        space = decode_payload(0xD7, struct.pack('>II', 29736960, 27115520))
        self.assertEqual(space['total_space_bytes'], 29736960)
        self.assertEqual(space['free_space_bytes'], 27115520)

    def test_backup_glasses_fallback_to_relay(self):
        class BleakBluetoothNotAvailableError(Exception):
            pass

        def _fail_no_bt(coro):
            coro.close()
            raise BleakBluetoothNotAvailableError('No Bluetooth adapter found')

        expected = {'partners': ['ENGO', 'ActiveLook by Microoled'], 'tx_frames_captured': 14}
        with patch('src.glasses.backup.asyncio.run', side_effect=_fail_no_bt), \
             patch('src.glasses.backup.backup_via_relay', return_value=expected) as mock_relay:
            res = backup_glasses(out_dir='D:/tmp/out', address='C0:06:46:0A:D7:B4')
        self.assertEqual(res, expected)
        mock_relay.assert_called_once()


if __name__ == '__main__':
    unittest.main()
