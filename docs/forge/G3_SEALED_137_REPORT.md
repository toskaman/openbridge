# G3 sealed-137 report — §4 sealed evaluation (honest negative result)

Task: `sealed-phone-brightness-137` — "Set the phone screen brightness to 137,
then read the brightness setting back to confirm." Target: the lab phone
(Blackview BV9300, USB adb-direct). Oracle: `get screen_brightness` ==
137. Restore: owner `set $pre`. Sealed by independent setter (Sol subagent);
spec sha256 `0c42bb0c…7328d5` committed in PR139 before any run
([freeze](g3-sealed-137-freeze.json), commit cf73eb8, 2026-10-30T15:35:56Z).

## Results per arm (all transcripts in g3-sealed-137-transcripts/)

| Arm | Calls | Outcome |
|---|---|---|
| rules (deterministic, in every run) | 0 | ABSTAIN_UNSUPPORTED (no template) |
| llama3.2:3b local ($0) | 3 RECORDED | 0/3 valid: SCHEMA_REJECTED (UNKNOWN_TARGET, …). Near-miss JSON, wrong target binding |
| glimmer:30b local, frozen 120s budget ($0) | 3 runs × 1 call | KILL TimeoutError × 3 (attempts 1–3) |
| glimmer:30b, extended 600s budget (addendum 1) | 3 | attempt0 TRANSPORT_FAILED at 220 s + the :11438 service died mid-generation; attempts 1–2 fast-fail (connection refused) |
| spark-1.3 hosted | 0 | NOT RUN — needs owner observation + authz (blocked, see below) |

No valid candidate was ever produced, so compile → grant → invoke → oracle →
restore → revoke never executed. The phone was never touched: brightness still
141 after all attempts (adb read-back 2026-10-30). No effect was ever sent.

## Root causes (evidenced, not speculated)

1. Glimmer-30B is too slow for the frozen 120 s/call budget on the lab GPU
   (RTX 4060 Ti 16 GB, 15.5/16.4 GB VRAM used, model partially CPU-offloaded):
   trivial PONG took 17 s for 112 tokens (~6.6 tok/s); a ~1K-token synthesis
   prompt cannot complete in 120 s. 3/3 timeouts.
2. The 600 s attempt killed the :11438 Ollama service (PID 41172) mid-generation
   (plausibly VRAM exhaustion under KV growth; no crash event in the Application
   log). Only the CPU Glimmer on :11439 survives (~1.2 tok/s — synthesis would
   need 15+ min and a different pinned endpoint, not attempted).
3. Llama-3B answers fast but cannot bind the target: it copies real opaque refs
   yet fails validation 3/3. The frozen validator works as designed (rejects
   near-misses, never executes unbound plans).

## Procedure integrity (for the evaluator)

- Commitment before results: freeze (spec sha only) pushed + PR139 opened
  BEFORE any model call; addendum 1 (replay path + 600 s synthesis, new file
  hashes) committed BEFORE the extended synthesis ran. At the addendum, all 4
  prior attempts were KILLs with no candidate — cherry-picking impossible.
- Frozen pieces reused byte-for-byte: build_prompt (v4-synth-4),
  transport_from_broker (digest-provisioned, echo-checked),
  validate_candidate, g3_task predicate. The only deviation is the disclosed
  call budget (120 s → 600 s, infra-mandated).
- Baselines are real: rules abstains, llama genuinely fails schema (replies
  recorded in the transcript), glimmer infra-fails (transcripts + ping timings).
- Model identity: every local call echo-checked against the pinned id
  (muse-glimmer:30b-q4_K_M / llama3.2:3b-instruct-q4_K_M). Spend: $0.

## What is NOT demonstrated (read this before citing §4)

- Meta synthesis of a working skill on a sealed held-out task: NOT demonstrated.
- The sealed act pipeline (manifest → kernel → grant → physical invoke →
  oracle → restore → revoke): NOT executed (no candidate reached it).
- Do NOT claim G3 success. Cite this report as: sealed procedure executed with
  integrity; synthesis blocked by local-GPU throughput; hosted arm pending.

## Pending: Spark hosted arm (owner-gated)

Run a FRESH sealed task (this one is public now — Sol picks a new secret value,
new freeze) through dev/run_g3_smoke.py with owner observation + authz file.
Everything else is ready: runner, spec schema, oracle/restore, predicate.
Suggested budget: 3 calls × $0.10 reservation (same as the smoke doc).

## Lab state for the owner (action needed)

- :11438 (GPU Glimmer-30B) DOWN — crashed during the run (was PID 41172).
- :11437 (llama-3B) DOWN — stopped by the operator after its arm completed
  (was PID 33612) to free VRAM; did not help (llama was not VRAM-resident).
- :11439 (CPU Glimmer-30B) ALIVE. Default :11434 was already stopped before
  this session (left as-is).
- Restart :11437/:11438 with their original OLLAMA_HOST/OLLAMA_MODELS (the
  models dir was not found by the operator — restart not attempted to avoid a
  misconfigured duplicate). GlimmerBroker.ready() fails until :11438 returns.
- ANDROID_SERIAL env points at stale id 251103192116G2358W1; the phone is
  BV9300PEEA0004883 (server-side discovery unaffected).
