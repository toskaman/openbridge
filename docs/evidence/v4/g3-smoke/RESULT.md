# G3 integration smoke — 29 Oct 2026, owner present — result: KILL (honest negative)

Owner authorization (chat): Meta dashboard balance 132 EUR at 00:10 (recorded as a 132 USD lower bound),
authz "autorisé pour l'essai G3, 0,80 $ maximum", owner in front of the TV.
Runner: `dev/run_g3_smoke.py` (live signed facts, unchanged Forge `v4_synthesize`, kernel compile/grant/invoke).

| attempt | reasoning_effort | calls | outcome | est. cost | reserved |
|---|---|---|---|---|---|
| 1 | default | 3 | 3/3 empty content, finish=length at 4000 tokens (reasoning-exhausted) | $0.053 | $0.30 |
| 2 | low | 3 | 3/3 JSON replies, finish=stop, but not the CapabilityCandidate shape → SCHEMA_REJECTED | $0.026 | $0.30 |

Total: 6 Muse Spark 1.3 calls, about $0.079 estimated, $0.60 reserved of the $0.80 allowance (canonical ledger).
**No grant was issued, no manifest compiled, no device action taken** (0 steps in both transcripts).

## Root cause (attempt 2)
`v4_synthesize.build_prompt` (prompt `v4-synth-2`) asks for "exactly one JSON CapabilityCandidate" but never states
its 11 required keys (`schema_version`, `candidate_id`, `origin`, `intent`, `target_opaque_id`, `primitive_chain`,
`preconditions`, `postconditions`, `required_grants`, `evidence_refs`; `model_run_id` host-injected) nor each
primitive's typed input schema (e.g. `input.key` → `{"key": enum}`). The model, given no schema, invents
`plan`/`evidence`/`primitive_ids`. The validator correctly refused all three. The model's plans were semantically
right (mute key, then `state.audio` read-back) — the gap is the prompt contract, not model capability.

## Required before a retry (owner of `v4_synthesize`: Muse Code)
1. Prompt states the candidate schema and the per-primitive input schemas (bounded), with one shape example
   using placeholder ids only (no answer leakage).
2. `reasoning_effort: low` (or `minimal`) recorded in the frozen procedure; attempt 1 shows default exhausts 4000.
3. New freeze of the prompt bytes; the remaining $0.20 of this allowance (2 calls) or a fresh owner allowance.

## Attempt 3 (29 Oct ~13:00, owner "go", v4-synth-3, reasoning_effort=low, max 8000 tokens)
- 2 calls (~$0.012 estimated; $0.20 reserved, the allowance on this observation is now spent): call 1 rejected
  by the validator, **call 2 produced a valid Meta candidate**: `input.key {"key":"mute"}` then `state.audio`.
- Effect binding passed (one mute effect, one READ). Kernel **COMPILED** (manifest sha256:06abde31…,
  permissions control+read, 2 dispatches). Pre-oracle muted=false 20/100. Owner grant g-d7d88f2a… issued (2 uses).
- **Invoke refused by the kernel (SCHEMA)**: the runner's own trace_id `g3act` was 5 chars (contract 6–64).
  No device action. Grant revoked in `finally` (HTTP 200). Runner bug, fixed with a regression test.
- Attempt 3b (replay of the recorded candidate, no model call): refused `UNKNOWN_TARGET`. The bundle used
  the rotating discovery key as device id, so the cited opaque ids no longer bind. Fixed: the bundle now
  uses the stable kernel fingerprint.
- Status: the generation → validation → kernel compile → owner grant chain is demonstrated on live
  evidence; invoke → physical read-back is NOT yet demonstrated. Next run needs a fresh owner observation.

## Attempt 4 — SUCCESS (29 Oct 14:03 CET, owner present at the TV)
Owner observation: balance 129 USD at 14:02:59+01:00, authz "autorisé pour l'essai G3, 5 $ maximum".
The run used the code caps: allowance 0.80 USD on this observation, global ledger 2.00 USD.

| step | result |
|---|---|
| Muse Spark 1.3 (v4-synth-3, reasoning low) | **1 call**, valid candidate first try: `input.key {"key":"mute"}` → `state.audio`; ~$0.0067 estimated (request chatcmpl-01a187c2…) |
| effect binding | one mute effect + one READ: pass |
| kernel compile | COMPILED sha256:22ddffb1…, permissions control+read |
| oracle before | muted=false, 20/100 (tx-b972f478…) |
| owner grant | g-2b776e75… (2 uses) |
| invoke act | EXECUTED: input.key tx-17ef2a77…, state.audio tx-0782cfd2… (signed receipt) |
| oracle after act | **muted=true, 0/100** (tx-44187450…) |
| invoke restore | EXECUTED: tx-1072f4eb…, tx-defc4ee4… (signed receipt) |
| oracle after restore | muted=false, 20/100: **equal to the pre-run object** |
| revoke | HTTP 200 |
| invoke after revoke | **403 GRANT_REVOKED** |

Predicate: SUCCESS, no failed conditions. **Scope (unchanged):** this is an INTEGRATION SMOKE on a public target
(TV mute), not held-out novelty. The stocked deterministic path can also do this task. What it proves is the
chain Meta generation → validation → effect binding → kernel compile → owner grant → physical invoke →
independent read-back → restore → revoke → refusal after revoke, on owned hardware.
