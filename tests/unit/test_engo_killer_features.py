"""Unit test suite for ActiveLook / ENGO 'Watch-Impossible' Killer Features.

Tests all 6 core features:
1. Gaze-Aligned Spatial Device Radar (hud_spatial_radar)
2. Eyes-On-Target Action Verification Receipt (hud_eyes_on_target)
3. Two-Phase Commit Touchless Wave-to-Abort Gate (hud_wave_abort)
4. Silent Peripheral Telemetry Stream (hud_peripheral_stream)
5. Hands-Free Workshop / Culinary Prompter (hud_workflow_prompter)
6. Doorbell Intercom Live Subtitle Overlay (hud_doorbell_subtitles)
"""
import unittest
from src.adapters.activelook import (
    ActiveLookAdapter, cmd_clear, cmd_color, cmd_text, cmd_rectf, cmd_circ, cmd_gauge,
    COLOR_GREEN, COLOR_AMBER, COLOR_RED, COLOR_CYAN, COLOR_YELLOW,
    TempleTapMorseDecoder, ActiveLookArcadeEngine
)
from src.adapters.activelook_emulator import parse_frames, run_headless_benchmark


class EngoKillerFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.sent_bytes = bytearray()
        self.adapter = ActiveLookAdapter(
            transport=lambda b: self.sent_bytes.extend(b),
            model="ENGO 3"
        )

    def test_spatial_radar_polar_math_and_bytes(self):
        devices = [
            {"name": "VAC", "bearing_deg": 220, "dist_m": 2.5, "state": "docking"},
            {"name": "GATE", "bearing_deg": 35, "dist_m": 7.5, "state": "alert"},
            {"name": "SOLAR", "bearing_deg": 0, "dist_m": 5.0, "state": "ok"},
            {"name": "CAR", "bearing_deg": 315, "dist_m": 9.0, "state": "ok"}
        ]
        ok = self.adapter.push_spatial_radar(devices)
        self.assertTrue(ok)
        self.assertGreater(len(self.sent_bytes), 150)
        
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x35 for f in frames))  # circ range rings
        self.assertTrue(any(f.cmd == 0x36 for f in frames))  # circf device blips
        self.assertTrue(any(f.cmd == 0x32 for f in frames))  # line axes

    def test_eyes_on_target_receipt_oracle_verification(self):
        # 1. Verified Receipt (Green)
        ok = self.adapter.push_eyes_on_target_receipt(
            target_name="Salon Lights",
            action="Extinction & Verrouillage",
            oracle_verified=True,
            latency_ms=38,
            digest="#4f9a12c8-verified"
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        color_frames = [f for f in frames if f.cmd == 0x3D]
        self.assertEqual(color_frames[0].data, bytes([COLOR_GREEN]))
        self.assertTrue(any(b"IN-SITU VERIFIED" in f.data for f in frames if f.cmd == 0x37))

        # 2. Refused Receipt (Red)
        self.sent_bytes.clear()
        self.adapter.push_eyes_on_target_receipt(
            target_name="Front Gate",
            action="Unlock Attempt",
            oracle_verified=False,
            latency_ms=12,
            digest="#refusal-stale-state"
        )
        frames_refused = parse_frames(bytes(self.sent_bytes))
        color_frames_refused = [f for f in frames_refused if f.cmd == 0x3D]
        self.assertEqual(color_frames_refused[0].data, bytes([COLOR_RED]))
        self.assertTrue(any(b"ACTION REFUSED" in f.data for f in frames_refused if f.cmd == 0x37))

    def test_two_phase_abort_countdown_and_color_transitions(self):
        # 4 seconds left -> Amber phase
        self.adapter.push_two_phase_countdown("Bedtime Routine", seconds_remaining=4, max_seconds=5)
        frames_4s = parse_frames(bytes(self.sent_bytes))
        color_4s = [f for f in frames_4s if f.cmd == 0x3D]
        self.assertEqual(color_4s[0].data, bytes([COLOR_AMBER]))
        self.assertTrue(any(b"ABORT IN: 4s" in f.data for f in frames_4s if f.cmd == 0x37))

        # 1 second left -> Imminent Red phase
        self.sent_bytes.clear()
        self.adapter.push_two_phase_countdown("Bedtime Routine", seconds_remaining=1, max_seconds=5)
        frames_1s = parse_frames(bytes(self.sent_bytes))
        color_1s = [f for f in frames_1s if f.cmd == 0x3D]
        self.assertEqual(color_1s[0].data, bytes([COLOR_RED]))
        self.assertTrue(any(b"ABORT IN: 1s" in f.data for f in frames_1s if f.cmd == 0x37))

    def test_peripheral_telemetry_power_spike_thresholds(self):
        # Nominal load (1400W) -> Green
        self.adapter.push_peripheral_telemetry(grid_watts=1400, wan_mbps=940, ping_ms=8)
        frames_nom = parse_frames(bytes(self.sent_bytes))
        color_nom = [f for f in frames_nom if f.cmd == 0x3D]
        self.assertEqual(color_nom[0].data, bytes([0x00]))          # status row wiped in black first
        self.assertEqual(color_nom[-1].data, bytes([COLOR_GREEN]))  # then drawn in the status colour

        # High spike load (7400W) -> Red Alert
        self.sent_bytes.clear()
        self.adapter.push_peripheral_telemetry(grid_watts=7400, wan_mbps=940, ping_ms=8, alert="LINKY SURCHARGE")
        frames_spike = parse_frames(bytes(self.sent_bytes))
        color_spike = [f for f in frames_spike if f.cmd == 0x3D]
        self.assertEqual(color_spike[-1].data, bytes([COLOR_RED]))
        self.assertTrue(any(b"LINKY SURCHARGE" in f.data for f in frames_spike if f.cmd == 0x37))

    def test_workflow_prompter_step_advance_and_timer(self):
        ok = self.adapter.push_workflow_prompter(
            step_idx=3,
            total_steps=7,
            title="Connect Ribbon Bus",
            instruction="Insert I2C cable into J2 connector until click",
            timer_s=145
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(b"STEP 3/7" in f.data for f in frames if f.cmd == 0x37))
        self.assertTrue(any(b"02:25" in f.data for f in frames if f.cmd == 0x37))  # timer 145s = 2m25s
        # Progress gauge should be 3/7 = ~42%
        gauge_frames = [f for f in frames if f.cmd == 0x70]
        self.assertEqual(gauge_frames[0].data[1], 42)

    def test_doorbell_subtitles_box_clipping(self):
        ok = self.adapter.push_live_subtitles(
            speaker="Livreur Colis",
            text="Bonjour, j'ai un colis fragile pour vous a signer",
            is_urgent=True
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        # Clear is NOT called for subtitles to preserve the user's upper field of vision!
        self.assertFalse(any(f.cmd == 0x01 for f in frames))
        # Draws bounding box at bottom (y >= 165)
        rectf_frames = [f for f in frames if f.cmd == 0x34]
        self.assertEqual(len(rectf_frames), 1)
        # Verify text payload
        self.assertTrue(any(b"LIVREUR COLIS" in f.data for f in frames if f.cmd == 0x37))

    def test_compass_wayfinder_math_and_frames(self):
        # Target at 310 deg, Heading 285 deg -> relative bearing +25 deg (Turn Right)
        ok = self.adapter.push_compass_wayfinder(
            heading_deg=285,
            target_bearing_deg=310,
            target_dist_m=145.0,
            target_name="PARKING B3"
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x32 for f in frames))  # compass line
        self.assertTrue(any(f.cmd == 0x35 for f in frames))  # target circle
        self.assertTrue(any(f.cmd == 0x70 for f in frames))  # gauge
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"PARKING B3" in f.data for f in text_frames))
        self.assertTrue(any(b"VIRER A DROITE" in f.data for f in text_frames))

    def test_smart_home_security_alert_frames(self):
        ok = self.adapter.push_smart_home_security_alert(
            threat_type="SYN Port Scan",
            source_ip="192.168.1.189",
            mac_vendor="Rogue Pi",
            target_service="SSH Port 22"
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x33 for f in frames))  # outline box
        color_frames = [f for f in frames if f.cmd == 0x3D]
        self.assertEqual(color_frames[0].data, bytes([COLOR_RED]))
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"INTRUSION SHIELD" in f.data for f in text_frames))
        self.assertTrue(any(b"192.168.1.189" in f.data for f in text_frames))

    def test_bio_adaptive_pacer_zones_and_cadence(self):
        ok = self.adapter.push_bio_adaptive_pacer(
            target_spm=180,
            current_spm=174,
            hr_bpm=165,
            hr_zone=4,
            advice="AUGMENTER FREQUENCE"
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x70 for f in frames))  # metronome gauge
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"165 BPM" in f.data for f in text_frames))
        self.assertTrue(any(b"ZONE 4" in f.data for f in text_frames))
        self.assertTrue(any(b"ACCELERER" in f.data for f in text_frames))

    def test_media_remote_hud_progress_and_gauges(self):
        ok = self.adapter.push_media_remote_hud(
            media_title="Dune: Part Two",
            artist_or_source="Kodi Salon (4K HDR)",
            volume_pct=45,
            is_playing=True,
            progress_s=3420,
            total_s=9960
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        gauge_frames = [f for f in frames if f.cmd == 0x70]
        self.assertEqual(len(gauge_frames), 2)  # track progress + volume gauge
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"Dune: Part Two" in f.data for f in text_frames))
        self.assertTrue(any(b"Volume Salon : 45%" in f.data for f in text_frames))

    def test_temple_morse_decoder_logic(self):
        decoder = TempleTapMorseDecoder(dot_threshold_s=0.25, letter_pause_s=0.65)
        # Test 1: Tap dot (0.1s)
        decoder.on_touch_down(t=100.0)
        sym1 = decoder.on_touch_up(t=100.1)
        self.assertEqual(sym1, ".")

        # Test 2: Dash (0.4s) -> ".-" which is 'A'
        decoder.on_touch_down(t=100.2)
        sym2 = decoder.on_touch_up(t=100.6)
        self.assertEqual(sym2, "-")
        self.assertEqual(decoder.current_morse, ".-")

        # Test 3: Letter pause commit
        char = decoder.check_letter_timeout(t=101.3)
        self.assertEqual(char, "A")
        self.assertEqual(decoder.committed_text, "A")
        self.assertEqual(decoder.current_morse, "")

    def test_silent_morse_input_frames(self):
        ok = self.adapter.push_silent_morse_input(
            buffer_str="OUI MERCI",
            current_morse=".-",
            suggestion="ARRIVE DANS 5 MIN"
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"SAISIE SILENCIEUSE" in f.data for f in text_frames))
        self.assertTrue(any(b"OUI MERCI_" in f.data for f in text_frames))
        self.assertTrue(any(b"ARRIVE DANS 5 MIN" in f.data for f in text_frames))

    def test_speech_teleprompter_frames(self):
        ok = self.adapter.push_speech_teleprompter(
            current_line="OpenBridge connecte vos lunettes",
            next_line="aux modeles d'IA locaux et a vos objets",
            wpm=138,
            is_rushing=False,
            elapsed_s=45,
            total_s=180
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x70 for f in frames))  # progress gauge
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"138 WPM" in f.data for f in text_frames))
        self.assertTrue(any(b"OpenBridge connecte" in f.data for f in text_frames))
        self.assertTrue(any(b"aux modeles d'IA" in f.data for f in text_frames))

    def test_spatial_energy_heatmap_frames(self):
        ok = self.adapter.push_spatial_energy_heatmap(
            current_room="Cuisine",
            room_watts=2150,
            total_watts=3480,
            vampire_devices=[{"name": "Four Veille", "watts": 65, "idle_hours": 3}]
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x70 for f in frames))  # gauge
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"CUISINE" in f.data for f in text_frames))
        self.assertTrue(any(b"VEILLE FANTOME" in f.data for f in text_frames))
        self.assertTrue(any(b"Four Veille" in f.data for f in text_frames))

    def test_arcade_runner_game_physics_and_frames(self):
        game = ActiveLookArcadeEngine(ground_y=190)
        self.assertFalse(game.is_jumping)
        # Jump
        jumped = game.jump()
        self.assertTrue(jumped)
        self.assertTrue(game.is_jumping)

        # Physics tick
        tick_res = game.tick(dt=0.1)
        self.assertFalse(tick_res["game_over"])
        self.assertLess(game.player_y, 190.0)  # player moved up in air

        # Render frame
        self.sent_bytes.clear()
        ok = self.adapter.push_arcade_game_frame(
            player_y=int(game.player_y),
            obstacle_x=120,
            score=game.score,
            game_over=game.game_over
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x39 for f in frames))  # holdFlush
        self.assertTrue(any(f.cmd == 0x36 for f in frames))  # circf (player)
        self.assertTrue(any(f.cmd == 0x34 for f in frames))  # rectf (obstacle)

    def test_collision_sentry_frames(self):
        # Left side hazard
        ok = self.adapter.push_collision_sentry(
            hazard_side="left",
            speed_kmh=52,
            dist_m=18.5,
            ttc_s=1.3
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x34 for f in frames))  # rectf (side bar)
        self.assertTrue(any(f.cmd == 0x70 for f in frames))  # gauge
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"SENTRY ALERTE" in f.data for f in text_frames))
        self.assertTrue(any(b"LEFT" in f.data for f in text_frames))
        self.assertTrue(any(b"18.5 m" in f.data for f in text_frames))

    def test_executive_briefing_glance_frames(self):
        ok = self.adapter.push_executive_briefing_glance(
            contact_name="Sophie Martin",
            role_title="Directrice R&D",
            bullet_points=[
                "Partenariat OpenBridge v2",
                "Budget 85k EUR",
                "Validation a 17h"
            ],
            sentiment_hint="VIP"
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x33 for f in frames))  # rect frame
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"SOPHIE MARTIN" in f.data for f in text_frames))
        self.assertTrue(any(b"Directrice R&D" in f.data for f in text_frames))
        self.assertTrue(any(b"Partenariat OpenBridge v2" in f.data for f in text_frames))

    def test_biofeedback_stress_guardian_frames(self):
        ok = self.adapter.push_biofeedback_stress_guardian(
            stress_score=68,
            hrv_ms=42,
            breath_phase="INSP",
            phase_timer_s=3
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x35 for f in frames))  # circ reticle
        self.assertTrue(any(f.cmd == 0x70 for f in frames))  # stress gauge
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"STRESS: 68/100" in f.data for f in text_frames))
        self.assertTrue(any(b"HRV: 42ms" in f.data for f in text_frames))
        self.assertTrue(any(b"INSPIRER" in f.data for f in text_frames))

    def test_diy_ar_stud_level_frames(self):
        ok = self.adapter.push_diy_ar_stud_level(
            pitch_deg=0.1,
            roll_deg=0.0,
            is_level=True,
            detected_hazard="CABLE 230V ACTIF"
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x32 for f in frames))  # horizon line / crosshairs
        self.assertTrue(any(f.cmd == 0x35 for f in frames))  # circ reticle
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"0.0\xc2\xb0 LOCKED" in f.data or b"LOCKED" in f.data for f in text_frames))
        self.assertTrue(any(b"CABLE 230V ACTIF" in f.data for f in text_frames))

    def test_first_responder_cpr_and_triage_frames(self):
        # 1. CPR Mode
        ok_cpr = self.adapter.push_first_responder_triage(
            mode="cpr", bpm=110, compression_count=22, ccf_pct=86, cycle_s=42
        )
        self.assertTrue(ok_cpr)
        frames_cpr = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames_cpr))  # clear
        self.assertTrue(any(f.cmd == 0x35 for f in frames_cpr))  # circ reticle
        self.assertTrue(any(f.cmd == 0x70 for f in frames_cpr))  # CCF gauge
        text_cpr = [f for f in frames_cpr if f.cmd == 0x37]
        self.assertTrue(any(b"CPR PACER" in f.data for f in text_cpr))
        self.assertTrue(any(b"110 BPM" in f.data for f in text_cpr))
        self.assertTrue(any(b"COMPRESSION 22/30" in f.data for f in text_cpr))

        # 2. START Triage Mode (Immediate / Red)
        self.sent_bytes.clear()
        ok_tri = self.adapter.push_first_responder_triage(
            mode="triage", triage_level="IMMEDIATE", step_prompt="RESPIRATIONS >30 BPM"
        )
        self.assertTrue(ok_tri)
        frames_tri = parse_frames(bytes(self.sent_bytes))
        text_tri = [f for f in frames_tri if f.cmd == 0x37]
        self.assertTrue(any(b"START TRIAGE" in f.data for f in text_tri))
        self.assertTrue(any(b"IMMEDIATE / ROUGE" in f.data for f in text_tri))

    def test_directional_subtitles_frames(self):
        ok = self.adapter.push_directional_subtitles(
            speaker_name="Alice",
            direction="left",
            text_line1="Bonjour a tous",
            text_line2="Projet en cours de test.",
            is_translated=True
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        # Clear is omitted to keep upper sightline intact
        self.assertFalse(any(f.cmd == 0x01 for f in frames))
        self.assertTrue(any(f.cmd == 0x33 for f in frames))  # subtitle box
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"ALICE" in f.data for f in text_frames))
        self.assertTrue(any(b"Bonjour a tous" in f.data for f in text_frames))
        self.assertTrue(any(b"FR TRAD" in f.data for f in text_frames))

    def test_uav_avionics_hud_frames(self):
        ok = self.adapter.push_uav_avionics_hud(
            pitch_deg=4.5,
            roll_deg=-2.0,
            heading_deg=45,
            alt_agl_m=85.0,
            speed_kmh=48.0,
            home_dist_m=285.0,
            home_bearing_rel_deg=-30.0,
            cell_voltage=3.82,
            lq_pct=100
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x32 for f in frames))  # tape ruler lines & winglets
        self.assertTrue(any(f.cmd == 0x35 for f in frames))  # home chevron circle
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"3.82V" in f.data for f in text_frames))
        self.assertTrue(any(b"045" in f.data for f in text_frames))
        self.assertTrue(any(b"48kmh" in f.data for f in text_frames))
        self.assertTrue(any(b"85m" in f.data for f in text_frames))
        self.assertTrue(any(b"HOME: 285m" in f.data for f in text_frames))

    def test_stealth_rf_sentry_frames(self):
        # 1. BLE Tracker Mode (AirTag)
        ok_ble = self.adapter.push_stealth_rf_sentry(
            threat_type="airtag",
            target_id="Apple AirTag",
            rssi_dbm=-58,
            dist_m=1.8
        )
        self.assertTrue(ok_ble)
        frames_ble = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x70 for f in frames_ble))  # hot-cold gauge
        text_ble = [f for f in frames_ble if f.cmd == 0x37]
        self.assertTrue(any(b"RF SENTRY: BLE TRACKER" in f.data for f in text_ble))
        self.assertTrue(any(b"APPLE AIRTAG" in f.data for f in text_ble))
        self.assertTrue(any(b"-58 dBm" in f.data for f in text_ble))

        # 2. Deauth Flood Attack Mode
        self.sent_bytes.clear()
        ok_deauth = self.adapter.push_stealth_rf_sentry(
            threat_type="deauth_flood",
            target_id="D8:0D:17:B2:4F:90",
            is_critical=True
        )
        self.assertTrue(ok_deauth)
        frames_deauth = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x34 for f in frames_deauth))  # peripheral alarm brackets
        text_deauth = [f for f in frames_deauth if f.cmd == 0x37]
        self.assertTrue(any(b"DEAUTH FLOOD" in f.data for f in text_deauth))
        self.assertTrue(any(b"D8:0D:17:B2:4F:90" in f.data for f in text_deauth))

    def test_thermal_arc_flash_sentry_frames(self):
        ok = self.adapter.push_thermal_arc_flash_sentry(
            t_max_c=78.4,
            t_ambient_c=24.1,
            delta_t_c=54.3,
            reticle_xy=(152, 115),
            afb_dist_m=1.5,
            is_violating_boundary=False
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x32 for f in frames))  # corner bracket lines
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"THERMAL & ARC-FLASH" in f.data for f in text_frames))
        self.assertTrue(any(b"T_MAX : 78.4" in f.data for f in text_frames))
        self.assertTrue(any(b"1.5 m" in f.data for f in text_frames))

    def test_allergen_nutrition_scanner_frames(self):
        # 1. Danger Allergen Triggered
        ok_danger = self.adapter.push_allergen_nutrition_scanner(
            product_name="M&M's Peanut",
            detected_allergens=["ARACHIDES", "SOJA"],
            carbs_g=59.0,
            sugar_g=53.0,
            sodium_mg=40.0,
            nutri_score="E"
        )
        self.assertTrue(ok_danger)
        frames_danger = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x34 for f in frames_danger))  # rectf red alert banner
        text_danger = [f for f in frames_danger if f.cmd == 0x37]
        self.assertTrue(any(b"DANGER ALLERGENE" in f.data for f in text_danger))
        self.assertTrue(any(b"ARACHIDES" in f.data for f in text_danger))

        # 2. Safe Nutritional Mode
        self.sent_bytes.clear()
        ok_safe = self.adapter.push_allergen_nutrition_scanner(
            product_name="Pain Complet Bio",
            detected_allergens=[],
            carbs_g=41.0,
            sugar_g=2.5,
            sodium_mg=450.0,
            nutri_score="A"
        )
        self.assertTrue(ok_safe)
        frames_safe = parse_frames(bytes(self.sent_bytes))
        text_safe = [f for f in frames_safe if f.cmd == 0x37]
        self.assertTrue(any(b"AUCUN DETECTE" in f.data for f in text_safe))
        self.assertTrue(any(b"DIABETE" in f.data for f in text_safe))
        self.assertTrue(any(b"RENAL" in f.data for f in text_safe))

    def test_tactical_marine_hud_frames(self):
        ok = self.adapter.push_tactical_marine_hud(
            awa_deg=-42.0,
            aws_knots=14.5,
            sog_knots=7.8,
            cog_deg=218,
            depth_m=4.8,
            regatta_sec_left=222
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x35 for f in frames))  # circ polar rose
        self.assertTrue(any(f.cmd == 0x32 for f in frames))  # awa needle line
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"START: 03:42" in f.data for f in text_frames))
        self.assertTrue(any(b"7.8 kt" in f.data for f in text_frames))
        self.assertTrue(any(b"4.8 m" in f.data for f in text_frames))

    def test_multilingual_interpreter_frames(self):
        ok = self.adapter.push_multilingual_interpreter(
            speaker_origin="Tanaka",
            source_transcript="Getsuyobi wa chotto...",
            translated_text="Lundi sera un peu difficile...",
            etiquette_tag="[REFUS INDIRECT]",
            etiquette_tip="Politesse japonaise.",
            target_country="JAPON"
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x33 for f in frames))  # etiquette box
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"INTERPRETE: JAPON" in f.data for f in text_frames))
        self.assertTrue(any(b"REFUS INDIRECT" in f.data for f in text_frames))
        self.assertTrue(any(b"Tanaka" in f.data for f in text_frames))
        self.assertTrue(any(b"Lundi sera" in f.data for f in text_frames))

    def test_driver_vigilance_hud_frames(self):
        ok = self.adapter.push_driver_vigilance_hud(
            perclos_pct=18.5,
            microsleep_detected=True,
            saccade_target="LEFT",
            nearest_rest_km=4.2
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x70 for f in frames))  # gauge
        self.assertTrue(any(f.cmd == 0x34 for f in frames))  # rectf lateral ticks
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"MICROSOMMEIL" in f.data for f in text_frames))
        self.assertTrue(any(b"AIRE 4.2k" in f.data for f in text_frames))
        self.assertTrue(any(b"FIXER" in f.data for f in text_frames))

    def test_warehouse_pick_frames(self):
        ok = self.adapter.push_warehouse_pick(
            order_id="48291",
            progress_str="04/18",
            aisle_bay_str="ALLEE 04 - TRAVEE 12",
            shelf_bin_str="ETAGERE 03 (GOLDEN) - BAC 02",
            quantity=12,
            unit_str="PCS",
            sku_code="SKU-8842-M8",
            sku_desc="VIS INOX M8x40",
            scan_status="VERIFIED"
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x33 for f in frames))  # location & verification boxes
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"CMD #48291" in f.data for f in text_frames))
        self.assertTrue(any(b"ALLEE 04" in f.data for f in text_frames))
        self.assertTrue(any(b"x 12 PCS" in f.data for f in text_frames))
        self.assertTrue(any(b"SKU CONFORME" in f.data for f in text_frames))

    def test_avalanche_sar_hud_frames(self):
        # 1. Coarse search mode
        ok = self.adapter.push_avalanche_sar_hud(
            phase="COARSE",
            distance_m=12.4,
            tangent_angle_deg=14.0,
            victims_count=3,
            turn_180=False
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x32 for f in frames))  # tangent chevron lines
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"DVA SAR" in f.data for f in text_frames))
        self.assertTrue(any(b"12.4 m" in f.data for f in text_frames))

        # 2. Turn 180 alert
        self.sent_bytes.clear()
        ok_turn = self.adapter.push_avalanche_sar_hud(
            phase="COARSE",
            distance_m=14.1,
            tangent_angle_deg=0.0,
            victims_count=3,
            turn_180=True
        )
        self.assertTrue(ok_turn)
        frames_turn = parse_frames(bytes(self.sent_bytes))
        text_turn = [f for f in frames_turn if f.cmd == 0x37]
        self.assertTrue(any(b"DEMI-TOUR" in f.data for f in text_turn))

    def test_circadian_chrono_optimizer_frames(self):
        ok = self.adapter.push_circadian_chrono_optimizer(
            current_lux=4200,
            medi_lux=3800,
            dose_lux_min=222000,
            target_dose=300000,
            caffeine_active_mg=68,
            cutoff_time_str="14:30",
            sleep_clearance_hrs=4.3,
            melatonin_warning=False
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x70 for f in frames))  # light dose gauge
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"CIRCADIAN CHRONO" in f.data for f in text_frames))
        self.assertTrue(any(b"DOSE LUMIERE : 74%" in f.data for f in text_frames))
        self.assertTrue(any(b"STOP CAFEINE : 14:30" in f.data for f in text_frames))

    def test_firefighter_mayday_hud_frames(self):
        # 1. Normal SCBA navigation
        ok = self.adapter.push_firefighter_mayday_hud(
            unit_id="E42-A",
            cylinder_bar=220,
            ambient_temp_c=118,
            temp_rise_c_per_min=35,
            exit_bearing_deg=60,
            pass_alarm=False
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x70 for f in frames))  # cylinder air gauge
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"SCBA APPAREIL RESPIRATOIRE" in f.data for f in text_frames))
        self.assertTrue(any(b"AIR : 220 BAR" in f.data for f in text_frames))
        self.assertTrue(any(b"CAP 60 DEG" in f.data for f in text_frames))

        # 2. Mayday / PASS active alert
        self.sent_bytes.clear()
        ok_pass = self.adapter.push_firefighter_mayday_hud(
            unit_id="E42-A",
            cylinder_bar=60,
            ambient_temp_c=280,
            temp_rise_c_per_min=120,
            exit_bearing_deg=180,
            pass_alarm=True
        )
        self.assertTrue(ok_pass)
        frames_pass = parse_frames(bytes(self.sent_bytes))
        text_pass = [f for f in frames_pass if f.cmd == 0x37]
        self.assertTrue(any(b"MAYDAY / PASS ACTIF" in f.data for f in text_pass))
        self.assertTrue(any(b"FLASHOVER" in f.data for f in text_pass))

    def test_ballistic_drop_compensator_frames(self):
        ok = self.adapter.push_ballistic_drop_compensator(
            range_m=850.0,
            elevation_mrad=6.4,
            windage_mrad=-1.2,
            wind_speed_ms=4.5,
            wind_angle_deg=90,
            cant_deg=-0.4
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x32 for f in frames))  # crosshairs / reticle ticks
        self.assertTrue(any(f.cmd == 0x35 for f in frames))  # dynamic aiming pip
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"BALISTIQUE MIL-DOT" in f.data for f in text_frames))
        self.assertTrue(any(b"850m" in f.data for f in text_frames))
        self.assertTrue(any(b"ELEV: +6.4 MIL" in f.data for f in text_frames))
        self.assertTrue(any(b"DEVERS : -0.4 DEG" in f.data for f in text_frames))

    def test_surgical_vitals_hud_frames(self):
        ok = self.adapter.push_surgical_vitals_hud(
            patient_id="P-402",
            spo2_pct=98,
            hr_bpm=72,
            map_mmhg=85,
            etco2_mmhg=38,
            implant_torque_ncm=32.0
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x70 for f in frames))  # torque gauge
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"BLOC OPERATOIRE [P-402]" in f.data for f in text_frames))
        self.assertTrue(any(b"FC: 72 BPM" in f.data for f in text_frames))
        self.assertTrue(any(b"SpO2: 98%" in f.data for f in text_frames))
        self.assertTrue(any(b"COUPLE MOTEUR : 32.0 N.cm" in f.data for f in text_frames))

    def test_low_vision_echonav_hud_frames(self):
        # 1. Normal obstacle warning
        ok = self.adapter.push_low_vision_echonav_hud(
            head_obstacle_dist_m=1.8,
            head_obstacle_type="BRANCHE / PANNEAU",
            curb_drop_dist_m=2.2,
            is_critical_duck=False
        )
        self.assertTrue(ok)
        frames = parse_frames(bytes(self.sent_bytes))
        self.assertTrue(any(f.cmd == 0x01 for f in frames))  # clear
        self.assertTrue(any(f.cmd == 0x33 for f in frames))  # wireframe bracket box
        text_frames = [f for f in frames if f.cmd == 0x37]
        self.assertTrue(any(b"NAVIGATION BASSE VISION" in f.data for f in text_frames))
        self.assertTrue(any(b"OBSTACLE HAUT : a 1.8m" in f.data for f in text_frames))
        self.assertTrue(any(b"DESCENTE a 2.2m" in f.data for f in text_frames))

        # 2. Critical duck alert
        self.sent_bytes.clear()
        ok_duck = self.adapter.push_low_vision_echonav_hud(
            head_obstacle_dist_m=0.9,
            head_obstacle_type="ECHAFFAUDAGE FERRAILLE",
            curb_drop_dist_m=None,
            is_critical_duck=True
        )
        self.assertTrue(ok_duck)
        frames_duck = parse_frames(bytes(self.sent_bytes))
        text_duck = [f for f in frames_duck if f.cmd == 0x37]
        self.assertTrue(any(b"BAISSEZ-VOUS" in f.data for f in text_duck))

    def test_headless_benchmark_execution_and_power_bounds(self):
        results = run_headless_benchmark("ENGO 3")
        self.assertEqual(results["model"], "ENGO 3")
        self.assertEqual(len(results["scenarios"]), 34)
        
        # Verify all 34 scenarios completed with measured metrics
        for name, data in results["scenarios"].items():
            self.assertGreater(data["bytes_transferred"], 50)
            self.assertGreater(data["commands_parsed"], 0)
            self.assertLess(data["pixel_fill_percent"], 40.0)  # max fill <= 40%
            self.assertLess(data["estimated_power_mw"], 2.0)   # power <= 2.0 mW
            self.assertGreater(data["estimated_battery_hours"], 200) # runtime estimate

        # Total byte footprint must be extremely compact (< 15000 bytes for 34 scenarios)
        self.assertLess(results["total_bytes"], 15000)


if __name__ == "__main__":
    unittest.main()
