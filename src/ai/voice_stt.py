"""Shared speech-to-text error type.

Transcription runs on this PC only (src/ai/stt_local.py). The paid hosted client
(Meta "Muse Voice Transcribe") was removed: no audio leaves the PC.
"""


class STTBlocked(ValueError):
    """Transcription refused or unavailable (model missing, worker failure, invalid clip)."""


MAX_SECONDS = 15   # longest push-to-talk clip accepted
RATE = 16000       # PCM16 mono sample rate
