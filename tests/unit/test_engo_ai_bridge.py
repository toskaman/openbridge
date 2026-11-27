"""Unit test suite for OpenBridge EngoAIBridge.

Tests:
1. Touchless wave gesture voice pipeline (Wake -> Listen -> Transcribe -> Stream AI -> Dismiss).
2. Sight-Through-Phone vision proxy trigger (Temple tap -> Camera snapshot -> Vision AI -> HUD).
3. The Silent Interpreter (Live real-time foreign speech translation streaming).
4. Dynamic API injections (Linky RTE Tempo, Météo rain radar, Public Transit).
5. MicroOLED optical fill-factor and power safety constraints (< 20% fill, < 2.0 mW).
"""
import unittest
from src.adapters.activelook import ActiveLookAdapter
from src.adapters.activelook_emulator import parse_frames, HUDCanvas
from src.adapters.engo_ai_bridge import EngoAIBridge



# The HUD renderer needs Pillow, an optional dependency (requirements-optional.txt). The core suite runs
# dependency-free in CI, so these tests skip there and run in the dedicated "engo-emulator" job.
requires_pillow = unittest.skipUnless(__import__('importlib').util.find_spec('PIL') is not None,
                                      'Pillow required: HUD emulator renderer (requirements-optional.txt)')

class EngoAIBridgeTests(unittest.TestCase):
    def setUp(self):
        self.sent_bytes = bytearray()
        self.adapter = ActiveLookAdapter(
            transport=lambda b: self.sent_bytes.extend(b),
            model="ENGO 3"
        )
        self.adapter.native_frame = False   # these tests read the logical frames; test_activelook.NativeFrameTests covers the conversion
        self.bridge = EngoAIBridge(
            adapter=self.adapter,
            ai_inference_fn=lambda q: f"IA Réponse: {q} traité avec succès.",
            vision_inference_fn=lambda img, p: f"Vision: Objet détecté via smartphone ({len(img)} octets).",
            stt_fn=lambda b: "Éteindre les lumières du bureau"
        )

    def test_voice_interaction_three_phase_lifecycle(self):
        # Phase 1: Wave to wake microphone
        res1 = self.bridge.handle_glasses_interaction("wave")
        self.assertEqual(res1["status"], "LISTENING_STARTED")
        self.assertEqual(self.bridge.current_mode, "LISTENING")
        self.assertTrue(self.bridge.phone_state.mic_listening)
        
        frames1 = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(b"PHONE MIC LISTENING" in f.data for f in frames1 if f.cmd == 0x37))

        # Phase 2: Second wave to stop listening & stream AI response
        self.sent_bytes.clear()
        res2 = self.bridge.handle_glasses_interaction("wave")
        self.assertEqual(res2["status"], "AI_ANSWERED")
        self.assertEqual(self.bridge.current_mode, "STREAMING_AI")
        self.assertFalse(self.bridge.phone_state.mic_listening)
        self.assertIn("Éteindre les lumières", res2["query"])
        self.assertIn("IA Réponse", res2["answer"])

        frames2 = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(b"CO-PILOT" in f.data for f in frames2 if f.cmd == 0x37))

        # Phase 3: Third wave dismisses HUD overlay back to idle
        self.sent_bytes.clear()
        res3 = self.bridge.handle_glasses_interaction("wave")
        self.assertEqual(res3["status"], "DISMISSED")
        self.assertEqual(self.bridge.current_mode, "IDLE")

        frames3 = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames3))  # clear screen

    def test_sight_through_phone_vision_proxy(self):
        res = self.bridge.handle_glasses_interaction("double_tap")
        self.assertEqual(res["status"], "VISION_COMPLETED")
        self.assertEqual(self.bridge.current_mode, "VISION")
        self.assertIn("Vision: Objet détecté", res["result"])

        frames = parse_frames(bytes(self.sent_bytes))
        # Check title and diagnostic text
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"ANALYSE VISUELLE" in f.data for f in text_frames))
        self.assertTrue(any(b"DIAGNOSTIC VISION" in f.data for f in text_frames))

    def test_live_translation_streaming(self):
        ok = self.bridge.stream_live_translation(
            foreign_speaker="Agent Smith",
            source_lang="EN",
            translated_text="Bienvenue dans la matrice OpenBridge connectee."
        )
        self.assertTrue(ok)
        self.assertEqual(self.bridge.current_mode, "SUBTITLES")

        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x33 for f in frames))  # wireframe rect for subtitle box
        self.assertTrue(any(f.cmd == 0x32 for f in frames))  # top separator line
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"[EN" in f.data for f in text_frames))
        self.assertTrue(any(b"Bienvenue dans la matrice" in f.data for f in text_frames))

    def test_dynamic_api_weather_radar(self):
        ok = self.bridge.push_api_glance(
            api_type="weather_radar",
            data={"rain_in_minutes": 10, "temp_c": 13, "wind_kmh": 28}
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"RADAR PRECIPITATIONS" in f.data for f in text_frames))
        self.assertTrue(any(b"RAIN IN : 10 MINUTES" in f.data for f in text_frames))
        self.assertTrue(any(f.cmd == 0x70 for f in frames))  # gauge

    def test_dynamic_api_linky_rte_tempo(self):
        ok = self.bridge.push_api_glance(
            api_type="linky_rte_tempo",
            data={"tempo_today": "BLEU", "tempo_tomorrow": "ROUGE", "instant_watts": 3200}
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"RTE TEMPO : TOMORROW ROUGE" in f.data for f in text_frames))
        self.assertTrue(any(b"3200 W" in f.data for f in text_frames))

    def test_dynamic_api_transit_live(self):
        ok = self.bridge.push_api_glance(
            api_type="transit_live",
            data={"line": "Métro 14", "destination": "Aéroport d'Orly", "eta_minutes": 4}
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"LIVE TRANSIT : M" in f.data for f in text_frames))
        self.assertTrue(any(b"4 MIN" in f.data for f in text_frames))

    @requires_pillow
    def test_optical_power_and_fill_factor_benchmark(self):
        """Verifies that all AI bridge screens adhere to ultra-low MicroOLED power constraints."""
        canvas = HUDCanvas(model="ENGO 3")

        # Benchmark 1: AI Answer Screen
        self.bridge.stream_ai_response(
            title="TEST BENCH",
            answer="Freebox Pop: Débit 940 Mbps, 12 appareils connectés, ping 8ms.",
            query="Quel est le statut réseau ?"
        )
        canvas.dispatch(bytes(self.sent_bytes))
        fill_ai = canvas.compute_pixel_fill()
        pwr_ai = canvas.estimate_power_mw()
        self.assertLess(fill_ai, 20.0, f"AI screen fill factor {fill_ai}% exceeds 20%")
        self.assertLess(pwr_ai, 2.0, f"AI screen power {pwr_ai}mW exceeds 2.0mW")

        # Benchmark 2: Live Translation Subtitles
        self.sent_bytes.clear()
        self.bridge.stream_live_translation("Speaker", "EN", "Bonjour le monde en direct")
        canvas.dispatch(bytes(self.sent_bytes))
        fill_sub = canvas.compute_pixel_fill()
        pwr_sub = canvas.estimate_power_mw()
        self.assertLess(fill_sub, 25.0, f"Subtitles fill factor {fill_sub}% exceeds 25%")
        self.assertLess(pwr_sub, 2.5, f"Subtitles power {pwr_sub}mW exceeds 2.5mW")


if __name__ == "__main__":
    unittest.main()
