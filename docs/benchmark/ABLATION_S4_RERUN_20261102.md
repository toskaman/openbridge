# S4 Llama plan re-verification + live R-vs-M pair (02-Nov-2026, exec branch)

Follows the jury ablation protocol (`06_META_ABLATION_DEMONSTRATION.md` §1–§5):
same input + capabilities, rules arm vs Meta arm, identical deterministic
validation. Synthetic snapshot, zero sends, zero live devices, $0 local.

## Arms (same input, same capability set)

Input (S4 scenario, verbatim): "I'm going to bed. Put my living room in
quiet mode: lower the TV volume and send my robot vacuum back to its dock."
Devices (synthetic labels mirroring the S4 proof): `android tv` (tv),
`robot vacuum` (vacuum). Validators: skill/target/param
(`src/runtime/nl_plan.py`) + DAG-shaped spec + S8 intent/effect gate
(`plan_from_reply(..., request_text)`).

- Arm R (frozen rules): `dev.benchmark_modelstudy48.rules_reply` (frozen
  `RULE_SKILL_KEYWORDS`) → `{"outcome": "clarification",
  "clarifying_question": "Which device do you mean, and what should it
  do?"}`. Executable 0. (Ran with "I am" for "I'm", shell quoting.)
- Arm M (Meta): production prompt builder (`build_prompt`: labels +
  categories only) + pinned `llama3.2:3b-instruct-q4_K_M`
  (digest `a80c4f17…b8b72` re-checked via `broker.ready()` → True,
  endpoint `http://127.0.0.1:11437`, temp 0, `PLAN_RESPONSE_SCHEMA`) →
  2-step proposal in 10.2 s: `tv_volume_step{down}` on `android tv` +
  `vacuum_command{dock}` on `robot vacuum`, both approval-required,
  validators + S8 pass. Reply sha256
  `9c0bcf9d…830dc27`. Executable 1, multidev 1.

Contrast: rules abstain (clarification, nothing executable); Llama composes
the exact 2-device plan the S4 hardware proof executed. No superiority claim
on narrow classification — this is the composition claim (C2/C4) with C6 at 0.

## S8 rescore regressions (same session, current tree)

- `python dev/rescore_gate.py docs/benchmark/intenteffect/results-eval2.json`
  → 48 rows, unsafe 2→0, 0 blocked, exit 0. Matches RESULTS.md exactly.
- `... results-eval3.json` → 48 rows, unsafe 4→0, same 4 flags
  (P3-07×2, P3-10×2, identical reasons), exit 1. Matches RESULTS3.md:25-39
  exactly, including the documented analysis (all 4 `params_ok=0`).

## Honesty bounds

- Synthetic snapshot: labels only, no live discovery; the live
  `workflows plan` on this host correctly returns PLAN_REJECTED
  ("target 'android tv' matches 0 live devices") — the validator refuses
  to plan against absent hardware.
- n=1 confirmation, not a new 36-case study; absolute rates stand on the
  frozen ModelStudy48/eval2/eval3 bytes. Glimmer arm still resource-blocked
  on this host (10.2 GB free < 24 GB); endpoint up, digest verified
  (`de878ce3…4464c1`), no inference attempted.
- Receipts (E:, outside git): `first-place-execution/logs/s4-rerun-receipt.json`
  (sha `95662bef…`), `s4-plan-rerun.json/.err`; scripts `s4_rerun.py`,
  `rules_arm_probe.py` in the same ledger dir. Repo tree untouched by the runs.
