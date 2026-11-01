"""F90 Campaign One voice-worker slice: lifecycle + interrupted-session behavior.

TESTS ONLY. Covers worker crash/timeout containment, failure cooldown, no
orphans, interrupted voice sessions never yielding phantom commands, and
queue-during-transcription bounds. Also pins the free-RAM admission and
300 s timeout constants from ``src.ai.stt_local``.

Stub worker targets (top-level so spawn can pickle them) stand in for the
real multi-GB backend: no torch, no model download.
"""
import hashlib
import inspect
import json
import os
import secrets
import struct
import threading
import time
import types
import unittest
from unittest import mock

from src.ai import stt_local
from src.ai import voice_stt as stt
from src.fabric import relay as R

CLIP_A = b'\x00\x01' * 8000   # 1 s of 16 kHz PCM16 mono
CLIP_B = b'\x02\x03' * 4000   # 0.5 s of 16 kHz PCM16 mono
KEY = b'\x5a' * 32
RID = 'relay-f90voice1'


# ---------------------------------------------------------------------------
# Stub worker targets (top-level: spawn pickles them by reference)
# ---------------------------------------------------------------------------

def _f90_echo(conn, snapshot):
    try:
        while True:
            try:
                language, pcm = conn.recv()
            except EOFError:
                return
            conn.send(('ok', {'transcript': 'f90-live', 'model': 'stub', 'language': language,
                              'seconds': round(len(bytes(pcm)) / 2 / 16000, 1), 'backend': 'local-mms'}))
    finally:
        conn.close()


def _f90_crasher(conn, snapshot):
    os._exit(3)


def _f90_sleeper(conn, snapshot):
    try:
        conn.recv()
        time.sleep(120)
    finally:
        conn.close()


def _f90_fatal(conn, snapshot):
    try:
        conn.recv()
        conn.send(('fatal', 'local STT model failed to load (RuntimeError)'))
    finally:
        conn.close()


def _f90_slow_ok(conn, snapshot):
    """Answer correctly but too late: proves a late reply can never leak into the next request."""
    try:
        language, _pcm = conn.recv()
        time.sleep(3)
        try:
            conn.send(('ok', {'transcript': 'STALE', 'model': 'stub', 'language': language,
                              'seconds': 1.0, 'backend': 'local-mms'}))
        except (OSError, EOFError):
            pass  # parent already gave up: the late reply dies here, never leaks
    finally:
        conn.close()


def _f90_slow_echo(conn, snapshot):
    """Slow but correct per-request answers: pins single-flight serialization under concurrency."""
    try:
        while True:
            try:
                language, pcm = conn.recv()
            except EOFError:
                return
            time.sleep(1.0)
            n = len(bytes(pcm))
            conn.send(('ok', {'transcript': 'len-%d' % n, 'model': 'stub', 'language': language,
                              'seconds': round(n / 2 / 16000, 1), 'backend': 'local-mms'}))
    finally:
        conn.close()


class _RecordingWorker(stt_local._Worker):
    """Counts spawns and records every child proc so tests can prove no orphans."""
    procs = []

    def __init__(self, snapshot):
        super().__init__(snapshot)
        _RecordingWorker.procs.append(self.proc)


class _WorkerBase(unittest.TestCase):
    target = _f90_echo

    def setUp(self):
        _RecordingWorker.procs = []
        stt_local._failures.clear()
        stt_local.shutdown()
        self._patches = [
            mock.patch.object(stt_local, 'find_snapshot', return_value='/fake/snap'),
            mock.patch.object(stt_local, '_free_ram_mb', return_value=16 * 1024),
            mock.patch.object(stt_local, '_worker_target', type(self).target),
            mock.patch.object(stt_local, '_Worker', _RecordingWorker),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(self._stop)

    def _stop(self):
        for p in self._patches:
            p.stop()
        stt_local.shutdown()
        stt_local._failures.clear()

    def assertNoOrphans(self):
        """Every spawned child is reaped and dead: no orphan worker processes."""
        stt_local.shutdown()   # idempotent: also stops a legitimately warm worker
        for proc in _RecordingWorker.procs:
            proc.join(10)
            self.assertIsNotNone(proc.exitcode, 'orphan worker still alive')
            self.assertFalse(proc.is_alive(), 'orphan worker still alive')
        self.assertIsNone(stt_local._worker)


# ---------------------------------------------------------------------------
# §1  Constant pins (free-RAM admission + 300 s timeout)
# ---------------------------------------------------------------------------

class F90WorkerConstants(unittest.TestCase):
    def test_timeout_and_admission_constants_pinned(self):
        self.assertEqual(stt_local.WORKER_TIMEOUT_S, 300)
        self.assertEqual(stt_local.MIN_FREE_RAM_MB, 6 * 1024)
        self.assertEqual(stt_local.WORKER_MAX_FAILURES, 3)
        self.assertEqual(stt_local.WORKER_COOLDOWN_S, 60)

    def test_clip_bounds_pinned(self):
        self.assertEqual(stt.MAX_SECONDS, 15)
        self.assertEqual(stt.RATE, 16000)
        self.assertEqual(stt.MAX_SECONDS * stt.RATE * 2, 480000)

    def test_queue_bounds_pinned(self):
        from src.runtime import command_drain as D
        from src.runtime import companion_commands as CC
        self.assertEqual(R.MAX_COMMANDS, 8)
        self.assertEqual(R.VOICE_MAX_BYTES, 512 * 1024)
        self.assertEqual(CC.MAX_PENDING, 64)
        self.assertEqual(D.MAX_REPORT, 150)
        self.assertLessEqual(D.MAX_REPORT, R.MAX_COMMAND_REPORT)
        self.assertEqual(inspect.signature(stt.transcribe).parameters['max_events'].default, 400)


# ---------------------------------------------------------------------------
# §2  Worker lifecycle: containment + no orphans
# ---------------------------------------------------------------------------

class F90WorkerLifecycle(_WorkerBase):
    def test_lazy_spawn_then_warm_reuse(self):
        self.assertIsNone(stt_local._worker)
        first = stt_local.transcribe_pcm(CLIP_A, 'fr')
        self.assertEqual(first['transcript'], 'f90-live')
        worker = stt_local._worker
        self.assertTrue(worker.alive())
        self.assertEqual(len(_RecordingWorker.procs), 1)
        stt_local.transcribe_pcm(CLIP_B, 'en')
        self.assertIs(stt_local._worker, worker)   # warm worker reused, not respawned
        self.assertEqual(len(_RecordingWorker.procs), 1)
        stt_local.shutdown()
        self.assertNoOrphans()

    def test_dead_worker_is_replaced_never_reused(self):
        stt_local.transcribe_pcm(CLIP_A, 'fr')
        old, old_proc = stt_local._worker, stt_local._worker.proc
        old_proc.terminate()
        old_proc.join(10)
        stt_local.transcribe_pcm(CLIP_A, 'fr')     # must respawn, not reuse the corpse
        self.assertIsNot(stt_local._worker, old)
        self.assertTrue(stt_local._worker.alive())
        self.assertEqual(len(_RecordingWorker.procs), 2)
        self.assertNoOrphans()

    def test_crash_contained_parent_survives_no_orphan(self):
        with mock.patch.object(stt_local, '_worker_target', _f90_crasher):
            with self.assertRaises(stt.STTBlocked):
                stt_local.transcribe_pcm(CLIP_A, 'fr')
        self.assertIsNone(stt_local._worker)       # crashed worker discarded
        self.assertNoOrphans()
        # The control server (this process) is unaffected: a healthy worker serves again.
        self.assertEqual(stt_local.transcribe_pcm(CLIP_A, 'fr')['transcript'], 'f90-live')
        self.assertNoOrphans()

    def test_timeout_terminates_worker_and_next_request_is_fresh(self):
        with mock.patch.object(stt_local, '_worker_target', _f90_sleeper), \
                mock.patch.object(stt_local, 'WORKER_TIMEOUT_S', 1):
            with self.assertRaisesRegex(stt.STTBlocked, 'timed out'):
                stt_local.transcribe_pcm(CLIP_A, 'fr')
        self.assertIsNone(stt_local._worker)       # timed-out worker discarded, never reused
        self.assertNoOrphans()
        self.assertEqual(stt_local.transcribe_pcm(CLIP_A, 'fr')['transcript'], 'f90-live')
        self.assertNoOrphans()

    def test_late_reply_never_becomes_next_answer(self):
        with mock.patch.object(stt_local, '_worker_target', _f90_slow_ok), \
                mock.patch.object(stt_local, 'WORKER_TIMEOUT_S', 1):
            with self.assertRaisesRegex(stt.STTBlocked, 'timed out'):
                stt_local.transcribe_pcm(CLIP_A, 'fr')
        stale_proc = _RecordingWorker.procs[-1]
        stale_proc.join(10)
        self.assertFalse(stale_proc.is_alive())
        # Fresh worker, fresh answer: the late 'STALE' reply died with its worker.
        doc = stt_local.transcribe_pcm(CLIP_A, 'fr')
        self.assertEqual(doc['transcript'], 'f90-live')
        self.assertNoOrphans()

    def test_transcribe_uses_timeout_constant_for_poll(self):
        worker = _RecordingWorker('/fake/snap')
        try:
            calls = {}

            class _Pipe:
                def send(self, obj):
                    pass

                def poll(self, timeout):
                    calls['timeout'] = timeout
                    return True

                def recv(self):
                    return ('ok', {'transcript': 'x'})

            with mock.patch.object(worker, 'parent', _Pipe()):
                worker.transcribe('fr', CLIP_A)
                self.assertEqual(calls['timeout'], 300)
                with mock.patch.object(stt_local, 'WORKER_TIMEOUT_S', 7):
                    worker.transcribe('fr', CLIP_A)
                    self.assertEqual(calls['timeout'], 7)   # constant is wired in, not hardcoded
        finally:
            worker.shutdown()
            if stt_local._worker is worker:
                stt_local._worker = None
        self.assertNoOrphans()

    def test_concurrent_callers_serialize_with_own_answers(self):
        # One request at a time: two in-flight transcriptions queue behind the
        # module lock and each caller gets exactly its own result (no cross-talk).
        with mock.patch.object(stt_local, '_worker_target', _f90_slow_echo):
            results, errors = {}, []

            def call(name, clip):
                try:
                    results[name] = stt_local.transcribe_pcm(clip, 'fr')
                except Exception as e:  # noqa: BLE001 - collected, asserted below
                    errors.append(e)

            threads = [threading.Thread(target=call, args=('a', CLIP_A)),
                       threading.Thread(target=call, args=('b', CLIP_B))]
            start = time.monotonic()
            for t in threads:
                t.start()
            for t in threads:
                t.join(30)
            elapsed = time.monotonic() - start
        self.assertEqual(errors, [])
        self.assertEqual(results['a']['transcript'], 'len-%d' % len(CLIP_A))
        self.assertEqual(results['b']['transcript'], 'len-%d' % len(CLIP_B))
        self.assertGreaterEqual(elapsed, 1.9)   # serialized (≈2×1 s), not interleaved
        self.assertEqual(len(_RecordingWorker.procs), 1)   # single worker served both
        self.assertNoOrphans()

    def test_shutdown_idempotent_no_orphan(self):
        stt_local.transcribe_pcm(CLIP_A, 'fr')
        stt_local.shutdown()
        stt_local.shutdown()
        self.assertNoOrphans()


# ---------------------------------------------------------------------------
# §3  Failure cooldown + free-RAM admission
# ---------------------------------------------------------------------------

class F90FailureCooldown(_WorkerBase):
    target = _f90_fatal

    def test_three_failures_then_cooldown_without_spawning(self):
        for _ in range(3):
            with self.assertRaisesRegex(stt.STTBlocked, 'failed to load'):
                stt_local.transcribe_pcm(CLIP_A, 'fr')
        spawns = len(_RecordingWorker.procs)
        self.assertEqual(spawns, 3)
        with self.assertRaisesRegex(stt.STTBlocked, 'keeps failing'):
            stt_local.transcribe_pcm(CLIP_A, 'fr')    # cooldown: no spawn-crashing loop
        self.assertEqual(len(_RecordingWorker.procs), spawns)
        self.assertNoOrphans()

    def test_success_resets_consecutive_failure_count(self):
        with self.assertRaisesRegex(stt.STTBlocked, 'failed to load'):
            stt_local.transcribe_pcm(CLIP_A, 'fr')
        self.assertEqual(len(stt_local._failures), 1)
        with mock.patch.object(stt_local, '_worker_target', _f90_echo):
            stt_local.transcribe_pcm(CLIP_A, 'fr')
        self.assertEqual(stt_local._failures, [])
        stt_local.shutdown()   # drop the warm echo worker so the next call spawns fatal
        with self.assertRaisesRegex(stt.STTBlocked, 'failed to load'):   # counted from zero
            stt_local.transcribe_pcm(CLIP_A, 'fr')
        self.assertEqual(len(stt_local._failures), 1)
        self.assertNoOrphans()

    def test_cooldown_expires_after_cooldown_window(self):
        old = time.monotonic() - stt_local.WORKER_COOLDOWN_S - 1
        stt_local._failures[:] = [old, old, old]
        with mock.patch.object(stt_local, '_worker_target', _f90_echo):
            doc = stt_local.transcribe_pcm(CLIP_A, 'fr')   # old failures aged out: spawns
        self.assertEqual(doc['transcript'], 'f90-live')
        self.assertNoOrphans()

    def test_low_ram_refusal_never_counts_toward_cooldown(self):
        with mock.patch.object(stt_local, '_free_ram_mb', return_value=1024):
            for _ in range(stt_local.WORKER_MAX_FAILURES + 2):
                with self.assertRaisesRegex(stt.STTBlocked, 'free RAM'):
                    stt_local.transcribe_pcm(CLIP_A, 'fr')
        self.assertEqual(stt_local._failures, [])
        self.assertEqual(_RecordingWorker.procs, [])
        self.assertNoOrphans()

    def test_admission_boundary_exact_and_unknown(self):
        with mock.patch.object(stt_local, '_worker_target', _f90_echo):
            with mock.patch.object(stt_local, '_free_ram_mb',
                                   return_value=stt_local.MIN_FREE_RAM_MB - 1):
                with self.assertRaisesRegex(stt.STTBlocked, r'6 GB free RAM'):
                    stt_local.transcribe_pcm(CLIP_A, 'fr')
            self.assertEqual(_RecordingWorker.procs, [])
            with mock.patch.object(stt_local, '_free_ram_mb',
                                   return_value=stt_local.MIN_FREE_RAM_MB):
                self.assertEqual(stt_local.transcribe_pcm(CLIP_A, 'fr')['transcript'], 'f90-live')
            stt_local.shutdown()
            with mock.patch.object(stt_local, '_free_ram_mb', return_value=None):
                # Undeterminable RAM: admission proceeds rather than bricking voice.
                self.assertEqual(stt_local.transcribe_pcm(CLIP_A, 'fr')['transcript'], 'f90-live')
        self.assertNoOrphans()


# ---------------------------------------------------------------------------
# §4  Interrupted sessions never yield phantom commands
# ---------------------------------------------------------------------------

def _signed_reply(params):
    now = int(time.time())
    msg = {'protocol': R.PROTOCOL, 'relay_id': RID, 'op': 'reply', 'params': params,
           'nonce': secrets.token_hex(12), 'issued_at': now, 'expires_at': now + 60}
    return {**msg, 'mac': R.sign(KEY, msg)}


def _text_cmd(text='allume la lampe du salon'):
    return {'request_id': secrets.token_hex(16), 'kind': 'text', 'text': text,
            'lang': 'fr', 'quality': 'auto'}


def _voice_cmd(pcm):
    return {'request_id': secrets.token_hex(16), 'kind': 'voice', 'clip_id': 'f90clip1',
            'bytes': len(pcm), 'sha256': hashlib.sha256(pcm).hexdigest(),
            'lang': 'fr', 'quality': 'auto'}


class _FakeRelay:
    def __init__(self, commands=()):
        self.commands = list(commands)
        self.reports = []
        self.seen = {}

    def send(self, relay, msg):
        R.verify(KEY, msg, self.seen)
        if msg['op'] == 'get_commands':
            cmds, self.commands = self.commands, []
            return _signed_reply({'commands': cmds})
        if msg['op'] == 'report_command':
            p = msg['params']
            self.reports.append((p['request_id'], p['status'], p['text']))
            return _signed_reply({})
        raise AssertionError('unexpected op ' + msg['op'])


def _drain_server(fake):
    mgr = R.RelayManager(lambda relay, msg: relay['send'](relay, msg))
    mgr.enroll(RID, KEY, 'dev-1', {'capabilities': ['command_submit'], 'permissions': {}})
    mgr.relays[RID]['send'] = fake.send
    mgr.relays[RID]['url'] = 'http://127.0.0.1:9/'
    return types.SimpleNamespace(relays=mgr)


class F90InterruptedDrain(unittest.TestCase):
    """command_drain: a mid-session transcription crash yields no report for the
    voice item (certainly never a parsed/phantom one) and never stalls the drain."""

    def test_crashed_transcription_leaves_voice_unreported_text_still_served(self):
        from src.runtime import command_drain as D
        pcm = b'\x01\x02' * 8000
        voice, text = _voice_cmd(pcm), _text_cmd()
        fake = _FakeRelay([voice, text])
        parsed = []

        def parse(s, b):
            parsed.append(b['text'])
            return {'intent': {'status': 'resolved', 'outcome': 'Would run: ' + b['text'][:60],
                              'skill_id': 'demo.echo', 'targets': [], 'params': {},
                              'confidence': 0.9, 'ambiguities': []}}

        defboom = stt.STTBlocked('local STT worker died (exit 3); try again')

        def transcribe(p, lang):
            raise defboom

        stats = D.poll_once(_drain_server(fake), parse_fn=parse,
                            fetch_voice_fn=lambda *a, **k: pcm,
                            transcribe_fn=transcribe, sync=True)
        self.assertEqual(stats['commands'], 2)
        self.assertEqual(stats['reported'], 1)              # only the text command reported
        self.assertEqual([r[0] for r in fake.reports], [text['request_id']])
        self.assertEqual(fake.reports[0][1], 'resolved')
        self.assertEqual(len(stats['errors']), 1)           # the crash is counted, not raised
        self.assertIn('STTBlocked', stats['errors'][0])
        self.assertEqual(parsed, [text['text']])            # no phantom parse of the dead clip

    def test_silence_after_interrupt_reports_honestly_not_parsed(self):
        from src.runtime import command_drain as D
        pcm = b'\x00' * 32000
        fake = _FakeRelay([_voice_cmd(pcm)])
        stats = D.poll_once(_drain_server(fake),
                            parse_fn=lambda s, b: (_ for _ in ()).throw(
                                AssertionError('must not parse silence')),
                            fetch_voice_fn=lambda *a, **k: pcm,
                            transcribe_fn=lambda p, lang: '', sync=True)
        self.assertEqual(stats['reported'], 1)
        self.assertEqual(fake.reports[0][1], 'escalation_required')
        self.assertIn('silence', fake.reports[0][2].lower())


class F90InterruptedCompanion(unittest.TestCase):
    """companion_commands: a worker crash mid-transcription reports honestly and
    stores no pending intent (no phantom command)."""

    def test_crash_reports_escalation_and_stores_nothing(self):
        from src.runtime import companion_commands as CC
        pcm = CLIP_A
        item = {'request_id': secrets.token_hex(16), 'kind': 'voice', 'clip_id': 'clip-1',
                'bytes': len(pcm), 'sha256': hashlib.sha256(pcm).hexdigest(),
                'lang': 'fr', 'quality': 'auto'}
        sent = []
        server = types.SimpleNamespace(relays=types.SimpleNamespace(relays={
            'r1': {'key': KEY, 'url': 'http://127.0.0.1:9/', 'seen': {},
                   'capabilities': {'command_submit'}, 'online': True}}))
        cc = CC.CompanionCommands(server)

        def send(rid, op, params=None):
            sent.append((op, params))
            if op == 'get_commands':
                return {'commands': [item]}
            return {}

        with mock.patch.object(cc, '_send', side_effect=send), \
                mock.patch.object(R, 'fetch_voice_urls', return_value=pcm), \
                mock.patch.object(stt_local, 'available', return_value=True), \
                mock.patch.object(stt_local, 'transcribe_pcm',
                                  side_effect=stt.STTBlocked('local STT worker died (exit 3); try again')):
            self.assertEqual(cc.poll_once(), 0)
        self.assertEqual(cc.pending, {})                    # no phantom pending intent
        self.assertEqual(cc.list(), [])
        reports = [p for op, p in sent if op == 'report_command']
        self.assertEqual(len(reports), 1)                   # exactly one honest report
        self.assertEqual(reports[0]['status'], 'escalation_required')
        self.assertIn('died', reports[0]['text'])
        self.assertEqual(reports[0]['request_id'], item['request_id'])

    def test_http_transcribe_crash_is_409_with_fallback_never_phantom(self):
        import base64
        from src.runtime import api_v2
        body = {'audio_b64': base64.b64encode(CLIP_A).decode(), 'language': 'fr'}
        with mock.patch.object(stt_local, 'available', return_value=True), \
                mock.patch.object(stt_local, 'transcribe_pcm',
                                  side_effect=stt.STTBlocked('local STT timed out; try again')):
            code, doc = api_v2.voice(types.SimpleNamespace(), '/api/v2/voice/transcribe', body)
        self.assertEqual(code, 409)
        self.assertNotIn('transcript', doc)                 # never a phantom transcript
        self.assertEqual(doc['fallback'], 'type the command instead')


class _ScriptedSock:
    """Fake Meta realtime ASR server with a scripted post-endStream event list."""

    def __init__(self, events):
        self.buf, self.sent, self.events, self.stage = b'', b'', list(events), 0
        self.recvs = 0

    def _push(self, e):
        d = json.dumps(e).encode()
        self.buf += bytes([0x81, 126]) + struct.pack('>H', len(d)) + d

    def _push_close(self):
        self.buf += bytes([0x88, 0x00])

    def _parse(self):
        s, i, out = self.sent, self.sent.index(b'\r\n\r\n') + 4, []
        while i + 2 <= len(s):
            op, n = s[i] & 0x0f, s[i + 1] & 0x7f
            j = i + 2
            if n == 126:
                n, = struct.unpack('>H', s[j:j + 2]); j += 2
            elif n == 127:
                n, = struct.unpack('>Q', s[j:j + 8]); j += 8
            if j + 4 + n > len(s):
                break
            m = s[j:j + 4]
            out.append((op, bytes(b ^ m[k % 4] for k, b in enumerate(s[j + 4:j + 4 + n]))))
            i = j + 4 + n
        return out

    def sendall(self, data):
        self.sent += data
        if self.stage == 0 and b'\r\n\r\n' in self.sent:
            self.buf += b'HTTP/1.1 101 Switching Protocols\r\n\r\n'
            self.stage = 1
            return
        texts = [json.loads(p) for op, p in self._parse() if op == 1]
        if self.stage == 1 and texts:
            self._push({'sessionId': 'f90-s'})
            self.stage = 2
        if self.stage == 2 and any(t.get('type') == 'endStream' for t in texts):
            for e in self.events:
                if e == 'CLOSE':
                    self._push_close()
                else:
                    self._push(e)
            self.stage = 3

    def recv(self, n):
        self.recvs += 1
        if not self.buf:
            raise AssertionError('client read past scripted events (unbounded wait)')
        d, self.buf = self.buf[:n], self.buf[n:]
        return d

    def close(self):
        pass


class F90InterruptedCloudSession(unittest.TestCase):
    """Cloud STT: an interrupted session raises STTBlocked; a partial transcript
    is never returned as final (no phantom command source)."""

    def test_close_mid_stream_raises_never_partial(self):
        sock = _ScriptedSock([{'type': 'transcript', 'transcript': 'allume la', 'final': False},
                              'CLOSE'])
        with self.assertRaises(stt.STTBlocked):
            stt.transcribe(CLIP_A, 'k', 'fr', connect=lambda a, timeout: sock, pace=False)

    def test_error_event_raises(self):
        sock = _ScriptedSock([{'type': 'error', 'message': 'quota exceeded'}])
        with self.assertRaisesRegex(stt.STTBlocked, 'quota'):
            stt.transcribe(CLIP_A, 'k', 'fr', connect=lambda a, timeout: sock, pace=False)

    def test_endless_partials_bounded_by_max_events(self):
        sock = _ScriptedSock([{'type': 'transcript', 'transcript': 'still going', 'final': False}] * 6)
        with self.assertRaisesRegex(stt.STTBlocked, 'no final transcript'):
            stt.transcribe(CLIP_A, 'k', 'fr', connect=lambda a, timeout: sock,
                          max_events=5, pace=False)
        self.assertLess(sock.recvs, 60)   # bounded wait, no infinite partial loop

    def test_final_after_partial_still_returned(self):
        sock = _ScriptedSock([{'type': 'transcript', 'transcript': 'allume la', 'final': False},
                              {'type': 'transcript', 'transcript': 'allume la lampe', 'final': True}])
        doc = stt.transcribe(CLIP_A, 'k', 'fr', connect=lambda a, timeout: sock, pace=False)
        self.assertEqual(doc['transcript'], 'allume la lampe')


# ---------------------------------------------------------------------------
# §5  Queue-during-transcription bounds
# ---------------------------------------------------------------------------

class F90QueueBounds(unittest.TestCase):
    def _text_items(self, n, start=0):
        return [{'request_id': '%032x' % (start + i), 'kind': 'text',
                 'text': 'command %d' % (start + i), 'lang': 'en', 'quality': 'auto'}
                for i in range(1, n + 1)]

    def test_validate_commands_accepts_exact_cap(self):
        self.assertEqual(len(R.validate_commands({'commands': self._text_items(8)})), 8)

    def test_validate_commands_refuses_oversize_list_outright(self):
        with self.assertRaises(R.RelayError):
            R.validate_commands({'commands': self._text_items(9)})

    def test_voice_clip_bounds(self):
        good = {'request_id': 'b' * 32, 'kind': 'voice', 'clip_id': 'clip-1',
                'bytes': 480000, 'sha256': 'c' * 64, 'lang': 'fr', 'quality': 'auto'}
        self.assertEqual(len(R.validate_commands({'commands': [good]})), 1)   # full 15 s fits
        for bad_bytes in (0, 3, R.VOICE_MAX_BYTES + 2):
            bad = dict(good, bytes=bad_bytes)
            self.assertEqual(R.validate_commands({'commands': [bad]}), [],
                             'bytes=%r must be rejected' % (bad_bytes,))

    def test_pending_queue_evicts_oldest_past_64(self):
        from src.runtime import companion_commands as CC
        from src.runtime import nl_router as N
        server = types.SimpleNamespace(relays=types.SimpleNamespace(relays={
            'r1': {'key': KEY, 'capabilities': {'command_submit'}, 'online': True}}))
        batches = [self._text_items(8, start=i * 8) for i in range(9)]   # 72 commands
        calls = {'n': 0}

        def send(rid, op, params=None):
            if op == 'get_commands':
                batch = batches[calls['n']] if calls['n'] < len(batches) else []
                calls['n'] += 1
                return {'commands': batch}
            return {}

        cc = CC.CompanionCommands(server, low={}, medium={})
        with mock.patch.object(cc, '_send', side_effect=send), \
                mock.patch.object(N, 'parse', return_value={'status': 'resolved',
                                                            'skill_id': 'demo.echo',
                                                            'ambiguities': []}):
            for _ in range(9):
                self.assertEqual(cc.poll_once(), 8)
        self.assertEqual(len(cc.pending), 64)                 # hard cap holds
        self.assertEqual(len(cc.list()), 64)
        self.assertNotIn('%032x' % 1, cc.pending)             # oldest evicted first
        self.assertIn('%032x' % 72, cc.pending)               # newest retained

    def test_oversize_clip_rejected_before_any_transcription(self):
        too_big = b'\x00\x00' * (15 * 16000 + 1)             # 15 s + one frame
        with self.assertRaises(stt.STTBlocked):
            stt_local.transcribe_pcm(too_big, 'fr')
        with self.assertRaises(stt.STTBlocked):
            stt.transcribe(too_big, 'k', connect=lambda a, timeout: None, pace=False)
        self.assertIsNone(stt_local._worker)                 # rejected before any spawn


if __name__ == '__main__':
    unittest.main()
