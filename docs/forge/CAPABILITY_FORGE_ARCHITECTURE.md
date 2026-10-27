# Capability Forge architecture

Status: independent integration preview on feat/capability-forge. Not merged into the main Device Fabric server.

The compiler (`src/forge/compiler.py`) accepts one strict version-1 manifest and emits deterministic OpenAPI 3.1, standalone Draft 2020-12 JSON Schemas, a fixed Python client and documentation. It never evaluates model text or generates executable handlers. The sole approved primitive is read_observations. Publication is an internal lifecycle operation, not a hardware action.

`src/forge/service.py` owns a bounded registry of at most 32 services and a bounded 200-event history. A trusted CapabilityProvider supplies current snapshots. Every publish, read and contract export rechecks verification, device presence, relay availability, identity conflicts, provenance binding, permissions and observation age. Removal atomically revokes the service under the same lock as reads. Service removal allocates or releases no worker, device handle or port. Reads already returned to a client cannot be recalled.

`src/forge/planner.py` validates complete two-step JSON plans. `meta_planner.py` uses pinned local Meta Glimmer by default when explicitly configured. A proposal does not execute or authorize publication. The rules route is selected explicitly and remains available independently.

`demo_host.py` is a separate loopback-only host so Claude-owned integration files are untouched. It uses MemoryProvider exclusively and is labeled SIMULATED throughout. Production integration must replace that provider with a trusted adapter bridge using the final Claude contract. Accepting an untrusted HTTP manifest as provider truth is forbidden.

Dependencies: Python standard library at runtime; optional existing local Ollama Meta brokers for planning. Tests: tests/forge. Proofs: browser-verification.json, screenshots and benchmark JSON. Limits: one approved observation primitive, fixed two-step composition, no live hardware binding, no main-site navigation integration yet.

The v1 consumer bridge is now implemented in runtime_bridge.py. It is tested against additive-field runtime fixtures and never dispatches actions. It has not been mounted into the main server. Physical publication is gated on true per-fact RSSI timestamps, final permission review and a real authenticated relay test.
