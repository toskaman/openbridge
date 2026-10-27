# OpenBridge release-readiness implementation plan

Goal: close the actionable backlog from the 106-document audit without weakening device authority, spending paid credits, or generating videos.

Architecture: keep the main runtime unchanged. Add a separate authenticated Forge coordinator around its trusted in-process read model, with explicit candidate selection and stable per-session provider binding. A launcher composes existing servers rather than modifying protected backend/adapters. English onboarding and documentation/attribution cleanup are independent work packages. Evidence distinguishes actual tests, mocked tests and unavailable external acceptance.

Constraints: English; no desktop computer use; no video. Targeted delta ZIP before existing-file edits, not whole-project backups. No hosted inference without a fresh eligible credit observation. Hardware/Companion/permissions/transaction/recovery source and src/server.py remain protected. Do not attest to organizer acceptance or a human final review. Do not submit publicly without a concrete reviewed pack and any required missing account information.

- [ ] English Windows onboarding: translate static/dynamic text; verify four widths, copy/status states and privacy with mocked daemon data.
- [ ] Reconcile stale docs and links against current receipts; preserve historical measurements/failures. Create a current release index and actionable statuses.
- [ ] Verify model/dependency license provenance against primary sources; complete THIRD_PARTY ledger without redistributing weights.
- [ ] Product coordinator: list only verified eligible runtime relay/target bindings; select opaque candidate token explicitly; isolate sessions; Host/Origin/bearer protections; no URL/provider/manifests/commands from callers; expiry/revocation and removal always respected.
- [ ] Workspace launcher: start main server and coordinator with existing reader and optional explicit local Glimmer; no hosted fallback or automatic scans. Main UI links to coordinator; coordinator links back. Main server source stays unchanged.
- [ ] Tests first for binding forgery/staleness, lifecycle, concurrency, source labels and authenticated HTTP; browser walkthrough including unavailable states and keyboard controls at four widths.
- [ ] Freeze broader current-planner evaluation suite, then evaluate rules/Llama/Glimmer locally under explicit bounded runs; report held-out limits, failures, metrics and memory. Keep frozen v1 scores unchanged. Spark diagnostic requires fresh eligible credits; build/mocked checks can proceed independently.
- [ ] Anonymous fresh clone plus isolated clean-environment setup and offline replay; distinguish same-machine replay from independent physical-machine validation. Record reproducible commands/hashes and guard unwanted I/O.
- [ ] Threat-model/release-fault/accessibility evidence and remote-unpairing scope; do not claim a full assistive-technology or independent-human audit from automated checks.
- [ ] Prepare submission evidence pack, scorecard with evidence/unknowns, portal fields and explicit owner-only confirmations. No video creation; no invented receipt.
- [ ] Review, run required CI, publish changes/PRs, send compact Discord product notification and save checkpoint. Continue autonomous tasks; request only genuinely missing external information.
