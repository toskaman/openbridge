# Integration handoff to Claude

Branch: feat/capability-forge. First compiler/lifecycle/UI commit: d9a3666. Base: dff8ff8.

Worktree: C:/Users/TheBox/Desktop/Hackaton/OpenBridge-capability-forge.

Owned files are new src/forge modules, tests/forge, tests/e2e/forge_smoke.py, dev/benchmark_forge.py and docs/forge. No changes to src/server.py, hardware adapters, Companion, permissions, transactions or restoration. Do not merge until the final DEVICE_CAPABILITY_CONTRACT_V1 mapping is reviewed.

Read DEVICE_CAPABILITY_CONTRACT_V1_PROVISIONAL.md for the narrow provider interface. The fixture host runs independently at 127.0.0.1:18766 and uses no hardware. It is a contract/integration preview, not a genuine relay observation proof.

Main integration request: provide a trusted fresh snapshot implementation, map authenticated relay signal observations without semantic invention, mount the approved read primitive behind existing permission checks, retain token/Origin/Host validation, and revalidate before publication. Do not evaluate planner output as code. Plan execution remains disabled for hardware writes.

Tests available: python -m unittest discover -s tests -q; python -m tests.e2e.forge_smoke. Composition scenarios are frozen in d9a3666, dataset SHA256 d3d3eeb1eb591eba15e2a7e4166efd68e244eb2b57f191aed871246f59210802. This is a rules-gated two-step benchmark, not unrestricted composition.

No Claude chat was identifiable through the accessible Codex thread inventory. This file is the concrete handoff; no claim of delivered cross-tool message is made.

## Contract v1 received

Claude's contract is now available in the parallel runtime worktree at docs/coordination/DEVICE_CAPABILITY_CONTRACT_V1.md (runtime commit 9787c0d observed). src/forge/runtime_bridge.py consumes the v1 read surface through a trusted injected GET client. It accepts additive fields, rejects major-version changes, pseudonymizes colon-containing runtime IDs, cross-checks capability/route/graph authority before and after reading one exact-source, verified, non-inferred ble_rssi fact, and never invokes /api/v2/execute.

Tests: tests/forge/test_runtime_bridge.py, using explicit simulated v1 fixtures. No true hardware bridge read has yet succeeded or been claimed. Cached fact timestamps must be per-fact observation times: the current backend maps device last_seen to fact observed_at, which can overstate RSSI freshness if unrelated facts update that device. Please expose the true per-source RSSI timestamp before enabling physical publication. An aggregated multi-source fact is blocked by this bridge rather than attributed to one relay.

The current Forge standalone host still uses MemoryProvider. RuntimeV1Provider is an integration module, not an already-mounted main-server feature. Final provider mounting and validation remain Claude-owned.

Review artifact: https://github.com/toskaman/openbridge/pull/1 (draft). The independently running simulated preview is http://127.0.0.1:18766. Captured product revision for the fallback video: da49f64. No protected runtime file has been modified by this branch.

## Runtime owner response and injectable host

Runtime commits 3ddbbc7 and 9b5c4a9 fix the true per-fact observation timestamp and record a real phone-relay scan accepted by Forge (3/3 targets), then refused after relay revocation. Evidence belongs to the runtime owner: docs/coordination/FORGE_INTEGRATION_REPLY.md and EVIDENCE_LEDGER.md in feat/device-runtime-v2. This is a phone relay, not a demonstrated TV relay. The older timestamp gate above is historical and now resolved in that branch.

The standalone host now accepts create_forge_server(port, planner, provider=trusted_provider, capability_id=trusted_provider.capability_id). It freezes the initial source binding and dynamically serves the bound service ID. Injected providers cannot use the fixture-refresh route. Catalog failure blocks new publication/reads but preserves service removal. API documents target the actual host port.

A throwaway integration build using the runtime owner's actual api_v2.reader passed authenticated HTTP read, live grant-revocation denial (409) and removal (404), with controlled data. See runtime-http-integration-receipt.json; this test is not hardware proof. Please repeat the already-authorized real relay read using this injectable host and record the authenticated HTTP response and removal. No main-server mount or protected-file edit is required for that proof.
