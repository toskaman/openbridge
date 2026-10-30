# G3 model-side freeze — 30 Oct 2026 (main `f5124f6`)

Purpose: pin the model side (prompt, code, primitive registry, procedure,
budgets) BEFORE the independent party constructs the sealed task. Anything
the future sealed run may use is named here by hash. Code that changes after
this freeze is NOT the frozen revision: re-run from `f5124f6` or re-freeze.

This freeze does NOT include a sealed task. It must not be scored as an
independent evaluation: the sealed value/package and the task hash come from
the independent party (see `docs/forge/G3_SEALED_TASK_PROTOCOL.md`).

## Frozen revisions

- git commit: `f5124f653e57491989aeb30c9a9895cd4e47447e` (main, PR131 merged)
- prompt: `v4-synth-4` (`src/forge/v4_synthesize.py`)
- substrate contract: `obv4.1` (`src/substrate/kernel.py`)
- runtime contract: `1.0.0` (`src/runtime/contract.py`)
- primitive registry: 24 primitives (`src/substrate/registry.py`)

## Frozen file hashes (sha256)

- `6fc576d3a1e5edd6157b7b99d93ca0d8e3f71a2da5e3d4a2bf39017dcfef5190`  src/forge/v4_synthesize.py
- `b01cd36724ea4cb34f1924647476ee8ab5d069f45c0868576b0f18a3987ef848`  src/forge/v4_metaclient.py
- `80a483548b4aeddfdd1c9a13b68d2ccfe12f80bc415a7d2b3b477d0823ce5f4f`  src/forge/v4_evidence.py
- `de5ea3b408d8c4b9aa07b162590e7e19135bdfa88b920dea96a83e1eeb5ed96f`  dev/g3_task.py
- `1524c29a8a077040bc0876b9d0f8e1a9b049762fc3e59e9cdc2d1e450519dff7`  dev/run_g3_smoke.py
- `d787983e8a075d64116666c870de58168f8f0ef4d246d5b8e37092e858d9db3b`  src/substrate/registry.py
- `ecff559a1085d9a513ca3f72080bf743dbfeced3db85bbfc729bc07dea3bb85a`  src/substrate/kernel.py
- `6b1cdba2e08123898de867ff596530223d6fb58ee9a054c9bb7abcae3cd6e634`  src/runtime/primitives.py
- `051a6a15fa3ed7462b829e3eedc31645f301a0b420d83a9bb02f87712c4dce6e`  config/runtime_models.json

## Frozen models (manifest digests, re-verified live 30 Oct)

- `llama3.2:3b-instruct-q4_K_M` `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`
  (local CPU :11437, ctx 2048)
- `muse-glimmer:30b-q4_K_M` `de878ce33ad81d060001db1469a02eebe4d86f0ad58cfe52dc062fdcbe4464c1`
  (local GPU/CPU :11438, ctx 4096)
- `muse-spark-1.3` (hosted `https://api.meta.ai/v1/chat/completions`)

## Frozen budgets and procedure

- Per-attempt model budget: `max_s: 120`, fixed in `synthesize()`; attempts: MAX_CALLS=3.
- Max completion: 2000 tokens (runner default); reasoning effort: fixed before the run.
- Procedure: `docs/forge/G3_SEALED_TASK_PROTOCOL.md` (pool, budget, oracle, receipt, reveal).
- Hosted Spark needs a FRESH owner balance observation + explicit grant per run (never reused).

## Baselines in this directory

- `baselines-30oct.json`: RulesPlanner + Llama 3B + Glimmer 30B on a PUBLIC
  P1-shape intent with a synthetic bundle (my own public value 45000, NOT the
  sealed task). Synthesis + deterministic validation only: no devices, no
  spend, no physical acts. The sealed run repeats this shape with the
  independent party's secret value on live hardware.
