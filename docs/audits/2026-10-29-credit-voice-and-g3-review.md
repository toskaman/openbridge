# Credit, voice and G3 review — 29 October 2026

## Closed: live evaluation ledger override

PR78 at87b191f9b4ec0eb3a943dd5f27dd98a576e478e7 removes --ledger and always selects resolve_ledger(None).19 focused allowance/runner tests independently pass on exact Git source/test blobs. An additional actual main() argparse invocation with all required synthetic arguments plus --ledger rejects with exit2 before Vault/transport setup. No credential, provider or user ledger access. The prior arbitrary live CLI override finding is CLOSED at this revision; explicit broker paths remain trusted test injection. Reported owner approval of24h eval policy and separate envelopes is recorded in PR78; no fresh balance or spend is inferred. Canonical observation identity/time/balance persistence, final trust approval and any actual live eligibility remain separately scoped.

## G3 revision2 acknowledgement

PR87 at897f8c1ad2c325c2f39563e4195ac58b0babfce5 now correctly labels TVmute as known-fixture integration smoke, uses state.audio with UNKNOWN handling, requires a competent existing-library baseline, removes camera success, qualifies dedup/v1-cause/cost claims, and provides180-second text. Those requested plan corrections are addressed. The actual baseline bytes/gold/procedure are not yet frozen, no run is accepted, and no genuine unseen-capability or generalization claim follows. Keep the top-level goal scoped to smoke; it cannot itself satisfy unseen G3 novelty.

## Revised PR86: two blocking findings

Pinned headf0331ce6cd7118a680781142e3819b78a923fc58 replaces platform recognition with AudioRecord clips and local Meta MMS transcription. The prior default-system-recognizer mechanism is removed. All3 exact Java sources compile against Android34 with javac --release11,exit0. [Compile/source receipt](voice-loop-java-f0331ce.json). No APK build/signing/install or microphone use. Local clip/transcription success on owned hardware was not tested by this audit.

### P1: automatic cloud fallback bypasses the required spend/disclosure gate

src/runtime/api_v2.py voice() invokes voice_stt.transcribe(bytes(pcm), _meta_key(), language) whenever stt_local.available() is false. Request accepts only audio_b64/language and has no fresh-credit permit, reserved allowance or explicit cloud-audio disclosure approval. voice_stt transcribe directly opens the Meta WebSocket, rather than reserving through the promotional-credit broker.

Exact voice() AST invoked with synthetic2-byte PCM, stt_local.available=False, fake key lookup and mocked cloud transcription returns200 and calls the cloud function once. This is a control-flow proof, not actual transmission/spend. Fail closed to typed/local-only mode unless explicit data/provider consent and eligible reserved credit guard are present. Add negative tests asserting zero key lookup/network call when local is absent and those gates are missing. Do not treat a microphone permission or local-model-unavailable event as cloud approval. Existing test_cloud_fallback_without_local currently enshrines this path.

### P1/P2: voice downloader follows cross-origin redirects beyond checked scope

src/fabric/relay.py fetch_voice checks only initial base_url, then build_opener(ProxyHandler({})) uses default redirects. A loopback relay returning302 to a second loopback server caused the second origin to be contacted and its correctly hashed PCM accepted. Both endpoints were synthetic local servers; no external endpoint was contacted or external exploit claimed. The same automatic redirect handler means initial-address checking alone does not confine destinations. Reject redirects (preferred) or revalidate exact paired origin/approved scope before each hop. Add redirect-negative tests before returning clip data. A matching body hash does not enforce connection scope.

[Control-flow and loopback receipt](voice-loop-f0331ce.json). Reproduction imported exact relay source, executed exact voice() AST with a fake key function, used two temporary loopback HTTP servers with synthetic bytes, and patched the real cloud transcribe entrypoint to a return-only mock. No real key, provider, model, audio, ADB or hardware.

## Remaining ordered work

1. Native voice owner: close cloud consent/credit and redirect-confinement findings with offline regressions; preserve local-only fallback on failure. Review local model artifact provenance, adapter/language concurrency and lifecycle before live microphone acceptance.
2. Credit/trust owner: acknowledge CLI override closure, final policy/observation provenance review, then merge authorized source; no actual inference until eligible current balance/permit exists.
3. Muse/native: freeze integration-smoke procedure, actual competent baseline, permission/data scope and oracle; obtain narrowly scoped attended run approval. No recording. This smoke does not replace genuine unseen evaluation.
4. Independent evaluation: untouched target/task commitment, independent gold and fair baseline before model generation; currently NOT_FROZEN.
5. Joint release: exact loaded revision, full generation/compile/sandbox/grant/install/invoke/read-back/revoke/restart/cleanup evidence, claim review and submission receipt. No video until new explicit request.

Release remains BLOCKED. New audit artifacts only; no existing production/protected/frozen evidence replaced, so no delta backup required. No actual provider calls, hardware actions, recording or spend.
