"""mic_oracle: energy VAD, utterance dispatch and worker handling (no hardware).

PCM16 is synthesized in-test (silence vs loud frames); network and STT are
mocked. sounddevice is never imported (run_mic_loop is wiring only).
"""
import base64
import json
import struct
import unittest
from unittest import mock

from src.ai import mic_oracle as MO

SILENCE = b'\x00' * 960
LOUD = struct.pack('<480h', *([20000] * 480))   # ~ -4.3 dBFS


class Rms(unittest.TestCase):
    def test_silence_and_empty(self):
        self.assertEqual(MO.compute_rms_db(b''), -96.0)
        self.assertEqual(MO.compute_rms_db(b'\x00'), -96.0)
        self.assertEqual(MO.compute_rms_db(SILENCE), -96.0)

    def test_loud_level(self):
        self.assertAlmostEqual(MO.compute_rms_db(LOUD), -4.29, places=1)


class Vad(unittest.TestCase):
    def test_starts_after_two_loud_frames(self):
        vad = MO.VadRecorder()
        self.assertIsNone(vad.feed(SILENCE))
        self.assertIsNone(vad.feed(LOUD))
        self.assertFalse(vad._speaking)
        self.assertIsNone(vad.feed(LOUD))
        self.assertTrue(vad._speaking)

    def test_single_loud_frame_resets(self):
        vad = MO.VadRecorder()
        vad.feed(LOUD)
        vad.feed(SILENCE)
        self.assertFalse(vad._speaking)
        self.assertEqual(vad._active_streak, 0)

    def test_emits_after_silence_with_preroll(self):
        vad = MO.VadRecorder()                  # 650 ms -> 21 quiet frames
        vad.feed(SILENCE)
        vad.feed(LOUD)
        vad.feed(LOUD)
        out = None
        for _ in range(21):
            out = vad.feed(SILENCE)
        self.assertIsInstance(out, bytes)
        self.assertEqual(len(out), 24 * 960)    # 3 buffered + 21 quiet
        self.assertFalse(vad._speaking)

    def test_max_ms_caps_utterance(self):
        vad = MO.VadRecorder(max_ms=300)        # 10 frames max
        emits = [vad.feed(LOUD) for _ in range(12)]
        got = [e for e in emits if e is not None]
        self.assertEqual(len(got), 1)
        self.assertEqual(len(got[0]), 10 * 960)

    def test_flush(self):
        vad = MO.VadRecorder()
        self.assertIsNone(vad.flush())
        vad.feed(LOUD)
        vad.feed(LOUD)
        out = vad.flush()
        self.assertIsInstance(out, bytes)
        self.assertFalse(vad._speaking)
        self.assertIsNone(vad.flush())


class Dispatch(unittest.TestCase):
    def test_send_requires_input(self):
        with self.assertRaises(ValueError):
            MO.send_to_oracle()
        r = MO.send_to_oracle(transcript='   ')
        self.assertEqual((r['source'], r['hud_pushed']), ('empty', False))

    def test_send_server_url_payload(self):
        body = {'ok': True}
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = json.dumps(body).encode()
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen['url'] = req.full_url
            seen['payload'] = json.loads(req.data.decode())
            return resp

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            out = MO.send_to_oracle(audio_pcm16=b'\x01\x02', mic_source='usb',
                                    server_url='http://127.0.0.1:9', partial=True)
        self.assertEqual(out, body)
        self.assertTrue(seen['url'].endswith('/api/v2/voice/oracle'))
        self.assertEqual(base64.b64decode(seen['payload']['audio_b64']), b'\x01\x02')
        self.assertTrue(seen['payload']['partial'])
        self.assertEqual(seen['payload']['mic_source'], 'usb')

    def test_send_server_url_rejects_empty(self):
        with self.assertRaises(ValueError):
            MO.send_to_oracle(server_url='http://127.0.0.1:9')

    def test_send_local_transcript_path(self):
        with mock.patch.object(MO.Oracle, 'oracle_answer', return_value={'answer': 'x'}) as oa, \
                mock.patch.object(MO.Oracle, 'push_oracle_to_hud', return_value=True):
            r = MO.send_to_oracle(transcript='bonjour', mic_source='pc_mic', server=object())
        oa.assert_called_once_with('bonjour', timeout=8.0)
        self.assertEqual((r['mic_source'], r['hud_pushed']), ('pc_mic', True))

    def test_send_local_audio_path(self):
        with mock.patch.object(MO, 'transcribe_fast', return_value='bonjour') as tr, \
                mock.patch.object(MO.Oracle, 'oracle_answer', return_value={'answer': 'x'}), \
                mock.patch.object(MO.Oracle, 'push_oracle_to_hud', return_value=False):
            r = MO.send_to_oracle(audio_pcm16=b'\x00' * 960, language='fr')
        tr.assert_called_once_with(b'\x00' * 960, language='fr')
        self.assertFalse(r['hud_pushed'])

    def test_handle_utterance_ok(self):
        on_answer, on_error = mock.MagicMock(), mock.MagicMock()
        with mock.patch.object(MO, 'send_to_oracle', return_value={'answer': 'hi'}) as s:
            r = MO._handle_utterance(b'U', 'pc', 'fr', None, None, on_answer, on_error)
        s.assert_called_once()
        on_answer.assert_called_once_with({'answer': 'hi'})
        on_error.assert_not_called()
        self.assertEqual(r, {'answer': 'hi'})

    def test_handle_utterance_error_reported(self):
        on_answer, on_error = mock.MagicMock(), mock.MagicMock()
        with mock.patch.object(MO, 'send_to_oracle', side_effect=RuntimeError('stt down')):
            r = MO._handle_utterance(b'U', 'pc', 'fr', None, None, on_answer, on_error)
        self.assertIsNone(r)
        on_answer.assert_not_called()
        on_error.assert_called_once()
        self.assertIsInstance(on_error.call_args[0][0], RuntimeError)


if __name__ == '__main__':
    unittest.main()
