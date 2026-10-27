# Capability Forge implementation plan

Date: 2026-10-27. Base: dff8ff8. Branch: feat/capability-forge.

Goal: turn verified observations into reusable, revocable, read-only local services.

Architecture: a strict provisional v1 manifest compiler emits deterministic documents. A provider interface supplies fresh trusted snapshots; a service manager reevaluates permissions and evidence on every read. A local-only Meta planner proposes structured plans that a deterministic validator checks. A separate loopback demonstration host avoids changes to core integration files.

Alternatives considered: modifying the main HTTP server would cause ownership conflicts; generating executable routes would add unnecessary risk. Use independent approved primitives and a narrow integration interface instead.

1. Write failing tests for manifests, compilation, lifecycle and planner references.
2. Implement compiler and fresh-snapshot provider/service interfaces.
3. Add standalone authenticated loopback host and generated client example.
4. Add Glimmer planner with exact model/digest checks and no cloud fallback.
5. Build a clearly simulated, accessible Forge walkthrough and inspect four widths.
6. Freeze at least 60 composition scenarios with separate held-out cases. Report raw results, including losses and unavailable routes.
7. Publish integration contract, proofs and branch commits; keep main untouched.

Constraints: no hardware adapters, main server, Companion, transaction, permission registry or recovery edits. No true relay success claim without real relay evidence. Missing runtime contract is an explicit integration gate, not permission to invent trust. No cloud call without current free-credit checks. No model can grant consent.
