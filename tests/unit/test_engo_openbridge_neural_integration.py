"""Unit test suite for OpenBridge Neural AI & Sensory Proxy Integration on ActiveLook / ENGO.

Tests:
1. Audio streaming chunks, RMS energy, dB level, and Voice Activity Detection (VAD).
2. Streaming STT runner with incremental partial hypothesis token emission to HUD.
3. Multimodal vision proxy with bounding box reticle projection (304x256 MicroOLED).
4. 4-Quadrant ambient IoT and living infrastructure matrix layout and power metrics.
5. Spatial directional speech translation stream with acoustic azimuth indicator.
6. OpenBridge telemetry priority queue (Critical safety preemption over ambient).
7. Advanced gesture state machine (single wave, double wave cycle, wave hold, tap, triple tap).
8. Headless benchmark with 38 scenarios (34 legacy + 4 neural expansion scenarios).
"""
import struct
import unittest

from src.adapters.activelook import (
    ActiveLookAdapter,
    COLOR_GREEN,
    COLOR_AMBER,
    COLOR_RED,
    COLOR_CYAN,
    COLOR_YELLOW
)
from src.adapters.activelook_emulator import parse_frames, HUDCanvas, run_headless_benchmark
from src.adapters.engo_ai_bridge import (
    EngoAIBridge,
    PhoneSensoryState,
    AudioStreamingProxy,
    AudioChunk,
    StreamingSTTRunner,
    MultimodalVisionProxy,
    OpenBridgeTelemetryFabric
)


class EngoOpenBridgeNeuralIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.sent_bytes = bytearray()
        self.adapter = ActiveLookAdapter(
            transport=lambda b: self.sent_bytes.extend(b),
            model="ENGO 3"
        )
        self.bridge = EngoAIBridge(
            adapter=self.adapter,
            ai_inference_fn=lambda q: f"Synthese IA: {q} execute.",
            stt_fn=lambda b: "Eteindre le salon et verifier la Freebox"
        )

    # ── 1. Audio Streaming & VAD Tests ────────────────────────────────────────

    def test_audio_streaming_vad_and_vu_meter(self):
        proxy = AudioStreamingProxy(sample_rate=16000, vad_threshold_db=-35.0)

        # Silent frame (near zero amplitude)
        silent_samples = [0] * 320
        silent_pcm = struct.pack(f"<{len(silent_samples)}h", *silent_samples)
        chunk_silent = proxy.process_pcm_frame(silent_pcm)
        self.assertFalse(chunk_silent.is_speech)
        self.assertLess(chunk_silent.db_level, -40.0)
        vu_silent = proxy.db_to_vu_percent(chunk_silent.db_level)
        self.assertLessEqual(vu_silent, 35)

        # Loud speech frame (sinusoidal loud signal)
        speech_samples = [int(18000 * ((i % 16) / 8.0 - 1.0)) for i in range(320)]
        speech_pcm = struct.pack(f"<{len(speech_samples)}h", *speech_samples)
        chunk_speech = proxy.process_pcm_frame(speech_pcm)
        self.assertTrue(chunk_speech.is_speech)
        self.assertGreater(chunk_speech.db_level, -30.0)
        vu_speech = proxy.db_to_vu_percent(chunk_speech.db_level)
        self.assertGreater(vu_speech, 50)

    # ── 2. Streaming STT Runner Partial Hypothesis Tests ──────────────────────

    def test_streaming_stt_partial_token_emission(self):
        runner = StreamingSTTRunner()
        runner.arm_session(target_sentence="Allumer la Freebox du salon")

        chunk_speech = AudioChunk(raw_bytes=b"dummy", rms_energy=2500, db_level=-22.0, duration_ms=100, is_speech=True)

        # Step 1: First token
        t1, done1 = runner.process_stream_chunk(chunk_speech)
        self.assertEqual(t1, "Allumer")
        self.assertFalse(done1)

        # Step 2: Second token
        t2, done2 = runner.process_stream_chunk(chunk_speech)
        self.assertEqual(t2, "Allumer la")
        self.assertFalse(done2)

        # Step 3: Third token
        t3, done3 = runner.process_stream_chunk(chunk_speech)
        self.assertEqual(t3, "Allumer la Freebox")
        self.assertFalse(done3)

        # Step 4: Fourth token
        t4, done4 = runner.process_stream_chunk(chunk_speech)
        self.assertEqual(t4, "Allumer la Freebox du")
        self.assertFalse(done4)

        # Step 5: Final token
        t5, done5 = runner.process_stream_chunk(chunk_speech)
        self.assertEqual(t5, "Allumer la Freebox du salon")
        self.assertTrue(done5)

    def test_feed_audio_chunk_integration_with_hud_ticker(self):
        # Start voice listening
        self.bridge.handle_glasses_interaction("wave")
        self.assertEqual(self.bridge.current_mode, "LISTENING")

        # Ingest speech frame
        speech_samples = [12000] * 320
        speech_pcm = struct.pack(f"<{len(speech_samples)}h", *speech_samples)
        self.sent_bytes.clear()

        res = self.bridge.feed_audio_chunk(speech_pcm)
        self.assertIn(res["status"], ["STREAMING_CHUNK_PROCESSED", "AI_ANSWERED"])

        frames = parse_frames(bytes(self.sent_bytes))
        # Verify speech ticker text and audio VU-meter gauge/rect
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"ECOUTE" in f.data or b"CO-PILOT" in f.data for f in text_frames))

    # ── 3. Multimodal Vision Proxy Tests ──────────────────────────────────────

    def test_multimodal_vision_heuristics_and_reticle(self):
        proxy = MultimodalVisionProxy()

        # Detection 1: Electrical panel
        det_panel = proxy.analyze_frame(b"frame", prompt="Regarde ce disjoncteur")
        self.assertIn("DISJONCTEUR", det_panel.target_label)
        self.assertIn("DECLENCHEMENT", det_panel.diagnostic)
        self.assertEqual(det_panel.bounding_box, (60, 60, 244, 150))
        self.assertEqual(det_panel.confidence_pct, 96)

        # Detection 2: Appliance error code
        det_app = proxy.analyze_frame(b"frame", prompt="Quel est le code erreur ?")
        self.assertIn("LAVE-LINGE", det_app.target_label)
        self.assertIn("E18", det_app.diagnostic)

        # Detection 3: Allergen nutritional scan
        det_nutri = proxy.analyze_frame(b"frame", prompt="Scan cet aliment et ses allergenes")
        self.assertIn("ARACHIDES", det_nutri.diagnostic)

    def test_push_multimodal_vision_hud_rendering(self):
        ok = self.adapter.push_multimodal_vision_hud(
            target_label="DISJONCTEUR #4",
            confidence_pct=96,
            bounding_box=(60, 60, 244, 150),
            diagnostic_summary="POSITION BASSE : DECLENCHEMENT",
            action_recommendation="Re-armer apres verification",
            source_device="PHONE 50MP CAM"
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        
        # Verify bounding box rect and corner lines
        self.assertTrue(any(f.cmd == 0x33 for f in frames))  # outline rect
        self.assertTrue(any(f.cmd == 0x32 for f in frames))  # reticle lines
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"CIBLE: DISJONCTEUR #4" in f.data for f in text_frames))
        self.assertTrue(any(b"DECLENCHEMENT" in f.data for f in text_frames))

    # ── 4. 4-Quadrant Ambient IoT Matrix Tests ─────────────────────────────────

    def test_ambient_iot_matrix_quadrant_layout_and_power(self):
        res = self.bridge.push_ambient_matrix(
            linky_watts=2250,
            tempo_tomorrow="ROUGE",
            rain_min=8,
            temp_c=13,
            transit_line="M14",
            transit_eta_min=2,
            wan_mbps=940,
            ping_ms=6
        )
        self.assertTrue(res["success"])
        self.assertEqual(self.bridge.current_mode, "AMBIENT_MATRIX")

        frames = parse_frames(bytes(self.sent_bytes))
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"LINKY: 2250 W" in f.data for f in text_frames))
        self.assertTrue(any(b"ROUGE" in f.data for f in text_frames))
        self.assertTrue(any(b"PLUIE: 8m" in f.data for f in text_frames))
        self.assertTrue(any(b"M14: DANS 2m" in f.data for f in text_frames))
        self.assertTrue(any(b"FIBRE: 940M" in f.data for f in text_frames))

        # Optical benchmark
        canvas = HUDCanvas(model="ENGO 3")
        canvas.dispatch(bytes(self.sent_bytes))
        fill = canvas.compute_pixel_fill()
        pwr = canvas.estimate_power_mw()
        self.assertLess(fill, 20.0, f"Matrix fill factor {fill}% exceeds 20%")
        self.assertLess(pwr, 2.0, f"Matrix power {pwr}mW exceeds 2.0mW")

    # ── 5. Spatial Directional Speech Translation Stream ──────────────────────

    def test_spatial_speech_translation_stream(self):
        ok = self.adapter.push_neural_translation_stream(
            speaker_id="ORATEUR 02",
            source_lang="EN",
            target_lang="FR",
            live_text="The battery lasts up to 24 hours.",
            translated_text="La batterie dure jusqu'a 24 heures.",
            azimuth_dir="DROITE 60°",
            latency_ms=145
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"ORATEUR 02 [DROITE 60" in f.data for f in text_frames))
        self.assertTrue(any(b"La batterie dure" in f.data for f in text_frames))
        self.assertTrue(any(b"TRADUCTION IA" in f.data for f in text_frames))

    # ── 6. OpenBridge Telemetry Priority Fabric Tests ─────────────────────────

    def test_telemetry_priority_queue_ordering(self):
        fabric = OpenBridgeTelemetryFabric(adapter=self.adapter)
        fabric.enqueue("ambient_watts", {"watts": 1200}, priority=OpenBridgeTelemetryFabric.PRIO_AMBIENT_TELEMETRY)
        fabric.enqueue("two_phase_confirm", {"action": "bedtime"}, priority=OpenBridgeTelemetryFabric.PRIO_ACTION_CONFIRMATION)
        fabric.enqueue("mayday_flashover", {"temp": 280}, priority=OpenBridgeTelemetryFabric.PRIO_CRITICAL_SAFETY)

        # Pop 1: Must be Critical Safety
        e1 = fabric.pop_highest_priority()
        self.assertIsNotNone(e1)
        self.assertEqual(e1.priority, OpenBridgeTelemetryFabric.PRIO_CRITICAL_SAFETY)
        self.assertEqual(e1.event_type, "mayday_flashover")

        # Pop 2: Must be Action Confirmation
        e2 = fabric.pop_highest_priority()
        self.assertIsNotNone(e2)
        self.assertEqual(e2.priority, OpenBridgeTelemetryFabric.PRIO_ACTION_CONFIRMATION)

        # Pop 3: Ambient Telemetry
        e3 = fabric.pop_highest_priority()
        self.assertIsNotNone(e3)
        self.assertEqual(e3.priority, OpenBridgeTelemetryFabric.PRIO_AMBIENT_TELEMETRY)

    def test_dispatch_critical_telemetry_event(self):
        self.sent_bytes.clear()
        ok = self.bridge.dispatch_telemetry_event(
            event_type="intrusion_detected",
            data={"message": "Capteur portail franchi"},
            priority=OpenBridgeTelemetryFabric.PRIO_CRITICAL_SAFETY
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        color_frames = [f for f in frames if f.cmd == 0x3D]
        self.assertEqual(color_frames[0].data, bytes([COLOR_RED]))
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"CRITICAL" in f.data for f in text_frames))

    # ── 7. Advanced Gesture State Machine Tests ───────────────────────────────

    def test_double_wave_cycles_telemetry_pages(self):
        self.assertEqual(self.bridge.active_page_idx, 0)
        res1 = self.bridge.handle_glasses_interaction("double_wave")
        self.assertEqual(res1["page"], "linky_rte_tempo")
        self.assertEqual(self.bridge.active_page_idx, 1)

        res2 = self.bridge.handle_glasses_interaction("double_wave")
        self.assertEqual(res2["page"], "weather_radar")
        self.assertEqual(self.bridge.active_page_idx, 2)

        res3 = self.bridge.handle_glasses_interaction("double_wave")
        self.assertEqual(res3["page"], "transit_live")
        self.assertEqual(self.bridge.active_page_idx, 3)

    def test_wave_hold_emergency_and_triple_tap_audio_readback(self):
        # Wave hold -> Emergency beacon
        res_emer = self.bridge.handle_glasses_interaction("wave_hold")
        self.assertEqual(res_emer["status"], "EMERGENCY_TRIGGERED")
        frames = parse_frames(bytes(self.sent_bytes))
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"ALERTE MAYDAY" in f.data for f in text_frames))

        # Triple tap -> Audio readback
        res_audio = self.bridge.handle_glasses_interaction("triple_tap")
        self.assertEqual(res_audio["status"], "AUDIO_READBACK_DISPATCHED")
        self.assertIn("phone_speaker", res_audio["device"])

    # ── 8. Headless Benchmark with 38 Scenarios ───────────────────────────────

    def test_headless_benchmark_with_neural_scenarios(self):
        results = run_headless_benchmark("ENGO 3", include_neural=True)
        self.assertEqual(results["model"], "ENGO 3")
        self.assertEqual(len(results["scenarios"]), 38)

        # Verify all 38 scenarios have safe power and fill metrics
        for name, data in results["scenarios"].items():
            self.assertGreater(data["bytes_transferred"], 50, f"Scenario {name} transferred < 50 bytes")
            self.assertGreater(data["commands_parsed"], 0, f"Scenario {name} parsed 0 commands")
            self.assertLess(data["pixel_fill_percent"], 40.0, f"Scenario {name} fill exceeds 40%")
            self.assertLess(data["estimated_power_mw"], 2.0, f"Scenario {name} power exceeds 2.0mW")
            self.assertGreater(data["estimated_battery_hours"], 200, f"Scenario {name} battery < 200h")

        # Verify specific neural scenarios exist in benchmark dictionary
        self.assertIn("neural_voice_assistant", results["scenarios"])
        self.assertIn("multimodal_vision_hud", results["scenarios"])
        self.assertIn("ambient_iot_matrix", results["scenarios"])
        self.assertIn("neural_translation_stream", results["scenarios"])


if __name__ == "__main__":
    unittest.main()
