# S1 results — offline synth benchmark (29 Oct 2026, llama3.2:3b, $0.00)

Harness: `dev/synth_bench.py` (commit on `spark/meta-evolution-s1`).
8 frozen DEV cases (synthetic media/watch, read-only, disjoint from sealed pool).
Raw: `docs/evidence/v4/synth-bench/BENCH.json`.

## Outcome: 0/8 valid

| case | result | latency |
|---|---|---|
| D1,D3-D8 (7) | SCHEMA_REJECTED UNKNOWN_TARGET | 16-27 s |
| D2 (1) | SCHEMA_REJECTED GRANT_SCOPE | 26 s |

RulesPlanner baseline: 8/8 ABSTAIN_UNSUPPORTED by design (it cannot generate;
abstention is its correct behavior, 0 false positives).

## Read (honest negative, consistent with history)

The opaque target id IS in the prompt (`opaque:device:<16 hex>`, verified in
prompt) — llama 3B fails to copy it character-exactly. Same failure family as
N1 (synth-3 local probes) and G3 attempts 1-2; attempt 4 required Spark 1.3
(1 call, first-try valid). Conclusion: **copy-exact contract following is the
measured Spark-over-llama gap on synthesis**, not prompt wording. Median
latency 21 s (cold-ish local box) also disqualifies llama for interactive
synthesis; Spark attempt-4 latency was comparable but valid first try.

## What this does NOT claim

- Not a Spark-vs-llama controlled comparison (different cases than N4; no new
  Spark spend — ledger preserved at $1.30/$2.00 for the sealed run).
- Not evidence about the sealed task (dev cases are disjoint by device,
  primitive and effect; no tuning was done toward any pool task).
- Kill-criterion S1 status: synth-3's edge over the deterministic baseline is
  CONFIRMED in kind (baseline cannot generate at all; Spark generated valid
  first-try on hardware) but the local-model route is disqualified for exact
  synthesis. Story pivots to Spark-synthesis + local-verification, per plan.
