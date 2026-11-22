"""
OpenBridge HUD feature catalog — the single source of truth for F01–F38.

Used by the headless benchmark, the HUD Studio emulator UI, the control port
(``{"cmd": "feature", "id": "F07"}``) and the phone overlay (ActiveLook frame 0xF0 <n>).
Each scenario is a short demo payload pushed through ``ActiveLookAdapter``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

CATEGORIES = {
    "home":   ("Home & IoT",        "#22D3EE"),
    "sport":  ("Sport & Bio",       "#A3E635"),
    "pro":    ("Pro & Industry",    "#F59E0B"),
    "safety": ("Safety-critical",   "#F43F5E"),
    "ai":     ("Neural & AI",       "#A78BFA"),
}


@dataclass(frozen=True)
class Feature:
    fid: str        # "F01".."F38"
    key: str        # scenario key used by the benchmark
    title: str
    category: str   # key of CATEGORIES
    icon: str

    @property
    def number(self) -> int:
        return int(self.fid[1:])


FEATURES: list[Feature] = [
    Feature('F01', 'spatial_radar', 'Spatial Device Radar', 'home', '◎'),
    Feature('F02', 'eyes_on_target', 'Eyes-On-Target Receipt', 'home', '◉'),
    Feature('F03', 'two_phase_countdown', 'Two-Phase Abort Gate', 'home', '⏱'),
    Feature('F04', 'peripheral_telemetry', 'Peripheral Telemetry', 'home', '⚡'),
    Feature('F05', 'workflow_prompter', 'Workshop Prompter', 'pro', '🛠'),
    Feature('F06', 'doorbell_subtitles', 'Doorbell Subtitles', 'home', '💬'),
    Feature('F07', 'compass_wayfinder', 'AR Compass Wayfinder', 'sport', '🧭'),
    Feature('F08', 'security_shield', 'Intrusion Shield', 'safety', '🛡'),
    Feature('F09', 'bio_pacer', 'Bio-Adaptive Pacer', 'sport', '🏃'),
    Feature('F10', 'media_remote', 'Touchless Media Remote', 'home', '▶'),
    Feature('F11', 'silent_morse_input', 'TempleTap Morse Input', 'ai', '⌨'),
    Feature('F12', 'speech_teleprompter', 'Speech Teleprompter', 'pro', '🎙'),
    Feature('F13', 'spatial_energy_heatmap', 'Energy Ghost Heatmap', 'home', '♨'),
    Feature('F14', 'arcade_runner', 'Vector Runner Arcade', 'sport', '🎮'),
    Feature('F15', 'collision_sentry', 'Collision Sentry', 'safety', '⚠'),
    Feature('F16', 'executive_briefing', 'Executive Dossier', 'pro', '👤'),
    Feature('F17', 'biofeedback_stress', 'Biofeedback Stress', 'sport', '🧘'),
    Feature('F18', 'diy_ar_stud_level', 'AR Stud & Inclinometer', 'pro', '📐'),
    Feature('F19', 'first_responder_cpr', 'CPR & Triage Pacer', 'safety', '✚'),
    Feature('F20', 'directional_subtitles', 'Directional Subtitles', 'ai', '🗣'),
    Feature('F21', 'uav_avionics', 'UAV Avionics VLOS', 'pro', '✈'),
    Feature('F22', 'stealth_rf_sentry', 'Stealth RF Sentry', 'safety', '📡'),
    Feature('F23', 'thermal_arc_flash', 'Thermal Arc-Flash', 'pro', '🔥'),
    Feature('F24', 'allergen_nutrition', 'Allergen Scanner', 'safety', '🥜'),
    Feature('F25', 'tactical_marine', 'Tactical Marine HUD', 'sport', '⛵'),
    Feature('F26', 'multilingual_whisperer', 'Etiquette Whisperer', 'ai', '🌐'),
    Feature('F27', 'driver_vigilance', 'Driver Vigilance', 'safety', '🚗'),
    Feature('F28', 'warehouse_pick', 'Pick-by-Vision', 'pro', '📦'),
    Feature('F29', 'avalanche_sar', 'Avalanche SAR 457kHz', 'safety', '🏔'),
    Feature('F30', 'circadian_chrono', 'Circadian Chrono', 'sport', '☀'),
    Feature('F31', 'firefighter_mayday', 'Firefighter Mayday', 'safety', '🚒'),
    Feature('F32', 'ballistic_drop', 'Precision Ballistics', 'pro', '🎯'),
    Feature('F33', 'surgical_vitals', 'Sterile Surgical HUD', 'pro', '🩺'),
    Feature('F34', 'low_vision_echonav', 'Low-Vision Echo-Radar', 'safety', '🦯'),
    Feature('F35', 'neural_voice_assistant', 'Neural Voice Co-Pilot', 'ai', '🎧'),
    Feature('F36', 'multimodal_vision_hud', 'Multimodal Vision Proxy', 'ai', '👁'),
    Feature('F37', 'ambient_iot_matrix', 'Ambient IoT Matrix', 'home', '▦'),
    Feature('F38', 'neural_translation_stream', 'Spatial Translation', 'ai', '文'),
]
BY_ID = {f.fid: f for f in FEATURES}
BY_KEY = {f.key: f for f in FEATURES}
BY_NUMBER = {f.number: f for f in FEATURES}
CORE_COUNT = 34   # F01..F34 ; F35..F38 are the neural expansion set


def resolve(ref) -> Feature | None:
    """Accept a Feature, 'F07', 'f7', 7, or 'compass_wayfinder'."""
    if isinstance(ref, Feature):
        return ref
    if isinstance(ref, int):
        return BY_NUMBER.get(ref)
    s = str(ref).strip()
    if s.lower().startswith("f") and s[1:].isdigit():
        return BY_NUMBER.get(int(s[1:]))
    if s.isdigit():
        return BY_NUMBER.get(int(s))
    return BY_KEY.get(s)


def build_scenarios(adapter) -> list[tuple[str, Callable[[], object]]]:
    """Return the 38 (key, callable) demo scenarios in F01..F38 order."""
    scenarios = [
        ("spatial_radar", lambda: adapter.push_spatial_radar([
            {"name": "VAC", "bearing_deg": 220, "dist_m": 2.5, "state": "docking"},
            {"name": "GATE", "bearing_deg": 35, "dist_m": 7.5, "state": "alert"},
            {"name": "SOLAR", "bearing_deg": 0, "dist_m": 5.0, "state": "ok"},
            {"name": "CAR", "bearing_deg": 315, "dist_m": 9.0, "state": "ok"}
        ])),
        ("eyes_on_target", lambda: adapter.push_eyes_on_target_receipt(
            target_name="Salon Lights", action="Extinction & Verrouillage",
            oracle_verified=True, latency_ms=38, digest="#4f9a12c8-verified"
        )),
        ("two_phase_countdown", lambda: adapter.push_two_phase_countdown(
            routine_name="Bedtime Shutdown", seconds_remaining=4, max_seconds=5
        )),
        ("peripheral_telemetry", lambda: adapter.push_peripheral_telemetry(
            grid_watts=7420, wan_mbps=940, ping_ms=9, alert="LINKY SPIKE > 7kW"
        )),
        ("workflow_prompter", lambda: adapter.push_workflow_prompter(
            step_idx=3, total_steps=7, title="Connect Ribbon Bus",
            instruction="Insert I2C cable into J2 connector until click", timer_s=145
        )),
        ("doorbell_subtitles", lambda: adapter.push_live_subtitles(
            speaker="Livreur Colis", text="Bonjour, j'ai un paquet pour vous a deposer", is_urgent=True
        )),
        ("compass_wayfinder", lambda: adapter.push_compass_wayfinder(
            heading_deg=285, target_bearing_deg=310, target_dist_m=145.0, target_name="PARKING B3"
        )),
        ("security_shield", lambda: adapter.push_smart_home_security_alert(
            threat_type="SYN Port Scan", source_ip="192.168.1.189",
            mac_vendor="Raspberry Pi / Rogue", target_service="SSH Port 22"
        )),
        ("bio_pacer", lambda: adapter.push_bio_adaptive_pacer(
            target_spm=180, current_spm=174, hr_bpm=162, hr_zone=4, advice="AUGMENTER FREQUENCE (+6)"
        )),
        ("media_remote", lambda: adapter.push_media_remote_hud(
            media_title="Dune: Part Two", artist_or_source="Kodi Salon (4K HDR)",
            volume_pct=45, is_playing=True, progress_s=3420, total_s=9960
        )),
        ("silent_morse_input", lambda: adapter.push_silent_morse_input(
            buffer_str="OUI EN ROUTE", current_morse=".-", suggestion="ARRIVE 5 MIN"
        )),
        ("speech_teleprompter", lambda: adapter.push_speech_teleprompter(
            current_line="OpenBridge connecte vos lunettes",
            next_line="aux modeles d'IA locaux et a vos objets",
            wpm=138, is_rushing=False, elapsed_s=45, total_s=180
        )),
        ("spatial_energy_heatmap", lambda: adapter.push_spatial_energy_heatmap(
            current_room="Cuisine", room_watts=2150, total_watts=3480,
            vampire_devices=[{"name": "Four Veille", "watts": 65, "idle_hours": 3}]
        )),
        ("arcade_runner", lambda: adapter.push_arcade_game_frame(
            player_y=160, obstacle_x=180, score=50, game_over=False
        )),
        ("collision_sentry", lambda: adapter.push_collision_sentry(
            hazard_side="left", speed_kmh=52, dist_m=18.5, ttc_s=1.3
        )),
        ("executive_briefing", lambda: adapter.push_executive_briefing_glance(
            contact_name="Sophie Martin", role_title="Directrice R&D",
            bullet_points=["Partenariat v2", "Budget 85k", "Decision a 17h"],
            sentiment_hint="VIP"
        )),
        ("biofeedback_stress", lambda: adapter.push_biofeedback_stress_guardian(
            stress_score=68, hrv_ms=42, breath_phase="INSP", phase_timer_s=3
        )),
        ("diy_ar_stud_level", lambda: adapter.push_diy_ar_stud_level(
            pitch_deg=0.1, roll_deg=0.0, is_level=True, detected_hazard="CABLE 230V ACTIF"
        )),
        ("first_responder_cpr", lambda: adapter.push_first_responder_triage(
            mode="cpr", bpm=110, compression_count=22, ccf_pct=86, cycle_s=42
        )),
        ("directional_subtitles", lambda: adapter.push_directional_subtitles(
            speaker_name="Alice", direction="left",
            text_line1="On lance le test d'autonomie ?",
            text_line2="Le protocole BLE est stable.",
            is_translated=False
        )),
        ("uav_avionics", lambda: adapter.push_uav_avionics_hud(
            pitch_deg=4.5, roll_deg=-2.0, heading_deg=45, alt_agl_m=85.0,
            speed_kmh=48.0, home_dist_m=285.0, home_bearing_rel_deg=-30.0,
            cell_voltage=3.82, lq_pct=100
        )),
        ("stealth_rf_sentry", lambda: adapter.push_stealth_rf_sentry(
            threat_type="airtag", target_id="Apple AirTag", rssi_dbm=-58, dist_m=1.8
        )),
        ("thermal_arc_flash", lambda: adapter.push_thermal_arc_flash_sentry(
            t_max_c=78.4, t_ambient_c=24.1, delta_t_c=54.3,
            reticle_xy=(152, 115), afb_dist_m=1.5, is_violating_boundary=False
        )),
        ("allergen_nutrition", lambda: adapter.push_allergen_nutrition_scanner(
            product_name="M&M's Peanut", detected_allergens=["ARACHIDES"],
            carbs_g=59.0, sugar_g=53.0, sodium_mg=40.0, nutri_score="E"
        )),
        ("tactical_marine", lambda: adapter.push_tactical_marine_hud(
            awa_deg=-42.0, aws_knots=14.5, sog_knots=7.8, cog_deg=218, depth_m=4.8, regatta_sec_left=222
        )),
        ("multilingual_whisperer", lambda: adapter.push_multilingual_interpreter(
            speaker_origin="Tanaka", source_transcript="Getsuyobi wa chotto...",
            translated_text="Lundi sera un peu difficile...",
            etiquette_tag="[REFUS INDIRECT]", etiquette_tip="Ne pas insister.",
            target_country="JAPON"
        )),
        ("driver_vigilance", lambda: adapter.push_driver_vigilance_hud(
            perclos_pct=18.5, microsleep_detected=True, saccade_target="LEFT", nearest_rest_km=4.2
        )),
        ("warehouse_pick", lambda: adapter.push_warehouse_pick(
            order_id="48291", progress_str="04/18", aisle_bay_str="ALLEE 04 - TRAVEE 12",
            shelf_bin_str="ETAGERE 03 - BAC 02", quantity=12, unit_str="PCS",
            sku_code="SKU-8842-M8", sku_desc="VIS INOX M8x40", scan_status="VERIFIED"
        )),
        ("avalanche_sar", lambda: adapter.push_avalanche_sar_hud(
            phase="COARSE", distance_m=12.4, tangent_angle_deg=14.0, victims_count=3, turn_180=False
        )),
        ("circadian_chrono", lambda: adapter.push_circadian_chrono_optimizer(
            current_lux=4200, medi_lux=3800, dose_lux_min=222000, target_dose=300000,
            caffeine_active_mg=68, cutoff_time_str="14:30", sleep_clearance_hrs=4.3, melatonin_warning=False
        )),
        ("firefighter_mayday", lambda: adapter.push_firefighter_mayday_hud(
            unit_id="E42-A", cylinder_bar=220, ambient_temp_c=118, temp_rise_c_per_min=35,
            exit_bearing_deg=60, pass_alarm=False
        )),
        ("ballistic_drop", lambda: adapter.push_ballistic_drop_compensator(
            range_m=850.0, elevation_mrad=6.4, windage_mrad=-1.2, wind_speed_ms=4.5,
            wind_angle_deg=90, cant_deg=-0.4
        )),
        ("surgical_vitals", lambda: adapter.push_surgical_vitals_hud(
            patient_id="P-402", spo2_pct=98, hr_bpm=72, map_mmhg=85, etco2_mmhg=38,
            implant_torque_ncm=32.0
        )),
        ("low_vision_echonav", lambda: adapter.push_low_vision_echonav_hud(
            head_obstacle_dist_m=1.8, head_obstacle_type="BRANCHE / PANNEAU",
            curb_drop_dist_m=2.2, is_critical_duck=False
        ))
    ]

    neural_scenarios = [
        ("neural_voice_assistant", lambda: adapter.push_neural_voice_assistant_hud(
            state_str="ECOUTE EN COURS", partial_transcript="Eteindre le salon et verifier la Freebox",
            mic_source="PHONE BEAMFORMING MIC", vu_level_pct=76, latency_ms=115
        )),
        ("multimodal_vision_hud", lambda: adapter.push_multimodal_vision_hud(
            target_label="DISJONCTEUR #4 (CHAUFFE-EAU)", confidence_pct=96,
            bounding_box=(60, 60, 244, 150),
            diagnostic_summary="POSITION BASSE : DECLENCHEMENT",
            action_recommendation="Verifiez resistance avant de re-armer",
            source_device="50MP PHONE CAM"
        )),
        ("ambient_iot_matrix", lambda: adapter.push_ambient_iot_matrix(
            linky_watts=1950, tempo_tomorrow="BLANC", rain_min=14, temp_c=16,
            transit_line="M14", transit_eta_min=2, wan_mbps=940, ping_ms=8
        )),
        ("neural_translation_stream", lambda: adapter.push_neural_translation_stream(
            speaker_id="SPEAKER 01", source_lang="EN", target_lang="FR",
            live_text="Welcome to the OpenBridge AR ecosystem",
            translated_text="Bienvenue dans l'ecosysteme de realite augmentee OpenBridge",
            azimuth_dir="GAUCHE 30°", latency_ms=175
        ))
    ]
    return scenarios + neural_scenarios


def run_feature(adapter, ref) -> Feature:
    """Render one feature on whatever transport the adapter is bound to."""
    feat = resolve(ref)
    if feat is None:
        raise KeyError(f"unknown feature {ref!r}")
    dict(build_scenarios(adapter))[feat.key]()
    return feat
