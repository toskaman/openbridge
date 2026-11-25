"""Unit tests for Voice AI Oracle, Multi-Device Mic Connector & ENGO 3 Integration."""
import os
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.ai.oracle import (
    _format_hud,
    _try_math,
    classify,
    needs_web,
    oracle_answer,
)


class TestClassify(unittest.TestCase):
    def test_math_fr(self):
        self.assertEqual(classify("combien fait 2 fois 6"), "MATH")

    def test_math_en(self):
        self.assertEqual(classify("how much is 12 divided by 4"), "MATH")

    def test_math_symbol(self):
        self.assertEqual(classify("12 * 4 + 2"), "MATH")

    def test_locate_lac(self):
        self.assertEqual(classify("où se trouve le lac d'annecy"), "LOCATE")

    def test_locate_capitale(self):
        self.assertEqual(classify("capitale de la finlande"), "LOCATE")

    def test_general(self):
        self.assertEqual(classify("allume les lumières du salon"), "GENERAL")


class TestTryMath(unittest.TestCase):
    def test_simple_mult(self):
        self.assertEqual(_try_math("2 fois 6"), "12")

    def test_division(self):
        self.assertEqual(_try_math("12 divisé par 4"), "3")

    def test_sqrt(self):
        self.assertEqual(_try_math("racine de 144"), "12")

    def test_percent(self):
        self.assertEqual(_try_math("50 % 7"), "1")

    def test_invalid(self):
        self.assertIsNone(_try_math("où est paris"))

    def test_injection_blocked(self):
        self.assertIsNone(_try_math("import os"))
        self.assertIsNone(_try_math("__import__('os').system('echo hi')"))


class TestOracleAnswer(unittest.TestCase):
    def test_math_answer(self):
        result = oracle_answer("combien fait 2 fois 6")
        self.assertEqual(result["query_class"], "MATH")
        self.assertIn("12", result["answer"])
        self.assertEqual(result["source"], "math_eval")
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_locate_offline(self):
        result = oracle_answer("où est le lac d'annecy")
        self.assertEqual(result["query_class"], "LOCATE")
        self.assertIn("Annecy", result["answer"])
        self.assertEqual(result["source"], "offline_kb")

    def test_answer_max_lines(self):
        with patch("src.ai.oracle._call_gemini_grounded", return_value=None), \
             patch("src.ai.oracle._call_groq", return_value=None), \
             patch("src.ai.oracle._call_ollama", return_value="L1\nL2\nL3\nL4"):
            result = oracle_answer("test max lines unique")
        lines = result["answer"].split('\n')
        self.assertLessEqual(len(lines), 3)

    def test_answer_max_chars(self):
        result = oracle_answer("où est le lac d'annecy")
        for line in result["answer"].split('\n'):
            self.assertLessEqual(len(line), 32, f"Line too long: {repr(line)}")

    def test_transcript_in_result(self):
        result = oracle_answer("combien fait 3 plus 4")
        self.assertEqual(result["transcript"], "combien fait 3 plus 4")


class TestPushOracleAnswer(unittest.TestCase):
    def test_push_smoke(self):
        from src.adapters.activelook import ActiveLookAdapter
        adapter = ActiveLookAdapter.__new__(ActiveLookAdapter)
        adapter.is_color = True
        adapter.model = "ENGO 3"
        adapter._send = lambda data: True
        result = adapter.push_oracle_answer(
            query_class="MATH",
            transcript="combien fait 2 fois 6",
            answer="= 12",
            source="math_eval",
            latency_ms=1,
        )
        self.assertTrue(result)


class TestHybridRoutingAndFormat(unittest.TestCase):
    def test_format_hud_strips_markdown_and_wraps(self):
        formatted = _format_hud("**Annecy** est une *belle* ville situee en Haute-Savoie, France.")
        lines = formatted.splitlines()
        self.assertLessEqual(len(lines), 3)
        self.assertTrue(all("*" not in ln for ln in lines))
        self.assertTrue(all(len(ln) <= 32 for ln in lines))

    def test_gemini_grounded_priority(self):
        with patch("src.ai.oracle._call_gemini_grounded", return_value="Annecy\nHaute-Savoie"):
            r = oracle_answer("quelle heure est-il a Tokyo unique")
        self.assertEqual(r["source"], "gemini_search")
        self.assertIn("Annecy", r["answer"])

    def test_groq_with_web_fallback(self):
        with patch("src.ai.oracle._call_gemini_grounded", return_value=None), \
             patch("src.ai.oracle._web_search", return_value="- Annecy: Haute-Savoie"), \
             patch("src.ai.oracle._call_groq", return_value="Haute-Savoie, France"):
            r = oracle_answer("qui a gagne le match hier unique")
        self.assertEqual(r["source"], "groq+web")
        self.assertIn("Haute-Savoie", r["answer"])

    def test_ollama_with_web_fallback(self):
        with patch("src.ai.oracle._call_gemini_grounded", return_value=None), \
             patch("src.ai.oracle._web_search", return_value="- Result: 18C sunny"), \
             patch("src.ai.oracle._call_groq", return_value=None), \
             patch("src.ai.oracle._call_ollama", return_value="Paris: 18C soleil"):
            r = oracle_answer("quel temps fait-il a Paris unique")
        self.assertEqual(r["source"], "ollama+web")
        self.assertIn("18C", r["answer"])

    def test_needs_web_gating(self):
        self.assertTrue(needs_web("quel temps fait-il a Paris"))
        self.assertTrue(needs_web("prix du bitcoin aujourd'hui"))
        self.assertFalse(needs_web("where is the Eiffel tower"))
        self.assertFalse(needs_web("capitale du Japon"))

    def test_static_query_skips_web_search(self):
        with patch("src.ai.oracle._call_gemini_grounded", return_value=None), \
             patch("src.ai.oracle._web_search") as mock_web, \
             patch("src.ai.oracle._call_groq", return_value=None), \
             patch("src.ai.oracle._call_ollama", return_value="Tokyo"):
            r = oracle_answer("what is the capital of Japan unique")
        mock_web.assert_not_called()
        self.assertEqual(r["source"], "ollama")
        self.assertEqual(r["answer"], "Tokyo")

    def test_live_weather_bypasses_offline_kb(self):
        with patch("src.ai.oracle._call_gemini_grounded", return_value=None), \
             patch("src.ai.oracle._web_search", return_value="- Annecy: 12C"), \
             patch("src.ai.oracle._call_groq", return_value=None), \
             patch("src.ai.oracle._call_ollama", return_value="Annecy: 12C"):
            r = oracle_answer("quel temps fait-il a Annecy aujourd hui unique")
        self.assertEqual(r["source"], "ollama+web")
        self.assertIn("12C", r["answer"])

    def test_ttl_cache_hit(self):
        with patch("src.ai.oracle._call_gemini_grounded", return_value=None), \
             patch("src.ai.oracle._call_groq", return_value=None), \
             patch("src.ai.oracle._call_ollama", return_value="Paris") as mock_ol:
            r1 = oracle_answer("capitale unique test cache xyz2")
            r2 = oracle_answer("capitale unique test cache xyz2")
        self.assertEqual(mock_ol.call_count, 1)
        self.assertTrue(r2.get("cached"))
        self.assertEqual(r1["answer"], "Paris")
        self.assertEqual(r2["answer"], "Paris")


class TestMultiDeviceIntegration(unittest.TestCase):
    def test_api_v2_oracle_and_partial_hud_push(self):
        from src.runtime import api_v2

        calls = []

        class FakeAdapter:
            def push_neural_voice_assistant_hud(self, **kw):
                calls.append(("partial", kw))
                return True

            def push_oracle_answer(self, **kw):
                calls.append(("final", kw))
                return True

        srv = SimpleNamespace(engo_bridge=SimpleNamespace(adapter=FakeAdapter()), activelook=None)
        code_p, body_p = api_v2.voice(srv, "/api/v2/voice/oracle", {
            "transcript": "combien fait", "partial": True, "mic_source": "android_companion"
        })
        self.assertEqual(code_p, 200)
        self.assertEqual(body_p["status"], "listening")
        self.assertTrue(body_p["hud_pushed"])
        self.assertEqual(calls[0][0], "partial")

        code_f, body_f = api_v2.voice(srv, "/api/v2/voice/oracle", {
            "transcript": "combien fait 2 fois 6", "mic_source": "wear_os"
        })
        self.assertEqual(code_f, 200)
        self.assertEqual(body_f["answer"], "= 12")
        self.assertTrue(body_f["hud_pushed"])
        self.assertEqual(body_f["mic_source"], "wear_os")
        self.assertEqual(calls[1][0], "final")

    def test_relay_and_command_drain_oracle(self):
        from src.fabric import relay as R
        from src.runtime import command_drain as CD

        cmds = R.validate_commands({"commands": [{
            "request_id": "a" * 32,
            "kind": "oracle",
            "text": "combien fait 3 fois 7",
            "lang": "fr",
            "quality": "auto",
            "mic_source": "android_companion",
        }]})
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0]["kind"], "oracle")
        self.assertEqual(cmds[0]["mic_source"], "android_companion")

        pushed = []

        class FakeBridge:
            def push_oracle_answer(self, **kw):
                pushed.append(kw)
                return True

        srv = SimpleNamespace(engo_bridge=FakeBridge(), activelook=None)
        status, text = CD._handle(srv, {}, "relay-1", cmds[0], None, None, None, None)
        self.assertEqual(status, "resolved")
        self.assertIn("= 21", text)
        self.assertEqual(len(pushed), 1)
        self.assertEqual(pushed[0]["answer"], "= 21")

    def test_glasses_hub_oracle_renders_oracle_screen(self):
        from src.ai import oracle as Oracle
        from src.glasses import ui as glass_ui
        from src.glasses.hub import Hub, NullLink

        link = NullLink()
        hub = Hub(link=link, settings={'apps': [], 'privacy': 'full'})
        srv = SimpleNamespace(glasses_hub=hub, engo_bridge=None, activelook=None)
        ans = Oracle.oracle_answer("combien fait 4 fois 8")
        self.assertEqual(ans["answer"], "= 32")
        pushed = Oracle.push_oracle_to_hud(srv, ans, mic_source="android_companion")
        self.assertTrue(pushed)
        self.assertIsInstance(hub.menu.screen, glass_ui.OracleScreen)
        self.assertGreater(len(link.last), 0)
        hub.press("back")
        hub.tick()
        self.assertNotIsInstance(hub.menu.screen, glass_ui.OracleScreen)

    def test_mic_oracle_vad_and_dispatch(self):
        from src.ai.mic_oracle import FRAME_SAMPLES, VadRecorder, send_to_oracle
        from src.glasses.hub import Hub, NullLink

        vad = VadRecorder(threshold_db=-40.0, silence_ms=90, pre_roll_frames=2)
        silence = struct.pack(f'<{FRAME_SAMPLES}h', *([10] * FRAME_SAMPLES))
        loud = struct.pack(f'<{FRAME_SAMPLES}h', *([8000] * FRAME_SAMPLES))

        self.assertIsNone(vad.feed(silence))
        self.assertIsNone(vad.feed(silence))
        self.assertIsNone(vad.feed(loud))
        self.assertIsNone(vad.feed(loud))
        self.assertIsNone(vad.feed(loud))
        self.assertIsNone(vad.feed(silence))
        self.assertIsNone(vad.feed(silence))
        utt = vad.feed(silence)
        self.assertIsNotNone(utt)
        self.assertEqual(len(utt), 6 * FRAME_SAMPLES * 2)

        hub = Hub(link=NullLink(), settings={'apps': [], 'privacy': 'full'})
        srv = SimpleNamespace(glasses_hub=hub, engo_bridge=None, activelook=None)
        res = send_to_oracle(transcript="combien fait 7 fois 7", mic_source="ble_headset", server=srv)
        self.assertEqual(res["answer"], "= 49")
        self.assertTrue(res["hud_pushed"])
        self.assertEqual(res["mic_source"], "ble_headset")

    def test_companion_commands_oracle_and_status_endpoint(self):
        from src.glasses.hub import Hub, NullLink
        from src.runtime import api_v2

        hub = Hub(link=NullLink(), settings={'apps': [], 'privacy': 'full'})
        srv = SimpleNamespace(glasses_hub=hub, engo_bridge=None, activelook=None)
        code, st = api_v2.get(srv, "/api/v2/voice/oracle/status", "")
        self.assertEqual(code, 200)
        self.assertTrue(st["glasses_connected"])
        self.assertIn("model", st)

        code_p, bp = api_v2.voice(srv, "/api/v2/voice/oracle", {
            "transcript": "combien", "partial": True, "mic_source": "pc_mic"
        })
        self.assertEqual(code_p, 200)
        self.assertTrue(bp["hud_pushed"])


if __name__ == '__main__':
    unittest.main()
