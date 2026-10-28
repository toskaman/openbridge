# Remaining work — reconciled after PR #57

Verified integration: `ad7e2fc1a62ee872c433ea1f5a64c63a20d844f0`. PR #54 history and PR #57 fixes are merged. Final feature head `48c7275` passed 508 local tests, six CI checks, six local browser suites and responsive main/Forge checks. These are software results; the running hardware service has not been reloaded to this revision.

Corrected persistence is delivered through [PR59](https://github.com/toskaman/openbridge/pull/59), preserving PR56 history: [saved completed unresolved outcomes and routing policies](runtime/PERSISTENCE.md) use coordinated atomic updates, corrupt-state blocking and explicit write errors. Eleven focused persistence tests and 519 local tests passed; exact-head CI/review is recorded on the PR. This does not assert live deployment or pre-dispatch crash recovery.

Delivered: [complete contributor-recorded TV-to-phone handover](release/COMPLETE_HANDOVER.md), [qualified Watch hold-to-TV action evidence](release/WATCH_CONTROL_ACCEPTANCE.md), controller initialization and grant ordering fixes. The original two-tap/sixteen-action cause remains unproven. Duplicate delivery and expiry have unit coverage, not physical acceptance. Hardware demonstrations are not scored evaluations.

| Priority | Remaining gate | Owner and next concrete action | Acceptance evidence |
|---|---|---|---|
| P1 | Frozen unseen evaluation | Codex prepares harness/design; Spark reviews the frozen design before results | Commit case set, separate gold, metrics, baselines, abstention and failure schedule before any scored run. Existing handover cannot be retroactively scored. No hosted inference until eligible fresh promotional-credit guard. |
| P1 | Hardware cleanup and acceptance limits | Claude: reconcile owner hardware state and retained receipts | Confirm earlier location-restoration request and test relay/forward cleanup; retain uncertainty where independent proof is unavailable. Do not change settings without exact baseline. |
| P1 | Revised control hardware edge cases | Claude: coordinate owner-attended targeted validation | Same-request duplicate and expired request produce no second action; preserve original amplification as unresolved unless evidence establishes cause. No automatic grant or broad replay. |
| Release | Coordinated live reload | Runtime owner + Codex, after active work/state check | Exact loaded revision, preserved pending recovery/open changes, read-only endpoint checks; no interruption of active contributor tests. |
| Release | Participant review and submission | Owner | Final commit, portal-required fields, private eligibility/terms declarations and actual submission receipt. Track/theme/solo already confirmed. |

Supported read-only multi-PC review is complete; OpenBridge remains single-PC and the previously safety-blocked port is not retried. Scheduling remains cancelled. Claude's main theme is retained. No videos until a NEW explicit owner request; no desktop keyboard/mouse automation, new hosted spending or automatic control grants.

The snapshots below are historical and may describe superseded blockers or scheduling.

---

# Current update — 28 October 2026, physical rerun

Latest audited main: `0aed8a6` (relay fixes #51–#53), 489 local tests passed. [New two-relay transcript](release/PHYSICAL_FAILOVER_FOLLOWUP.md) records a verified TV scan, TV-loss refusal, automatic selection of the phone and PINNED refusal; the fresh phone scan was blocked as Bluetooth turned off. This remains PARTIAL, not complete failover or a scored evaluation.

PR #54 watch/Companion controls remain unmerged: two taps produced sixteen executions in the reported run. Codex review requires root-cause isolation, revocation-race and poller-lifecycle fixes, request-expiry binding and a clean single-intent rerun; long-press/rate limits alone are insufficient. Location is still enabled on the phone and TV; the earlier requested restoration is not confirmed. No additional settings writes were made in this rerun.

The requested subsequent [multi-PC review](release/MULTI_PC_REVIEW.md) is complete at read-only scope: existing bridge fake tests11/11 pass, OpenBridge remains single-PC, and the earlier safety-blocked port is not retried. Scheduling remains cancelled. Current blockers are the phone radio instability, full device-cleanup confirmation and B3 repeated-action defect. No videos until a NEW explicit owner request.

---

# Integration update — 28 October 2026

B1 revised recovery/MCP/nonce fixes and B2 rev2 schema/contract helpers are integrated for combined verification, together with Claude's owner-selected application theme and onboarding. This does not implement the B2 routing endpoints or physical failover. Codex added tested APK expiry/timer fixes and an in-flight dedup expiry regression fix. Multi-PC work is deferred to 29 October 09:00 Paris for supported-scope review, not an automatic retry of the previously blocked port. The dated audit table below is historical; current review status is on issue36 and the integration PR. Videos remain on explicit owner hold.

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
