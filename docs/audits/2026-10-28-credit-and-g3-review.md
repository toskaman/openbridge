# Credit and G3 plan review — 28 October 2026

## Credit re-review

PR78 at42416d6cb17010f16d39647d8d8dc6a8583f4322:18 allowance/runner tests pass independently on exact Git source/test blobs in fresh in-memory modules. Runner main, Vault and provider transport were not invoked.

The canonical default fixes the previous default output-directory bug: same observation/authz/$0.80 allowance, two runs, one canonical temporary ledger =>8 accepted reservations,8 refusals,$0.80 total. Close that specific default-path finding.

The same pinned broker resolve_ledger accepts arbitrary explicit paths; runner exposes --ledger without requiring offline/mock mode. Two explicit ledgers with identical authorization =>16 accepted reservations,$1.60 total. Help text saying tests/one-offs does not enforce a live/test boundary. Hold live eligibility until arbitrary overrides are rejected for real transport or an independently enforced canonical allowance store caps all ledger paths. Keep test dependency injection available through an explicitly offline path. Also preserve trust-owner/owner decision on24h freshness and canonical observation binding. No actual excess spend is alleged.

[Retained default/override receipt](credit-shared-42416d6.json). Reproduce with `python -B -m dev.audit_v4_credit_shared --output <NEW_PATH>`. LOCALAPPDATA is patched to a temporary directory only within the probe; the real user ledger is untouched. Source dependencies were inspected from audit checkout0a58097; the target broker and test modules were loaded from exact PR78 blobs.

## G3 plan and submission pack — changes required before freeze

Source: merged PR83/main9167df8, docs/forge/G3_RUN_PLAN.md and docs/submission/DRAFT_PACK.md. These are correctly marked proposals, not execution authorization. No protected/owner document was modified here.

1. **Novelty/contamination:** the proposed TV mute mapping and target family already appear in public development fixtures and integration tests (PR72 tests/substrate/fixtures/manifest_tv_mute.json; tests/substrate/test_forge_wiring.py). A TV-mute run can be an integration smoke demonstration, not an unseen held-out capability. Rename/scope it accordingly or select a genuinely untouched target/task and freeze its independent gold before Muse sees it. Record registry absence; new IDs alone do not establish novelty.
2. **Independent oracle:** registry state.screen explicitly reads power/focused app, not audio mute. A following screen read cannot prove mute toggled. Define an independent supported mute-state or owner-observed audio oracle before generation and record UNKNOWN when unavailable. Do not invent an audio primitive or treat a generic signed receipt as audio truth. Initial state and exact restoration semantics must be recorded; repeated toggle is not an unconditional rollback.
3. **Fair ablation:** RulesPlanner always abstains and the plan explicitly expects ABSTAIN. That is a placeholder, not a competent baseline for a public known key mapping. Use the existing deterministic key mapping/template or a frozen capability-library baseline with comparable facts/permissions/time; retain ties or rules wins. No Meta advantage is established by defeating forced abstention.
4. **No recording authorization:** remove camera recording as a mandatory success condition. Current owner forbids all video until a new explicit request. An attended unrecorded run may retain permitted nonvideo receipts; do not silently turn supervision into recording consent.
5. **Claims:** model availability, parameters, cost and tokens need exact actual receipts. v1 empty explanations have no retained finish-reason evidence sufficient to establish the exact cause; say empty content with cause unconfirmed. Separate estimated costs from billed/total project spend. Qualify command dedup as the verified in-process/request scope, not crash-proof exactly-once effects.
6. **Demo packaging:** draft ~5min scene order is not the requested180-second artifact. Prepare a180-second textual scene order with only supported claims and truthful hardware-failure fallback, while leaving video creation/submission pending explicit owner approval. Do not weaken official deliverables just because recording is currently prohibited.

## Required frozen G3 acceptance fields

Before any generation: immutable source/primitive/skill registry hashes; unseen target/task commitment and contamination check; independently established fact/read-back gold; authorized primitive/permission/data scope; a competent no-model baseline; actual eligible model and approved credit record; bounded calls/retries/stop conditions; independent compile/sandbox checks; exact install/grant/physical read-back/revoke/restart/cleanup receipts. Missing gold remains NOT_FROZEN, and unsupported native mechanisms remain blocked engineering requests.

## Current remaining work

Credit override boundary and explicit policy approval; proposed PR72 integration/merge and trusted runtime model provisioning; unseen evaluation freeze and fair baseline; scoped end-to-end physical acceptance; correct jury claims and final submission receipt. PR80 is now merged in main1bb2215: earlier S1 closure is no longer only a proposed branch finding, but no live process revision/restart is asserted. PR72 remains proposed at7e6196a. Gate BLOCKED.

No provider calls, hardware, credentials, spending, video, production edits or protected/frozen evidence edits. New collector/receipt/review files only; no existing targeted files required backup.
