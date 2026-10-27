# Runtime v2 — initial audit (HEAD dff8ff8, 27 Oct 2026)

Evidence: `git rev-parse HEAD` = dff8ff8155655a22131e2a3dd0f89ca0e334226b, clean tree; `python -m compileall` OK; `python -m unittest discover -s tests` → 175 tests OK (Windows, Python 3.14); GitHub CI green for dff8ff8 and 547f542. Branch `feat/device-runtime-v2` created in an isolated worktree.

| Priority | Finding | Evidence | Plan |
|---|---|---|---|
| P0 | No shared, versioned capability contract; `src/fabric/contracts.py` has observations/links but no CapabilityDescriptor, ActionDescriptor, ReversibilityClass, TransactionReceipt, RecoveryState | contracts.py | `src/runtime/contract.py` + docs/coordination/DEVICE_CAPABILITY_CONTRACT_V1.md + golden-schema compatibility test |
| P0 | Capability states conflated: `Capability.level/status` mixes "observed", "read", "restore"; nothing distinguishes DISCOVERED/OBSERVED/READABLE/CONTROLLABLE/REVERSIBLE/VERIFIED | contracts.py, discovery.py | capability engine with six independent flags + evidence, contract tests per adapter |
| P0 | No stable backend for a second module (Capability Forge): graph, facts, capabilities, admissible operations and events are only reachable through UI-oriented routes | server.py (526 lines, 24 handlers) | `/api/v2/*` read routes + primitive registry; actions only through registered primitives and the existing gate |
| P0 | Diagnostics are raw facts; no interpretation separating API-returned facts from inferences | android.py inspect, freebox_auth | diagnostics module with `observed` vs `inferred` findings |
| P1 | Relay observations have no freshness, provenance per observation, or stale detection; rotating BLE addresses only handled implicitly | relay.py | timestamps, relay id per observation, staleness, rotating-id policy |
| P1 | Optional-app allowlist is 3 fixed packages (2 Xiaomi-specific) | android_package.py:11 | keep allowlist for writes; add read-only identification of candidate optional apps with reasons |
| P1 | Doc divergence: Wi-Fi ADB marked IMPLEMENTED_UNVERIFIED although verified on the TV | HARDWARE_TEST_MATRIX.md:6, DISCOVERY_PROTOCOLS.md:7 | correct statuses |
| P1 | Reliability gaps not covered by tests: USB loss during write (mock), device replaced under same IP, inconsistent read-back, concurrent primitive requests | tests/ | add recovery/concurrency tests |
| P2 | Routers/protocols absent (OpenWrt, FRITZ!Box, HA, ESPHome, Matter) — no hardware | ROUTER_ADAPTERS.md | remain UNSUPPORTED |

Coordination: GPT-6.1 owns Capability Forge, Meta planner, virtual capability API, UX, benchmarks. This branch owns adapters, transport, identity, permission broker, journal, Companion and backend integration.
