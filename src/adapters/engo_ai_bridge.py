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
    cmd_rect,
    cmd_line,
    cmd_gauge,
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

def wrap_text_for_hud(text: str, max_chars: int = 28, max_lines: int = 4) -> List[str]:
    """Wraps text into lines not exceeding max_chars, cleanly splitting long words if needed."""
    if not text:
        return []
    words = text.split()
    lines: List[str] = []
    cur_line = ""

    for w in words:
        # If single word exceeds max_chars, split the word itself cleanly
        while len(w) > max_chars:
            if cur_line:
                lines.append(cur_line)
                cur_line = ""
                if len(lines) >= max_lines:
                    return lines[:max_lines]
            lines.append(w[:max_chars])
            w = w[max_chars:]
            if len(lines) >= max_lines:
                return lines[:max_lines]

        if not w:
            continue

        if not cur_line:
            cur_line = w
        elif len(cur_line) + len(w) + 1 <= max_chars:
            cur_line += " " + w
        else:
            lines.append(cur_line)
            cur_line = w
            if len(lines) >= max_lines:
                break

    if cur_line and len(lines) < max_lines:
        lines.append(cur_line)

    return lines[:max_lines]


class AudioStreamingProxy:
    """Buffers, normalizes, and analyzes incoming audio streams from Phone or PC microphones."""

    def __init__(
        self,
        sample_rate: int = 16000,
        vad_threshold_db: float = -38.0,
        bit_depth: int = 16,
        channels: int = 1
    ):
        self.sample_rate = sample_rate
        self.vad_threshold_db = vad_threshold_db
        self.bit_depth = bit_depth
        self.channels = channels
        self.noise_floor_db = -50.0
        self.consecutive_speech_frames = 0
        self.consecutive_silence_frames = 0

    def decode_pcm_samples(
        self,
        pcm_bytes: bytes,
        bit_depth: Optional[int] = None,
        channels: Optional[int] = None,
        is_big_endian: bool = False
    ) -> List[int]:
        """Decodes raw audio bytes into signed 16-bit equivalent mono sample values."""
        b_depth = bit_depth or self.bit_depth
        chans = channels or self.channels

        if not pcm_bytes:
            return []

        samples: List[int] = []

        if b_depth == 16:
            endian = ">" if is_big_endian else "<"
            sample_count = len(pcm_bytes) // 2
            if sample_count > 0:
                raw_samples = list(struct.unpack(f"{endian}{sample_count}h", pcm_bytes[:sample_count * 2]))
                if chans == 2 and len(raw_samples) >= 2:
                    # Downmix stereo to mono
                    samples = [(raw_samples[i] + raw_samples[i + 1]) // 2 for i in range(0, len(raw_samples) - 1, 2)]
                else:
                    samples = raw_samples

        elif b_depth == 8:
            # 8-bit unsigned PCM (128 = 0 center)
            raw_samples = [(int(b) - 128) * 256 for b in pcm_bytes]
            if chans == 2 and len(raw_samples) >= 2:
                samples = [(raw_samples[i] + raw_samples[i + 1]) // 2 for i in range(0, len(raw_samples) - 1, 2)]
            else:
                samples = raw_samples

        elif b_depth == 24:
            # 24-bit signed PCM (3 bytes per sample)
            raw_samples = []
            for i in range(0, len(pcm_bytes) - 2, 3):
                val = int.from_bytes(pcm_bytes[i:i + 3], byteorder="big" if is_big_endian else "little", signed=True)
                raw_samples.append(val >> 8)  # normalize to 16-bit range
            if chans == 2 and len(raw_samples) >= 2:
                samples = [(raw_samples[i] + raw_samples[i + 1]) // 2 for i in range(0, len(raw_samples) - 1, 2)]
            else:
                samples = raw_samples

        elif b_depth == 32:
            # 32-bit float or signed int PCM
            sample_count = len(pcm_bytes) // 4
            if sample_count > 0:
                endian = ">" if is_big_endian else "<"
                try:
                    # Attempt float32 decode first
                    flt_samples = struct.unpack(f"{endian}{sample_count}f", pcm_bytes[:sample_count * 4])
                    raw_samples = [max(-32768, min(32767, int(s * 32767.0))) for s in flt_samples]
                except Exception:
                    int_samples = struct.unpack(f"{endian}{sample_count}i", pcm_bytes[:sample_count * 4])
                    raw_samples = [s >> 16 for s in int_samples]
                if chans == 2 and len(raw_samples) >= 2:
                    samples = [(raw_samples[i] + raw_samples[i + 1]) // 2 for i in range(0, len(raw_samples) - 1, 2)]
                else:
                    samples = raw_samples

        return samples

    def process_pcm_frame(
        self,
        pcm_bytes: bytes,
        bit_depth: Optional[int] = None,
        channels: Optional[int] = None,
        is_big_endian: bool = False
    ) -> AudioChunk:
        """Processes audio frame with adaptive noise floor tracking, SNR estimation, and VAD."""
        if not pcm_bytes:
            return AudioChunk(b"", 0.0, -100.0, 0, self.sample_rate, False)

        samples = self.decode_pcm_samples(
            pcm_bytes,
            bit_depth=bit_depth,
            channels=channels,
            is_big_endian=is_big_endian
        )
        sample_count = len(samples)

        if sample_count == 0:
            return AudioChunk(pcm_bytes, 0.0, -100.0, 0, self.sample_rate, False)

        sum_sq = sum(s * s for s in samples)
        rms = math.sqrt(sum_sq / sample_count)
        # Decibel relative to full-scale (32767)
        db = 20 * math.log10(max(1.0, rms) / 32767.0)

        # Dynamic VAD: adapt noise floor during silence
        dynamic_threshold = max(self.vad_threshold_db, self.noise_floor_db + 8.0)
        is_frame_speech = db > dynamic_threshold

        if is_frame_speech:
            self.consecutive_speech_frames += 1
            self.consecutive_silence_frames = 0
        else:
            self.consecutive_silence_frames += 1
            # Slowly adapt noise floor with 5% learning rate
            self.noise_floor_db = 0.95 * self.noise_floor_db + 0.05 * db
            if self.consecutive_silence_frames > 4:
                self.consecutive_speech_frames = 0

        # Speech active if sustained speech frames or brief pause in ongoing speech
        is_speech = (self.consecutive_speech_frames >= 1 and is_frame_speech)

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
        self.final_stt_fn = final_stt_fn or (lambda b: "Turn on the office lights")
        self.partial_tokens: List[str] = []
        self.current_token_idx: int = 0
        self.is_final: bool = False

    def arm_session(self, target_sentence: Optional[str] = None):
        """Prepares a new utterance session."""
        sentence = target_sentence or "Turn off the living room and check the router"
        self.partial_tokens = sentence.split()
        self.current_token_idx = 0
        self.is_final = False

    def get_current_transcript(self) -> str:
        """Returns the accumulated partial transcript text so far."""
        if not self.partial_tokens or self.current_token_idx == 0:
            return ""
        return " ".join(self.partial_tokens[:min(self.current_token_idx, len(self.partial_tokens))])

    def process_stream_chunk(self, chunk: AudioChunk) -> Tuple[str, bool]:
        """Returns incremental partial transcript hypothesis or final transcript."""
        if not self.partial_tokens:
            self.arm_session()

        if chunk.is_speech and self.current_token_idx < len(self.partial_tokens):
            self.current_token_idx += 1
            partial_text = self.get_current_transcript()
            is_done = self.current_token_idx >= len(self.partial_tokens)
            self.is_final = is_done
            return partial_text, is_done

        # Silence or end of speech
        if self.current_token_idx >= len(self.partial_tokens):
            self.is_final = True
            return " ".join(self.partial_tokens), True

        # Silence before speech began or between utterances
        return self.get_current_transcript(), False


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
        if "disjoncteur" in prompt_lower or "panneau" in prompt_lower or "tableau" in prompt_lower or "electric" in prompt_lower:
            return VisionDetection(
                target_label="BREAKER #4 (WATER HEATER)",
                confidence_pct=96,
                bounding_box=(60, 60, 244, 150),
                diagnostic="POSITION DOWN : THERMAL TRIP",
                action_hint="Check the heating element before resetting"
            )
        elif "qr" in prompt_lower or "oracle" in prompt_lower or "receipt" in prompt_lower or "audit" in prompt_lower:
            return VisionDetection(
                target_label="ORACLE RECEIPT #4F9A",
                confidence_pct=99,
                bounding_box=(70, 70, 234, 170),
                diagnostic="PHYSICAL STATE VERIFIED : LOCKED",
                action_hint="In-situ proof saved to the evidence registry"
            )
        elif "erreur" in prompt_lower or "panne" in prompt_lower or "lave" in prompt_lower or "defect" in prompt_lower:
            return VisionDetection(
                target_label="BOSCH SERIES 6 WASHER",
                confidence_pct=98,
                bounding_box=(40, 50, 264, 140),
                diagnostic="ERROR E18 : PUMP FILTER BLOCKED",
                action_hint="Unscrew the drain filter, bottom right"
            )
        elif "aliment" in prompt_lower or "ingredient" in prompt_lower or "nutri" in prompt_lower or "allergen" in prompt_lower:
            return VisionDetection(
                target_label="CHOCOLATE CEREAL BAR",
                confidence_pct=94,
                bounding_box=(50, 55, 254, 145),
                diagnostic="ALLERGENS : PEANUTS, SOY, GLUTEN",
                action_hint="Nutri-Score D | Sugar: 28g / 100g"
            )
        elif "qr" in prompt_lower or "oracle" in prompt_lower or "receipt" in prompt_lower or "audit" in prompt_lower:
            return VisionDetection(
                target_label="ORACLE RECEIPT #4F9A",
                confidence_pct=99,
                bounding_box=(70, 70, 234, 170),
                diagnostic="PHYSICAL STATE VERIFIED : LOCKED",
                action_hint="In-situ proof saved to the evidence registry"
            )
        elif "danger" in prompt_lower or "collision" in prompt_lower or "vehicule" in prompt_lower or "angle" in prompt_lower:
            return VisionDetection(
                target_label="VEHICLE IN LEFT BLIND SPOT",
                confidence_pct=97,
                bounding_box=(30, 40, 180, 190),
                diagnostic="SPEED: 54 km/h | TTC: 1.2s",
                action_hint="Imminent alert : hold your line"
            )
        elif "somnolence" in prompt_lower or "yeux" in prompt_lower or "conducteur" in prompt_lower or "fatigue" in prompt_lower:
            return VisionDetection(
                target_label="DRIVER VIGILANCE",
                confidence_pct=95,
                bounding_box=(80, 60, 224, 160),
                diagnostic="PERCLOS: 19% | MICROSLEEP DETECTED",
                action_hint="Rest area advised in 3.8 km"
            )
        elif "sku" in prompt_lower or "colis" in prompt_lower or "entrepot" in prompt_lower or "barcode" in prompt_lower:
            return VisionDetection(
                target_label="PARCEL SKU-8842-M8",
                confidence_pct=98,
                bounding_box=(45, 50, 259, 155),
                diagnostic="AISLE 04 - BAY 12 | QTY: 12 PCS",
                action_hint="Scanned and confirmed for order picking"
            )
        elif "stud" in prompt_lower or "fil" in prompt_lower or "tension" in prompt_lower or "mur" in prompt_lower:
            return VisionDetection(
                target_label="MATERIAL & CABLE DETECTOR",
                confidence_pct=93,
                bounding_box=(65, 55, 239, 145),
                diagnostic="LIVE 230V CABLE AT 2.5 CM",
                action_hint="Do not drill in this area"
            )
        elif "obstacle" in prompt_lower or "trottoir" in prompt_lower or "marche" in prompt_lower or "echonav" in prompt_lower:
            return VisionDetection(
                target_label="OVERHEAD OBSTACLE DETECTED",
                confidence_pct=96,
                bounding_box=(50, 40, 254, 130),
                diagnostic="BRANCH AT HEAD HEIGHT (1.75M)",
                action_hint="Duck / step to the right"
            )
        
        # Default smart detection
        if self.custom_vision_fn:
            res_str = self.custom_vision_fn(frame_bytes, prompt)
            return VisionDetection(
                target_label="OBJECT RECOGNISED",
                confidence_pct=92,
                bounding_box=(55, 60, 249, 145),
                diagnostic=res_str[:32],
                action_hint="Vision analysis checked by OpenBridge"
            )

        return VisionDetection(
            target_label="EQUIPMENT DETECTED",
            confidence_pct=91,
            bounding_box=(50, 60, 254, 145),
            diagnostic="All parameters nominal",
            action_hint="Wave to close the view"
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
        self.stt_fn = stt_fn or (lambda b: "Hello, what is the vacuum status?")
        
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
            return "Tuya vacuum: charging on the dock (battery 78%, bin clean)."
        elif "météo" in prompt_lower or "weather" in prompt_lower or "pluie" in prompt_lower:
            return "Rain in 12 min. 14 C, wind 22 km/h."
        elif "freebox" in prompt_lower or "wifi" in prompt_lower or "débit" in prompt_lower:
            return "Freebox Pop: 940 Mbps, 12 devices online, ping 8 ms."
        elif "edf" in prompt_lower or "linky" in prompt_lower or "électricité" in prompt_lower:
            return "Smart meter: 1.4 kW now. Off-peak from 22:00. Tomorrow: WHITE day."
        elif "qui es-tu" in prompt_lower or "who are you" in prompt_lower:
            return "OpenBridge Neural HUD. AI linked to your devices and your eyes."
        return f"AI summary: {prompt[:30]} done. All systems nominal."

    def _default_mock_vision(self, image_data: bytes, prompt: str) -> str:
        """Deterministic mock multimodal vision reasoning."""
        return "Breaker #4 found: position DOWN (water heater tripped)."

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
            state_str="LISTENING",
            partial_transcript=partial_transcript,
            mic_source=self.phone_state.active_mic_source.upper(),
            vu_level_pct=vu_level_pct,
            latency_ms=latency_ms,
            is_speaking=True
        )

    def stop_listening_and_execute(
        self,
        simulated_audio_bytes: Optional[bytes] = None,
        query_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """Stops listening, transcribes audio, prompts AI, and streams response to HUD."""
        self.phone_state.mic_listening = False

        # 1. Determine transcript from streaming tokens or override
        if query_override:
            transcript = query_override
        elif self.stt_runner.current_token_idx > 0:
            transcript = self.stt_runner.get_current_transcript()
        else:
            transcript = self.stt_fn(simulated_audio_bytes or b"mock_audio")

        self.last_query = transcript

        # 2. Query AI model
        ai_reply = self.ai_inference_fn(transcript)
        self.last_ai_response = ai_reply

        # 3. Stream concise response to HUD
        self.stream_ai_response(title="CO-PILOT IA", answer=ai_reply, query=transcript)
        self.current_mode = "STREAMING_AI"
        return {"status": "AI_ANSWERED", "query": transcript, "answer": ai_reply}

    def stream_ai_response(self, title: str, answer: str, query: str = "", model_tag: str = "LLM") -> bool:
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

        lines = wrap_text_for_hud(answer, max_chars=28, max_lines=4)
        start_y = 56 if query else 40
        for i, line in enumerate(lines):
            cmds += cmd_text(4, start_y + i * 22, line, font=1, color_or_grey=15)

        # Footer
        if self.adapter.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 230, ">> [WAVE] CLOSE AI", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 8)

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
        cmds += cmd_text(4, 50, "Capturing the image with the phone", font=0, color_or_grey=14)
        cmds += cmd_text(4, 75, "Multimodal analysis in progress...", font=1, color_or_grey=COLOR_AMBER if self.adapter.is_color else 15)
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
            device_target="BREAKER PANEL"
        )
        return {
            "status": "VISION_COMPLETED",
            "result": vision_result
        }

    def stream_vision_insight(self, title: str, insight: str, device_target: str = "DETECTED") -> bool:
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

        lines = wrap_text_for_hud(insight, max_chars=28, max_lines=3)
        for i, line in enumerate(lines):
            cmds += cmd_text(4, 64 + i * 22, line, font=1, color_or_grey=15)

        # Footer
        cmds += cmd_text(4, 230, ">> [WAVE] CLOSE VISION", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 8)
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

        cmds += cmd_text(6, 236, ">> [WAVE] CLOSE SUBTITLES", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 8)
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
            ok = self.stream_ai_response("ROUTER STATUS", "Fibre 940 Mbps, 14 devices, ping 6 ms.")
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

            cmds += cmd_text(4, 45, f"RAIN IN : {rain_min} MINUTES", font=1, color_or_grey=COLOR_RED if rain_min <= 10 else COLOR_AMBER if self.adapter.is_color else 15)
            cmds += cmd_text(4, 75, f"Temp: {temp_c}°C | Wind: {wind_kmh} km/h", font=0, color_or_grey=14)
            cmds += cmd_gauge(0, max(0, min(100, 100 - rain_min * 2)))

        elif api_type == "linky_rte_tempo":
            color_today = data.get("tempo_today", "BLEU")
            color_tomorrow = data.get("tempo_tomorrow", "BLANC")
            instant_watts = data.get("instant_watts", 1850)

            tempo_col = COLOR_RED if color_tomorrow == "ROUGE" else (COLOR_AMBER if color_tomorrow == "BLANC" else COLOR_GREEN)
            if self.adapter.is_color:
                cmds += cmd_color(tempo_col)
            cmds += cmd_line(0, 26, 303, 26)
            cmds += cmd_text(4, 6, f"⚡ RTE TEMPO : TOMORROW {color_tomorrow}", font=0, color_or_grey=tempo_col if self.adapter.is_color else 15)

            cmds += cmd_text(4, 45, f"Aujourd'hui : {color_today} (HC 22h-06h)", font=0, color_or_grey=14)
            cmds += cmd_text(4, 72, f"Live draw   : {instant_watts} W", font=1, color_or_grey=tempo_col if self.adapter.is_color else 15)
            cmds += cmd_gauge(0, min(100, int(instant_watts / 90.0)))

        elif api_type == "transit_live":
            line = data.get("line", "M1")
            dest = data.get("destination", "La Defense")
            eta_m = data.get("eta_minutes", 3)

            if self.adapter.is_color:
                cmds += cmd_color(COLOR_CYAN)
            cmds += cmd_line(0, 26, 303, 26)
            cmds += cmd_text(4, 6, f"🚇 LIVE TRANSIT : {line}", font=0, color_or_grey=COLOR_CYAN if self.adapter.is_color else 15)

            cmds += cmd_text(4, 45, f"To : {dest[:22]}", font=0, color_or_grey=14)
            cmds += cmd_text(4, 72, f"NEXT : {eta_m} MIN ⬆", font=2, color_or_grey=COLOR_GREEN if self.adapter.is_color else 15)

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
            cmds += cmd_text(10, 30, "🚨 MAYDAY ALERT TRIGGERED", font=1, color_or_grey=COLOR_RED if self.adapter.is_color else 15)
            cmds += cmd_text(10, 70, "GPS position sent to the phone", font=0, color_or_grey=14)
            cmds += cmd_text(10, 100, "Position : 48.8566 N, 2.3522 E", font=0, color_or_grey=12)
            cmds += cmd_text(10, 220, ">> [WAVE] CANCEL THE ALERT", font=0, color_or_grey=COLOR_GREEN if self.adapter.is_color else 10)
            self.adapter.send(bytes(cmds))
            return {"status": "EMERGENCY_TRIGGERED", "action": action}
        else:
            # Dimming mode
            cmds += cmd_text(10, 110, "MODE NUIT ACTIVE (LUMA: 1)", font=1, color_or_grey=10)
            self.adapter.send(bytes(cmds))
            return {"status": "NIGHT_MODE_ACTIVE", "action": action}

    def trigger_audio_readback(self) -> Dict[str, Any]:
        """Triple tap handler: initiates text-to-speech audio readback through the smartphone."""
        content = self.last_ai_response or "All systems nominal. No active warnings."
        return {
            "status": "AUDIO_READBACK_DISPATCHED",
            "device": "phone_speaker_or_earbuds",
            "content": content
        }

    def dispatch_telemetry_event(self, event_type: str, data: Dict[str, Any], priority: int = 4) -> bool:
        """Enqueues and processes OpenBridge telemetry events via the priority fabric for all 38 features."""
        evt_id = self.telemetry_fabric.enqueue(event_type, data, priority)
        evt = self.telemetry_fabric.pop_highest_priority()
        if not evt:
            return False

        p = evt.payload
        e_type = evt.event_type

        # Critical Safety immediate override
        if evt.priority == OpenBridgeTelemetryFabric.PRIO_CRITICAL_SAFETY:
            cmds = bytearray()
            cmds += cmd_clear()
            if self.adapter.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_text(4, 4, f"⚠️ CRITICAL : {e_type.upper()}", font=1, color_or_grey=COLOR_RED if self.adapter.is_color else 15)
            cmds += cmd_text(4, 40, str(p.get("message", "Securite compromise"))[:32], font=0, color_or_grey=15)
            return self.adapter.send(bytes(cmds))

        # Core Killer Features (F01 - F38)
        if e_type == "spatial_radar":
            return self.adapter.push_spatial_radar(p.get("devices", []))
        elif e_type == "eyes_on_target":
            return self.adapter.push_eyes_on_target_receipt(
                target_name=p.get("target_name", "Device"),
                action=p.get("action", "Command"),
                oracle_verified=p.get("oracle_verified", True),
                latency_ms=p.get("latency_ms", 35),
                digest=p.get("digest", "#verified")
            )
        elif e_type == "two_phase_countdown":
            return self.adapter.push_two_phase_countdown(
                routine_name=p.get("routine_name", "Routine"),
                seconds_remaining=p.get("seconds_remaining", 3),
                max_seconds=p.get("max_seconds", 5)
            )
        elif e_type == "peripheral_telemetry":
            return self.adapter.push_peripheral_telemetry(
                grid_watts=p.get("grid_watts", 1850),
                wan_mbps=p.get("wan_mbps", 940),
                ping_ms=p.get("ping_ms", 8),
                alert=p.get("alert")
            )
        elif e_type == "workflow_prompter":
            return self.adapter.push_workflow_prompter(
                step_idx=p.get("step_idx", 1),
                total_steps=p.get("total_steps", 5),
                title=p.get("title", "Step"),
                instruction=p.get("instruction", "Instruction"),
                timer_s=p.get("timer_s", 60)
            )
        elif e_type == "doorbell_subtitles":
            return self.adapter.push_live_subtitles(
                speaker=p.get("speaker", "Interphone"),
                text=p.get("text", "Hello"),
                is_urgent=p.get("is_urgent", False)
            )
        elif e_type == "compass_wayfinder":
            return self.adapter.push_compass_wayfinder(
                heading_deg=p.get("heading_deg", 0),
                target_bearing_deg=p.get("target_bearing_deg", 45),
                target_dist_m=p.get("target_dist_m", 100.0),
                target_name=p.get("target_name", "TARGET")
            )
        elif e_type == "security_shield":
            return self.adapter.push_smart_home_security_alert(
                threat_type=p.get("threat_type", "Intrusion"),
                source_ip=p.get("source_ip", "0.0.0.0"),
                mac_vendor=p.get("mac_vendor", "Unknown"),
                target_service=p.get("target_service", "LAN")
            )
        elif e_type == "bio_pacer":
            return self.adapter.push_bio_adaptive_pacer(
                target_spm=p.get("target_spm", 180),
                current_spm=p.get("current_spm", 175),
                hr_bpm=p.get("hr_bpm", 155),
                hr_zone=p.get("hr_zone", 3),
                advice=p.get("advice", "CADENCE OPTIMALE")
            )
        elif e_type == "media_remote":
            return self.adapter.push_media_remote_hud(
                media_title=p.get("media_title", "Titre"),
                artist_or_source=p.get("artist_or_source", "Source"),
                volume_pct=p.get("volume_pct", 50),
                is_playing=p.get("is_playing", True),
                progress_s=p.get("progress_s", 0),
                total_s=p.get("total_s", 100)
            )
        elif e_type == "silent_morse":
            return self.adapter.push_silent_morse_input(
                buffer_str=p.get("buffer_str", ""),
                current_morse=p.get("current_morse", ""),
                suggestion=p.get("suggestion", "")
            )
        elif e_type == "speech_teleprompter":
            return self.adapter.push_speech_teleprompter(
                current_line=p.get("current_line", ""),
                next_line=p.get("next_line", ""),
                wpm=p.get("wpm", 130),
                is_rushing=p.get("is_rushing", False),
                elapsed_s=p.get("elapsed_s", 0),
                total_s=p.get("total_s", 120)
            )
        elif e_type == "spatial_energy_heatmap":
            return self.adapter.push_spatial_energy_heatmap(
                current_room=p.get("current_room", "Home"),
                room_watts=p.get("room_watts", 1200),
                total_watts=p.get("total_watts", 2500),
                vampire_devices=p.get("vampire_devices", [])
            )
        elif e_type == "arcade_runner":
            return self.adapter.push_arcade_game_frame(
                player_y=p.get("player_y", 160),
                obstacle_x=p.get("obstacle_x", 180),
                score=p.get("score", 0),
                game_over=p.get("game_over", False)
            )
        elif e_type == "collision_sentry":
            return self.adapter.push_collision_sentry(
                hazard_side=p.get("hazard_side", "left"),
                speed_kmh=p.get("speed_kmh", 50),
                dist_m=p.get("dist_m", 15.0),
                ttc_s=p.get("ttc_s", 1.2)
            )
        elif e_type == "executive_briefing":
            return self.adapter.push_executive_briefing_glance(
                contact_name=p.get("contact_name", "Contact"),
                role_title=p.get("role_title", "Role"),
                bullet_points=p.get("bullet_points", []),
                sentiment_hint=p.get("sentiment_hint", "NOMINAL")
            )
        elif e_type == "biofeedback_stress":
            return self.adapter.push_biofeedback_stress_guardian(
                stress_score=p.get("stress_score", 50),
                hrv_ms=p.get("hrv_ms", 45),
                breath_phase=p.get("breath_phase", "INSP"),
                phase_timer_s=p.get("phase_timer_s", 4)
            )
        elif e_type == "diy_ar_stud_level":
            return self.adapter.push_diy_ar_stud_level(
                pitch_deg=p.get("pitch_deg", 0.0),
                roll_deg=p.get("roll_deg", 0.0),
                is_level=p.get("is_level", True),
                detected_hazard=p.get("detected_hazard")
            )
        elif e_type == "first_responder_cpr":
            return self.adapter.push_first_responder_triage(
                mode=p.get("mode", "cpr"),
                bpm=p.get("bpm", 110),
                compression_count=p.get("compression_count", 30),
                ccf_pct=p.get("ccf_pct", 85),
                cycle_s=p.get("cycle_s", 30)
            )
        elif e_type == "directional_subtitles":
            return self.adapter.push_directional_subtitles(
                speaker_name=p.get("speaker_name", "Speaker"),
                direction=p.get("direction", "center"),
                text_line1=p.get("text_line1", ""),
                text_line2=p.get("text_line2", ""),
                is_translated=p.get("is_translated", False)
            )
        elif e_type == "uav_avionics":
            return self.adapter.push_uav_avionics_hud(
                pitch_deg=p.get("pitch_deg", 0.0),
                roll_deg=p.get("roll_deg", 0.0),
                heading_deg=p.get("heading_deg", 0),
                alt_agl_m=p.get("alt_agl_m", 50.0),
                speed_kmh=p.get("speed_kmh", 30.0),
                home_dist_m=p.get("home_dist_m", 150.0),
                home_bearing_rel_deg=p.get("home_bearing_rel_deg", 0.0),
                cell_voltage=p.get("cell_voltage", 3.85),
                lq_pct=p.get("lq_pct", 98)
            )
        elif e_type == "stealth_rf_sentry":
            return self.adapter.push_stealth_rf_sentry(
                threat_type=p.get("threat_type", "tracker"),
                target_id=p.get("target_id", "BLE Beacon"),
                rssi_dbm=p.get("rssi_dbm", -65),
                dist_m=p.get("dist_m", 3.0)
            )
        elif e_type == "thermal_arc_flash":
            return self.adapter.push_thermal_arc_flash_sentry(
                t_max_c=p.get("t_max_c", 65.0),
                t_ambient_c=p.get("t_ambient_c", 22.0),
                delta_t_c=p.get("delta_t_c", 43.0),
                reticle_xy=p.get("reticle_xy", (152, 115)),
                afb_dist_m=p.get("afb_dist_m", 1.2),
                is_violating_boundary=p.get("is_violating_boundary", False)
            )
        elif e_type == "allergen_nutrition":
            return self.adapter.push_allergen_nutrition_scanner(
                product_name=p.get("product_name", "Product"),
                detected_allergens=p.get("detected_allergens", []),
                carbs_g=p.get("carbs_g", 0.0),
                sugar_g=p.get("sugar_g", 0.0),
                sodium_mg=p.get("sodium_mg", 0.0),
                nutri_score=p.get("nutri_score", "B")
            )
        elif e_type == "tactical_marine":
            return self.adapter.push_tactical_marine_hud(
                awa_deg=p.get("awa_deg", 45.0),
                aws_knots=p.get("aws_knots", 12.0),
                sog_knots=p.get("sog_knots", 7.0),
                cog_deg=p.get("cog_deg", 180),
                depth_m=p.get("depth_m", 5.0),
                regatta_sec_left=p.get("regatta_sec_left", 180)
            )
        elif e_type == "multilingual_interpreter":
            return self.adapter.push_multilingual_interpreter(
                speaker_origin=p.get("speaker_origin", "Locuteur"),
                source_transcript=p.get("source_transcript", "..."),
                translated_text=p.get("translated_text", "..."),
                etiquette_tag=p.get("etiquette_tag", "[INFO]"),
                etiquette_tip=p.get("etiquette_tip", ""),
                target_country=p.get("target_country", "")
            )
        elif e_type == "driver_vigilance":
            return self.adapter.push_driver_vigilance_hud(
                perclos_pct=p.get("perclos_pct", 10.0),
                microsleep_detected=p.get("microsleep_detected", False),
                saccade_target=p.get("saccade_target", "AHEAD"),
                nearest_rest_km=p.get("nearest_rest_km", 10.0)
            )
        elif e_type == "warehouse_pick":
            return self.adapter.push_warehouse_pick(
                order_id=p.get("order_id", "00001"),
                progress_str=p.get("progress_str", "1/1"),
                aisle_bay_str=p.get("aisle_bay_str", "A01"),
                shelf_bin_str=p.get("shelf_bin_str", "B01"),
                quantity=p.get("quantity", 1),
                unit_str=p.get("unit_str", "PCS"),
                sku_code=p.get("sku_code", "SKU-001"),
                sku_desc=p.get("sku_desc", "Article"),
                scan_status=p.get("scan_status", "PENDING")
            )
        elif e_type == "avalanche_sar":
            return self.adapter.push_avalanche_sar_hud(
                phase=p.get("phase", "COARSE"),
                distance_m=p.get("distance_m", 25.0),
                tangent_angle_deg=p.get("tangent_angle_deg", 0.0),
                victims_count=p.get("victims_count", 1),
                turn_180=p.get("turn_180", False)
            )
        elif e_type == "circadian_chrono":
            return self.adapter.push_circadian_chrono_optimizer(
                current_lux=p.get("current_lux", 1000),
                medi_lux=p.get("medi_lux", 800),
                dose_lux_min=p.get("dose_lux_min", 100000),
                target_dose=p.get("target_dose", 250000),
                caffeine_active_mg=p.get("caffeine_active_mg", 0),
                cutoff_time_str=p.get("cutoff_time_str", "15:00"),
                sleep_clearance_hrs=p.get("sleep_clearance_hrs", 8.0),
                melatonin_warning=p.get("melatonin_warning", False)
            )
        elif e_type == "firefighter_mayday":
            return self.adapter.push_firefighter_mayday_hud(
                unit_id=p.get("unit_id", "RESCUE-1"),
                cylinder_bar=p.get("cylinder_bar", 200),
                ambient_temp_c=p.get("ambient_temp_c", 80),
                temp_rise_c_per_min=p.get("temp_rise_c_per_min", 10),
                exit_bearing_deg=p.get("exit_bearing_deg", 180),
                pass_alarm=p.get("pass_alarm", False)
            )
        elif e_type == "ballistic_drop":
            return self.adapter.push_ballistic_drop_compensator(
                range_m=p.get("range_m", 500.0),
                elevation_mrad=p.get("elevation_mrad", 3.2),
                windage_mrad=p.get("windage_mrad", 0.0),
                wind_speed_ms=p.get("wind_speed_ms", 2.0),
                wind_angle_deg=p.get("wind_angle_deg", 90),
                cant_deg=p.get("cant_deg", 0.0)
            )
        elif e_type == "surgical_vitals":
            return self.adapter.push_surgical_vitals_hud(
                patient_id=p.get("patient_id", "P-01"),
                spo2_pct=p.get("spo2_pct", 99),
                hr_bpm=p.get("hr_bpm", 70),
                map_mmhg=p.get("map_mmhg", 80),
                etco2_mmhg=p.get("etco2_mmhg", 35),
                implant_torque_ncm=p.get("implant_torque_ncm", 30.0)
            )
        elif e_type == "low_vision_echonav":
            return self.adapter.push_low_vision_echonav_hud(
                head_obstacle_dist_m=p.get("head_obstacle_dist_m", 2.0),
                head_obstacle_type=p.get("head_obstacle_type", "OBSTACLE"),
                curb_drop_dist_m=p.get("curb_drop_dist_m", 3.0),
                is_critical_duck=p.get("is_critical_duck", False)
            )
        elif e_type == "neural_voice_assistant":
            return self.adapter.push_neural_voice_assistant_hud(
                state_str=p.get("state_str", "LISTENING"),
                partial_transcript=p.get("partial_transcript", ""),
                mic_source=p.get("mic_source", "PHONE MIC"),
                vu_level_pct=p.get("vu_level_pct", 50),
                latency_ms=p.get("latency_ms", 110),
                is_speaking=p.get("is_speaking", True)
            )
        elif e_type == "multimodal_vision_hud":
            return self.adapter.push_multimodal_vision_hud(
                target_label=p.get("target_label", "TARGET"),
                confidence_pct=p.get("confidence_pct", 90),
                bounding_box=p.get("bounding_box", (50, 50, 250, 150)),
                diagnostic_summary=p.get("diagnostic_summary", "Diagnostic"),
                action_recommendation=p.get("action_recommendation", "Action"),
                source_device=p.get("source_device", "PHONE 50MP CAM")
            )
        elif e_type == "ambient_iot_matrix":
            return self.push_ambient_matrix(
                linky_watts=p.get("linky_watts", 1850),
                tempo_tomorrow=p.get("tempo_tomorrow", "BLANC"),
                rain_min=p.get("rain_min", 12),
                temp_c=p.get("temp_c", 15),
                transit_line=p.get("transit_line", "M14"),
                transit_eta_min=p.get("transit_eta_min", 3),
                wan_mbps=p.get("wan_mbps", 940),
                ping_ms=p.get("ping_ms", 7)
            )["success"]
        elif e_type == "neural_translation_stream":
            return self.adapter.push_neural_translation_stream(
                speaker_id=p.get("speaker_id", "LOCUTEUR"),
                source_lang=p.get("source_lang", "EN"),
                target_lang=p.get("target_lang", "FR"),
                live_text=p.get("live_text", ""),
                translated_text=p.get("translated_text", ""),
                azimuth_dir=p.get("azimuth_dir", "CENTRE 0°"),
                latency_ms=p.get("latency_ms", 120)
            )
        elif e_type == "oracle_answer":
            # VoiceAI Oracle: show Q&A answer card on ENGO 3
            return self.adapter.push_oracle_answer(
                query_class=p.get("query_class", "GENERAL"),
                transcript=p.get("transcript", ""),
                answer=p.get("answer", ""),
                source=p.get("source", "unavailable"),
                latency_ms=p.get("latency_ms", 0),
            )
        elif e_type == "linky_rte_tempo":
            return self.push_api_glance("linky_rte_tempo", p)
        elif e_type == "weather_radar":
            return self.push_api_glance("weather_radar", p)
        elif e_type == "transit_live":
            return self.push_api_glance("transit_live", p)

        return True
