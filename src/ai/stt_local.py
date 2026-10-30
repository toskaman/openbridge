"""Local Meta STT (facebook/mms-1b-all) for push-to-talk clips. No network, no spend.

Input is the same short PCM16 mono 16 kHz clip the cloud Muse Voice path takes;
output is the same transcript dict shape with backend='local-mms'.

The multi-GB model never loads in the control server process: transcription runs in
a supervised worker subprocess (spawned lazily, one request at a time). A worker
crash, timeout or OOM-kill is reported as unavailable voice processing; the
control server keeps running. A free-RAM admission check refuses to spawn when
loading the model would starve the host, and repeated worker failures cool down
instead of spawn-crashing in a loop.

Model lookup: $HF_HOME, else $OB_STT_HOME, else D:\\OBModels\\hf, else the
default HuggingFace cache. Set OB_STT_LOCAL=0 to disable the local path.

Residual: no VRAM admission check (a CUDA OOM now kills the worker only, which is
the containment); no idle TTL (a warm worker holds its RAM like the old in-process
backend did).
"""
import atexit
import multiprocessing
import os
import threading
import time
from pathlib import Path

from src.ai.voice_stt import MAX_SECONDS, RATE, STTBlocked

MODEL_ID = 'facebook/mms-1b-all'
LANG_CODE = {'fr': 'fra', 'en': 'eng'}
MIN_FREE_RAM_MB = 6 * 1024     # mms-1b-all weights (~4 GB fp32) + torch working set, with margin
WORKER_TIMEOUT_S = 300         # cold multi-GB load + 15 s of inference, worst case
WORKER_MAX_FAILURES = 3        # consecutive worker failures before a cooldown (no spawn-crash loop)
WORKER_COOLDOWN_S = 60

_lock = threading.Lock()
_worker = None                 # live _Worker, or None (lazy spawn, respawn after death)
_failures = []                 # monotonic times of consecutive worker failures (reset by any success)


def _candidate_homes():
    homes = []
    for env in ('HF_HOME', 'OB_STT_HOME'):
        v = os.environ.get(env)
        if v:
            homes.append(Path(v))
    homes.append(Path(r'D:\OBModels\hf'))
    homes.append(Path.home() / '.cache' / 'huggingface' / 'hub')
    return homes


_home_override = None  # tests only


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


def _free_ram_mb():
    """Free host RAM in MiB, or None when it cannot be determined (admission then proceeds)."""
    try:
        if os.name == 'nt':
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('memory_load', ctypes.c_ulong),
                            ('total_phys', ctypes.c_ulonglong), ('avail_phys', ctypes.c_ulonglong),
                            ('total_page', ctypes.c_ulonglong), ('avail_page', ctypes.c_ulonglong),
                            ('total_virt', ctypes.c_ulonglong), ('avail_virt', ctypes.c_ulonglong),
                            ('avail_ext', ctypes.c_ulonglong)]

            st = _Status()
            st.length = ctypes.sizeof(_Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return st.avail_phys // (1024 * 1024)
            return None
        with open('/proc/meminfo', encoding='utf-8') as handle:
            for line in handle:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError):
        pass
    return None


def _load_backend(snapshot):
    """Worker-side only: load the model + one processor per language. Never runs in the server."""
    import torch
    from transformers import AutoProcessor, Wav2Vec2ForCTC
    model = Wav2Vec2ForCTC.from_pretrained(str(snapshot), target_lang=LANG_CODE['fr'], local_files_only=True)
    if torch.cuda.is_available():
        model = model.to('cuda')
    model.eval()
    # One processor per language: set_target_lang does not reload the decode vocab.
    processors = {lang: AutoProcessor.from_pretrained(str(snapshot), target_lang=code, local_files_only=True)
                  for lang, code in LANG_CODE.items()}
    return model, processors, 'fr'


def _run_inference(backend, language, pcm16):
    import torch
    model, processors, loaded = backend
    if loaded != language:
        model.load_adapter(LANG_CODE[language])
        backend = (model, processors, language)
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
    return backend, {'transcript': ' '.join(str(text).split())[:400], 'model': MODEL_ID,
                     'language': language, 'seconds': round(len(pcm16) / 2 / RATE, 1), 'backend': 'local-mms'}


def _worker_main(conn, snapshot):
    """Worker entry (top-level for spawn pickling): lazy-load once, serve transcriptions."""
    backend = None
    try:
        while True:
            try:
                language, pcm = conn.recv()
            except EOFError:
                return
            if backend is None:
                try:
                    backend = _load_backend(snapshot)
                except Exception as error:  # noqa: BLE001 - unloadable install: report once, exit, no retry loop
                    try:
                        conn.send(('fatal', f'local STT model failed to load ({type(error).__name__})'))
                    except (OSError, EOFError):
                        pass
                    return
            try:
                backend, result = _run_inference(backend, language, bytes(pcm))
            except STTBlocked as error:
                conn.send(('error', str(error)))
            except Exception as error:  # noqa: BLE001 - the worker must never die on a bad clip
                conn.send(('error', f'local STT failed ({type(error).__name__})'))
            else:
                try:
                    conn.send(('ok', result))
                except (OSError, EOFError):
                    return
    finally:
        conn.close()


_worker_target = _worker_main   # seam: tests inject crashing/sleeping stub targets
_ctx = multiprocessing.get_context('spawn')


class _WorkerGone(STTBlocked):
    """Transport/timeout/death/fatal: the worker must be discarded (and counts toward cooldown)."""


class _Worker:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.parent, child = _ctx.Pipe(duplex=True)
        self.proc = _ctx.Process(target=_worker_target, args=(child, str(snapshot)), daemon=True)
        self.proc.start()
        child.close()

    def alive(self):
        return self.proc.exitcode is None

    def transcribe(self, language, pcm):
        if not self.alive():
            raise _WorkerGone(f'local STT worker died (exit {self.proc.exitcode}); try again')
        try:
            self.parent.send((language, bytes(pcm)))
        except (OSError, EOFError):
            raise _WorkerGone('local STT worker unreachable; try again') from None
        if not self.parent.poll(WORKER_TIMEOUT_S):
            # The worker may still be busy: it is discarded (terminated) by the caller, never reused,
            # so a late reply can never be mistaken for the next request's answer.
            raise _WorkerGone('local STT timed out; try again')
        try:
            status, payload = self.parent.recv()
        except (OSError, EOFError):
            raise _WorkerGone('local STT worker failed mid-transcription; try again') from None
        if status == 'ok':
            return payload
        if status == 'fatal':    # worker-side load failure: the worker exits itself; never reuse it
            raise _WorkerGone(payload)
        raise STTBlocked(payload)

    def shutdown(self):
        try:
            self.parent.close()
        except (OSError, EOFError):
            pass
        self.proc.join(5)
        if self.proc.is_alive():
            self.proc.terminate()
            self.proc.join(5)
        if self.proc.is_alive():
            self.proc.kill()
            self.proc.join(5)


def shutdown():
    """Stop the worker if any (idempotent). Safe to call at server shutdown and in tests."""
    global _worker
    with _lock:
        worker, _worker = _worker, None
    if worker is not None:
        worker.shutdown()


atexit.register(shutdown)


def _cooling_down():
    now = time.monotonic()
    while _failures and now - _failures[0] > WORKER_COOLDOWN_S:
        _failures.pop(0)
    return len(_failures) >= WORKER_MAX_FAILURES


def transcribe_pcm(pcm16, language='fr'):
    """Transcribe raw PCM16 mono 16 kHz bytes in the supervised worker. Raises STTBlocked."""
    if not isinstance(pcm16, (bytes, bytearray)) or not pcm16 or len(pcm16) > MAX_SECONDS * RATE * 2 or len(pcm16) % 2:
        raise STTBlocked(f'push-to-talk clip must be 16 kHz PCM16 mono, at most {MAX_SECONDS} s')
    if language not in ('fr', 'en'):
        raise STTBlocked('language must be fr or en')
    snap = find_snapshot()
    if snap is None:
        raise STTBlocked('local STT model not installed')
    global _worker
    with _lock:
        if _cooling_down():
            raise STTBlocked('local STT worker keeps failing; try again later')
        worker = _worker
        if worker is not None and not worker.alive():
            worker.shutdown()
            worker = _worker = None
        if worker is None:
            free = _free_ram_mb()
            if free is not None and free < MIN_FREE_RAM_MB:
                raise STTBlocked(f'local STT needs {MIN_FREE_RAM_MB // 1024} GB free RAM '
                                  f'({free // 1024} GB available); close something and try again')
            worker = _worker = _Worker(snap)
        try:
            result = worker.transcribe(language, pcm16)
        except _WorkerGone:
            _failures.append(time.monotonic())
            worker.shutdown()        # never reuse a timed-out, dead or fatally failed worker
            if _worker is worker:
                _worker = None
            raise
        else:
            _failures.clear()
            return result
