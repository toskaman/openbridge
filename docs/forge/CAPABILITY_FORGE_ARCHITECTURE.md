# Capability Forge architecture

Status: standalone Forge host merged into the release. A normal runtime-bound main-app entrypoint remains next work; main-process mounting is optional. See [release index](../RELEASE_STATUS.md).

The compiler (`src/forge/compiler.py`) accepts one strict version-1 manifest and emits deterministic OpenAPI 3.1, standalone Draft 2020-12 JSON Schemas, a fixed Python client and documentation. It never evaluates model text or generates executable handlers. The sole approved primitive is read_observations. Publication is an internal lifecycle operation, not a hardware action.

`src/forge/service.py` owns a bounded registry of at most 32 services and a bounded 200-event history. A trusted CapabilityProvider supplies current snapshots. Every publish, read and contract export rechecks verification, device presence, relay availability, identity conflicts, provenance binding, permissions and observation age. Removal atomically revokes the service under the same lock as reads. Service removal allocates or releases no worker, device handle or port. Reads already returned to a client cannot be recalled.

`src/forge/planner.py` validates complete two-step JSON plans. `meta_planner.py` uses pinned local Meta Glimmer by default when explicitly configured. A proposal does not execute or authorize publication. The rules route is selected explicitly and remains available independently.

`demo_host.py` is a separate loopback-only host. Its default MemoryProvider remains explicitly SIMULATED. Trusted internal callers can inject RuntimeV1Provider and its capability ID, bound through `api_v2.reader(server)` to the final runtime contract. HTTP/model inputs cannot choose providers or establish authority. Accepting an untrusted HTTP manifest as provider truth is forbidden.

Dependencies: Python standard library at runtime; optional existing local Ollama Meta brokers for planning. Tests: tests/forge. Proofs: browser-verification.json, screenshots and benchmark JSON. Limits: one approved observation primitive, fixed two-step composition, physical phone/TV injected-provider proof exists; no normal main-site navigation integration yet.

The v1 consumer bridge is now implemented in runtime_bridge.py. It is tested against additive-field runtime fixtures and never dispatches actions. It has not been mounted into the main server. True per-fact RSSI timestamps, source-filtered reads, authenticated phone/TV publication and revocation/removal gates are proven. The bridge refuses missing/expired filtered facts without aggregate fallback. See [TV journey](TV_GLIMMER_JOURNEY.md). Product integration and independent security acceptance remain open.
