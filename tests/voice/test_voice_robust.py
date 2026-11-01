"""E1 robustness: voice screen ReDoS bound + short-command language guard.

- screen_voice_transcript truncates past MAX_SCREEN_CHARS before any regex
  runs (several screens use `.*` patterns with quadratic worst cases);
- compile_intent takes lang_hint so short signal-free commands ('scan
  bluetooth') honor caller locale instead of defaulting to English; the
  /api/v2/voice/intent endpoint threads an optional lang through.
"""
import time
import unittest
from types import SimpleNamespace

from src.ai import voice_intent as VI
from src.ai import voice_normalize as VN


class ScreenBound(unittest.TestCase):
    def test_huge_neutral_input_screens_fast_to_none(self):
        # Many `.*`-pattern start positions, no match: ~20s unbounded.
        evil = 'finish ' * 20000
        t0 = time.time()
        out = VN.screen_voice_transcript(evil, 'en')
        elapsed = time.time() - t0
        self.assertIsNone(out)
        self.assertLess(elapsed, 5)

    def test_refusal_prefix_survives_truncation(self):
        evil = 'reboot the tv ' + 'x' * 100000
        hit = VN.screen_voice_transcript(evil, 'en')
        self.assertIsNotNone(hit)
        self.assertEqual(hit['status'], 'unsupported')

    def test_cap_matches_compile_intent(self):
        self.assertEqual(VN.MAX_SCREEN_CHARS, 400)


class LangGuard(unittest.TestCase):
    def test_short_neutral_command_uses_hint(self):
        out = VI.compile_intent('scan bluetooth', lang_hint='fr')
        self.assertEqual(out['lang'], 'fr')
        self.assertIn('Scanner', out['clarifying_question'])

    def test_short_neutral_command_defaults_english_without_hint(self):
        out = VI.compile_intent('scan bluetooth')
        self.assertEqual(out['lang'], 'en')

    def test_detected_language_beats_hint(self):
        out = VI.compile_intent('allume la lampe', lang_hint='en')
        self.assertEqual(out['lang'], 'fr')

    def test_api_threads_optional_lang(self):
        from src.runtime.api_v2 import voice
        server = SimpleNamespace(fabric_snapshot={'devices': []})
        status, out = voice(server, '/api/v2/voice/intent',
                            {'text': 'scan bluetooth', 'lang': 'fr'})
        self.assertEqual(status, 200)
        self.assertEqual(out['lang'], 'fr')
        status, out = voice(server, '/api/v2/voice/intent', {'text': 'scan bluetooth'})
        self.assertEqual((status, out['lang']), (200, 'en'))
        status, _ = voice(server, '/api/v2/voice/intent', {'text': 'x', 'nope': 1})
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
