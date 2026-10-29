# Voice closure and smoke-runner review — 29 October 2026

## Verified closures at proposed PR90

At d68b890da5fe3dd4df12f720970b19b002de7e94, both prior voice findings close in the exact isolated reproductions:

- Synthetic loopback302 is refused; second-origin server sees0 requests. Actual relay fetch_voice source was executed, with correctly hashed synthetic2-byte PCM available at the destination. No external endpoint.
- Actual api_v2.voice AST with local model unavailable returns409; mocked cloud function is called0times. Fake local availability only; no key lookup or cloud request. No actual microphone/model/credential/hardware.

[Closure receipt](voice-closure-d68b890.json). This is scoped to redirect confinement and automatic cloud fallback; plaintext LAN clip confidentiality, local artifact provenance, language concurrency, lifecycle and actual human-voice acceptance remain separate review items. No full PR90 suite or real transcription is claimed.

## Prompt PR89

At2ec28d914286e2e3908359bfe54b77a5eadb718f,37 agent-layer tests pass independently using exact Forge source/test Git blobs in fresh in-memory modules. v4-synth-3 now states model output keys, input-key vocabulary, exact refs and target-grant constraints. This addresses the missing prompt-contract content; it does not prove generation success, and other primitive schemas must be derived accurately rather than presumed empty when expanding the offer. A revised immutable prompt/procedure must be frozen before new measured calls. Do not rewrite attempts1/2 around the new prompt.

## PR88 retained failed attempts acknowledged

At f207a3ea9b145f969e9a52465ac21abfe02782e9, contributor reports6 hosted calls in two integration-smoke attempts, both KILL; no compiled manifest, grant or hardware steps. Retain both failures, request/model/usage/finish-reason data and estimated/reserved cost distinction. This audit has not independently repeated calls or verified billing/physical attendance. No new success or unseen-capability claim follows.

## Runner HOLD before another physical attempt

1. **False success oracle:** exact runner `ok` assignment evaluates true with pre=mid=post={'muted':true,'readable':true,'volume_index':0}, two successful read-only receipts and denied post-revoke request. [Synthetic expression receipt](g3-oracle-f207a3e.json). No full runner or device was invoked. An already-muted TV plus a model-generated read-only plan can satisfy the current predicate without any toggle. Require the approved intended transition relative to pre-state (or explicitly require unmuted precondition), read-back readability/identity and restoration, rather than only mid.muted=true and post==pre. Add read-only/no-op negative cases.
2. **Unconditional non-idempotent restore:** invoke('restore') runs after invoke('act') regardless of st1/r1 or intermediate unknown state. Same model manifest may contain multiple input.key steps or another supported key; generic kernel validity is not authorization for the specific mute-only smoke. Before grant, validate the concrete approved semantic action scope, exact target fingerprint and bounded effects. If act is failed/unknown, stop and reconcile observed state; do not blindly repeat a non-idempotent plan. Add transport-unknown and wrong-key/multi-toggle negatives.
3. **Revocation cleanup:** no try/finally protects revoke after grant; an exception during invoke/oracle can leave a usable grant until expiry. Ensure an auditable cleanup/revocation path for every post-grant exit, preserve unknown outcomes, never label automatic compensation successful without read-back.
4. **No invented grants/target:** selecting first TV and defaulting an empty link-grant union to observe/read/control is not factual scope. Bind the exact owner-approved fingerprint and fail closed on absent grants. Kernel enforcement still applies; this is not a proven kernel privilege escape.

The runner was not imported/executed by this review; only its actual isolated success predicate was evaluated. Request safe offline runner regressions before further supervised execution. Existing failed attempt evidence remains unchanged.

## Next work and verdict

Native owner corrects runner outcome/restore/cleanup and remaining voice acceptance boundaries. Muse owner freezes corrected prompt and procedure with accurate primitive schemas. Independent held-out evaluation still needs untouched task, gold and competent baseline; known TVmute smoke is not novelty. Exact loaded runtime revision, scoped physical run/read-back/revoke/restart and final release/submission evidence remain pending. No videos until a new explicit owner request.

Release BLOCKED. New audit artifacts only, no existing production/protected/frozen files replaced; no delta backup required. No provider calls, microphone/hardware operations, credentials, spend or recording.
