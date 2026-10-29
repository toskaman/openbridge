# Sealed G3 attempt 1 — REVEAL (KILL, honest)

Commitment: sha256 `a97a8f41c8a2d8ad3f6f0113450c13e4812a6f8ad6732f3420993b4c7ecf404e`
(prompt v4-synth-3 pin `2ec28d9`, runner pin `de0651b`).
Verify: `python -c "import json; from dev import g3_task as G;
s=json.load(open('docs/evidence/v4/g3-sealed/attempt1_KILL/spec.json'));
print(G.spec_sha256(s))"` → must equal the commitment.

## Spec (revealed)

P1 family: TV `screen_timeout_ms` → `120000`, oracle `get.value`,
owner restore `set $pre`. Full spec: `spec.json`.

## Outcome: KILL (no device effect sent, TV untouched)

- **run1**: KILL before any model call — authz text exceeded the broker's
  120-char limit (`Evaluation allowance requires explicit owner
  authorization reference`). 0 calls, $0. Retained as
  `run1_authz-KILL.json`.
- **run2**: 1 Muse Spark call ($0.0059), candidate passed the validator,
  then the kernel refused the manifest: `INVALID_ARGS s1.setting required`.
  Retained as `run2_INVALID_ARGS-KILL.json`.

## Root cause (verified)

The synth layer did not know the true input schemas:

1. `INPUT_SCHEMAS` contained only `input.key`, so the prompt told the model
   that `setting.set_exact` takes **no inputs** (`use "input": {} exactly`).
   The model obeyed and emitted `"input": {}`.
2. `validate_candidate` only rejected *undeclared* keys, never *missing
   required* ones, so `{}` passed.
3. The kernel (true schema: required `setting` + `value`) refused after the
   paid call.

Fix (new pins, new seal): v4-synth-4 carries the true per-primitive input
schemas + required keys, the validator enforces required inputs and integer
types, and a contract test pins them against the kernel registry.

## Spend

Attempt budget: allowance $0.80, global cap $2.00. Spent: $0.0059
(1 call). No retry beyond the frozen budget under this commitment.
