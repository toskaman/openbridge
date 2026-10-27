# Capability Forge API

## Trusted provider injection

`create_forge_server(port, planner, provider=trusted_provider, capability_id=trusted_provider.capability_id)` now binds an existing capability through a trusted internal provider. HTTP and model inputs cannot select providers or supply commands. The initial snapshot fixes device, relay, source, status, capability and service identity. Subsequent snapshots must retain that binding and remain eligible.

GET /api/catalog reports `mode`, `available`, `fixture_reset_enabled`, `observation_path`, current services and bounded history. If authority fails, manifest is null and a safe error is returned; service removal remains available. The literal observation route uses the validated service ID. Exported contracts and clients use the actual numeric loopback port. Injected providers can never be overwritten through POST /api/reset-fixture. Refresh availability only rereads existing provider state; it starts no scan.

`runtime-http-integration-receipt.json` records real authenticated HTTP using Claude's actual v2 reader in a throwaway integration build: controlled observation read, denial after grant revocation (409), removal (404). This is controlled data, not physical proof. Runtime-owner commits 3ddbbc7 and 9b5c4a9 separately fix timestamps and record real phone-relay snapshots. Physical HTTP publication through this injectable host still needs its own proof.

The optional `--glimmer-cpu-v2` flag selects only the explicitly started isolated CPU Meta service; it is mutually exclusive with `--glimmer`. The default CLI remains simulated with no configured model.

Run `python -m src.forge.demo_host` from the branch checkout. Open http://127.0.0.1:18766. Optional `--glimmer` configures the existing pinned local Muse Glimmer broker; it does not start a model service or fall back to cloud.

GET /api/session supplies an ephemeral bearer token to the same-origin local page. All data and mutation routes require Authorization: Bearer <token>. Mutations additionally require exact Origin. Never put tokens in URLs, generated documents or screenshots.

- GET /api/catalog: simulated manifest, service inventory, bounded history and planner configuration.
- POST /api/plan with {"planner":"glimmer"} or {"planner":"rules"}: untrusted proposal only; no publication.
- POST /api/publish with {"consent":true}: publish the server-owned fixture after current checks. Caller-provided manifests, commands and URLs are rejected.
- GET /v1/services/ble-observations/observations: fresh read-only synthetic relay response.
- GET /api/documents: generated OpenAPI, standalone schemas, fixed client, documentation and manifest hash; also enforces current grants.
- POST /api/remove with {}: idempotent revocation.

Errors: 400 invalid body; 401 absent bearer; 403 Host/Origin denied; 404 absent route or removed service; 409 current permission, freshness, provenance or model failure; 413 oversized body. No CORS access is granted. Query-selected commands and arbitrary endpoints do not exist. The generated client targets the default 18766 port; custom demo-host ports are for testing and require an explicit client endpoint update during integration.

Tests: tests/forge/test_http.py exercises real loopback HTTP, authentication, origin, host, body bounds, lifecycle and unavailable Meta. This API is a standalone integration host, not a claim that main src/server.py exposes these endpoints.
