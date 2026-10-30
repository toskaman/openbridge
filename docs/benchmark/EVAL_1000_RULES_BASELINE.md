# §11 Eval-Kit — Rules-Baseline Replay Report

## Provenance
- Kit: `OpenBridge_V7/05_TESTS/MODEL_VISIBLE_1000_USER_TURNS.jsonl` (1000 turns,
  200 conversations x 5) + `EVALUATOR_ONLY_1000_ORACLES_DO_NOT_INJECT.jsonl`.
- Harness: `dev/eval_1000.py`. Unit tests: `tests/runtime/test_eval_1000.py` (5/5).
- Raw results: `docs/benchmark/eval_1000_rules_baseline.json`.
- Run: 2026-10-30, commit `2ad4688` (+ working tree: harness only), Windows 10 PC1.
- Oracle discipline: only the FIRST oracle was glanced (format); the loader
  STRIPS `expected_invariants` / `turn_invariant` / `grading` on load (asserted
  by test). Only id->category + hard_fail_if are kept for aggregate grouping.
  No prompt, skill or keyword was tuned from the kit.

## Method (rules-path phase — no models, no network, no devices)
Each turn goes through the REAL `nl_router.parse` with an abstaining stub
transport, so the deterministic keyword fallback is the only resolution path,
plus real skill validation (`S.resolve` + `validate_intent`). Resolved turns
get a mock-provenance receipt (`eval-mock`); nothing is sent anywhere.
Finished = every turn of a conversation reaches a terminal status with zero
escaped exceptions and zero external sends.

## Results
- Turns: 1000. Conversations finished: **200/200**.
- By status: `unsupported` 986, `resolved` 14.
- Hard-fail proxies: crashes 0, external sends 0, unknown-skill proposals 0,
  fabricated receipts 0 (receipts carry `eval-mock` provenance only).
- Parse-path CPU: mean 0.016 ms/turn, p50 0.015, p95 0.020 (rules path only).

## By category (n=40 each; resolved / 40)
BATTERY_PRIORITY 2, CALL_AUDIO_TV 0, CAPABILITY_INVENTORY 1,
CONCURRENCY_SAFETY 0, DEV_AI_PC 0, DYNAMIC_LAYOUT 0, FILE_RELAY 2,
HOME_AUTOMATION 1, META_EVALUATION 0, MINECRAFT_PC 0, PERMISSIONS_GRANTS 0,
PRIVACY_SECURITY 0, RECOVERY_FAILOVER 1, SCREENSHOT_MONTAGE 1,
SCREENSHOT_SINGLE 0, SELECTIVE_FANOUT 0, SMS_CONTACTS 0,
SYSTEM_DIAGNOSTICS 0, TV_REMOTE_UI 0, UNKNOWN_DEVICE_FORGE 0,
VOICE_MULTILINGUAL 2, WALLPAPER_MEDIA 1, WATCH_VACUUM 0,
WHATSAPP_MESSAGES 1, WIFI_BANDS 2.

## Reading (honest)
- The catalog holds 10 skills / 62 keywords, English except 4 French keywords
  (`combien`, `appareils`, `etat`, `resume`) on `fabric.status`
  (`src/runtime/skills.py`). The fallback additionally resolves ONLY
  fabric-scoped skills with model-supplied (here: empty) targets.
- All 14 resolved turns went to `fabric.status` via those French keywords.
  Correctness of those 14 is UNGRADED (judge phase needs a model + oracles).
- Net: the rules path covers ~1% of the French kit. French understanding,
  device-targeted skills and UI-building turns REQUIRE the model tiers
  (low/medium local, high hosted). This 1.4% is the baseline the model tiers
  must beat — the harness stands ready (`stub_transport` -> real transport).

## Physical acceptance (real hardware)
- PC (this machine): `pc_facts()` live sample OK — 16 threads, 31.9 GB RAM,
  real OS-reported values (2026-10-30T16:55Z). VERIFIED.
- Phone BV9300: unreachable at sample time (ping false, adb 10060, mDNS
  empty — device asleep/off-network). Phone-side acceptance sample PENDING,
  does not block the mock baseline.

## NOT proven by this run
Model-tier parse rates, graded-dimension scores, hosted-vs-local comparison,
prompt-evolution gains, Router/Executor full path with devices. Blocked on:
local models down (`:11437`/`:11438` down, `:11439` CPU-only Glimmer alive),
no hosted-model observation/authorization. All PENDING, none claimed.
