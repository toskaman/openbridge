# Rerun manifest — F90 Model Contribution Study (§4.8)

Base: `34ff6f5`, branch `feat/f90-model-study`. Verified 2026-11-01 on this
worktree (Windows, Python 3.14.4). Run every command from the repo root.

## Self-check suite (16/16, exit 0)

`python -m unittest tests.runtime.test_modelstudy48`

Enforces the study's mechanical guarantees: case-file validity against the
real skill catalog, golden-proposal full executability, held-out/dev combo
disjointness, rules-keyword disjointness, rules determinism, grading and
focus rules, prompt oracle isolation.

## A. Deterministic rules baseline — byte-or-explained-diff verified

### A1. `docs/benchmark/modelstudy48/results-<UTC>.json`, `rules` arm

- Command: `python dev/benchmark_modelstudy48.py --arms rules`
  (repeats ignored for `rules`: 1 rep, hardcoded).
- Inputs (frozen, pinned by SHA-256 in `REGISTRATION.md`):
  `docs/benchmark/modelstudy48/heldout_cases.json` (36 cases),
  `docs/benchmark/modelstudy48/dev_examples.json` (12 examples, rules
  vocabulary source only — never scored).
- Validators: real `nl_plan.parse_plan_response` (S4.7 envelope) + real
  `composer.compose` with the audience-aware route double + DAG compile.
- Caution: the script writes a NEW file only when `--out` is passed; without
  it nothing is written. Rerun outputs live outside the repo at
  `E:\OpenBridge-Overnight\evidence\evals\` (prefix `w4-`) and are
  intentionally NOT committed.
- Registered result: n=36, intent_acc 0.361 (proposals 0/14, refusals 3/12,
  clarification outcomes 10/10, mention 0.10), 0 invalid, 0 unsafe
  executions. Only `started_utc`, `git_sha`, per-row `ms` and the `env_*`
  snapshots differ between reruns (wall clock + host memory, not behavior).

## B. Model arms — method reproducible, bytes NOT reproducible

Committed JSONs are archival. Identical commands + pinned inputs reproduce
the method; model sampling, GPU state and local-server versions make
byte-identical output unreproducible. Do not compare reruns byte-wise.

### B1. Llama arm

- Command: `python dev/benchmark_modelstudy48.py --arms llama --repeats 2
  --out <OUT>` (temperature 0, CPU 4 threads, `num_ctx` 2048).
- Requires the digest-pinned model behind 127.0.0.1:11437
  (`llama3.2:3b-instruct-q4_K_M`, digest `a80c4f17…b8b72`, ~2.0 GB); the
  harness refuses on digest mismatch. Start the private service with
  `python -m dev.start_local_meta` (no `--pull-model` needed when the
  pinned blob is already cached).
- Sequential, one model at a time; the harness unloads the model after the
  arm. $0, no cloud calls. UNREPRODUCIBLE byte-wise.

### B2. Glimmer arm

- Command: `python dev/benchmark_modelstudy48.py --arms glimmer --repeats 2
  --out <OUT>` (temperature 0, `num_ctx` 4096).
- Requires the digest-pinned model behind 127.0.0.1:11438
  (`muse-glimmer:30b-q4_K_M`, digest `de878ce3…4464c1`, ~18.2 GB).
- Resource note (1 Nov 2026): the arm is RESOURCE-BLOCKED on this host —
  `llama-server` fails to load the weights (`failed to allocate
  CUDA_Host buffer of size 3994822656`, HTTP 500) with ~10.5 GB free RAM /
  ~10.6 GB free VRAM against the 18 GB model. The harness records two
  real load probes as evidence and marks every case row `blocked` (not
  scored). Rerun on a host with enough contiguous memory; blocked rows
  must not be read as model answers.

### B3. No hosted arm

Hosted Meta inference was not authorized for this study. No hosted calls
were made, none are claimed, and the harness has no hosted path.

## C. Full run (archival)

- Command: `python dev/benchmark_modelstudy48.py --arms rules,llama,glimmer
  --repeats 2 --out docs/benchmark/modelstudy48/results-<UTC>.json`
- External pristine copy: `E:\OpenBridge-Overnight\evidence\evals\`
  (`w4-modelstudy48-full.json`).
- Scorecard: `docs/benchmark/modelstudy48/RESULTS.md`.
- SHA-256 (committed):
  `0dcea66a1127fa532f5d664b57b297ba63208d635279b8f8d0319450e4b3f3c5`
  (`results-20261101T024033Z.json`, 88,316 bytes worktree).
- SHA-256 (external pristine copy `w4-modelstudy48-full.json`, 91,689 bytes):
  `c07837b12c397e901539724b215bcda6c8b3c576e62ce222c5d1586d8b6f4b5d`.
