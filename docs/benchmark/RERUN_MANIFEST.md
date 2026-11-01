# Rerun manifest — committed eval JSONs (Phase I determinism)

Base: `5f1d084`, branch `feat/f30-eval-determinism`. Verified 2026-11-01 on this
worktree (Windows, Python 3.14.4). Run every command from the repo root.
Rerun outputs live outside the repo at `E:\OpenBridge-Overnight\evidence\evals\`
(prefix `w4-`) and are intentionally NOT committed.

Self-check suites (all pass, 23/23, exit 0):
`python -m unittest tests.runtime.test_eval_1000 tests.forge.test_benchmark_v2 tests.forge.test_synth_bench`

## A. Deterministic rules baselines — byte-or-explained-diff verified

### A1. `docs/benchmark/agent-benchmark-rules.json`

- Command: `python -m dev.benchmark_agent --route rules --repeats 3`
- Inputs/seeds: synthetic, generated in-code — `cases(n=30, seed=2026)` in
  `dev/benchmark_agent.py`. No external input file. Gate: `src/core/gate.py`
  `evaluate` + `src/adapters/android_package.py` allowlist.
- Caution: the script overwrites this file in place. Back it up first, then
  restore with `git checkout -- docs/benchmark/agent-benchmark-rules.json`.
- Rerun 2026-11-01: MATCH vs committed (30 cases x 3 repeats, 90 rows;
  100.0% valid, 90.0% correct, 9 unsafe proposals, 100% refused by gate).
  Only `recorded_at` and per-row `ms`/`median_ms` differ (wall clock).
- SHA-256 (committed): `7c389e391f8195770c06731de0e712714531a98b7fd784fbbd5ebab47c1cf8a5`

### A2. `docs/benchmark/v4/ablation-20261027T191220Z.json` (rules-only, registration) and the `rules` arm of `docs/benchmark/v4/ablation-20261027T210021Z.json`

- Command: `python -m dev.benchmark_v4_ablation --arms rules`
  (`--repeats` is ignored for `rules`: 1 rep, hardcoded.)
- Input: `docs/benchmark/v4/heldout_cases.json` — 24 frozen cases,
  SHA-256 `acf7224aef0d34a18d91d1ff45fda8dc5e5aef3e5dd68572dd6dbc1fd1a166a8`
  (matches `docs/benchmark/v4/REGISTRATION.md`). `REGISTRATION.md` cites
  generator seed `20261027`, but no generator script exists in the repo; the
  frozen file itself is the pinned input. Registered equivalence class:
  `unobserved_cause` == `device_local_link`.
- Caution: the script writes a NEW timestamped file
  `docs/benchmark/v4/ablation-<UTC>.json` next to the committed ones. Move it
  out of the worktree after the run; do not commit it.
- Rerun 2026-11-01: MATCH vs `ablation-20261027T191220Z.json` AND vs the
  `rules` arm inside `ablation-20261027T210021Z.json` (n=24, top-1 0.833,
  0 errors; all 4 failures are `wan_outage` ranked `shared_outage` first).
  Only `at` and per-row `ms` differ. `cases_sha256` identical.
- SHA-256 (committed): `8e755255d16238b86b2b30b53ca16096e8debc8569aad66f747bdf5fb84eb352`
  (191220Z), `441079268ab914f0e8b76eba3b82f41dd5029ff516a482f28f55df8885986e99`
  (210021Z).

### A3. `docs/benchmark/eval_1000_rules_baseline.json`

- Command (pass `--turns`/`--oracles` unless `OpenBridge_V7/05_TESTS` sits
  next to the checkout — the `dev/eval_1000.py` defaults resolve in the
  canonical layout; explicit paths work everywhere):
  `python dev/eval_1000.py --turns <KIT>/MODEL_VISIBLE_1000_USER_TURNS.jsonl --oracles <KIT>/EVALUATOR_ONLY_1000_ORACLES_DO_NOT_INJECT.jsonl --out <OUT>`
- Pinned kit (outside the repo, `OpenBridge_V7/05_TESTS/`), SHA-256:
  - `MODEL_VISIBLE_1000_USER_TURNS.jsonl`: `05ff617360ec6689008c3023d11820f6d616c6db2ea218b17ccff69335876a1e`
  - `EVALUATOR_ONLY_1000_ORACLES_DO_NOT_INJECT.jsonl`: `82a1e081047404cff8164a9154201c88ff55e72630db571e56f6f0d3c49514a4`
- Method: no seed — sequential replay of 1000 turns through real
  `nl_router.parse` with an abstaining stub transport (deterministic keyword
  fallback only) + real skill validation; mock-provenance receipts, zero
  sends. Oracle loader strips `expected_invariants`/`turn_invariant`/`grading`
  (asserted by `tests/runtime/test_eval_1000.py`).
- Original run (per `EVAL_1000_RULES_BASELINE.md`): 2026-10-30, commit
  `2ad4688`, Windows 10 PC1.
- Rerun 2026-11-01: MATCH vs committed (1000 turns, 200/200 conversations
  finished; `unsupported` 986 / `resolved` 14; 0 crashes, 0 sends).
  Only the `latency_ms` block and per-row `latency_ms` differ (committed
  mean/p50/p95 0.016/0.015/0.020 ms vs rerun 0.017/0.016/0.022 ms — machine
  timing, not behavior).
- SHA-256 (committed): `9663074c66c4cde03881d07b77901bdd6ce536f223f369845134ac0aa0ee2baa`

## B. Model arms — method reproducible, bytes NOT reproducible

Committed JSONs below are archival. Identical commands + pinned inputs
reproduce the method; model sampling, GPU state, and local-server versions
make byte-identical output unreproducible. Do not compare reruns byte-wise.

### B1. Agent-planning model arms (same synthetic inputs as A1: `seed=2026`, n=30)

| File | Command | Notes |
|---|---|---|
| `agent-benchmark-llama3b.json` | `python -m dev.benchmark_agent --route llama3b --repeats 3` | 2026-10-26T21:05, 60.0% valid / 53.3% correct. Llama 3.2 3B Q4_K_M, CPU 4 threads |
| `agent-benchmark-llama3b-v1.json` | same, pre-schema-fix code | 2026-10-26T20:42, 53.3% / 46.7%. Superseded; kept for the record (see STATUS.md) |
| `agent-benchmark-llama3b-2026-10-27-repeats1.json` | `... --route llama3b --repeats 1` | 30 attempts, 60.0% / 53.3% |
| `agent-benchmark-glimmer.json` | `python -m dev.benchmark_agent --route glimmer --repeats 3` | 2026-10-26T21:37, 90.0% / 86.7%. Muse Glimmer 30B Q4_K_M, RTX 4060 Ti 16 GB |

Requires the digest-pinned local model behind `LocalMetaBroker`/`GlimmerBroker`
(readiness check refuses on digest mismatch). UNREPRODUCIBLE byte-wise.

### B2. Coverage-advisor arms (NO committed rules JSON exists)

- Command: `python -m dev.benchmark_advisor --route llama3b|glimmer --repeats 2`
- Inputs: synthetic graphs in-code — `graphs(n=12, seed=7)` filtered to
  >=2 candidate steps → 10 graphs x 3 goals x 2 repeats = 60 attempts.
- The harness has NO `--route rules`: the STATUS.md "rule" row (100% goal fit
  by construction) is an in-run reference, not a file. Nothing rules-based to
  rerun here.
- Committed: `advisor-benchmark-llama3b.json` (0% valid — every call blocked),
  `advisor-benchmark-glimmer.json` (93.3% valid). Both UNREPRODUCIBLE
  byte-wise (model inference).

### B3. V4 model arms inside `ablation-20261027T210021Z.json`

- Command: `python -m dev.benchmark_v4_ablation --arms rules,llama,glimmer,spark --repeats 3`
  (temperature 0; models may only re-rank rule hypothesis ids, schema-enforced).
- Committed: llama 72 runs top-1 0.833 / 0 errors; glimmer 72 runs top-1 0.722
  / 8 validator-rejected answers. UNREPRODUCIBLE byte-wise.
- `spark` arm NOT run (and still not runnable here): needs
  `OPENBRIDGE_CREDIT_OBSERVATION_ID` / `OPENBRIDGE_CREDIT_VERIFIED_AT` /
  `OPENBRIDGE_FREE_CREDITS_USD` env + supervised budget (~9 calls allowed, 72
  needed). No spark rows exist in any committed file.

### B4. `EVAL_SUBSET_50_LOCAL.md` — no committed JSON, cannot verify

- Raw results `.xbuild/eval_subset_50.json` were never committed (local
  artifact). Command was `python dev/eval_local_subset.py --limit 50 --out
  .xbuild/eval_subset_50.json` (frozen 50-turn prefix, $0, sequential).
- Glimmer arm environmentally BLOCKED (llama-server OOM on ~6 GB free RAM vs
  18 GB model), not scored. UNREPRODUCIBLE from the repo as committed.

## C. Cited-file existence check (all verified present, 2026-11-01)

Sizes below are Windows-worktree bytes (CRLF), not git-blob sizes.

| File | Exists | Bytes |
|---|---|---|
| `docs/benchmark/agent-benchmark-rules.json` | yes | 19404 |
| `docs/benchmark/agent-benchmark-llama3b.json` | yes | 26168 |
| `docs/benchmark/agent-benchmark-llama3b-v1.json` | yes | 25975 |
| `docs/benchmark/agent-benchmark-llama3b-2026-10-27-repeats1.json` | yes | 8579 |
| `docs/benchmark/agent-benchmark-glimmer.json` | yes | 26184 |
| `docs/benchmark/advisor-benchmark-llama3b.json` | yes | 13897 |
| `docs/benchmark/advisor-benchmark-glimmer.json` | yes | 12543 |
| `docs/benchmark/eval_1000_rules_baseline.json` | yes | 287870 |
| `docs/benchmark/v4/heldout_cases.json` | yes | 13252 |
| `docs/benchmark/v4/ablation-20261027T191220Z.json` | yes | 4606 |
| `docs/benchmark/v4/ablation-20261027T210021Z.json` | yes | 31041 |
| `docs/benchmark/STATUS.md` | yes | 11006 |
| `docs/benchmark/v4/REGISTRATION.md` | yes | 3237 |
| `docs/benchmark/EVAL_1000_RULES_BASELINE.md` | yes | 3526 |
| `docs/benchmark/EVAL_SUBSET_50_LOCAL.md` | yes | 1945 |
| `docs/benchmark/S5_UI_FREEZE.md` (frozen spec, not an eval output) | yes | 2203 |

Kit files above are OUTSIDE the repo (`OpenBridge_V7/05_TESTS/`): turns
139420 bytes, oracles 738760 bytes. Default kit paths in `dev/eval_1000.py`
do NOT resolve inside this worktree — pass `--turns`/`--oracles` explicitly.
