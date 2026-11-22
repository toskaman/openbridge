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
    cmd_clear,
    cmd_color,
    cmd_grey,
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
    OpenBridgeTelemetryFabric,
    wrap_text_for_hud
)



# The HUD renderer needs Pillow, an optional dependency (requirements-optional.txt). The core suite runs
# dependency-free in CI, so these tests skip there and run in the dedicated "engo-emulator" job.
requires_pillow = unittest.skipUnless(__import__('importlib').util.find_spec('PIL') is not None,
                                      'Pillow required: HUD emulator renderer (requirements-optional.txt)')

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

    # ── 1. Audio Streaming, Multi-format Decoding & VAD Tests ─────────────────

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

    def test_audio_decoding_multi_formats_and_stereo(self):
        proxy = AudioStreamingProxy(sample_rate=16000)

        # 1. 8-bit unsigned PCM
        raw_8bit = bytes([128, 200, 50, 128])
        samples_8bit = proxy.decode_pcm_samples(raw_8bit, bit_depth=8)
        self.assertEqual(len(samples_8bit), 4)
        self.assertEqual(samples_8bit[0], 0)
        self.assertGreater(samples_8bit[1], 0)
        self.assertLess(samples_8bit[2], 0)

        # 2. 16-bit stereo downmixing
        stereo_pairs = [1000, 2000, 3000, 4000]
        raw_stereo = struct.pack("<4h", *stereo_pairs)
        samples_mono = proxy.decode_pcm_samples(raw_stereo, bit_depth=16, channels=2)
        self.assertEqual(len(samples_mono), 2)
        self.assertEqual(samples_mono[0], 1500)
        self.assertEqual(samples_mono[1], 3500)

        # 3. 24-bit PCM
        val = 1000000
        val_bytes = val.to_bytes(3, byteorder="little", signed=True)
        samples_24bit = proxy.decode_pcm_samples(val_bytes, bit_depth=24)
        self.assertEqual(len(samples_24bit), 1)
        self.assertEqual(samples_24bit[0], val >> 8)

        # 4. 32-bit float PCM
        flt_vals = [0.0, 0.5, -0.5]
        raw_flt = struct.pack("<3f", *flt_vals)
        samples_flt = proxy.decode_pcm_samples(raw_flt, bit_depth=32)
        self.assertEqual(len(samples_flt), 3)
        self.assertEqual(samples_flt[0], 0)
        self.assertAlmostEqual(samples_flt[1], int(0.5 * 32767), delta=2)

    # ── 2. Streaming STT Runner Partial Hypothesis Tests ──────────────────────

    def test_streaming_stt_silence_initial_and_partial_tokens(self):
        runner = StreamingSTTRunner()
        runner.arm_session(target_sentence="Allumer la Freebox du salon")

        # Crucial fix verification: Silent chunk before speech MUST NOT emit first word!
        chunk_silent = AudioChunk(raw_bytes=b"dummy", rms_energy=10, db_level=-55.0, duration_ms=100, is_speech=False)
        t_silent, done_silent = runner.process_stream_chunk(chunk_silent)
        self.assertEqual(t_silent, "")
        self.assertFalse(done_silent)

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

    @requires_pillow
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

    def test_text_wrapping_for_hud_long_unbroken_words(self):
        # Extremely long unbroken technical identifiers must not crash, produce empty lines, or exceed 28 chars
        long_text = "DECLENCHEMENT_DIFFERENTIEL_DISJONCTEUR_PRINCIPAL_230V_TRIP verifie par OpenBridge."
        lines = wrap_text_for_hud(long_text, max_chars=28, max_lines=4)
        self.assertGreater(len(lines), 0)
        self.assertLessEqual(len(lines), 4)
        for line in lines:
            self.assertLessEqual(len(line), 28)
            self.assertTrue(len(line) > 0, "Line must not be empty string")

    def test_doorbell_subtitles_wipe_black_rectf(self):
        self.sent_bytes.clear()
        ok = self.adapter.push_live_subtitles(
            speaker="Livreur",
            text="Colis depose devant la porte",
            is_urgent=False
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        # Verify color 0 (black) or grey 0 was explicitly set before cmd_rectf
        color_frames = [f for f in frames if f.cmd == 0x3D or f.cmd == 0x30]
        self.assertTrue(any(f.data == bytes([0]) for f in color_frames), "Must set black (0) before wiping box")
        self.assertTrue(any(f.cmd == 0x34 for f in frames))  # rectf

    def test_multimodal_vision_heuristics_all_domains(self):
        proxy = MultimodalVisionProxy()
        # QR / Oracle receipt
        d1 = proxy.analyze_frame(b"img", prompt="Scan ce qr code receipt")
        self.assertIn("ORACLE RECEIPT", d1.target_label)

        # Vehicle collision threat
        d2 = proxy.analyze_frame(b"img", prompt="Attention danger vehicule gauche")
        self.assertIn("VEHICULE", d2.target_label)

        # Driver vigilance
        d3 = proxy.analyze_frame(b"img", prompt="Surveillance somnolence yeux conducteur")
        self.assertIn("VIGILANCE", d3.target_label)

        # Warehouse SKU
        d4 = proxy.analyze_frame(b"img", prompt="Verification colis sku entrepot")
        self.assertIn("COLIS", d4.target_label)

        # DIY Stud live-wire
        d5 = proxy.analyze_frame(b"img", prompt="Detecte fil tension dans le mur")
        self.assertIn("DETECTEUR", d5.target_label)

        # Echonav obstacle
        d6 = proxy.analyze_frame(b"img", prompt="Scan obstacle hauteur tete trottoir")
        self.assertIn("OBSTACLE", d6.target_label)

    def test_stop_listening_and_execute_streamed_transcript_handoff(self):
        self.bridge.handle_glasses_interaction("wave")
        self.assertEqual(self.bridge.current_mode, "LISTENING")
        self.bridge.stt_runner.arm_session("Allumer la Freebox du salon")

        # Ingest speech chunk to advance tokens
        chunk_speech = AudioChunk(raw_bytes=b"dummy", rms_energy=2500, db_level=-22.0, duration_ms=100, is_speech=True)
        self.bridge.stt_runner.process_stream_chunk(chunk_speech)
        self.bridge.stt_runner.process_stream_chunk(chunk_speech)

        # Stop listening and verify the recognized transcript was handed to AI
        res = self.bridge.stop_listening_and_execute()
        self.assertEqual(res["status"], "AI_ANSWERED")
        self.assertEqual(res["query"], "Allumer la")
        self.assertIn("Allumer la", res["answer"])

    def test_telemetry_event_dispatch_all_38_features(self):
        events_to_test = [
            ("spatial_radar", {"devices": [{"name": "GATE", "bearing_deg": 30, "dist_m": 5.0, "state": "ok"}]}),
            ("eyes_on_target", {"target_name": "Salon", "action": "Lock", "oracle_verified": True}),
            ("two_phase_countdown", {"routine_name": "Sleep", "seconds_remaining": 3}),
            ("peripheral_telemetry", {"grid_watts": 1500, "wan_mbps": 900, "ping_ms": 7}),
            ("workflow_prompter", {"step_idx": 2, "total_steps": 4, "title": "Cabler", "instruction": "Clipsez"}),
            ("doorbell_subtitles", {"speaker": "Postier", "text": "Bonjour"}),
            ("compass_wayfinder", {"heading_deg": 90, "target_bearing_deg": 100, "target_dist_m": 50.0}),
            ("security_shield", {"threat_type": "SYN", "source_ip": "192.168.1.50"}),
            ("bio_pacer", {"target_spm": 175, "current_spm": 170, "hr_bpm": 150}),
            ("media_remote", {"media_title": "Interstellar", "volume_pct": 50}),
            ("silent_morse", {"buffer_str": "OUI", "current_morse": ".-"}),
            ("speech_teleprompter", {"current_line": "Bonjour", "wpm": 120}),
            ("spatial_energy_heatmap", {"current_room": "Bureau", "room_watts": 450}),
            ("arcade_runner", {"player_y": 150, "obstacle_x": 100, "score": 20}),
            ("collision_sentry", {"hazard_side": "right", "speed_kmh": 45, "dist_m": 12.0}),
            ("executive_briefing", {"contact_name": "Alice", "role_title": "CTO", "bullet_points": ["Review"]}),
            ("biofeedback_stress", {"stress_score": 40, "hrv_ms": 55}),
            ("diy_ar_stud_level", {"pitch_deg": 0.0, "roll_deg": 0.0, "is_level": True}),
            ("first_responder_cpr", {"mode": "cpr", "bpm": 110, "compression_count": 30}),
            ("directional_subtitles", {"speaker_name": "Bob", "direction": "left", "text_line1": "Salut"}),
            ("uav_avionics", {"pitch_deg": 2.0, "roll_deg": 0.0, "speed_kmh": 25.0}),
            ("stealth_rf_sentry", {"threat_type": "airtag", "target_id": "Tag-1", "dist_m": 2.0}),
            ("thermal_arc_flash", {"t_max_c": 60.0, "t_ambient_c": 20.0, "delta_t_c": 40.0}),
            ("allergen_nutrition", {"product_name": "Biscuit", "detected_allergens": ["Gluten"]}),
            ("tactical_marine", {"awa_deg": 40.0, "aws_knots": 15.0, "sog_knots": 8.0}),
            ("multilingual_interpreter", {"speaker_origin": "Hans", "translated_text": "Guten Tag"}),
            ("driver_vigilance", {"perclos_pct": 8.0, "microsleep_detected": False}),
            ("warehouse_pick", {"order_id": "ORD-1", "sku_code": "SKU-99", "quantity": 5}),
            ("avalanche_sar", {"phase": "COARSE", "distance_m": 15.0}),
            ("circadian_chrono", {"current_lux": 2500, "dose_lux_min": 150000}),
            ("firefighter_mayday", {"unit_id": "F-01", "cylinder_bar": 210}),
            ("ballistic_drop", {"range_m": 600.0, "elevation_mrad": 4.1}),
            ("surgical_vitals", {"patient_id": "P-9", "spo2_pct": 98, "hr_bpm": 68}),
            ("low_vision_echonav", {"head_obstacle_dist_m": 2.5, "head_obstacle_type": "BRANCH"}),
            ("neural_voice_assistant", {"state_str": "ACTIF", "partial_transcript": "Test assistant"}),
            ("multimodal_vision_hud", {"target_label": "OBJET", "confidence_pct": 95}),
            ("ambient_iot_matrix", {"linky_watts": 2100, "rain_min": 10}),
            ("neural_translation_stream", {"speaker_id": "JOHN", "translated_text": "Hello"})
        ]

        self.assertEqual(len(events_to_test), 38, "Must test all 38 features in telemetry fabric")

        for event_type, payload in events_to_test:
            self.sent_bytes.clear()
            ok = self.bridge.dispatch_telemetry_event(event_type=event_type, data=payload, priority=4)
            self.assertTrue(ok, f"Event {event_type} failed to dispatch")
            self.assertGreater(len(self.sent_bytes), 0, f"Event {event_type} produced 0 bytes on display")

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

    @requires_pillow
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
