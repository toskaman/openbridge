# Campaign Two §4.6 — Voice-flow corpus results (2026-11-01)

Controlled FR/EN evaluation of the deterministic voice-to-capability path:
55 cases in [corpus_voice_flow.json](corpus_voice_flow.json), run through
`src/ai/voice_intent.py`, `src/ai/voice_normalize.py` (new) and
`src/runtime/migrate.py::parse_request`.

## Headline

| Metric | Baseline (pre-change) | Improved |
|---|---|---|
| Exact-match vs expected | 16 / 55 | **55 / 55** |
| KEEP-SAFE violations (uncertain speech -> proposal) | 6 | **0** |
| Regressions (passed before, fail after) | — | **0** |
| Full worktree suite | — | **1726 passed** |

Every gain is clarification/refusal quality. The branch adds **zero** new
proposal (command) paths: uncertain speech now clarifies or refuses instead
of guessing.

## Method

- Baseline: corpus executed against pristine `HEAD` code before the change
  (old `compile_intent` outcomes inferred from its reason strings;
  `normalize_*` engines did not exist yet, marked `n/a (new)`).
- Improved: same corpus through the new code, asserted by
  [test_voice_flow_corpus.py](test_voice_flow_corpus.py) (all green).
- AD-01 baseline shows `ok`: the old dict carries no `needs_target` key
  (script artifact), but its outcome was already the correct clarification.

## Watch7 regression rows (verbatim STT, must never become commands)

All three were safe-but-generic before (`unsupported`) and stay safe after,
now with targeted migration guidance in French:

- W7-01 `enlève les boutons de volumes de la montre et met les bouton`
- W7-02 `mas les boutons de volume sur la tellée` (mets->mas, télé->tellée)
- W7-03 `mais les boutons de volume sur la tellée` (mets->mais)

## Baseline over-eager proposals fixed (6 -> 0)

| Case | Baseline proposal | Why it was wrong |
|---|---|---|
| SH-01 `scan` | discover | Lone trigger: network discovery vs BLE scan unclear |
| SH-05 `check` | diagnose | Lone trigger: full report vs disconnect probe unclear |
| SA-01 `find my phone` | discover | Locate-my-device vs network discovery |
| CF-01 `découvre ... et termine la session` | finish_session | Two intents; first-match won silently |
| CF-02 `scan bluetooth via the TV and the phone` | ble_scan_via_tv **on dev-ph** | Mislabeled intent on the wrong device key |
| PR-02 `appuie sur le bouton scan de la montre` | discover | Word `scan` inside a button label |

## Deliberate behavior changes (all proposal -> clarification)

SH-01, SH-05, SA-01, CF-01, CF-02, PR-02 (above). Each is a case where the
old code picked a winner from ambiguous speech; the new code asks. No
existing test pinned the old behavior (verified: full suite green).

## Per-case results

ID | Category | Baseline | Improved | Expected | Safety
---|---|---|---|---|---
W7-01 | watch7-regression | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
W7-02 | watch7-regression | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
W7-03 | watch7-regression | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
XS-01..XS-07 | existing-samples | 7 x proposal ok | 7 x proposal ok | proposal | —
XR-01..XR-02 | existing-refusals | 2 x refusal ok | 2 x refusal ok | refusal | —
MR-01 | misrecognized-names | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
MR-02 | misrecognized-names | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
MR-03 | misrecognized-names | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
MR-04 | misrecognized-names | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
AC-01..AC-04 | accents | 4 x proposal ok | 4 x proposal ok | proposal | —
SH-01 | short-partial | proposal:discover MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
SH-02 | short-partial | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
SH-03 | short-partial | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
SH-04 | short-partial | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
SH-05 | short-partial | proposal:diagnose MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
SA-01 | similar-actions | proposal:discover MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
SA-02 | similar-actions | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
SA-03 | similar-actions | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
SA-04 | similar-actions | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
CF-01 | conflicting-intents | proposal:finish_session MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
CF-02 | conflicting-intents | proposal:ble_scan_via_tv MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
CF-03 | conflicting-intents | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
CF-04 | conflicting-intents | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
PR-01 | generated-controls | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
PR-02 | generated-controls | proposal:discover MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
PR-03 | generated-controls | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
AD-01 | ambiguous-destinations | needs_clarification ok | needs_clarification ok | needs_clarification | KEEP-SAFE
AD-02 | ambiguous-destinations | unsupported MISS | needs_clarification ok | needs_clarification | KEEP-SAFE
RV-01 | revoked-controls | n/a (new) | revoked ok | revoked | —
RV-02 | revoked-controls | n/a (new) | press_active ok | press_active | —
RV-03 | revoked-controls | n/a (new) | revoked ok | revoked | —
IR-01..IR-06 | irreversible | 6 x unsupported MISS | 6 x refusal ok | refusal | —
LG-01 | language | n/a (new) | lang=fr ok | lang=fr | —
LG-02 | language | n/a (new) | lang=en ok | lang=en | —
LG-03 | language | n/a (new) | lang=unknown ok | lang=unknown | —
LG-04 | language | n/a (new) | lang=unknown ok | lang=unknown | —
LG-05 | language | n/a (new) | lang=unknown ok | lang=unknown | —
LG-06 | language | n/a (new) | lang=fr ok | lang=fr | —
MP-01 | migration-parse | parsed ok | parsed ok | parsed | —
MP-02 | migration-parse | unparsed ok | unparsed ok | unparsed | —

(`XS`, `XR`, `AC`, `IR` rows are grouped; every member matches the shown
verdict. `MISS` on a baseline row means "did not meet the new expectation",
not "was unsafe": only the 6 KEEP-SAFE `proposal` rows above were unsafe.)

## What changed in code

- NEW `src/ai/voice_normalize.py`: folding, FR/EN detection, single-reading
  STT repairs (matching only), ambiguous-verb detection, and fail-closed
  screens (refusal-extra, conflict, press, migration, volume, locate) with
  localized questions. Pure functions; screens never return commands.
- `src/ai/voice_intent.py`: screens run before the legacy patterns; two-pass
  rule (clean match proposes, repaired-only match clarifies); fragment and
  short-utterance clarification; new machine-readable keys
  (`outcome`, `lang`, `clarifying_question`, `normalization`). Legacy
  proposal/refusal strings are byte-identical.
- `src/runtime/command_drain.py`: voice transcripts pass the same screens
  before the model tier (volume excluded: the model may legitimately
  resolve volume steps). Typed text is untouched.
- NEW `tests/voice/`: this corpus (55 cases), module unit tests, drain
  wiring tests, and this report.

## Known limitations / follow-ups

- Single-token language (`scan`, `volume`) is unknowable without the clip
  hint; `/api/v2/voice/intent` falls back to English, the drain uses the
  clip language (correct there).
- `restart`/`redémarre` over-refuses benign re-scans
  (`redémarre la découverte`); accepted as fail-closed for voice.
- Revoked-label lookup is wired at module level; the drain reports
  press-shapes generically (voice can never press either way).
- Proposal `says`/`note` strings stay English for backward compatibility;
  only new clarification/refusal texts are localized.
