"""§3.6: local STT runs in a supervised worker; crash/timeout/low-RAM never take down the server.

Stub worker targets (top-level so spawn can pickle them) stand in for the real
multi-GB backend: no torch, no model download. One test proves the parent never
imports torch at all.
"""
import os
import time
import unittest
from unittest.mock import patch

from src.ai import stt_local
from src.ai.voice_stt import STTBlocked

CLIP = b'\x00\x01' * 8000   # 1 s of 16 kHz PCM16 mono


def _echo(conn, snapshot):
    try:
        while True:
            try:
                language, pcm = conn.recv()
            except EOFError:
                return
            conn.send(('ok', {'transcript': 'allume la lampe', 'model': 'stub', 'language': language,
                              'seconds': round(len(bytes(pcm)) / 2 / 16000, 1), 'backend': 'local-mms'}))
    finally:
        conn.close()


def _crasher(conn, snapshot):
    os._exit(3)


def _sleeper(conn, snapshot):
    try:
        conn.recv()
        time.sleep(120)
    finally:
        conn.close()


def _fatal_loader(conn, snapshot):
    try:
        conn.recv()
        conn.send(('fatal', 'local STT model failed to load (RuntimeError)'))
    finally:
        conn.close()


class SupervisedWorker(unittest.TestCase):
    def setUp(self):
        self._snap = patch.object(stt_local, 'find_snapshot', return_value='/fake/snap')
        self._snap.start()
        self._ram = patch.object(stt_local, '_free_ram_mb', return_value=16 * 1024)
        self._ram.start()
        self._target = patch.object(stt_local, '_worker_target', _echo)
        self._target.start()
        self.addCleanup(stt_local.shutdown)
        for p in (self._target, self._ram, self._snap):
            self.addCleanup(p.stop)
        stt_local._failures.clear()

    def procs(self):
        w = stt_local._worker
        return [] if w is None else [w.proc]

    def test_roundtrip_serves_transcript_and_reuses_warm_worker(self):
        first = stt_local.transcribe_pcm(CLIP, 'fr')
        self.assertEqual((first['transcript'], first['backend']), ('allume la lampe', 'local-mms'))
        worker = stt_local._worker
        self.assertTrue(worker.alive())
        stt_local.transcribe_pcm(CLIP, 'en')
        self.assertIs(stt_local._worker, worker)   # warm worker reused, not respawned

    def test_bad_input_never_spawns(self):
        with self.assertRaises(STTBlocked):
            stt_local.transcribe_pcm(b'', 'fr')
        with self.assertRaises(STTBlocked):
            stt_local.transcribe_pcm(CLIP, 'de')
        with self.assertRaises(STTBlocked):
            stt_local.transcribe_pcm(b'\x00' * 3, 'fr')
        self.assertIsNone(stt_local._worker)

    def test_transcribing_never_imports_torch_in_parent(self):
        import sys
        before = 'torch' in sys.modules
        stt_local.transcribe_pcm(CLIP, 'fr')
        self.assertEqual('torch' in sys.modules, before)

    def test_repeated_low_memory_refuses_without_spawning(self):
        # §3.6: repeated low-memory failures stay contained; the server (this process) is unaffected.
        self._ram.stop()
        low = patch.object(stt_local, '_free_ram_mb', return_value=1024)
        low.start()
        self.addCleanup(low.stop)
        for _ in range(3):
            with self.assertRaisesRegex(STTBlocked, 'free RAM'):
                stt_local.transcribe_pcm(CLIP, 'fr')
        self.assertIsNone(stt_local._worker)

    def test_worker_crash_reports_unavailable_and_cleans_up(self):
        self._target.stop()
        crash = patch.object(stt_local, '_worker_target', _crasher)
        crash.start()
        self.addCleanup(crash.stop)
        with self.assertRaises(STTBlocked):
            stt_local.transcribe_pcm(CLIP, 'fr')
        self.assertEqual(self.procs(), [])          # crashed worker discarded, none left behind
        with self.assertRaises(STTBlocked):         # repeated crashes stay contained too
            stt_local.transcribe_pcm(CLIP, 'fr')
        self.assertEqual(self.procs(), [])

    def test_worker_timeout_terminates_and_cleans_up(self):
        self._target.stop()
        sleep = patch.object(stt_local, '_worker_target', _sleeper)
        sleep.start()
        self.addCleanup(sleep.stop)
        for _ in range(2):
            with patch.object(stt_local, 'WORKER_TIMEOUT_S', 1):
                with self.assertRaisesRegex(STTBlocked, 'timed out'):
                    stt_local.transcribe_pcm(CLIP, 'fr')
        self.assertEqual(self.procs(), [])

    def test_fatal_load_reports_once_and_cools_down(self):
        self._target.stop()
        fatal = patch.object(stt_local, '_worker_target', _fatal_loader)
        fatal.start()
        self.addCleanup(fatal.stop)
        for _ in range(3):
            with self.assertRaisesRegex(STTBlocked, 'failed to load'):
                stt_local.transcribe_pcm(CLIP, 'fr')
        with self.assertRaisesRegex(STTBlocked, 'keeps failing'):
            stt_local.transcribe_pcm(CLIP, 'fr')    # cooldown: no spawn-crashing loop
        self.assertEqual(self.procs(), [])

    def test_shutdown_is_idempotent_and_kills_worker(self):
        stt_local.transcribe_pcm(CLIP, 'fr')
        proc = stt_local._worker.proc
        stt_local.shutdown()
        stt_local.shutdown()
        self.assertIsNone(stt_local._worker)
        self.assertIsNotNone(proc.exitcode)
