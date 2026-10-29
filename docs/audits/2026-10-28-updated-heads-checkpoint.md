# Updated owner heads checkpoint — 28 October 2026

Read this after earlier historical checkpoints. [Machine receipt](updated-heads-4f379e5-eb2de8b-f4f2360.json); collector `python -B -m dev.audit_v4_updated_heads --output <NEW_PATH>`. Original receipts are preserved.

## Narrow closures

- S1, proposed PR80 at4f379e534b776914468144aa7f5eebf581c32a2b: independently reproducing baseline dcf8527 yields2 effects and two receipts; revised code yields1 effect and identical receipts for2 concurrent callers. Actual Executor, fake runner, serialized effects; identical bounded delay on both revisions. Five new concurrency tests pass independently on the exact command Git blob. This closes the original in-process reproduction, not restart/crash durability or physical acceptance.
- Forge adapter, merged PR81 atf4f236075cbfce354b1b0cd809ee511f15d0652e: the real proposed PR72 Substrate class (366784f) now resolves module-level version/hash helpers. Unicode manifest hash matches the actual kernel helper. compile is explicitly overridden with a fake; real compiler/invoke/device acceptance remains unproven. This closes the earlier helper-resolution mismatch only.
- Previous PR72 S4/S5 closures at366784f remain limited to the separately retained admission/fact-trust probes. No merger or general security clearance is implied.

## Credit review still blocked

Revised PR78 at eb2de8b39068876c3525b97dddc9f357679ea1e7:15 focused allowance/runner tests pass independently using exact source/test blobs loaded into fresh in-memory modules. No runner main or Vault access occurred. Original timestamp CLI, per-file allowance/authz binding, whitespace refusal and migration tests are acknowledged improvements.

Same observation ID, timestamp, balance, authz and $0.80 allowance across two output-local SQLite files still accepts16 reservations totaling$1.60. This is synthetic reservation accounting only, no actual spending. Runner still uses out/budget.sqlite3. Required fix: an authoritative ledger across output paths/resumes and a cross-output regression. Observation identity should bind original timestamp/balance; authorization provenance/freshness policy still needs trust-owner approval. New CLI input alone is not an immutable persisted observation record.

## Remaining work

1. Credit/trust owner: shared accounting and canonical observation binding; approve explicit policy before live calls.
2. Muse/native: real compiler/invoke integration, approved model provisioning, inspected-source allowlist and target-aware proposal permission checks. PR79 improvements do not close these residual findings.
3. Sol: independently verify revised immutable heads and retain scoped failures/closures; freeze fair held-out evaluation only when contract/task provenance and gold permit it.
4. Joint owners: scoped physical acceptance, runtime reload/revision evidence, jury claims review and submission receipt. No video without a new explicit request.

Release remains BLOCKED. No provider/hardware calls, private-key access or spend. Existing production/protected/frozen artifacts unchanged. Collector first run failed because its bounded-delay replacement lacked time in its copied namespace; corrected before the retained run, with targeted delta backup D:/DevBackups/OpenBridge/OpenBridge_2026-10-28_19-43-42.zip containing dev/audit_v4_updated_heads.py only. No failure receipt was overwritten.
