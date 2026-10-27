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
