# Frozen routing snapshot evaluation — results

Recorded 2026-10-28T13:59:59.244152+00:00. Freeze: `414d1c0`; reviewed and executed source: `f8873d93a942bd2ef053f77e5ebdd8ce502339c1`. The tracked worktree was clean. [Registration](REGISTRATION.md), [pre-run clarification](CORRIGENDUM.md), [inputs](cases.json), [separate gold](gold.json), [full report](results/run-f8873d9.json) and [checksums](results/SHA256SUMS) are retained. The exact executed script bytes are [archived](results/harness-executed.py.txt), including platform line endings; its hash matches the report. No cases or gold were changed after scoring.

## Deterministic selection results

| Arm | Correct / cases | Errors |
|---|---|---|
| router | 32/32 | 0 |
| catalog_first | 7/32 | 0 |
| first_eligible | 20/32 | 0 |
| random_eligible | 18/32 | 0 |
| historical_freshest | 8/32 | 0 |
| policy_aware | 32/32 | 0 |

The router and independent policy-aware heuristic both scored32/32 and eight perfect template families out of eight. Router candidate unavailable-reason checks scored96/96 separately; these are deterministic checks, not model successes. Router abstention precision/recall are both1.0 (eight expected abstentions). All failures from weaker baselines remain in the full report with inputs, gold and recorded decisions.

Final-router-call latency: p50 2.563ms, p95 3.478ms on the recorded environment. This includes local state reads and excludes setup. It is not device-task or model latency. Setup snapshots, final route documents, grants, freshness, rules, revisions and event payloads are retained per case.

The report includes per-family, expected-device-class and hop-count slices, errors, abstention metrics and descriptive Wilson intervals. Correlated permutations are not independent trials; intervals do not support a statistical superiority claim. The pre-run clarification correctly identifies the all32 two-hop slice; small slices are marked indicative.

## Actual Meta contribution

**Meta Model API, Muse Spark1.3 (`muse-spark-1.3`) reviewed the frozen public synthetic design before scoring.** [Exact request](meta-design-review-request.json) and [usage/review receipt](meta-design-review-receipt.json) record APPROVE, no requested revisions, 8057 prompt tokens, 1988 completion tokens, estimated $0.01852025, and a $0.10 reservation through the existing promotional-credit guard. This is an estimated token cost using the prototype's configured rates, not an independently verified provider bill. No retry or paid fallback occurred. The initial oversized local payload was rejected before any reservation or network request, then compacted without changing its logical content; exactly one hosted request was made.

Spark reviewed the original registration/cases/gold, not the subsequent slice-count clarification or the implementation. A separate independent code reviewer caught baseline errors being incorrectly coupled to router failures; a failed-first development regression fixed that before any scored run, and the reviewer cleared the corrected source. No model scored or generated routing decisions in this run. Meta explanation quality, dynamic failover and new-protocol generalization remain unmeasured.

## Limits and next gate

32 newly composed synthetic snapshots, eight correlated families, three fictional providers and two declared hops. The author knows the router and existing tests; this is not a claim of unseen semantics or model-training independence. There is no live hardware proof, task execution, model-vs-rules advantage or broad protocol coverage. A correct policy-aware rule baseline matches the router, as retained above.

Software verification:526 local tests; seven harness regressions use development-only cases and do not score the frozen set. Source compilation and diff checks pass; exact final integration CI is recorded on the publishing PR.

A later Meta explanation stage requires a separate frozen prompt, sample and citation rubric before calls, with a fresh credit observation and bounded reservations. No explanation score is claimed here. Hardware cleanup/edge cases, coordinated live reload and participant submission remain separate gates. Videos remain on explicit owner hold.
