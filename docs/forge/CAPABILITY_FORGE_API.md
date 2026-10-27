# Capability Forge API

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
