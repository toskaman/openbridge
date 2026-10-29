"""Local Meta STT (facebook/mms-1b-all) for push-to-talk clips. No network, no spend.

Input is the same short PCM16 mono 16 kHz clip the cloud Muse Voice path takes;
output is the same transcript dict shape with backend='local-mms'. The model is
loaded lazily on first use and shared across calls (one language adapter at a
time, switched under a lock).

Model lookup: $HF_HOME, else $OB_STT_HOME, else D:\\OBModels\\hf, else the
default HuggingFace cache. Set OB_STT_LOCAL=0 to disable the local path.
"""
import os
import threading
from pathlib import Path

from src.ai.voice_stt import MAX_SECONDS, RATE, STTBlocked

MODEL_ID = 'facebook/mms-1b-all'
LANG_CODE = {'fr': 'fra', 'en': 'eng'}

_lock = threading.Lock()
_backend = None        # (model, {'fr': processor, 'en': processor}, loaded_lang)
_home_override = None  # tests only


def _candidate_homes():
    homes = []
    for env in ('HF_HOME', 'OB_STT_HOME'):
        v = os.environ.get(env)
        if v:
            homes.append(Path(v))
    homes.append(Path(r'D:\OBModels\hf'))
    homes.append(Path.home() / '.cache' / 'huggingface' / 'hub')
    return homes


def find_snapshot():
    """Return the local mms-1b-all snapshot dir, or None when not downloaded."""
    repo = 'models--facebook--mms-1b-all'
    best = None
    for home in _candidate_homes() if _home_override is None else [Path(_home_override)]:
        snaps = home / 'hub' / repo / 'snapshots'
        if not snaps.is_dir():
            continue
        for snap in snaps.iterdir():
            if (snap / 'config.json').is_file() and (
                    (snap / 'pytorch_model.bin').is_file() or (snap / 'model.safetensors').is_file()):
                if best is None or snap.stat().st_mtime > best.stat().st_mtime:
                    best = snap
    return best


def available():
    if os.environ.get('OB_STT_LOCAL') == '0':
        return False
    return find_snapshot() is not None


def _load():
    global _backend
    with _lock:
        if _backend is not None:
            return _backend
        snap = find_snapshot()
        if snap is None:
            raise STTBlocked('local STT model not installed')
        import torch
        from transformers import AutoProcessor, Wav2Vec2ForCTC
        cuda = torch.cuda.is_available()
        model = Wav2Vec2ForCTC.from_pretrained(
            str(snap), target_lang=LANG_CODE['fr'], local_files_only=True)
        if cuda:
            model = model.to('cuda')
        model.eval()
        # One processor per language: set_target_lang does not reload the decode vocab.
        processors = {lang: AutoProcessor.from_pretrained(str(snap), target_lang=code, local_files_only=True)
                      for lang, code in LANG_CODE.items()}
        _backend = (model, processors, 'fr')
        return _backend


def transcribe_pcm(pcm16, language='fr'):
    """Transcribe raw PCM16 mono 16 kHz bytes. Raises STTBlocked on bad audio."""
    if not isinstance(pcm16, (bytes, bytearray)) or not pcm16 or len(pcm16) > MAX_SECONDS * RATE * 2 or len(pcm16) % 2:
        raise STTBlocked(f'push-to-talk clip must be 16 kHz PCM16 mono, at most {MAX_SECONDS} s')
    if language not in ('fr', 'en'):
        raise STTBlocked('language must be fr or en')
    global _backend
    model, processors, loaded = _load()
    import torch
    with _lock:
        if loaded != language:
            model.load_adapter(LANG_CODE[language])
            _backend = (model, processors, language)
        processor = processors[language]
        samples = torch.frombuffer(bytearray(pcm16), dtype=torch.int16).to(torch.float32) / 32768.0
        device = next(model.parameters()).device
        inputs = processor(samples.tolist(), sampling_rate=RATE, return_tensors='pt')
        input_values = inputs.input_values.to(device)
        attention = inputs.get('attention_mask')
        if attention is not None:
            attention = attention.to(device)
        with torch.no_grad():
            logits = model(input_values, attention_mask=attention).logits
        ids = torch.argmax(logits, dim=-1)
        text = processor.batch_decode(ids)[0]
    return {'transcript': ' '.join(str(text).split())[:400], 'model': MODEL_ID,
            'language': language, 'seconds': round(len(pcm16) / 2 / RATE, 1), 'backend': 'local-mms'}
