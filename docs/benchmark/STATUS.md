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

## Phase C closing sync (1 Nov 2026; append-only — earlier sections unchanged)

Newer committed numbers since the 26 Oct ablations above. All paths verified
present in the repo at sync time except where marked MISSING.

### Frozen 50-turn local eval (31 Oct 2026)

Full scorecard: `docs/benchmark/EVAL_SUBSET_50_LOCAL.md`. Command
`python dev/eval_local_subset.py --limit 50 --out .xbuild/eval_subset_50.json`
($0, sequential, one model at a time, no cloud calls). Identical frozen
50-turn prefix and identical rubric for all three arms:

| Arm | Resolved | Needs clarification | Unsupported | Escalation | Crashes | Sends | p50 |
|---|---|---|---|---|---|---|---|
| rules | 0 / 50 | 0 | 50 | 0 | 0 | 0 | 0.0 ms |
| llama (llama3.2:3b-instruct-q4_K_M) | 4 / 50 | 44 | 1 | 1 | 0 | 0 | 5.5 s |
| glimmer (muse-glimmer:30b-q4_K_M) | BLOCKED (OOM, not scored) | — | — | 50 rows are transport failures | 0 | 0 | 6.7 s |

Reading: the keyword baseline resolves nothing on this prefix; Llama resolves
4/50 and asks for clarification on 44/50 (a coverage signal, not a
semantic-correctness proof). The Glimmer arm is BLOCKED, not scored: every
call failed in transport (`llama-server startup failed … out-of-memory`,
HTTP 500; ~6 GB free RAM against an 18 GB model). The 50
`escalation_required` rows must not be read as model answers. No hosted-Spark
arm (paid inference needs separate authorization, not given). Honest limits:
frozen prefix ≠ full set (the 1.4% rules figure is the full-kit number; this
prefix is harder for rules at 0/50); single run, latencies indicative only.

### §11 eval-kit rules baseline, 1,000 turns (30 Oct 2026, commit `2ad4688`)

Full report: `docs/benchmark/EVAL_1000_RULES_BASELINE.md`; raw results
`docs/benchmark/eval_1000_rules_baseline.json` (committed); unit tests
`tests/runtime/test_eval_1000.py` (5/5). Real `nl_router.parse` with an
abstaining stub transport, so only the deterministic keyword fallback resolves;
oracles stripped on load (only id→category + hard_fail_if kept).
Turns 1,000, conversations finished 200/200; by status: `unsupported` 986,
`resolved` 14 (1.4%, all 14 to `fabric.status` via keyword fallback — 13 via
French keywords, 1 (`OB-CORE-192-T5`) via English `fabric` matched as a
substring of "fabricant"; correctness UNGRADED); crashes 0, external sends 0,
unknown-skill proposals 0,
fabricated receipts 0. This 1.4% is the baseline the model tiers must beat.
Physical acceptance: PC live sample VERIFIED (2026-10-30T16:55Z); phone
BV9300 sample PENDING (device unreachable). Model-tier parse rates, graded
scores and hosted-vs-local comparison remain PENDING, none claimed.

### V4-04 registered re-ranking ablation (27 Oct 2026)

Registration + results: `docs/benchmark/v4/REGISTRATION.md`; frozen cases
`docs/benchmark/v4/heldout_cases.json` (24 synthetic cases, 6 templates × 4,
seed 20261027, SHA-256 `acf7224a…1a166a8`); raw results
`docs/benchmark/v4/ablation-20261027T191220Z.json` (rules registration run)
and `docs/benchmark/v4/ablation-20261027T210021Z.json` (full run), both
committed. Models may only re-rank rule hypothesis ids (schema-enforced).
Top-1: rules 0.833 (20/24, 0 errors, <1 ms), Llama 3.2 3B 0.833 (72 runs,
0 errors, 5.1 s median), Glimmer 30B 0.722 (72 runs, 8 validator-rejected
answers, 32.6 s median), Spark not run (supervised budget allows ~9 calls,
not 72). Unfavourable result kept as registered: no model arm beat the rules.

### Committed receipts with dates (all paths verified)

| Receipt | Recorded | Kind |
|---|---|---|
| `docs/runtime-meta-receipt.json` | 2026-10-26T16:57Z | synthetic advisory, Muse Spark 1.3 (recorded runtime-core call, $0.00335, SIMULATED facts) |
| `docs/meta-design-receipt.json` | 2026-10-26T16:39Z | design-time Meta call (not runtime evidence) |
| `docs/physical-transaction-attempt.json` | 2026-10-26T18:22+01:00 | physical transaction attempt record |
| `docs/local-meta-adb-receipt.json` | 2026-10-26T19:08Z | local Llama vs real ADB facts (grounded summary) |
| `docs/agent-loop-receipt.json` | 2026-10-26T19:25Z | REAL_AGENT_LOOP: observe → local Llama plan → gate → consent → execute → undo |
| `docs/physical-package-receipt.json` | 2026-10-26T20:17+01:00 | VERIFIED_CHANGE_AND_UNDO, one allowlisted app, reverted |
| `docs/glimmer-smoke-receipt.json` | 2026-10-26T21:10+01:00 | real local Glimmer inference, synthetic facts, RTX 4060 Ti |
| `docs/crash-recovery-receipt.json` | 2026-10-26T21:50+01:00 | crash-recovery drill record |
| `docs/tuya-hardware-receipt.json` | 2026-10-27T20:37 | Tuya hardware observation |
| `docs/DEVICE_EVIDENCE.json` | from 2026-10-29T17:45Z | hardware test registry (multiple rows; see HARDWARE_TEST_HISTORY.md) |
| `docs/local-meta-smoke-receipt.json` | undated (no timestamp field in file) | local Llama smoke, SIMULATED facts |
| `docs/simulated-transaction-receipt.json` | undated (no timestamp field in file) | synthetic rollback drill only, not physical evidence |

### Missing / unpublished artifacts (explicit)

- `.xbuild/eval_subset_50.json` (frozen-50 raw results): MISSING from the
  repo by design — local artifact, stays uncommitted. Only the scorecard
  (`EVAL_SUBSET_50_LOCAL.md`) is published.
- Hosted-Spark eval arms (frozen-50 and v4): NOT RUN — no authorization /
  supervised budget too small. Not claimed anywhere.
- Phone-side (BV9300) §11 acceptance sample: PENDING — device unreachable at
  sample time; does not block the mock baseline.
- No battery, speed or storage gains are claimed by any run above.
