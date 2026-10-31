"""Device-side voice loop: signed clip download, local STT routing, validation. No model, no network beyond loopback."""
import hashlib
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from src.ai import stt_local, voice_stt
from src.fabric import relay as R
from src.runtime import api_v2
from src.runtime import companion_commands as CC

RID = 'a' * 32
KEY = b'k' * 32
PCM = b'\x00\x01' * 8000  # 1 s of 16 kHz PCM16


class STTLocalValidation(unittest.TestCase):
    def test_bad_audio_rejected_without_loading_model(self):
        for bad in (b'', b'\x00', b'\x00' * 3, b'\x00\x00' * (16000 * 16), 'nope', None):
            with self.subTest(n=repr(bad)[:12]), self.assertRaises(voice_stt.STTBlocked):
                stt_local.transcribe_pcm(bad)
        with self.assertRaises(voice_stt.STTBlocked):
            stt_local.transcribe_pcm(b'\x00\x00', 'de')

    def test_available_respects_opt_out_and_missing_home(self):
        with mock.patch.dict(os.environ, {'OB_STT_LOCAL': '0'}):
            self.assertFalse(stt_local.available())
        old = stt_local._home_override
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                stt_local._home_override = tmp
                with mock.patch.dict(os.environ, {}, clear=False):
                    os.environ.pop('OB_STT_LOCAL', None)
                    self.assertFalse(stt_local.available())
        finally:
            stt_local._home_override = old

    def test_find_snapshot_needs_config_and_weights(self):
        import tempfile
        old = stt_local._home_override
        try:
            with tempfile.TemporaryDirectory() as tmp:
                stt_local._home_override = tmp
                snaps = os.path.join(tmp, 'hub', 'models--facebook--mms-1b-all', 'snapshots', 'r1')
                os.makedirs(snaps)
                self.assertIsNone(stt_local.find_snapshot())
                open(os.path.join(snaps, 'config.json'), 'w').write('{}')
                self.assertIsNone(stt_local.find_snapshot())
                open(os.path.join(snaps, 'model.safetensors'), 'w').write('x')
                self.assertTrue(str(stt_local.find_snapshot()).endswith('r1'))
        finally:
            stt_local._home_override = old


class VoiceItems(unittest.TestCase):
    def voice(self, **kw):
        d = {'request_id': RID, 'kind': 'voice', 'clip_id': 'clip-1', 'bytes': len(PCM),
             'sha256': hashlib.sha256(PCM).hexdigest(), 'lang': 'fr', 'quality': 'auto'}
        d.update(kw)
        return d

    def test_voice_item_accepted(self):
        out = R.validate_commands({'commands': [self.voice()]})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['clip_id'], 'clip-1')

    def test_voice_item_bounds(self):
        bad = [self.voice(clip_id='../x'), self.voice(clip_id='x' * 33),
               self.voice(sha256='zz'), self.voice(sha256='a' * 63),
               self.voice(bytes=0), self.voice(bytes=3), self.voice(bytes=R.VOICE_MAX_BYTES + 2),
               self.voice(bytes='100'), self.voice(lang='de'), self.voice(quality='ultra'),
               self.voice(kind='video')]
        for i in range(0, len(bad), R.MAX_COMMANDS):
            self.assertEqual(R.validate_commands({'commands': bad[i:i + R.MAX_COMMANDS]}), [])

    def test_text_items_unchanged_with_default_kind(self):
        out = R.validate_commands({'commands': [{'request_id': RID, 'text': ' hi ', 'lang': 'en', 'quality': 'low'}]})
        self.assertEqual(out, [{'request_id': RID, 'kind': 'text', 'text': 'hi', 'lang': 'en', 'quality': 'low'}])

    def test_sig_stable_and_binding(self):
        a = R.voice_sig(KEY, 'clip-1', 100, 'n' * 16)
        self.assertEqual(a, R.voice_sig(KEY, 'clip-1', 100, 'n' * 16))
        self.assertNotEqual(a, R.voice_sig(KEY, 'clip-1', 101, 'n' * 16))
        self.assertNotEqual(a, R.voice_sig(KEY, 'clip-2', 100, 'n' * 16))
        self.assertNotEqual(a, R.voice_sig(b'q' * 32, 'clip-1', 100, 'n' * 16))
        with self.assertRaises(R.RelayError):
            R.voice_url('http://127.0.0.1:9', KEY, '../x')


class StubVoice(BaseHTTPRequestHandler):
    body = PCM
    code = 200
    redirect_to = None

    def do_GET(self):
        if self.redirect_to is not None:
            self.send_response(302)
            self.send_header('Location', self.redirect_to)
            self.end_headers()
            return
        self.send_response(self.code)
        self.send_header('Content-Length', str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *a):
        pass


class FetchVoice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(('127.0.0.1', 0), StubVoice)
        cls.url = 'http://127.0.0.1:%d' % cls.srv.server_port
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_ok(self):
        StubVoice.body, StubVoice.code = PCM, 200
        got = R.fetch_voice(self.url, KEY, 'clip-1', len(PCM), hashlib.sha256(PCM).hexdigest())
        self.assertEqual(got, PCM)

    def test_size_and_hash_mismatch(self):
        StubVoice.body, StubVoice.code = PCM, 200
        with self.assertRaises(R.RelayError):
            R.fetch_voice(self.url, KEY, 'clip-1', len(PCM) - 2, hashlib.sha256(PCM).hexdigest())
        with self.assertRaises(R.RelayError):
            R.fetch_voice(self.url, KEY, 'clip-1', len(PCM), 'b' * 64)
        StubVoice.body = PCM + b'\x00\x00'
        with self.assertRaises(R.RelayError):
            R.fetch_voice(self.url, KEY, 'clip-1', len(PCM), hashlib.sha256(PCM).hexdigest())
        StubVoice.body = PCM

    def test_redirect_never_followed(self):
        # Sol audit: a 302 must not carry the download off the scope-checked URL —
        # even to loopback, even when the target would pass size+sha.
        class EvilVoice(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(PCM)))
                self.end_headers()
                self.wfile.write(PCM)

            def log_message(self, *a):
                pass

        evil = HTTPServer(('127.0.0.1', 0), EvilVoice)
        threading.Thread(target=evil.serve_forever, daemon=True).start()
        try:
            StubVoice.body, StubVoice.code = PCM, 200
            target = 'http://127.0.0.1:%d/voice' % evil.server_port
            StubVoice.redirect_to = target
            try:
                with self.assertRaises(R.RelayError):
                    R.fetch_voice(self.url, KEY, 'clip-1', len(PCM), hashlib.sha256(PCM).hexdigest())
            finally:
                StubVoice.redirect_to = None
            StubVoice.redirect_to = 'http://8.8.8.8/voice'
            try:
                with self.assertRaises(R.RelayError):
                    R.fetch_voice(self.url, KEY, 'clip-1', len(PCM), hashlib.sha256(PCM).hexdigest())
            finally:
                StubVoice.redirect_to = None
        finally:
            evil.shutdown()
            evil.server_close()

    def test_refused_and_out_of_scope(self):
        StubVoice.code = 404
        try:
            with self.assertRaises(R.RelayError):
                R.fetch_voice(self.url, KEY, 'clip-1', len(PCM), hashlib.sha256(PCM).hexdigest())
        finally:
            StubVoice.code = 200
        for bad in ('http://example.com', 'http://8.8.8.8', 'http://[ff02::1]', 'http://[2001:4860:4860::8888]'):
            with self.subTest(bad), self.assertRaises(R.RelayError):
                R.fetch_voice(bad, KEY, 'clip-1', 2, 'c' * 64)
        with self.assertRaises(R.RelayError):
            R.fetch_voice(self.url, KEY, 'clip-1', R.VOICE_MAX_BYTES + 2, 'c' * 64)


class FakeServer:
    def __init__(self, relays):
        self.relays = type('R', (), {'relays': relays})()


class VoiceText(unittest.TestCase):
    def test_missing_url_reports_and_skips(self):
        sent = []
        cc = CC.CompanionCommands(FakeServer({'r1': {'key': KEY, 'seen': {}}}))
        cc._send = lambda rid, op, params=None: sent.append((op, params)) or {}
        item = {'request_id': RID, 'kind': 'voice', 'clip_id': 'c', 'bytes': 2, 'sha256': 'd' * 64,
                'lang': 'fr', 'quality': 'auto'}
        self.assertIsNone(cc._voice_text('r1', {'key': KEY}, item))
        self.assertEqual(sent[0][0], 'report_command')
        self.assertEqual(sent[0][1]['status'], 'escalation_required')

    def test_happy_path_parses_transcript(self):
        relay = {'key': KEY, 'url': 'http://127.0.0.1:9', 'seen': {}}
        cc = CC.CompanionCommands(FakeServer({'r1': relay}))
        item = {'request_id': RID, 'kind': 'voice', 'clip_id': 'c', 'bytes': len(PCM),
                'sha256': hashlib.sha256(PCM).hexdigest(), 'lang': 'fr', 'quality': 'auto'}
        with mock.patch.object(R, 'fetch_voice_urls', return_value=PCM) as f, \
                mock.patch.object(stt_local, 'available', return_value=True), \
                mock.patch.object(stt_local, 'transcribe_pcm', return_value={'transcript': '  start vacuum '}) as t:
            self.assertEqual(cc._voice_text('r1', relay, item), 'start vacuum')
            f.assert_called_once_with(['http://127.0.0.1:9'], KEY, 'c', len(PCM), mock.ANY, relay_id=mock.ANY, aead_version=None)
            t.assert_called_once_with(PCM, 'fr')

    def test_download_failure_reports_and_skips(self):
        sent = []
        relay = {'key': KEY, 'url': 'http://127.0.0.1:9', 'seen': {}}
        cc = CC.CompanionCommands(FakeServer({'r1': relay}))
        cc._send = lambda rid, op, params=None: sent.append((op, params)) or {}
        item = {'request_id': RID, 'kind': 'voice', 'clip_id': 'c', 'bytes': 2,
                'sha256': 'd' * 64, 'lang': 'fr', 'quality': 'auto'}
        with mock.patch.object(R, 'fetch_voice_urls', side_effect=R.RelayError('nope')), \
                mock.patch.object(stt_local, 'available', return_value=True):
            self.assertIsNone(cc._voice_text('r1', relay, item))
        self.assertEqual(sent[0][1]['status'], 'escalation_required')


class FakeBatch(dict):
    def __getattr__(self, k):
        return self[k]


class FakeSTTModel:
    def __init__(self):
        self.switches = []

    def load_adapter(self, code):
        self.switches.append(code)

    def parameters(self):
        import torch
        return iter([torch.zeros(1)])

    def __call__(self, input_values, attention_mask=None):
        import torch
        out = type('L', (), {})()
        out.logits = torch.zeros(1, 4, 3)
        return out


class FakeSTTProcessor:
    def __call__(self, samples, sampling_rate=16000, return_tensors='pt'):
        import torch
        return FakeBatch(input_values=torch.zeros(1, 4), attention_mask=torch.ones(1, 4))

    def batch_decode(self, ids):
        return ['x']


@unittest.skipUnless(__import__('importlib').util.find_spec('torch') is not None,
                       'torch required: exercises transcribe_pcm tensor path with a fake backend')
class STTSwitchTracking(unittest.TestCase):
    """FR-after-EN must re-switch the adapter: the worker-side inference path tracks the loaded language (no model)."""

    def test_language_tracking_across_calls(self):
        model = FakeSTTModel()
        backend = (model, {'fr': FakeSTTProcessor(), 'en': FakeSTTProcessor()}, 'fr')
        pcm = b'\x00\x01' * 800
        backend, doc = stt_local._run_inference(backend, 'fr', pcm)
        self.assertEqual(doc['transcript'], 'x')
        self.assertEqual(model.switches, [])
        backend, doc = stt_local._run_inference(backend, 'en', pcm)
        self.assertEqual(doc['transcript'], 'x')
        self.assertEqual(model.switches, ['eng'])
        self.assertEqual(backend[2], 'en')
        backend, doc = stt_local._run_inference(backend, 'fr', pcm)
        self.assertEqual(doc['transcript'], 'x')
        self.assertEqual(model.switches, ['eng', 'fra'])
        self.assertEqual(backend[2], 'fr')


class TranscribeRouting(unittest.TestCase):
    def test_local_first(self):
        import base64
        body = {'audio_b64': base64.b64encode(PCM).decode(), 'language': 'fr'}
        with mock.patch.object(stt_local, 'available', return_value=True), \
                mock.patch.object(stt_local, 'transcribe_pcm', return_value={'transcript': 'x', 'backend': 'local-mms'}) as t, \
                mock.patch.object(voice_stt, 'transcribe', side_effect=AssertionError('cloud must not run')):
            code, doc = api_v2.voice(FakeServer({}), '/api/v2/voice/transcribe', body)
        self.assertEqual((code, doc['backend']), (200, 'local-mms'))
        t.assert_called_once_with(PCM, 'fr')

    def test_no_cloud_fallback_without_local(self):
        # Sol audit: no silent cloud STT (would need consent + fresh reservation).
        import base64
        body = {'audio_b64': base64.b64encode(PCM).decode()}
        with mock.patch.object(stt_local, 'available', return_value=False), \
                mock.patch.object(voice_stt, 'transcribe',
                                  side_effect=AssertionError('cloud must not run')):
            code, doc = api_v2.voice(FakeServer({}), '/api/v2/voice/transcribe', body)
        self.assertEqual(code, 409)
        self.assertEqual(doc['fallback'], 'type the command instead')

    def test_local_crash_is_503_not_500(self):
        import base64
        body = {'audio_b64': base64.b64encode(PCM).decode()}
        with mock.patch.object(stt_local, 'available', return_value=True), \
                mock.patch.object(stt_local, 'transcribe_pcm', side_effect=RuntimeError('oom')):
            code, doc = api_v2.voice(FakeServer({}), '/api/v2/voice/transcribe', body)
        self.assertEqual(code, 503)


if __name__ == '__main__':
    unittest.main()
