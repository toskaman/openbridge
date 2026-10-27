# Resume checkpoint - 27 October 2026

## Owner constraints

- No video generation, recording, editing, rendering or new publication until a new explicit owner request, including after project completion.
- All responses, product content and public docs in English. No desktop keyboard/mouse automation.
- Runtime inference uses Meta models only. Cloud requests may use promotional credits only with fresh verification; no paid fallback. The earlier $148 confirmation is stale. Keep the DPAPI-protected key out of logs, arguments, browser state and Git.
- Runtime owner retains hardware adapters, main server integration, Companion, permissions, transactions and recovery. This branch changes only Forge, tests, CI, tooling and docs.
- Targeted delta backup before changing existing files to D:/DevBackups/OpenBridge; purge archives older than 90 days; report files/location. Required compact English Discord changelog after a completed milestone.

## Workspace and services

Worktree: C:/Users/TheBox/Desktop/Hackaton/OpenBridge-capability-forge. Branch: feat/forge-verified-publication, based on already-merged Forge work. Reuse this isolated worktree. Check git status/log and GitHub checks before continuing.

Forge preview restarted at http://127.0.0.1:18766 with python -m src.forge.demo_host --glimmer-cpu-v2 (managed command session 47996). SIMULATED observations, no hardware. Local CPU Meta endpoint 11439 is separately running; startup made no inference request. Fixture evidence expires after 120 seconds: explicit fixture refresh required. Do not stop unrelated model services. The main app was not listening on 18765 when checked; mounting/restart coordination remains runtime-owned.

## Completed foundations

- Forge PR #1 merged as 767dcdb; its last checked CI jobs passed.
- README correction PR #7 merged as dcb71c3: measured Glimmer explanations 56/60 (93.3%) first, rules have no scored prose output, full planning/goal-fit results retained. No invented superiority or diagnosis score.
- Runtime-owner physical phone HTTP proof: publish/read/docs 200, read 409 after revocation, removed route 404. TV provider accepted 5/5 targets, then refused after revocation (e50c708). TV permission involved a dev-harness grant and journaled changes, not complete product-consent proof.
- Spark diagnostic implemented and mocked-tested. One live attempt BLOCKED, one $0.10 reservation retained, no retry; accepted diagnosis/usage/cost unknown. Stale $148 balance cannot authorize another call. See SPARK_DIAGNOSTIC.md.
- Windows bridge PR #8 merged on main; do not duplicate adapter work.

## Current change: verified publication

ForgeService.publish_verified requires exact consent, rejects an existing service ID, creates a service and independently rereads trusted evidence under its lifecycle lock. Failed verification removes only the new service and returns PUBLICATION_VERIFICATION_FAILED. Low-level publish remains for staged integrations. This verifies provider/lifecycle data, not HTTP transport or a new scan.

Standalone POST /api/publish uses this flow and refuses false consent before provider access. UI displays the verified read automatically. Failed verification clears plan/consent, explains removal and requires an explicit new attempt. Test service remains a separate authenticated HTTP read.

Tests cover freshness, permission/provenance/provider failures, preservation of existing services, concurrency, intermediate-state isolation, HTTP cleanup and four-width recovery. Review found no important publication defects. Its receipt-provenance issue was fixed: archive the captured runtime revision, freeze overlay bytes and record hashes. Runner now handles already-merged Forge folders, backing up only differing existing overlay files.

Pinned runtime dee5ba1 plus current overlay passed 294 tests, authenticated runtime HTTP lifecycle and seven browser modules; zero forbidden attempts in the self-tested Python I/O guard. Controlled evidence, not new hardware/model proof. See verified-publication-test-receipt.json. Artifacts and exact backup file lists: artifacts/forge-publication/. Check new branch CI/PR status after publication.

## Next

1. Publish/finish the verified-publication PR after checks, preserving its exact evidence scope.
2. Coordinate main-process mounting with trusted runtime reader and explicitly bound relay/target; no silent physical source selection or protected server edits.
3. Complete physical TV HTTP + local Glimmer product journey with fresh evidence; distinguish device consent from harness grants.
4. Expand composition evaluation beyond narrow two-step selection; preserve frozen v1 results.
5. No video work without a new explicit owner request.

Earlier checkpoint history remains in Git; this file describes current state.
