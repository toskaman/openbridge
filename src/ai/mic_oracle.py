"""Universal Microphone Connector for OpenBridge VoiceAI Oracle.

Connects ANY microphone-capable device (PC built-in mic, USB headset, Bluetooth
hands-free mic, pipe/FIFO audio, or remote HTTP device) to the Oracle AI + ENGO 3 HUD.

Features:
- Zero-dependency pure-Python energy VAD (Voice Activity Detection) on 16 kHz PCM16 mono.
- Fast local STT (uses faster-whisper if installed, else src.ai.stt_local mms-1b-all).
- Direct in-process Oracle execution or HTTP dispatch to POST /api/v2/voice/oracle.
- Optional live microphone capture via `sounddevice` (when installed) or stdin text mode.
"""
from __future__ import annotations

import base64
import json
import math
import queue
import struct
import threading
import time
import urllib.request
from typing import Callable, Optional

from src.ai import oracle as Oracle

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)   # 480 samples = 960 bytes PCM16


def compute_rms_db(pcm16_frame: bytes) -> float:
    """Return RMS energy in dBFS (-96.0 to 0.0) for a PCM16 mono buffer."""
    n = len(pcm16_frame) // 2
    if n <= 0:
        return -96.0
    samples = struct.unpack(f'<{n}h', pcm16_frame[: n * 2])
    sq = sum(s * s for s in samples)
    rms = math.sqrt(sq / n)
    if rms < 1.0:
        return -96.0
    return 20.0 * math.log10(rms / 32768.0)


class VadRecorder:
    """Lightweight energy VAD segmenter for 16 kHz PCM16 mono frames (30 ms each).

    Segments speech utterances cleanly:
      - Pre-roll buffer (4 frames = 120 ms) so initial consonants are never clipped.
      - Triggers speech start after 2 consecutive active frames above threshold_db.
      - Ends utterance after silence_ms (default 650 ms) of silence, or max_ms (8000 ms).
    """

    def __init__(
        self,
        threshold_db: float = -38.0,
        silence_ms: int = 650,
        max_ms: int = 8000,
        pre_roll_frames: int = 4,
    ):
        self.threshold_db = threshold_db
        self.silence_limit = max(1, silence_ms // FRAME_MS)
        self.max_frames = max(10, max_ms // FRAME_MS)
        self.pre_roll_frames = pre_roll_frames
        self._preroll: list[bytes] = []
        self._buf: list[bytes] = []
        self._active_streak = 0
        self._silence_streak = 0
        self._speaking = False

    def feed(self, pcm16_frame: bytes) -> Optional[bytes]:
        """Feed one PCM16 chunk. Returns complete PCM16 utterance bytes when finished, else None."""
        db = compute_rms_db(pcm16_frame)
        loud = db >= self.threshold_db

        if not self._speaking:
            self._preroll.append(pcm16_frame)
            if len(self._preroll) > self.pre_roll_frames:
                self._preroll.pop(0)
            if loud:
                self._active_streak += 1
                if self._active_streak >= 2:
                    self._speaking = True
                    self._buf = list(self._preroll)
                    self._preroll.clear()
                    self._silence_streak = 0
            else:
                self._active_streak = 0
            return None

        self._buf.append(pcm16_frame)
        if loud:
            self._silence_streak = 0
        else:
            self._silence_streak += 1

        if self._silence_streak >= self.silence_limit or len(self._buf) >= self.max_frames:
            utterance = b''.join(self._buf)
            self._reset()
            return utterance
        return None

    def flush(self) -> Optional[bytes]:
        """Force-emit any active utterance buffer."""
        if not self._speaking or not self._buf:
            self._reset()
            return None
        utterance = b''.join(self._buf)
        self._reset()
        return utterance

    def _reset(self) -> None:
        self._buf.clear()
        self._preroll.clear()
        self._active_streak = 0
        self._silence_streak = 0
        self._speaking = False


def transcribe_fast(pcm16: bytes, language: str = 'fr') -> str:
    """Transcribe PCM16 16 kHz mono audio using fastest available local STT."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
        import numpy as np
        model = getattr(transcribe_fast, '_fw_model', None)
        if model is None:
            model = WhisperModel('tiny', device='auto', compute_type='int8')
            setattr(transcribe_fast, '_fw_model', model)
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = model.transcribe(audio, language=language, beam_size=1, vad_filter=False)
        return ' '.join(s.text.strip() for s in segments).strip()
    except ImportError:
        pass

    from src.ai import stt_local
    if not stt_local.available():
        raise RuntimeError('No local STT engine available (install faster-whisper or mms-1b-all)')
    return str(stt_local.transcribe_pcm(pcm16, language).get('transcript', '')).strip()


def send_to_oracle(
    transcript: Optional[str] = None,
    audio_pcm16: Optional[bytes] = None,
    mic_source: str = 'pc_mic',
    language: str = 'fr',
    partial: bool = False,
    server=None,
    server_url: Optional[str] = None,
    timeout: float = 8.0,
) -> dict:
    """Dispatch text or PCM16 audio from any mic device to Oracle + ENGO 3 HUD."""
    if server_url:
        payload: dict = {'language': language, 'mic_source': mic_source}
        if partial:
            payload['partial'] = True
        if transcript is not None:
            payload['transcript'] = transcript
        elif audio_pcm16 is not None:
            payload['audio_b64'] = base64.b64encode(audio_pcm16).decode('ascii')
        else:
            raise ValueError('transcript or audio_pcm16 required')
        url = server_url.rstrip('/') + '/api/v2/voice/oracle'
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    if transcript is None:
        if audio_pcm16 is None:
            raise ValueError('transcript or audio_pcm16 required')
        transcript = transcribe_fast(audio_pcm16, language=language)

    if not transcript.strip():
        return {'query_class': 'GENERAL', 'answer': '', 'latency_ms': 0,
                'source': 'empty', 'transcript': '', 'mic_source': mic_source, 'hud_pushed': False}

    if partial:
        Oracle.prefetch_web(transcript)
        pushed = Oracle.push_oracle_to_hud(
            server, {'transcript': transcript}, mic_source=mic_source, partial=True
        )
        return {'status': 'listening', 'transcript': transcript, 'mic_source': mic_source, 'hud_pushed': pushed}

    ans = Oracle.oracle_answer(transcript, timeout=timeout)
    ans['mic_source'] = mic_source
    ans['hud_pushed'] = Oracle.push_oracle_to_hud(server, ans, mic_source=mic_source, partial=False)
    return ans


def _handle_utterance(utt, mic_source, language, server, server_url, on_answer, on_error):
    """Transcribe + Oracle + HUD for one utterance. Runs on the worker thread.

    Returns the result dict, or None when it failed (reported via on_error).
    """
    try:
        res = send_to_oracle(
            audio_pcm16=utt,
            mic_source=mic_source,
            language=language,
            server=server,
            server_url=server_url,
        )
    except Exception as e:
        if on_error is not None:
            on_error(e)
        return None
    try:
        if on_answer and res.get('answer'):
            on_answer(res)
    except Exception as e:
        if on_error is not None:
            on_error(e)
    return res


def run_mic_loop(
    mic_source: str = 'pc_mic',
    language: str = 'fr',
    server=None,
    server_url: Optional[str] = None,
    threshold_db: float = -38.0,
    on_answer: Optional[Callable[[dict], None]] = None,
    device=None,
    on_error: Optional[Callable[[BaseException], None]] = None,
    queue_size: int = 8,
) -> None:
    """Continuous listening loop for PC / USB / Bluetooth mics (requires `sounddevice`).

    The audio callback only segments speech and queues utterances; a worker
    thread does the blocking STT + Oracle + HUD work, so transcription never
    stalls the input stream. Errors go to on_error (utterances dropped while
    the worker is overloaded are reported the same way).
    """
    import sounddevice as sd  # type: ignore

    Oracle.warmup()
    vad = VadRecorder(threshold_db=threshold_db)
    work: queue.Queue = queue.Queue(maxsize=max(1, queue_size))
    stop = threading.Event()

    def _worker():
        while not stop.is_set():
            try:
                utt = work.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                _handle_utterance(utt, mic_source, language, server, server_url,
                                  on_answer, on_error)
            finally:
                work.task_done()

    threading.Thread(target=_worker, name='mic-oracle-worker', daemon=True).start()

    def _callback(indata, frames, time_info, status):
        utt = vad.feed(bytes(indata))
        if utt is None:
            return
        try:
            work.put_nowait(utt)
        except queue.Full:
            if on_error is not None:
                on_error(RuntimeError('utterance dropped: worker overloaded'))

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            dtype='int16',
            channels=1,
            device=device,
            callback=_callback,
        ):
            while True:
                time.sleep(0.25)
    finally:
        stop.set()
