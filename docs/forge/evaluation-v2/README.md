# Frozen planner v2 evaluation

This is a new synthetic coverage suite for the current `SchemaConstrainedPlanner` path. It leaves the original 64 v1 cases, planner, brokers and unfavorable results unchanged. No model call has been made to construct or validate this suite. The test suite uses controlled fake brokers; the rules receipt is not model evidence.

## Frozen design

`scenarios.json` contains 80 new cases across 16 categories: single route, multiple routes, real-status preference, wrong source binding, identity conflict, offline relay, missing permission, stale observation, incompatible primitive, partial availability, all unavailable, physical Undo request, hosted-model requirement, local-only execution, duplicate capability identity and malformed evidence. All input data is synthetic, including any status named REAL_HARDWARE_VERIFIED. Those labels exercise a policy branch; they never become hardware proof.

Even case IDs are development and odd IDs heldout: 40 each, fixed before any inference. Development contains 12 proposed-plan cases, 20 unavailable cases, three ambiguity refusals and five scope refusals. Heldout contains 13 proposed-plan cases, 20 unavailable cases, two ambiguity refusals and five scope refusals. Thus there are at most 25 inferences per model across the full suite. Variants change pseudonymous identifiers, evidence references, observation times, signal values and route ordering; this is broader policy-boundary coverage, not 80 independent semantic problems or novel arbitrary composition.

Dataset SHA-256: `f0ba6ace2af7edee83847847dd07ed6c284cc4210f8bb8f16d298f27e5ec2095` (also in SHA256SUMS). Commit these exact dataset bytes and splits before any local model call. The CLI checks `git show HEAD:docs/forge/evaluation-v2/scenarios.json` against that digest for model routes. Freeze the harness/planner source revision too, retain it with receipts, and do not tune prompts, cases or gold labels after viewing any score. If later work changes the evaluation, use a new version and fresh heldout cases. No silent repair of failed proposals or retries.

## What gets measured

The production planner accepts only `expose_remote_ble_observations`, producing exactly one read step followed by local read-only publication. It does not accept arbitrary goal strings or an Undo/cloud policy. Unsupported physical-Undo and hosted-model requirements are refused by an explicit **harness scope gate**, without invoking the planner. Scope-refusal correctness is separate and must never be marketed as model reasoning or a newly implemented product feature.

For supported goals, each local route independently uses the unchanged current v2 planner. It performs deterministic eligibility/source checks before inference; unavailable-source and duplicate-ID refusals therefore measure deterministic policy. Model completion success is reported separately on the 25 eligible proposal cases. A missing or digest-mismatched model on an eligible case is a failed supported-plan result, with no fallback. The rules route uses the existing deterministic planner with the same fixtures and gold expectations.

Correctness requires a complete validator-accepted two-step plan, expected decision and exact preferred capability; wrong candidate ordering, wrong evidence, missing consent requirement or a failed model are failures. Raw invalid proposals, errors and returned token counts remain recorded. Metrics include supported correctness, complete-plan correctness, source/policy refusal correctness, separate harness scope refusal, hallucinated IDs, proposed permission violations, latency and tokens. Hallucination/permission counters inspect raw proposals even when validation rejects them. Safety depends on deterministic policy, never benchmark accuracy.

Memory fields distinguish Python `tracemalloc` peak allocation from Ollama `/api/ps` loaded-model `size`/`size_vram`. Neither is model process RSS or artifact disk size; process RSS is explicitly unmeasured (`null`). Local provider cost is $0, excluding electricity/hardware. Every fixture is synthetic; no hardware adapter, server, desktop control, recording or hosted API is invoked.

## Controlled verification already performed

- `python -m unittest tests.forge.test_benchmark_v2 -q`: 14 tests pass with controlled brokers, including unavailability, invalid proposals, permission/hallucination accounting and hard call/time budgets. The initial test invocation failed because the harness did not yet exist, before implementation.
- Rules-only CLI over all 80 cases: 80/80 correct, zero model calls, zero proposed permission violations or hallucinated IDs. Local receipt: ignored `artifacts/evaluation-v2/rules-controlled.json`.
- Model scores remain **NOT RUN**. These checks do not claim general reasoning advantage or final release acceptance.

## Exact bounded commands

Run from the repository root after committing the frozen evaluation. Existing local services must already be running with the exact pinned model/digest: Llama at `127.0.0.1:11437`, Glimmer GPU/CPU-offload at `127.0.0.1:11438` (`--glimmer-service gpu-v2`, default), or explicitly isolated CPU v2 at `127.0.0.1:11439` (`--glimmer-service cpu-v2`). The harness neither starts/pulls models nor uses another endpoint if unavailable. Do not reuse an output filename; it refuses overwrites.

```powershell
python -m unittest tests.forge.test_benchmark_v2 -q
python -m dev.benchmark_forge_v2 --route rules --split development --max-calls 0 --budget-seconds 60 --output artifacts/evaluation-v2/rules-development.json
python -m dev.benchmark_forge_v2 --route rules --split heldout --max-calls 0 --budget-seconds 60 --output artifacts/evaluation-v2/rules-heldout.json
python -m dev.benchmark_forge_v2 --route llama3b --split development --max-calls 12 --budget-seconds 1800 --confirm-local-model-calls --output artifacts/evaluation-v2/llama-development.json
python -m dev.benchmark_forge_v2 --route llama3b --split heldout --max-calls 13 --budget-seconds 1800 --confirm-local-model-calls --output artifacts/evaluation-v2/llama-heldout.json
python -m dev.benchmark_forge_v2 --route glimmer --glimmer-service cpu-v2 --split development --max-calls 12 --budget-seconds 1800 --confirm-local-model-calls --output artifacts/evaluation-v2/glimmer-development.json
python -m dev.benchmark_forge_v2 --route glimmer --glimmer-service cpu-v2 --split heldout --max-calls 13 --budget-seconds 1800 --confirm-local-model-calls --output artifacts/evaluation-v2/glimmer-heldout.json
```

The hard call budget counts actual inference attempts before dispatch. Time budget is checked between cases; one in-flight request may finish after it. Current broker timeouts are Llama 120 seconds, Glimmer GPU/offload 300 seconds and isolated CPU v2 180 seconds; each receipt reports the actual endpoint, provider and selected timeout, with additional bounded readiness/telemetry checks. A stopped run records `complete: false`; never present it as the complete frozen evaluation. A model error is retained and the harness advances to the next distinct case without retrying the failed case. Capture all attempts, including incomplete receipts; no automatic rerun.

Feasibility: standard-library harness, no added dependencies; already configured pinned local models only. Rules finish in seconds. Prior narrow Llama measurements suggest roughly 2â€“4 minutes per 12/13-call split; Glimmer depends heavily on CPU/GPU loading and could take roughly 4â€“20 minutes per split based on earlier distinct tasks. These are planning estimates, not measurements of this dataset. With 30-minute between-case budgets, slower runs can be incomplete; a final in-flight Glimmer request can extend the run by up to its selected timeout (180 seconds for isolated CPU) plus readiness/telemetry overhead. Across both model routes and splits the absolute request count is at most 50; there are no hosted charges. Review actual resource availability before running, without silently unloading unrelated models.
