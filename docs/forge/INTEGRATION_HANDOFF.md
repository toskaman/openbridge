# Integration handoff to Claude

Branch: feat/capability-forge. First compiler/lifecycle/UI commit: d9a3666. Base: dff8ff8.

Worktree: C:/Users/TheBox/Desktop/Hackaton/OpenBridge-capability-forge.

Owned files are new src/forge modules, tests/forge, tests/e2e/forge_smoke.py, dev/benchmark_forge.py and docs/forge. No changes to src/server.py, hardware adapters, Companion, permissions, transactions or restoration. Do not merge until the final DEVICE_CAPABILITY_CONTRACT_V1 mapping is reviewed.

Read DEVICE_CAPABILITY_CONTRACT_V1_PROVISIONAL.md for the narrow provider interface. The fixture host runs independently at 127.0.0.1:18766 and uses no hardware. It is a contract/integration preview, not a genuine relay observation proof.

Main integration request: provide a trusted fresh snapshot implementation, map authenticated relay signal observations without semantic invention, mount the approved read primitive behind existing permission checks, retain token/Origin/Host validation, and revalidate before publication. Do not evaluate planner output as code. Plan execution remains disabled for hardware writes.

Tests available: python -m unittest discover -s tests -q; python -m tests.e2e.forge_smoke. Composition scenarios are frozen in d9a3666, dataset SHA256 d3d3eeb1eb591eba15e2a7e4166efd68e244eb2b57f191aed871246f59210802. This is a rules-gated two-step benchmark, not unrestricted composition.

No Claude chat was identifiable through the accessible Codex thread inventory. This file is the concrete handoff; no claim of delivered cross-tool message is made.
