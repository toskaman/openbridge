# Overnight N2/N3 — STT robustness + latency profile (2026-10-28, ~00:40 CEST)

Branch: `spark/overnight-reason`. Box: RTX 4060 Ti 16GB, Ollama llama3b :11437, Glimmer :11438 (OOM).
Live 18765 queried read-only for timings (no reload/restart). All numbers measured, n stated.

## N2a — MMS-1B STT matrix (local TTS corpus, 16 phrases FR+EN)

Corpus: espeak FR 8 + EN 8 (device-voice style commands). Conditions: clean / +white noise
SNR≈10dB / SNR≈0dB. STT: MMS-1B per-lang processors (post PR90 fix), CPU.

| condition | exact match | keyword recall |
|---|---|---|
| clean | 5/16 (31%) | ~66% |
| snr10 | — | 49% |
| snr0 | — | 26% |

Typical errors: `vacuum→vacum`, `living room→living-room`, `éteins→êteint`.
Corpus bias noted: espeak artifacts, not human voice. Owner human voice: 2/2 perfect
('test voix', 'allume la lampe du salon', 2026-10-27) — N=2, do not over-claim.

## N2b — STT→parse: wrong-skill rate on clean STT output (16/16)

Each clean transcript fed to `src/runtime/intent.py::parse_text` with matching lang.
Result: **16 ok, 0 wrong-skill**. Misspellings (`vacum`, `aspirateur` variants) resolve
via keyword path to the CORRECT skill (vacuum.start/vacuum.pause); all other errors
become honest `needs_clarification`, never a wrong skill. No fix needed; parser is
defensive-correct under STT noise.

## N3 — Latency profile (live 18765, local-only)

| op | cold | warm | n | notes |
|---|---|---|---|---|
| low parse FR resolved (llama3b) | 10.7–11.0s | 3.8s | 5 | ~7s = model load (keep_alive 30s) |
| medium parse FR (glimmer OOM) | 8.6s → `escalation_required` | — | 1 | honest, no fallback lie |
| companion poll GET | 48ms | — | 1 | |
| MMS transcribe / clip | ~11s (incl load) | ~4s | 16+ | singleton stays warm |
| tiers GET | <100ms | — | 3 | medium `last_inference`: unknown→failed (honest) |

Probe notes:
- `/api/v2/command/parse` takes `quality` + `lang`, NOT `tier`. Early probes omitting
  `lang` defaulted to `en` and mis-parsed FR text — probe artifact, not a bug: the UI
  (`src/ui/command_center.js:311`) sends `lang: reqLang` correctly. Closed, no fix.
- tiers medium: `ready:true` (tags present) + `last_inference:failed` after the OOM
  attempt — the flag works as designed (tags-present ≠ inference works).

## N3 optimizations (measured justification, in night PR)

1. `nl_router.OllamaIntentTransport` keep_alive `30s`→`10m`: keeps llama resident
   between demo commands, saves ~7s reload whenever gap >30s. 1 line + unit test.
2. New `dev/warm_models.py`: pre-demo warm-up script (llama no-op chat + MMS load),
   zero production change. Saves ~7s+11s on first voice command.
3. Medium tier on THIS box: unusable (30b-q4 needs 12.8GB CUDA, 10.8GB free).
   No code fix; `auto` stays correct (low resolves, medium honest-escalates).
   Documented, not hidden.

## N3b — MMS loader segfault under low RAM (VERIFIED, environmental)

`transcribe_pcm` first-load segfaults (0xC0000005) inside
`transformers/core_model_loading.py::_materialize_copy` ← `torch/storage.py`
when free RAM is ~4.7–5.1GB (box crowded: Electron apps + agents running).
Needs ~6GB+ free for fp32 weight materialization. NOT an OpenBridge bug:
same snapshot transcribed fine earlier at 7.3GB free (N2a).
Mitigations shipped: `dev/warm_models.py` isolates MMS warm in a subprocess +
pre-checks free RAM (exit 2 = partial, honest skip).
MORNING RISK FLAG: live 18765 loads MMS in-process; the FIRST `/voice/transcribe`
after a reload segfaults THE WHOLE SERVER if free RAM <6GB. Before any voice
demo: close apps, run `python -m dev.warm_models` (expect WARM_OK), then demo.
Structural fix (STT subprocess isolation in server) is out of night-PR scope.
