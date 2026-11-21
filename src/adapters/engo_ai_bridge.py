"""OpenBridge Neural HUD & Sensory Proxy Bridge for ENGO Eyewear.

Connects ENGO Smart Glasses (via BLE GATT 0783b03e-8535-b5a0-7140-a304d2495cb7)
to the tethered Smartphone (acting as sensory proxy) and the OpenBridge PC Brain
(LLMs, Whisper STT, Computer Vision, Live Device Fabric APIs).

Hardware Topology:
- Glasses: 304x256 MicroOLED display + Optical IR proximity wave sensor + Capacitive touch temple.
  (NO microphone, NO camera, NO speaker).
- Phone: High-end beamforming microphone, 50MP camera, GPS, 5G/Wi-Fi, Companion relay.
- PC / OpenBridge Core: Local LLM (Llama 3.2 3B / Mistral), Whisper STT, device fabric, live APIs.

Interaction Pipeline & Gestures:
1. Single wave [0x01] -> Toggle Phone Microphone listening / dismiss active card / confirm action.
2. Double wave [0x02] -> Cycle Ambient Telemetry Pages (Ambient Matrix -> Linky -> Weather -> Transit -> Freebox).
3. Wave hold (>1.5s)  -> Emergency Mayday / PASS alert or Night stealth dimming mode.
4. Temple tap         -> Quick ambient glance / acknowledge alert.
5. Temple double tap  -> Phone 50MP Camera capture & Multimodal Vision analysis.
6. Temple triple tap  -> Voice readback via phone speaker or connected wireless earbuds.
7. Temple Morse tap   -> Silent Morse text entry with Local LLaMA autocomplete.
"""
from __future__ import annotations

import math
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.adapters.activelook import (
    ActiveLookAdapter,
    cmd_clear,
    cmd_color,
    cmd_text,
    cmd_rectf,
    cmd_rect,
    cmd_line,
    cmd_gauge,
    cmd_hold_flush,
    COLOR_GREEN,
    COLOR_AMBER,
    COLOR_RED,
    COLOR_CYAN,
    COLOR_YELLOW
)


# ──────────────────────────────────────────────────────────────────────────────
# Dataclasses & Sensory Telemetry Structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PhoneSensoryState:
    """State of the smartphone tethered to the glasses."""
    mic_listening: bool = False
    camera_ready: bool = True
    battery_pct: int = 85
    network_type: str = "5G"
    gps_lat: float = 48.8566
    gps_lon: float = 2.3522
    ambient_noise_db: float = 42.0
    active_mic_source: str = "smartphone_mic"  # smartphone_mic, pc_mic, headset_mic, doorbell_mic


@dataclass
class AudioChunk:
    """Audio buffer chunk for Voice Activity Detection and Streaming STT."""
    raw_bytes: bytes
    rms_energy: float
    db_level: float
    duration_ms: int
    sample_rate: int = 16000
    is_speech: bool = False


@dataclass
class TelemetryEvent:
    """Unified OpenBridge telemetry notification."""
    event_id: str
    event_type: str
    priority: int  # 1: CRITICAL_SAFETY, 2: ACTION_CONFIRMATION, 3: ASSISTANT, 4: AMBIENT
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class VisionDetection:
    """Multimodal computer vision detection result mapped to HUD coordinates."""
    target_label: str
    confidence_pct: int
    bounding_box: Tuple[int, int, int, int]  # (x0, y0, x1, y1) in 304x256 space
    diagnostic: str
    action_hint: str


# ──────────────────────────────────────────────────────────────────────────────
# Audio Streaming & Voice Activity Detection Proxy
# ──────────────────────────────────────────────────────────────────────────────

class AudioStreamingProxy:
    """Simulates or buffers incoming audio streams from Phone or PC microphones."""

    def __init__(self, sample_rate: int = 16000, vad_threshold_db: float = -38.0):
        self.sample_rate = sample_rate
        self.vad_threshold_db = vad_threshold_db
        self.noise_floor_db = -50.0
        self.consecutive_speech_frames = 0
        self.consecutive_silence_frames = 0

    def process_pcm_frame(self, pcm_bytes: bytes) -> AudioChunk:
        """Processes 16-bit PCM audio frame and computes RMS energy, dB, and VAD."""
        if not pcm_bytes:
            return AudioChunk(b"", 0.0, -100.0, 0, self.sample_rate, False)

        # 16-bit signed PCM samples
        sample_count = len(pcm_bytes) // 2
        if sample_count == 0:
            return AudioChunk(pcm_bytes, 0.0, -100.0, 0, self.sample_rate, False)

        try:
            samples = struct.unpack(f">{sample_count}h" if pcm_bytes[:1] == b"\x00" else f"<{sample_count}h", pcm_bytes[:sample_count * 2])
            sum_sq = sum(s * s for s in samples)
            rms = math.sqrt(sum_sq / sample_count)
            # Decibel relative to full-scale (32767)
            db = 20 * math.log10(max(1.0, rms) / 32767.0)
        except Exception:
            rms = 1200.0
            db = -28.0

        is_speech = db > self.vad_threshold_db
        if is_speech:
            self.consecutive_speech_frames += 1
            self.consecutive_silence_frames = 0
        else:
            self.consecutive_silence_frames += 1
            if self.consecutive_silence_frames > 5:
                self.consecutive_speech_frames = 0

        duration_ms = int((sample_count / self.sample_rate) * 1000)
        return AudioChunk(
            raw_bytes=pcm_bytes,
            rms_energy=rms,
            db_level=round(db, 1),
            duration_ms=duration_ms,
            sample_rate=self.sample_rate,
            is_speech=is_speech
        )

    @staticmethod
    def db_to_vu_percent(db: float) -> int:
        """Maps -60.0 dB (silent) to 0.0 dB (maximum) into 0-100% scale."""
        clamped = max(-60.0, min(0.0, db))
        return int(((clamped + 60.0) / 60.0) * 100)


# ──────────────────────────────────────────────────────────────────────────────
# Streaming STT Engine (Whisper / Vosk / Cloud Simulator)
# ──────────────────────────────────────────────────────────────────────────────

class StreamingSTTRunner:
    """Simulates real-time streaming speech-to-text with partial word hypotheses."""

    def __init__(self, final_stt_fn: Optional[Callable[[bytes], str]] = None):
        self.final_stt_fn = final_stt_fn or (lambda b: "Allumer les lumieres du bureau")
        self.partial_tokens: List[str] = []
        self.current_token_idx: int = 0
        self.is_final: bool = False

    def arm_session(self, target_sentence: Optional[str] = None):
        """Prepares a new utterance session."""
        sentence = target_sentence or "Eteindre le salon et verifier la Freebox"
        self.partial_tokens = sentence.split()
        self.current_token_idx = 0
        self.is_final = False

    def process_stream_chunk(self, chunk: AudioChunk) -> Tuple[str, bool]:
        """Returns incremental partial transcript hypothesis or final transcript."""
        if not self.partial_tokens:
            self.arm_session()

        if chunk.is_speech and self.current_token_idx < len(self.partial_tokens):
            self.current_token_idx += 1
            partial_text = " ".join(self.partial_tokens[:self.current_token_idx])
            is_done = self.current_token_idx >= len(self.partial_tokens)
            self.is_final = is_done
            return partial_text, is_done

        # Silence or end of speech
        if self.current_token_idx >= len(self.partial_tokens):
            self.is_final = True
            return " ".join(self.partial_tokens), True

        return " ".join(self.partial_tokens[:max(1, self.current_token_idx)]), False


# ──────────────────────────────────────────────────────────────────────────────
# Multimodal Sight-Through-Phone Vision Proxy
# ──────────────────────────────────────────────────────────────────────────────

class MultimodalVisionProxy:
    """Multimodal vision reasoning proxy converting phone camera views into HUD overlays."""

    def __init__(self, custom_vision_fn: Optional[Callable[[bytes, str], str]] = None):
        self.custom_vision_fn = custom_vision_fn

    def analyze_frame(self, frame_bytes: bytes, prompt: str = "") -> VisionDetection:
        """Analyzes frame and emits structured detection with 304x256 bounding box."""
        prompt_lower = prompt.lower()
        if "disjoncteur" in prompt_lower or "panneau" in prompt_lower or "tableau" in prompt_lower:
            return VisionDetection(
                target_label="DISJONCTEUR #4 (CHAUFFE-EAU)",
                confidence_pct=96,
                bounding_box=(60, 60, 244, 150),
                diagnostic="POSITION BASSE : DECLENCHEMENT THERMIQUE",
                action_hint="Verifiez la resistance avant reenclenchement"
            )
        elif "erreur" in prompt_lower or "code" in prompt_lower or "lave" in prompt_lower:
            return VisionDetection(
                target_label="LAVE-LINGE BOSCH SERIE 6",
                confidence_pct=98,
                bounding_box=(40, 50, 264, 140),
                diagnostic="CODE ERREUR E18 : FILTRE POMPE BLOQUE",
                action_hint="Devissez le filtre de vidange en bas a droite"
            )
        elif "aliment" in prompt_lower or "ingredient" in prompt_lower or "nutri" in prompt_lower:
            return VisionDetection(
                target_label="BARRE CEREALES CHOCOLAT",
                confidence_pct=94,
                bounding_box=(50, 55, 254, 145),
                diagnostic="ALLERGENES : ARACHIDES, SOJA, GLUTEN",
                action_hint="Nutri-Score D | Sucres: 28g / 100g"
            )
        
        # Default smart detection
        if self.custom_vision_fn:
            res_str = self.custom_vision_fn(frame_bytes, prompt)
            return VisionDetection(
                target_label="OBJET RECONNU",
                confidence_pct=92,
                bounding_box=(55, 60, 249, 145),
                diagnostic=res_str[:32],
                action_hint="Analyse vision validee par OpenBridge"
            )

        return VisionDetection(
            target_label="EQUIPEMENT DETECTE",
            confidence_pct=91,
            bounding_box=(50, 60, 254, 145),
            diagnostic="Tous parametres nominaux",
            action_hint="Geste wave pour fermer la vue"
        )


# ──────────────────────────────────────────────────────────────────────────────
# OpenBridge Telemetry Priority Fabric
# ──────────────────────────────────────────────────────────────────────────────

class OpenBridgeTelemetryFabric:
    """Manages prioritizing, debouncing, and pacing telemetry events to the ActiveLook display."""

    PRIO_CRITICAL_SAFETY = 1
    PRIO_ACTION_CONFIRMATION = 2
    PRIO_ASSISTANT_INTERACTION = 3
    PRIO_AMBIENT_TELEMETRY = 4

    def __init__(self, adapter: ActiveLookAdapter):
        self.adapter = adapter
        self.queue: List[TelemetryEvent] = []
        self.last_dispatch_ts: float = 0.0
        self.min_interval_s: float = 0.15  # Max ~6.6 updates/sec to prevent BLE MCU saturation

    def enqueue(self, event_type: str, payload: Dict[str, Any], priority: int = 4) -> str:
        """Enqueues an event according to strict priority order."""
        event_id = f"evt-{int(time.time() * 1000)}-{len(self.queue)}"
        evt = TelemetryEvent(
            event_id=event_id,
            event_type=event_type,
            priority=priority,
            payload=payload,
            timestamp=time.time()
        )
        # Higher priority (lower int) at front of queue
        inserted = False
        for idx, existing in enumerate(self.queue):
            if evt.priority < existing.priority:
                self.queue.insert(idx, evt)
                inserted = True
                break
        if not inserted:
            self.queue.append(evt)
        return event_id

    def pop_highest_priority(self) -> Optional[TelemetryEvent]:
        """Pops the most urgent event."""
        if not self.queue:
            return None
        return self.queue.pop(0)


# ──────────────────────────────────────────────────────────────────────────────
# Master EngoAIBridge: Neural Sensory Hub for OpenBridge
# ──────────────────────────────────────────────────────────────────────────────

class EngoAIBridge:
    """Orchestrates AI, Voice, Computer Vision, and Live APIs for ENGO Smart Glasses."""

    def __init__(
        self,
        adapter: ActiveLookAdapter,
        ai_inference_fn: Optional[Callable[[str], str]] = None,
        vision_inference_fn: Optional[Callable[[bytes, str], str]] = None,
        stt_fn: Optional[Callable[[bytes], str]] = None
    ):
        self.adapter = adapter
        self.phone_state = PhoneSensoryState()
        self.ai_inference_fn = ai_inference_fn or self._default_mock_llm
        self.vision_inference_fn = vision_inference_fn or self._default_mock_vision
        self.stt_fn = stt_fn or (lambda b: "Bonjour, quel est le statut de l'aspirateur ?")
        
        # Operational sub-engines
        self.audio_proxy = AudioStreamingProxy()
        self.stt_runner = StreamingSTTRunner(final_stt_fn=self.stt_fn)
        self.vision_proxy = MultimodalVisionProxy(custom_vision_fn=self.vision_inference_fn)
        self.telemetry_fabric = OpenBridgeTelemetryFabric(adapter=self.adapter)

        # Mode & telemetry navigation state
        self.current_mode = "IDLE"  # IDLE, LISTENING, STREAMING_AI, SUBTITLES, VISION, AMBIENT_MATRIX
        self.last_query = ""
        self.last_ai_response = ""
        self.active_page_idx = 0
        self.pages_catalog = ["ambient_matrix", "linky_rte_tempo", "weather_radar", "transit_live", "freebox_telemetry"]

    # ── Default Fallback Inferences (Hermetic & Deterministic) ──────────────────

    def _default_mock_llm(self, prompt: str) -> str:
        """Deterministic mock AI reasoning if no external model is bound."""
        prompt_lower = prompt.lower()
        if "aspirateur" in prompt_lower or "vacuum" in prompt_lower:
            return "Aspirateur Tuya: en charge au dock (Batterie 78%, Bac propre)."
        elif "météo" in prompt_lower or "weather" in prompt_lower or "pluie" in prompt_lower:
            return "Pluie imminente dans 12 min. Température 14°C, vent 22 km/h."
        elif "freebox" in prompt_lower or "wifi" in prompt_lower or "débit" in prompt_lower:
            return "Freebox Pop: Débit 940 Mbps, 12 appareils connectés, ping 8ms."
        elif "edf" in prompt_lower or "linky" in prompt_lower or "électricité" in prompt_lower:
            return "Linky: 1.4 kW en cours. Heures Creuses à 22h00. Demain: BLANC."
        elif "qui es-tu" in prompt_lower or "who are you" in prompt_lower:
            return "OpenBridge Neural HUD. L'IA connectée à vos appareils et vos yeux."
        return f"AI Synthèse: {prompt[:30]} validé. Tous systèmes nominaux."

    def _default_mock_vision(self, image_data: bytes, prompt: str) -> str:
        """Deterministic mock multimodal vision reasoning."""
        return "Disjoncteur #4 identifié : Position BASSE (Chauffe-eau déclenché)."

    # ── Master Gesture Dispatcher from Glasses ─────────────────────────────────

    def handle_glasses_interaction(self, trigger_type: str) -> Dict[str, Any]:
        """Handles physical sensor inputs detected by the glasses.
        - 'wave': Single front optical IR swipe
        - 'double_wave': Two rapid front optical IR swipes
        - 'wave_hold': Holding hand in front of IR sensor > 1.5s
        - 'tap': Single capacitive touch on temple
        - 'double_tap': Two rapid temple taps
        - 'triple_tap': Three rapid temple taps
        """
        if trigger_type == "wave":
            if self.current_mode == "LISTENING":
                # User waves to stop listening and trigger immediate AI answer
                return self.stop_listening_and_execute()
            elif self.current_mode in ("STREAMING_AI", "VISION", "SUBTITLES", "AMBIENT_MATRIX"):
                # Wave dismisses the active HUD overlay back to idle
                self.current_mode = "IDLE"
                self.adapter.send(cmd_clear())
                return {"status": "DISMISSED", "mode": "IDLE"}
            else:
                # Wave wakes the Phone Microphone for voice input!
                return self.start_voice_listening()

        elif trigger_type == "double_wave":
            # Cycle through ambient telemetry dashboard views!
            return self.cycle_telemetry_page()

        elif trigger_type == "wave_hold":
            # Emergency Mayday / PASS alert trigger or Night dimming
            return self.trigger_night_or_emergency_mode("emergency")

        elif trigger_type == "tap":
            # Quick glance at ambient matrix
            return self.push_ambient_matrix()

        elif trigger_type == "double_tap":
            # Temple double tap triggers phone camera capture for multimodal vision analysis!
            return self.trigger_sight_through_phone_scan()

        elif trigger_type == "triple_tap":
            # Triple tap triggers phone audio readback
            return self.trigger_audio_readback()

        return {"status": "IGNORED", "trigger": trigger_type}

    # ── Feature 1: Mind's Eye AI Voice Co-Pilot & Streaming Audio Pipeline ─────

    def start_voice_listening(self, mic_source: str = "smartphone_mic") -> Dict[str, Any]:
        """Feature 1: Arm microphone and show live listening state in HUD."""
        self.phone_state.mic_listening = True
        self.phone_state.active_mic_source = mic_source
        self.current_mode = "LISTENING"
        self.stt_runner.arm_session()

        cmds = bytearray()
        cmds += cmd_clear()
        if self.adapter.is_color:
            cmds += cmd_color(COLOR_CYAN)

        # Top line and banner
        cmds += cmd_line(0, 26, 303, 26)
        src_label = "PHONE MIC" if mic_source == "smartphone_mic" else mic_source.upper()
        cmds += cmd_text(4, 6, f"🎙 {src_label} LISTENING...", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 15)
        cmds += cmd_text(4, 45, "Parlez naturellement...", font=1, color_or_grey=COLOR_YELLOW if self.adapter.is_color else 14)
        cmds += cmd_text(4, 80, f"(Micro: {mic_source} connecte)", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 10)
        cmds += cmd_text(4, 225, ">> [WAVE] STOP & ENVOYER IA", font=0, color_or_grey=COLOR_GREEN if self.adapter.is_color else 12)

        self.adapter.send(bytes(cmds))
        return {"status": "LISTENING_STARTED", "input_source": mic_source}

    def feed_audio_chunk(self, pcm_bytes: bytes) -> Dict[str, Any]:
        """Ingests live audio chunk from phone or PC microphone, updates VAD and HUD partial transcript."""
        if not self.phone_state.mic_listening or self.current_mode != "LISTENING":
            return {"status": "IGNORED_NOT_LISTENING"}

        chunk = self.audio_proxy.process_pcm_frame(pcm_bytes)
        partial_text, is_final = self.stt_runner.process_stream_chunk(chunk)
        vu_pct = self.audio_proxy.db_to_vu_percent(chunk.db_level)

        # Update HUD live speech ticker with partial transcription
        self.stream_speech_ticker(partial_transcript=partial_text, vu_level_pct=vu_pct)

        if is_final:
            return self.stop_listening_and_execute(simulated_audio_bytes=pcm_bytes)

        return {
            "status": "STREAMING_CHUNK_PROCESSED",
            "is_speech": chunk.is_speech,
            "db_level": chunk.db_level,
            "vu_pct": vu_pct,
            "partial_transcript": partial_text
        }

    def stream_speech_ticker(
        self,
        partial_transcript: str,
        vu_level_pct: int = 65,
        latency_ms: int = 110
    ) -> bool:
        """Draws streaming live transcript ticker and dynamic audio VU-meter."""
        return self.adapter.push_neural_voice_assistant_hud(
            state_str="ECOUTE ACTIVE",
            partial_transcript=partial_transcript,
            mic_source=self.phone_state.active_mic_source.upper(),
            vu_level_pct=vu_level_pct,
            latency_ms=latency_ms,
            is_speaking=True
        )

    def stop_listening_and_execute(self, simulated_audio_bytes: Optional[bytes] = None) -> Dict[str, Any]:
        """Stops listening, transcribes audio, prompts AI, and streams response to HUD."""
        self.phone_state.mic_listening = False

        # 1. Transcribe audio via STT
        transcript = self.stt_fn(simulated_audio_bytes or b"mock_audio")
        self.last_query = transcript

        # 2. Query AI model
        ai_reply = self.ai_inference_fn(transcript)
        self.last_ai_response = ai_reply

        # 3. Stream concise response to HUD
        self.stream_ai_response(title="CO-PILOT IA", answer=ai_reply, query=transcript)
        self.current_mode = "STREAMING_AI"
        return {"status": "AI_ANSWERED", "query": transcript, "answer": ai_reply}

    def stream_ai_response(self, title: str, answer: str, query: str = "", model_tag: str = "GEMINI / LLM") -> bool:
        """Renders an AI answer cleanly formatted for 304x256 MicroOLED."""
        cmds = bytearray()
        cmds += cmd_clear()

        # Banner with model identity - line separator
        if self.adapter.is_color:
            cmds += cmd_color(COLOR_GREEN)
        cmds += cmd_line(0, 26, 303, 26)
        hdr_text = f"✨ [{model_tag[:12]}] {title[:16]}"
        cmds += cmd_text(4, 6, hdr_text, font=0, color_or_grey=COLOR_GREEN if self.adapter.is_color else 15)

        # User Query reminder (sparse cyan line)
        if query:
            if self.adapter.is_color:
                cmds += cmd_color(COLOR_CYAN)
            cmds += cmd_text(4, 34, f"Q: {query[:30]}", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 8)

        # AI Answer (high contrast, formatted multi-line)
        if self.adapter.is_color:
            cmds += cmd_color(COLOR_YELLOW)

        # Wrap text in max 32 characters chunks
        words = answer.split()
        lines = []
        cur_line = ""
        for w in words:
            if len(cur_line) + len(w) + 1 <= 28:
                cur_line += (" " if cur_line else "") + w
            else:
                lines.append(cur_line)
                cur_line = w
                if len(lines) >= 4:
                    break
        if cur_line and len(lines) < 4:
            lines.append(cur_line)

        start_y = 56 if query else 40
        for i, line in enumerate(lines):
            cmds += cmd_text(4, start_y + i * 22, line, font=1, color_or_grey=15)

        # Footer
        if self.adapter.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 230, ">> [WAVE] FERMER L'IA", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 8)

        return self.adapter.send(bytes(cmds))

    # ── Feature 2: Sight-Through-Phone Camera AI Proxy ────────────────────────

    def trigger_sight_through_phone_scan(self, prompt: str = "Analyse ce que je regarde") -> Dict[str, Any]:
        """Feature 2: Uses phone camera as an optical proxy to provide visual multimodal AI in HUD."""
        self.current_mode = "VISION"

        # 1. Show scanning status in glasses
        cmds = bytearray()
        cmds += cmd_clear()
        if self.adapter.is_color:
            cmds += cmd_color(COLOR_AMBER)
        cmds += cmd_line(0, 26, 303, 26)
        cmds += cmd_text(4, 6, "📷 CAMERA TELEPHONE ACTIVE...", font=0, color_or_grey=COLOR_AMBER if self.adapter.is_color else 15)
        cmds += cmd_text(4, 50, "Capture de l'image via le smartphone", font=0, color_or_grey=14)
        cmds += cmd_text(4, 75, "Analyse multimodale en cours...", font=1, color_or_grey=COLOR_AMBER if self.adapter.is_color else 15)
        self.adapter.send(bytes(cmds))

        # 2. Simulate phone capturing image via ADB / Companion
        simulated_frame_bytes = b"mock_50mp_jpeg_stream"

        # 3. Analyze through Vision Model
        if self.vision_inference_fn:
            vision_result = self.vision_inference_fn(simulated_frame_bytes, prompt)
        else:
            detection = self.vision_proxy.analyze_frame(simulated_frame_bytes, prompt)
            vision_result = detection.diagnostic

        # 4. Project Vision Insights on HUD
        self.stream_vision_insight(
            title="ANALYSE VISUELLE",
            insight=vision_result,
            device_target="TABLEAU ÉLECTRIQUE"
        )
        return {
            "status": "VISION_COMPLETED",
            "result": vision_result
        }

    def stream_vision_insight(self, title: str, insight: str, device_target: str = "DETECTÉ") -> bool:
        """Projects computer vision diagnostics onto the MicroOLED screen."""
        cmds = bytearray()
        cmds += cmd_clear()

        # Amber/Red Banner - line separator
        if self.adapter.is_color:
            cmds += cmd_color(COLOR_AMBER)
        cmds += cmd_line(0, 26, 303, 26)
        cmds += cmd_text(4, 6, f"👁️ [{device_target[:14]}] {title[:16]}", font=0, color_or_grey=COLOR_AMBER if self.adapter.is_color else 15)

        # Insight body
        if self.adapter.is_color:
            cmds += cmd_color(COLOR_GREEN)
        cmds += cmd_text(4, 42, "DIAGNOSTIC VISION :", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 10)

        words = insight.split()
        lines = []
        cur_line = ""
        for w in words:
            if len(cur_line) + len(w) + 1 <= 28:
                cur_line += (" " if cur_line else "") + w
            else:
                lines.append(cur_line)
                cur_line = w
                if len(lines) >= 3:
                    break
        if cur_line and len(lines) < 3:
            lines.append(cur_line)

        for i, line in enumerate(lines):
            cmds += cmd_text(4, 64 + i * 22, line, font=1, color_or_grey=15)

        # Footer
        cmds += cmd_text(4, 230, ">> [WAVE] FERMER VISION", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 8)
        return self.adapter.send(bytes(cmds))

    # ── Feature 3: The Silent Interpreter (Live Translation Subtitles) ─────────

    def stream_live_translation(self, foreign_speaker: str, source_lang: str, translated_text: str) -> bool:
        """Feature 3: Streams translated foreign speech into French in real-time."""
        self.current_mode = "SUBTITLES"
        cmds = bytearray()

        # Dedicated lower third box (y: 160 to 255)
        if self.adapter.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_line(0, 160, 303, 160)
        cmds += cmd_rect(0, 160, 303, 255)

        # Language tag (e.g. "[EN -> FR] TRADUCTION :")
        tag = f"[{source_lang.upper()} ➔ FR] {foreign_speaker.upper()[:12]}:"
        cmds += cmd_text(6, 168, tag, font=0, color_or_grey=COLOR_YELLOW if self.adapter.is_color else 15)

        # Translated text
        clean = translated_text.strip()
        line1 = clean[:32]
        line2 = clean[32:64]
        cmds += cmd_text(6, 190, line1, font=0, color_or_grey=15)
        if line2:
            cmds += cmd_text(6, 210, line2, font=0, color_or_grey=15)

        cmds += cmd_text(6, 236, ">> [WAVE] FERMER SOUS-TITRES", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 8)
        return self.adapter.send(bytes(cmds))

    # ── Feature 4: Live Dynamic API HUD Injector & Ambient Matrix ──────────────

    def push_ambient_matrix(
        self,
        linky_watts: int = 1850,
        tempo_tomorrow: str = "BLANC",
        rain_min: int = 12,
        temp_c: int = 15,
        transit_line: str = "M14",
        transit_eta_min: int = 3,
        wan_mbps: int = 940,
        ping_ms: int = 7
    ) -> Dict[str, Any]:
        """Projects the 4-quadrant ambient IoT and living infrastructure matrix."""
        self.current_mode = "AMBIENT_MATRIX"
        ok = self.adapter.push_ambient_iot_matrix(
            linky_watts=linky_watts,
            tempo_tomorrow=tempo_tomorrow,
            rain_min=rain_min,
            temp_c=temp_c,
            transit_line=transit_line,
            transit_eta_min=transit_eta_min,
            wan_mbps=wan_mbps,
            ping_ms=ping_ms
        )
        return {"status": "AMBIENT_MATRIX_RENDERED", "success": ok}

    def cycle_telemetry_page(self) -> Dict[str, Any]:
        """Cycles to the next telemetry page via double wave gesture."""
        self.active_page_idx = (self.active_page_idx + 1) % len(self.pages_catalog)
        page_name = self.pages_catalog[self.active_page_idx]

        if page_name == "ambient_matrix":
            res = self.push_ambient_matrix()
            res["page"] = page_name
            return res
        elif page_name == "linky_rte_tempo":
            ok = self.push_api_glance("linky_rte_tempo", {"tempo_today": "BLEU", "tempo_tomorrow": "BLANC", "instant_watts": 1950})
            return {"status": "PAGE_RENDERED", "page": page_name, "success": ok}
        elif page_name == "weather_radar":
            ok = self.push_api_glance("weather_radar", {"rain_in_minutes": 15, "temp_c": 16, "wind_kmh": 20})
            return {"status": "PAGE_RENDERED", "page": page_name, "success": ok}
        elif page_name == "transit_live":
            ok = self.push_api_glance("transit_live", {"line": "M14", "destination": "Chatelet", "eta_minutes": 2})
            return {"status": "PAGE_RENDERED", "page": page_name, "success": ok}
        elif page_name == "freebox_telemetry":
            ok = self.stream_ai_response("FREEBOX STATUT", "Fibre 940 Mbps, 14 appareils, ping 6ms.")
            return {"status": "PAGE_RENDERED", "page": page_name, "success": ok}

        return {"status": "PAGE_CYCLE_COMPLETED", "page_idx": self.active_page_idx}

    def push_api_glance(self, api_type: str, data: Dict[str, Any]) -> bool:
        """Feature 4: Formats live real-world APIs directly onto the HUD."""
        cmds = bytearray()
        cmds += cmd_clear()

        if api_type == "weather_radar":
            rain_min = data.get("rain_in_minutes", 15)
            temp_c = data.get("temp_c", 14)
            wind_kmh = data.get("wind_kmh", 25)

            if self.adapter.is_color:
                cmds += cmd_color(COLOR_AMBER if rain_min <= 15 else COLOR_CYAN)
            cmds += cmd_line(0, 26, 303, 26)
            cmds += cmd_text(4, 6, "🌧️ METEO : RADAR PRECIPITATIONS", font=0, color_or_grey=COLOR_AMBER if rain_min <= 15 and self.adapter.is_color else 15)

            cmds += cmd_text(4, 45, f"PLUIE DANS : {rain_min} MINUTES", font=1, color_or_grey=COLOR_RED if rain_min <= 10 else COLOR_AMBER if self.adapter.is_color else 15)
            cmds += cmd_text(4, 75, f"Temp: {temp_c}°C | Vent: {wind_kmh} km/h", font=0, color_or_grey=14)
            cmds += cmd_gauge(0, max(0, min(100, 100 - rain_min * 2)))

        elif api_type == "linky_rte_tempo":
            color_today = data.get("tempo_today", "BLEU")
            color_tomorrow = data.get("tempo_tomorrow", "BLANC")
            instant_watts = data.get("instant_watts", 1850)

            tempo_col = COLOR_RED if color_tomorrow == "ROUGE" else (COLOR_AMBER if color_tomorrow == "BLANC" else COLOR_GREEN)
            if self.adapter.is_color:
                cmds += cmd_color(tempo_col)
            cmds += cmd_line(0, 26, 303, 26)
            cmds += cmd_text(4, 6, f"⚡ RTE TEMPO : DEMAIN {color_tomorrow}", font=0, color_or_grey=tempo_col if self.adapter.is_color else 15)

            cmds += cmd_text(4, 45, f"Aujourd'hui : {color_today} (HC 22h-06h)", font=0, color_or_grey=14)
            cmds += cmd_text(4, 72, f"Conso live  : {instant_watts} W", font=1, color_or_grey=tempo_col if self.adapter.is_color else 15)
            cmds += cmd_gauge(0, min(100, int(instant_watts / 90.0)))

        elif api_type == "transit_live":
            line = data.get("line", "M1")
            dest = data.get("destination", "La Defense")
            eta_m = data.get("eta_minutes", 3)

            if self.adapter.is_color:
                cmds += cmd_color(COLOR_CYAN)
            cmds += cmd_line(0, 26, 303, 26)
            cmds += cmd_text(4, 6, f"🚇 TRANSIT EN DIRECT : {line}", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 15)

            cmds += cmd_text(4, 45, f"Direction : {dest[:22]}", font=0, color_or_grey=14)
            cmds += cmd_text(4, 72, f"PROCHAIN : {eta_m} MIN ⬆", font=2, color_or_grey=COLOR_GREEN if self.adapter.is_color else 15)

        cmds += cmd_text(4, 230, ">> [WAVE] RETOUR AMBIANT", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 8)
        return self.adapter.send(bytes(cmds))

    # ── Advanced Gestures & Accessibility ─────────────────────────────────────

    def trigger_night_or_emergency_mode(self, action: str = "emergency") -> Dict[str, Any]:
        """Wave-hold gesture handler: triggers emergency strobe or night dimming."""
        cmds = bytearray()
        cmds += cmd_clear()

        if action == "emergency":
            if self.adapter.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rect(0, 0, 303, 255)
            cmds += cmd_text(10, 30, "🚨 ALERTE MAYDAY DECLENCHEE", font=1, color_or_grey=COLOR_RED if self.adapter.is_color else 15)
            cmds += cmd_text(10, 70, "Signalement GPS transmis au telephone", font=0, color_or_grey=14)
            cmds += cmd_text(10, 100, "Position : 48.8566 N, 2.3522 E", font=0, color_or_grey=12)
            cmds += cmd_text(10, 220, ">> [WAVE] ANNULER L'ALERTE", font=0, color_or_grey=COLOR_GREEN if self.adapter.is_color else 10)
            self.adapter.send(bytes(cmds))
            return {"status": "EMERGENCY_TRIGGERED", "action": action}
        else:
            # Dimming mode
            cmds += cmd_text(10, 110, "MODE NUIT ACTIVE (LUMA: 1)", font=1, color_or_grey=10)
            self.adapter.send(bytes(cmds))
            return {"status": "NIGHT_MODE_ACTIVE", "action": action}

    def trigger_audio_readback(self) -> Dict[str, Any]:
        """Triple tap handler: initiates text-to-speech audio readback through the smartphone."""
        content = self.last_ai_response or "Tous systèmes nominaux. Aucun avertissement en cours."
        return {
            "status": "AUDIO_READBACK_DISPATCHED",
            "device": "phone_speaker_or_earbuds",
            "content": content
        }

    def dispatch_telemetry_event(self, event_type: str, data: Dict[str, Any], priority: int = 4) -> bool:
        """Enqueues and processes OpenBridge telemetry events via the priority fabric."""
        evt_id = self.telemetry_fabric.enqueue(event_type, data, priority)
        evt = self.telemetry_fabric.pop_highest_priority()
        if not evt:
            return False

        if evt.priority == OpenBridgeTelemetryFabric.PRIO_CRITICAL_SAFETY:
            # Immediate override
            cmds = bytearray()
            cmds += cmd_clear()
            if self.adapter.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_text(4, 4, f"⚠️ CRITICAL : {evt.event_type.upper()}", font=1, color_or_grey=COLOR_RED if self.adapter.is_color else 15)
            cmds += cmd_text(4, 40, str(evt.payload.get("message", "Securite compromise"))[:32], font=0, color_or_grey=15)
            return self.adapter.send(bytes(cmds))
        elif evt.event_type == "linky_rte_tempo":
            return self.push_api_glance("linky_rte_tempo", evt.payload)
        elif evt.event_type == "weather_radar":
            return self.push_api_glance("weather_radar", evt.payload)
        elif evt.event_type == "transit_live":
            return self.push_api_glance("transit_live", evt.payload)
        return True
