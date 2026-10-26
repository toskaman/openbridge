# Benchmark status

## Agent planning ablation (synthetic inputs, 26 Oct 2026)

30 synthetic phone-planning cases × 3 repeats per route (`python -m dev.benchmark_agent --route rules|llama3b|glimmer`). Each case has an owner goal (review/declutter), numeric facts and 0–3 allowlisted optional apps; every fifth case adds an unsafe distractor package (system UI, messaging, Google services) that the deterministic gate must refuse. Expected outcome: review or no eligible app → NO_ACTION; declutter with an eligible app → REVIEW_REQUIRED.

| Route | Hardware | Schema-valid | Correct decision | Unsafe packages proposed | Refused by gate | Median latency | Cost |
|---|---|---|---|---|---|---|---|
| Rules only (naive baseline) | — | 100% | 90.0% | 9 / 90 | 100% | 0 ms | $0 |
| Llama 3.2 3B Q4_K_M | CPU, 4 threads | 60.0% | 53.3% | 6 / 90 | 100% | 9.7 s | $0 |
| **Muse Glimmer 30B Q4_K_M** | RTX 4060 Ti 16 GB, 78% of weights in VRAM | **90.0%** | **86.7%** | **3 / 90** | 100% | 16.7 s | $0 |

Reading the results honestly:
- Muse Glimmer is much more reliable than Llama 3B: 1.6× more correct decisions, no false action proposals, failures are blocked validations (6 ungrounded summaries, 3 incomplete completions), never unsafe execution.
- On this deliberately narrow task, a hand-written rule is as accurate. The model's added value is a grounded explanation and fewer unsafe proposals (3 vs 9), not raw accuracy. The deterministic gate is what guarantees safety: 100% of unsafe proposals from every route were refused.
- An earlier Llama 3B run (docs/benchmark/agent-benchmark-llama3b-v1.json, 53.3% valid / 46.7% correct) led to a schema fix (separate branches for observe-only and action plans) before the runs above.
- Inputs are synthetic. Physical results are recorded separately (docs/agent-loop-receipt.json, docs/physical-package-receipt.json). No battery, speed or storage gains are claimed.

## Coverage advisor ablation (synthetic graphs, 26 Oct 2026)

10 synthetic device graphs with ≥2 candidate steps × 3 owner goals × 2 repeats (`python -m dev.benchmark_advisor`). "Goal fit" = the chosen step is the goal's primary kind under the fixed priority, so the rule scores 100% by construction.

| Route | Valid explanation | Goal fit | Agrees with rule | Median latency |
|---|---|---|---|---|
| Rule (goal priority) | n/a | 100% | 100% | 0 ms |
| Llama 3.2 3B | **0%** (never a usable sentence; always blocked) | 0% | 0% | 7.8 s |
| Muse Glimmer 30B | 93.3% | 53.3% | 36.7% | 21.2 s |

Per goal, Glimmer picked the expected step for "find Bluetooth" in 18/20 runs; for "extend coverage" it preferred installing a companion (also extends coverage, via Bluetooth) over authorizing the router; for "tidy inventory" it sometimes chose an unrelated step. Choices were identical across repeats (30/30). Conclusion: the deterministic rule decides better on this task; Glimmer's value is a grounded explanation, and the UI always shows the rule's choice next to the model's. Results unfavourable to the models are kept on purpose.

## Endurance (synthetic, no network) — `python -m dev.endurance`
500 announced devices × 20 discovery rounds + 50 rotating-address BLE advertisers per round, 5,000 random malformed mDNS packets, a relay failing repeatedly (Windows, Python 3.14): 8.8 s, peak Python memory 5.6 MB, snapshot 682 KB for 1,500 nodes, 5,000/5,000 malformed packets rejected without crash, relay marked offline after 3 failures, no leaked threads. Strong-identity devices stay at 500 across rounds; BLE devices with rotating private addresses appear as new nodes each round (1,000 after 20 rounds) — by design they cannot be linked; the product rebuilds the graph at each discovery, which bounds this. A scaled-down version runs in the unit suite (tests/fabric/test_endurance.py).
