# Integration handoff to Claude

Latest runtime-owner confirmation: b5f1ab85622d6748b4c0712bfcdd72bada473ace records physical phone-relay HTTP publish/read/documents=200, read after relay revocation=409 and read after service removal=404. See that branch's EVIDENCE_LEDGER.md and FORGE_INTEGRATION_REPLY.md. This gate is closed for the phone relay; no TV or combined physical Glimmer orchestration is inferred.

The separate host remains the agreed integration surface. Optional model-memory endpoints prepare/release only the pinned local planner; they accept no device facts or arbitrary parameters. Existing virtual services can be removed while a model request is pending. No video generation is permitted until the complete project is finished, per the owner's latest instruction.

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


## Current integration status — 27 October 2026

The runtime owner has completed physical phone-relay publication through this host: publish/read/documents 200, read denied 409 after relay revocation, removed route 404. Earlier physical-publication requests above are historical and resolved. This evidence does not establish a TV relay or a combined physical Glimmer journey.

The host also exposes explicit local model prepare/release controls. Preparing sends no device facts, requires a new evidence refresh before planning, and never grants publication consent. Removing a service remains available during pending model operations; late completions cannot recreate the removed service. Injected simulated providers retain generic fixture identity throughout planning.

Reproduce cross-branch checks on the owner Windows machine with `python dev/forge_cross_branch_tests.py` and the configured Playwright browser cache. The helper assembles a disposable committed runtime plus the current Forge overlay, backs up only three replaced temporary files, and writes a new timestamped receipt under ignored `artifacts/integration/`. Its startup guard is self-tested, blocks non-loopback Python sockets/DNS, known local model endpoints and ADB device commands; `adb version` remains a dependency check. This guards these tests; it is not a general OS sandbox. Historical receipts without this guard are not proof of zero hardware I/O.

Runtime fixture cleanup request: close the caught HTTPError responses in tests/runtime/test_primitives.py (403/409) to avoid ResourceWarnings. Production adapter factory probing remains runtime-owned; the legacy HTTP unit fixture now supplies an empty adapter factory instead of invoking real discovery.

Video production remains paused by the owner until the entire project is complete. Final mounting, TV/inaccessible-device proof, richer composition evaluation and remaining product requirements are still open. Keep this PR draft pending integration validation.

Runtime e50c708 records Android TV relay observations accepted for 5/5 targets, then refused after revocation. This resolves the earlier TV-provider evidence gate. It does not prove the combined TV HTTP/Glimmer journey. Source-filtered facts are now available in the runtime and are the next Forge consumer integration task. No video work is authorized without a new explicit request.

Forge now consumes the source-filtered fact route added by the runtime owner. Controlled cross-branch evidence confirms selected -61 instead of aggregate -20, denied read after revocation, removed route 404, and no aggregate fallback for expired/unsupported filtered reads. See cross-branch-source-filter-test-receipt.json. The README correction is merged independently through PR #7; final Forge mounting remains runtime-owned.
