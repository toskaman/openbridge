# Sealed G3 attempt 2 — REVEAL (KILL, honest no-op)

Commitment: sha256 `f27d06313258abfe7ce9e7d4ac2176cebb57a6b0e7ad8d76acc98e824a518a1b`
(prompt v4-synth-4 pin `b22ba4e`, runner pin `23c642c`).

## Spec (revealed)

P1 family: TV `screen_timeout_ms` → `300000`, oracle `get.value`,
owner restore `set $pre`. Full spec: `spec.json`.

## Outcome: KILL — oracle pre-read already showed the expected value

v4-synth-4 worked end to end up to the no-op gate:

- 1 Muse Spark call ($0.0072) composed
  `setting.set_exact {setting: screen_timeout_ms, value: 300000}` +
  `state.read_setting` read-back.
- Validator accepted (required inputs present and typed).
- Kernel COMPILED (manifest `sha256:96ff8a07…`, permissions
  control+read). Effect binding passed.
- Oracle pre-read showed `value = 300000` = expected → KILL
  (`oracle already shows the expected value: nothing to prove, no
  effect sent`). No grant, no act, TV untouched.

This KILL is the protocol working as designed: a no-op scores no
success. Transcript: `run3_noop-KILL.json`.

## Consequence

The TV's live default (`300000`) is now revealed. Attempt 3 picks a
fresh value different from this known pre (disclosed, not blind):
real transition required, model sees the value in the intent either
way, so no tuning advantage.

## Spend

Attempt budget: allowance $0.80, global cap $2.00. Spent: $0.0072
(1 call). No retry under this commitment (sealed value == live
value; re-running cannot prove anything).
