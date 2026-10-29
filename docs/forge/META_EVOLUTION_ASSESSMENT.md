# Meta Capability Evolution — implementation assessment (29 Oct 2026, main `eae305c`)

Author lane: Muse/Spark (Meta intelligence). Claude owns deterministic platform.
Status words: VERIFIED (code+test/log), PARTIAL, MISSING, BLOCKED_EXTERNAL.

## 1. Recon findings (repo-grounded)

| Subsystem | Status | Evidence |
|---|---|---|
| Command Center P0 (NL→approve→execute) | VERIFIED | `src/runtime/command.py`, 771 tests OK, live 18765 tiers ready, N4 Spark-vs-llama results |
| Forge v4 synthesis (synth-3) | VERIFIED | `src/forge/v4_synthesize.py` (PROMPT_VERSION v4-synth-3), G3 attempt-4 SUCCESS transcript |
| G3 smoke (public target) | VERIFIED | `docs/evidence/v4/g3-smoke/attempt4_SUCCESS.json`: 1 Spark call, mute false/20→true/0→restore, revoke 200, post-revoke 403 |
| G3 sealed-task machinery | VERIFIED (protocol only) | `dev/g3_task.py`, `--task-spec/--task-sha256`, `G3_SEALED_TASK_PROTOCOL.md`, offline e2e tests green |
| G3 sealed novelty RUN | BLOCKED_EXTERNAL | No Sol seal published (no commitment sha). F0 gate armed; no scored run before seal. Must not pre-tune. |
| UI manifests (schema) | PARTIAL | `src/forge/v4_ui.py`: text/button/status patches, binding allowlist. No Meta generator wiring, no watch/TV publish path verified |
| Meta planner | PARTIAL | `meta_planner.py` + `planner_v2.py` (2-step publish task); ablation v1: rules 100%, llama 0% exact, Glimmer OOM, Spark not run. No multi-device planner |
| Discovery | VERIFIED (passive) | mDNS/ADB/Wi-Fi via `/api/fabric-discover`; keys rotate per discover (privacy). No event-driven incremental layer, no doc-research |
| Voice in | VERIFIED (local) | MMS-1B FR/EN, companion 0.7.0 AudioRecord; needs ≥6 GB free RAM; TTS engine OEM-broken on test phone |
| Companions | VERIFIED | 0.7.0 phone+TV, launch-clean, no crash; renderer for dynamic UI manifests: MISSING (Claude lane) |
| Ledger/spend | VERIFIED | $1.30/$2.00 reserved (G3 $0.80 + N4 $0.40 + retry $0.10); every call receipted; $128 owner balance observed |
| Benchmarks | PARTIAL | Frozen v1 ablation (rules≫llama on the narrow task); no synthesis-vs-baseline benchmark on manifest generation |

Honest headline: the generate→validate→approve→deploy→verify→revoke MACHINERY is
proven on real hardware (attempt 4). What is NOT proven: held-out novelty
(seal pending), UI generation end-to-end, multi-device planning, discovery
research. Llama 3B is proven WEAK at exact planning (0% v1) — the synthesis
value must be measured on manifest generation (attempt 4: 1-call success),
not on the narrow 2-step task where rules dominate.

## 2. Build plan (my lane only; $0 unless stated)

- S1 (now): offline synthesis benchmark — v4-synth-3 vs RulesPlanner baseline on
  frozen manifest-generation cases, local llama ($0) + recorded Spark cases
  replayed offline. Metrics: compile-first-try, schema-reject rate, evidence
  precision, latency. No seal contamination (dev cases only, disjoint from pool).
- S2: Meta UI-drafting module (Forge side): natural-language → `v4_ui`
  patch candidates + validator + refusal cases. Renderer/publish = Claude
  contract below. Offline tests only.
- S3: multi-device planner v0 (my lane): dependency-aware plan objects over
  VERIFIED capability descriptors, consent points, per-step verification hooks.
  Execution stays Claude-side. Offline tests + simulated transports.
- S4 (on Sol seal): sealed run support — frozen runner hash, witness transcript,
  no pre-tuning. Separate session, owner present.
- S5: improvement loop: failure → structured diagnostic → revised manifest
  candidate through the same pipeline (offline until verified).

## 3. Handoff: what Claude must implement (contracts)

- C1 UI renderer: consume `v4_ui.validate_patch` output on watch/phone/TV/PC;
  expose publish/withdraw/persist/sync endpoints + versioning. I deliver
  candidates + refusal semantics; Claude delivers render + binding execution.
- C2 Planner execution: consume S3 plan objects (steps with primitive,
  target, consent, verify-hook); per-step receipts; recovery without duplicate
  unsafe acts. Strawman schema to be agreed before I finalize S3.
- C3 Discovery events: incremental device add/remove/update callbacks with
  stable fingerprints (keys rotate today — fingerprint binding needed).
- C4 No-go: I will not touch `src/substrate`, broker caps, relay auth, or
  `dev/run_g3_smoke.py` scored paths. Sealed spec content stays unread by me
  until reveal.

## 4. Kill criteria
- S1: if synth-3 shows no measurable edge over RulesPlanner on manifest
  generation after fair cases, report it and pivot the story to safety
  (abstinence) rather than generation quality.
- S2/S3: if renderer/executor contracts are not agreed, ship validators +
  offline proofs only; no fake end-to-end.
- S4: no seal → no run. No exceptions.
