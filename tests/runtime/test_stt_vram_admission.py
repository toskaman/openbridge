"""VRAM admission for the local STT worker: a full GPU sends the model to the CPU instead of an OOM crash."""
import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from src.ai import stt_local


def _report_device(conn, snapshot):
    """Stub worker target (top-level: spawn pickles it): answers with the device the parent chose."""
    try:
        conn.recv()
        conn.send(('ok', {'transcript': os.environ.get(stt_local.DEVICE_ENV, 'unset'), 'model': 'stub',
                          'language': 'fr', 'seconds': 0.5, 'backend': 'local-mms'}))
    finally:
        conn.close()


class VramAdmission(unittest.TestCase):
    def test_free_vram_is_read_from_nvidia_smi(self):
        run = SimpleNamespace(stdout='3120\n11800\n')
        with mock.patch.object(stt_local.shutil, 'which', return_value='nvidia-smi'), \
                mock.patch.object(stt_local.subprocess, 'run', return_value=run):
            self.assertEqual(stt_local._free_vram_mb(), 11800)
        with mock.patch.object(stt_local.shutil, 'which', return_value=None):
            self.assertIsNone(stt_local._free_vram_mb())
        with mock.patch.object(stt_local.shutil, 'which', return_value='nvidia-smi'), \
                mock.patch.object(stt_local.subprocess, 'run', side_effect=subprocess.TimeoutExpired('nvidia-smi', 5)):
            self.assertIsNone(stt_local._free_vram_mb())

    def test_device_choice(self):
        for free, want in ((2048, 'cpu'), (stt_local.MIN_FREE_VRAM_MB, 'auto'), (16000, 'auto'), (None, 'auto')):
            with self.subTest(free=free), mock.patch.object(stt_local, '_free_vram_mb', return_value=free):
                self.assertEqual(stt_local.choose_device(), want)

    def test_the_spawned_worker_receives_the_chosen_device(self):
        for free, want in ((1024, 'cpu'), (12000, 'auto')):
            with self.subTest(free=free), mock.patch.object(stt_local, '_free_vram_mb', return_value=free), \
                    mock.patch.object(stt_local, '_worker_target', _report_device):
                w = stt_local._Worker('/fake/snap')
                try:
                    self.assertEqual(w.device, want)
                    self.assertEqual(w.transcribe('fr', b'\x00\x01' * 8000)['transcript'], want)
                finally:
                    w.shutdown()
        self.assertNotIn(stt_local.DEVICE_ENV, os.environ)       # the parent environment is restored


if __name__ == '__main__':
    unittest.main()
