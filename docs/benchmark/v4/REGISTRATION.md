# V4-04 registered ablation — ranking cross-transport hypotheses

Registered 27 Oct 2026, before any model arm was run. The rules arm was run once at registration time; its result is recorded as-is (including its failures) and the rules are **not** tuned against these cases.

## Question
Given the same minimised timeline payload, does a Meta model re-rank the deterministic hypotheses better than the rules alone?

## Cases (frozen)
- `heldout_cases.json`, 24 synthetic cross-transport cases (6 templates × 4, seed 20261027), SHA-256 `acf7224aef0d34a18d91d1ff45fda8dc5e5aef3e5dd68572dd6dbc1fd1a166a8`.
- Labels come from the template that generated each case, never from the rules. `distractor_ble` cases (a stale BLE relay next to a link loss) are labelled `unobserved_cause`: BLE presence is not evidence of interference.
- Equivalence class registered in advance: `unobserved_cause` ≡ `device_local_link` (both mean "no observed source explains it").
- All cases are SIMULATED. They are separate from the CI drills in `tests/runtime/drills/`.

## Arms
| Arm | Model | Where | Input |
|---|---|---|---|
| rules | none | local | timeline |
| llama | `llama3.2:3b-instruct-q4_K_M` (pinned digest) | local | redacted projection (same bytes as cloud) |
| glimmer | `muse-glimmer:30b-q4_K_M` (pinned digest) | local | same |
| spark | `muse-spark-1.3` | Meta Model API, supervised credits | same, after preview/consent flow |

Models may only re-rank hypothesis ids produced by the rules (schema-enforced); any other answer is an error, counted as wrong.

## Metrics
Primary: top-1 accuracy over cases × repeats (3 repeats for model arms, temperature 0). Secondary: error rate, median latency, cost. No metric is dropped after the run; unfavourable results are published.

## Result at registration (rules arm)
top-1 accuracy **0.833** (20/24). All 4 failures are `wan_outage` cases ranked `shared_outage` first: two devices dropping together is correctly seen, but the router's WAN state change is not preferred over it. This is the gap the model arms are tested on. Run: `python -m dev.benchmark_v4_ablation --arms rules,llama,glimmer,spark --repeats 3` (results land next to this file).
