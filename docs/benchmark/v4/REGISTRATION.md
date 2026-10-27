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

## Results, model arms (27 Oct 2026, 21:00 UTC, owner's PC, local, temperature 0, 3 repeats; `ablation-20261027T210021Z.json`)
| Arm | n | Top-1 | Errors | Median latency |
|---|---|---|---|---|
| rules | 24 | **0.833** | 0 | <1 ms |
| Llama 3.2 3B (local) | 72 | **0.833** | 0 | 5.1 s |
| Muse Glimmer 30B (local) | 72 | 0.722 | 8 (answers rejected by the validator) | 32.6 s |
| Muse Spark 1.3 | — | not run | — | the supervised budget ($0.10 reserved per call, $1 ceiling) allows ~9 calls, not 72 |

Unfavourable result kept as registered: **no model arm beat the rules**. Every arm failed all 12 `wan_outage` repeats (the rules put `shared_outage` first and both models kept that order). Llama re-ranked nothing away from the rules' choice; Glimmer lost 6 `device_sleep` and 2 `router_radio_change` repeats, 8 of them through invalid answers. The re-ranking design (models may only reorder rule hypotheses) gives models little room on cases the rules already get right; this is a finding, not a tuning target for these frozen cases.
