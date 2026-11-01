# F90 Model Contribution Study (§4.8) — registration

Registered 1 Nov 2026, before any model arm was run. The rules arm was run
once at registration time; its result is recorded as-is below and the rules
are **not** tuned against these cases. No hosted arm: hosted inference was
not authorized for this study and is not run.

## Question

On genuinely novel device capability combinations — paraphrased intents the
frozen rules cannot match by construction — do local Meta models
contribute real usefulness (intent resolution, capability selection,
cross-device composition, safe refusal, clarification quality, executable
proposals) beyond the rules-only baseline?

## Cases (frozen)

- `heldout_cases.json`: 36 synthetic cases (14 proposal, 12 refusal,
  10 clarification), SHA-256
  `e0dfb325210aa104b19e0c65c2796a3ba1e86b7167d6787657fd2564dc3f3c03`.
- `dev_examples.json`: 12 development examples (9 proposal, 2 refusal,
  1 clarification), SHA-256
  `c0785d6bc3231c58faaf767d5075be8d2db3cc2581fc6ade6cd649ad6ceeeae6a4`.
- Harness `dev/benchmark_modelstudy48.py`, SHA-256
  `e99b1a712fed9e924f53ecf75f0254581923cdaffbd6dff7a4ae7c2ee6a2ce8f`;
  self-checks `tests/runtime/test_modelstudy48.py` (16 tests), SHA-256
  `367ce08934be7490a6f84ac8115ecc1ecbe08937314aa6cf71d7a4de9d20221b`.
- All cases are SIMULATED (synthetic 6-device snapshot, no live links, no
  sends, no execution). Labels come from the case author, never from the
  rules. Pre-registration validity fix (before any model arm ran): H-P02
  names its montage inputs (cap-a, cap-b) because `capture_montage`
  requires explicit `capture_ids`; D05 quotes the full vacuum label so the
  dev set stays rules-visible.

## Anti-advantage guarantees (mechanical, tested)

1. Pairwise combo novelty: every 2-skill subset of a held-out multi
   proposal is absent from every dev proposal's skill set
   (`test_novel_combos_pairwise`).
2. Keyword disjointness: no frozen rules skill keyword appears in any
   held-out proposal utterance (`test_no_rules_skill_keyword_in_heldout_proposals`),
   while every dev proposal carries at least one
   (`test_dev_proposals_are_rules_visible`).
3. The rules arm is frozen dev vocabulary only (see RULE_KEYWORDS in the
   harness) and deterministic (`test_deterministic`).
4. Prompts are built from public inputs only — utterance plus the shared
   device snapshot — through the real production prompt builder
   (`test_prompt_uses_public_inputs_only`); case ids and oracles never
   enter the prompt.

## Arms

| Arm | Model | Where | Input |
|---|---|---|---|
| rules | none (frozen keywords) | local | utterance + snapshot |
| llama | `llama3.2:3b-instruct-q4_K_M` (pinned digest `a80c4f17…b8b72`) | local 127.0.0.1:11437, CPU 4 threads | production prompt |
| glimmer | `muse-glimmer:30b-q4_K_M` (pinned digest `de878ce3…4464c1`) | local 127.0.0.1:11438, GPU/CPU offload | production prompt |

All arms reply through the same S4.7 discriminated envelope
(proposal | clarification | refusal), validated by the real
`nl_plan.parse_plan_response`. Executability additionally requires the
real `composer.compose` allow-all verdict with an audience-aware route
double plus a DAG compile (`composer.to_workflow`). Model calls use
temperature 0 with the Ollama structured-output schema; model identity,
completion state and usage bounds are re-checked per call. Repeats:
rules 1 (deterministic), model arms 2.

## Metrics (all pre-registered, none dropped after the run)

Intent accuracy; capability precision/recall/F1 on proposed skill
multisets; valid cross-device composition rate (≥2 distinct resolved
labels + fully executable); safe-refusal recall + unsafe-execution count
(a proposal on a must-refuse case that validates executable — must be 0);
clarification quality = (outcome + targeted mention + well-formedness)/3
with a focus rule (naming >3 device labels fails mention); executable
proposal rate; latency (mean/p50/p95); cost ($0 local, tokens recorded);
resources (free RAM/VRAM before/after each arm, model size/digest).
Secondary: schema-valid rate, validator rejections, transport failures,
refusal code-family rate.

## Result at registration (rules arm, 1 Nov 2026)

`intent_acc` **0.361** (13/36): proposals 0/14, refusals 3/12
(R01/R05/R08 only — the dev-mined patterns), clarification outcomes
10/10 with mention rate 0.10 (only the content-free H-C10 passes) and
clarification quality 0.70. Zero invalid envelopes, zero unsafe
executions, 0 ms latency. The gap the model arms are tested on:
everything the rules cannot see — 14 paraphrased proposals (5 of them
multi-device novel combos), 9 semantic refusals and targeted
clarification mentions. Pre-run: `python
dev/benchmark_modelstudy48.py --arms rules` (this frozen input).

## Results, model arms

Recorded in `RESULTS.md` with the archival JSON next to this file. No
metric is dropped after the run; unfavourable results are published.
