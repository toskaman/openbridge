# Remaining work — audited 27 October 2026

Source: main `038f463`; shared coordination: [issue #36](https://github.com/toskaman/openbridge/issues/36). This is the current actionable backlog, superseding historical unchecked plans. Source inspection and contributor receipts remain distinct from newly repeated physical tests.

| Priority | Task | Owner / current status | Completion evidence |
|---|---|---|---|
| P0 | Preserve unresolved recovery receipts when the in-memory cap is reached | Claude B1 follow-up; review delivered, no published fix found | Failed-first saturation test; no UNKNOWN_TIMEOUT/FAILED/PARTIAL recovery state silently disappears; bounded refusal or durable retention; reviewed commit. |
| P0 | Close MCP endpoint/privacy and nonce-retention findings | Claude B1 follow-up; not published | Loopback target validation, explicit redaction boundary, expiry-aware replay handling, compatibility tests and documented remaining limits. Existing review is not a fix. |
| P0 | Deliver typed read-only route contract | Claude B2; absent from inspected shared handoffs | Operation/provider identity, graph revision, READY vs ACTIVE vs STANDBY, reasons, permission scope, freshness/lease, AUTO/PREFERRED/PINNED and retry/dedup semantics. |
| P1 | Implement Living Skill Graph UI against that contract | Codex; M1 rev1.2 design reviewed, backend-dependent | Real backend state, unavailable reasons and evidence; immediate revocation, four-width/keyboard tests; simulated evidence labeled. No fabricated routes. |
| P1 | Define fair unseen protocol/multi-hop evaluation | Spark design review + Codex harness; depends on B2 | New frozen cases/splits before inference; matched rules baseline, full failures/tokens/latency and separate deterministic policy scores. Existing v2 is only fixed observation-publication planning. |
| P1 | Integrate multi-PC support in OpenBridge | Assessment complete; previously blocked port remains unimplemented | Confirm permitted scope using the exact prior safety rejection; verify source provenance; retain authenticated identity binding, explicit target choice, no broadcast and controlled multi-session tests. Existing bridge 10-test suite passed locally; that is not OpenBridge integration. |
| P1 | Prove fresh TV-to-phone BLE failover | Claude hardware/routing; not proved end-to-end | Real TV route loss, new phone scan with fresh provenance, PINNED refusal, both unavailable and permission-revocation checks. Separate phone/TV scans do not establish failover. |
| P1 | Signed Companion UI and Watch-to-TV action | Claude B3; not proved | Actor-scoped authorized manifest, physical Watch action, target response/read-back and revocation. Current direct PC-to-watch ADB sweep is a different direction. |
| P1 | Coordinate live-app reload | Runtime owner + Codex; long-running wrapper may retain older imports | Check active operations/recovery first; restart only the owned service, verify actual loaded revision and read-only entrypoints. No uncoordinated interruption of hardware work. |
| Release | Final participant review and portal submission | Owner; fields/attestations/receipt outstanding | Confirm private eligibility/declarations, final revision, portal-required assets and actual submission receipt. Track/theme/solo credit already confirmed; do not ask again. |
| Hold | Any video/recording/render | Owner-only trigger | NEW explicit owner request, even after project completion. No automatic video work. |

## Completed and retained

- Trusted Forge selector, source-bound workspace lifecycle and physical TV publication/removal; separate exact-source hardware receipts.
- Frozen v2 evaluation: Rules/Llama/Glimmer 80/80 total; each model made 25 calls, with 45 deterministic refusals and 10 harness scope refusals separately counted. No general superiority claim.
- Spark synthetic diagnostic and recorded Spark/Wonder design contributions. No new hosted call in this audit.
- Release evidence PR37, exact-action consent PR39 and remote input validation PR40 merged after their passing checks.
- M1 revision1.2 proposal includes reviewed state semantics, data-boundary copy, exact PC command disclosure, evidence labels and focus-safe revocation. It is a proposal, not a shipped graph or a new provider inference receipt.
- New Blackview and Watch7 sweeps recorded in DEVICE_CAPABILITIES; do not erase Xiaomi/standby failures or relabel these as Watch-to-TV proof.

Runtime models remain Meta-only; hosted requests require the existing fresh promotional-credit guard and have no paid fallback. No desktop keyboard/mouse automation. No keys or private device identifiers in public evidence. Each contributor must name changed paths and report commits/tests on issue36; protected runtime changes remain Claude-owned unless ownership is explicitly handed over.
