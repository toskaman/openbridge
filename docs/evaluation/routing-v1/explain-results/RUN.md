# Explanation run record (routing-v1, 28 Oct 2026)

## Run
- Freeze: `4cdb926` (attestation PR #69; bytes approved in PR #66, merged `fe1b811`).
- Command: `python -m dev.run_explain_eval --observation-id owner-20261028-136usd --free-balance-usd 136 --out docs/evaluation/routing-v1/explain-results`
- Key: vault `meta-api-key` (no key bytes stored anywhere in this repo).
- Observation: owner-supplied free balance $136, 28 Oct 2026.
- Permits: 4 x $0.20 (`owner-20261028-136usd#1..4`, minted lazily, each reserve inside the 300 s window). The broker caps one supervised session at $0.20, so the frozen $0.80 total spans 4 permits; every reserve individually guarded, global sqlite ceiling $1.00 untouched otherwise.

## Outcome
- 8/8 calls RECORDED, model `muse-spark-1.3` on all, no BLOCKED / FAILED / LEAK_ABORT.
- Usage ~2100 prompt / 800 completion tokens each; estimated total $0.0487 against $0.80 reserved.
- **All 8 replies are EMPTY.** Completion tokens hit the frozen 800 cap exactly on every call with no message content — the documented reasoning-exhaustion mode of this model family (cf. `src/ai/broker.py` 'Model returned no content (reasoning budget exhausted); raise max_completion_tokens'). No retry was made: the frozen protocol forbids retries and extra calls.
- Runner limitation: `finish_reason` and raw envelopes were not captured, only content/usage/request id. Recommended for any v2 runner.

## Scoring
Per frozen RUBRIC.md: 8/8 INVALID (empty reply, no DECISION/EVIDENCE/LIMITS sections), 0 SUPPORTED / 0 UNSUPPORTED sentences. See `scoring.json` (deterministic) + human pass inline (CONFIRM-INVALID x8, no disputes). No quality score for the router is reported, per the rubric.

## Follow-up (not authorized yet)
A v2 freeze with a higher `max_completion_tokens` (e.g. 4000, matching the broker's own advisory calls) would test whether the emptiness is purely budget exhaustion. That needs NEW frozen bytes, a NEW owner approval, and a NEW spend authorization — this run's freeze must not be edited or re-spent.
