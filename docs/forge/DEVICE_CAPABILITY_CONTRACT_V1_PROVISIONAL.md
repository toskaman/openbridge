# Provisional capability integration boundary

This document is not Claude's final DEVICE_CAPABILITY_CONTRACT_V1.md. That file was absent during the initial branch audit.

Implement CapabilityProvider.snapshot(capability_id: str) -> dict, conforming to the strict fields in src/forge/fixtures.py and compiler.validate_manifest. Return a newly read snapshot of permissions, source identity, availability and observations. It must derive from Claude's canonical registry and authenticated relay manager; never accept a client-authored assertion of verification. Snapshot lookup must fail for unknown or revoked capabilities.

Return pseudonymous device/relay IDs, exact authenticated RELAY:<relay_id> provenance, physical status REAL_HARDWARE_VERIFIED only after genuine relay verification, or explicit SIMULATED_VERIFIED for fixtures. Preserve observation Unix time and a bounded freshness limit. Expose only actually available signal/name/raw advertisement fields. No inferred battery or temperature fields.

ForgeService(provider) supports publish(manifest,consent=True), read(service_id), documents(service_id), remove(service_id), list_services(), history(), close(). Claude should keep authorization and auditing in the final integration layer. A bool passed internally as consent must be backed by a real owner authorization; model JSON is not that authorization.

MetaCapabilityPlanner(GlimmerBroker()).plan(manifests,now) returns a validated proposal trace and authorizes_execution=false. Revalidate against current provider state before publishing; no plan executes a hardware action. Integrate approved read handlers rather than model-generated code.

Compatibility gates: final contract mapping review, live revoked-grant test, authenticated relay response read, stale/conflicting/removed device tests, generated client against integrated host, clean service removal, no physical-write regression and final main-site navigation integration. Until these pass, the branch stays an independent simulated preview.

Superseded for runtime compatibility by Claude’s final v1 contract and src/forge/runtime_bridge.py. The strict Forge manifest remains an internal compiler representation, not a competing external contract. See INTEGRATION_HANDOFF.md for the received version and remaining timestamp gate.
