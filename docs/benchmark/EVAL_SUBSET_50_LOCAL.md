# Frozen 50-turn local eval — scorecard (31 Oct 2026)

Command: `python dev/eval_local_subset.py --limit 50 --out .xbuild/eval_subset_50.json`
($0, sequential, one model loaded at a time, no cloud calls.)
Raw results: `.xbuild/eval_subset_50.json` (local artifact, not committed).

## Manifest (verified at run time)

| Arm | Model | Endpoint | Digest (sha256:) | Size |
|---|---|---|---|---|
| llama | llama3.2:3b-instruct-q4_K_M | 127.0.0.1:11437 | a80c4f17…b8b72 | 2.0 GB |
| glimmer | muse-glimmer:30b-q4_K_M | 127.0.0.1:11438 | de878ce3…4464c | 18.2 GB |

## Results (identical frozen 50-turn prefix, identical rubric)

| Arm | Resolved | Needs clarification | Unsupported | Escalation | Crashes | Sends | p50 |
|---|---|---|---|---|---|---|---|
| rules | 0 | 0 | 50 | 0 | 0 | 0 | 0.0 ms |
| llama | 4 | 44 | 1 | 1 | 0 | 0 | 5.5 s |
| glimmer | 0 | 0 | 0 | 50 | 0 | 0 | 6.7 s |

Tokens: llama prompt 33,264 / eval 3,445; glimmer 0/0 (no inference completed).

## Reading

- On this frozen prefix the keyword baseline resolves nothing; Llama resolves
  4/50 and asks for clarification on 44/50 instead of guessing. That is a
  coverage signal, not a semantic-correctness proof.
- The Glimmer arm is BLOCKED, not scored: every call failed in transport with
  `llama-server startup failed … out-of-memory` (HTTP 500). The host had
  ~6 GB free RAM against an 18 GB model; the failure is environmental and
  reproducible, not a model-quality result. Rerun when RAM is available; the
  50 escalation_required rows must not be read as model answers.
- No hosted-Spark arm: paid inference needs separate authorization, not given.

## Honest limits

- Frozen prefix ≠ full set: the 1.4% rules figure (14/1,000) is the full-kit
  number; this prefix happens to be harder for rules (0/50).
- Resolution coverage ≠ demonstrated semantic correctness (per §10).
- Single run, sequential, CPU/GPU-shared host; latencies are indicative only.
