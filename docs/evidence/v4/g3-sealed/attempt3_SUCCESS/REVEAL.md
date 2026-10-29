# Sealed G3 attempt 3 — REVEAL (SUCCESS)

Commitment: sha256 `0f1c5badf673d1210feae1ba08e80211a6b663b5aa0fe365a1eaf3e79a8c74a2`
(prompt v4-synth-4 pin `b22ba4e`, runner pin `d33c958`).
29 Oct 2026, owner present, live TV hardware, no prebuilt skill for the task.

## Spec (revealed)

P1 family: TV `screen_timeout_ms` → `60000`, oracle `get.value`,
owner restore `set $pre`. Full spec: `spec.json`.

## Outcome: SUCCESS — full sealed loop on real hardware

- 1 Muse Spark 1.3 call ($0.0072, reasoning low) composed first try:
  `setting.set_exact {setting: screen_timeout_ms, value: 60000}` with
  descriptor + read-back steps.
- Validator accepted; kernel COMPILED (`sha256:f4e88d8a…`, control+read);
  effect binding passed (plan effects == sealed allowed effects).
- Oracle pre: `300000` → grant → act EXECUTED → oracle mid: `60000` →
  owner restore (`set $pre`, never model-driven) → oracle post: `300000`
  == pre. Predicate: no failing reasons.
- Revoke 200 (`g-b0f2552915dba95e`), invoke after revoke refused
  (`GRANT_REVOKED`).

Transcript: `run4_SUCCESS.json`. All earlier attempts (2 KILLs) retained
in `attempt1_KILL/` and `attempt2_KILL/`.

## Spend (all 3 attempts)

Attempt allowance $0.80, global ledger cap $2.00. Total: $0.0059 +
$0.0072 + $0.0072 = **$0.0203** over 3 model calls.

## Integrity note

Sol unavailable; seal performed by Muse Spark on explicit owner order
(same party authored and ran). Mechanics (hash-lock, effect binding,
no-op KILL, owner restore, revoke check) enforced by code, and both
KILLs were reported honestly before this SUCCESS.
