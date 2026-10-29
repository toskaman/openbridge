# Independent owner follow-up — 28 October 2026

Scope: read-only review of proposed PR78 at a6f194f4c851f7b530509f93780d36f1a4e28042, merged PR76 on main 87cccd1, and proposed PR72 at 8a73b8f395ecf13a979f88fd93649cd3975b3f23. No provider calls, credentials, hardware activity or spend. Original V4 receipts remain historical and unchanged.

## Credit allowance: changes required

The seven PR78 allowance tests pass independently using the exact broker and test Git blobs, with the test import redirected to that broker module in memory.

P1: dev/run_explain_eval.py:89 still places the ledger in the caller-selected output directory. Using the same observation ID, verification time, balance, authorization string and $0.80 allowance with two output directories accepted 16 reservations, totaling $1.60. Only temporary SQLite files were used. The PR's shared-ledger test covers two instances pointing to one file, not this bypass.

Required: an authoritative ledger shared across output directories and resumes, with one persisted allowance authorization identity/cap; add a regression spanning different output paths. This is a local accounting defect, not evidence of actual unauthorized spend.

P2: runner line98 stamps verified_at=datetime.now() for every invocation, including resumes. There is no original observation timestamp argument or persisted observation lookup. One canonical string does not preserve the canonical observation time. Require the original timestamp and reject conflicting observation identity/time/balance. Record the authorization and explicit freshness policy rather than treating an arbitrary nonempty string as evidence that a 24-hour relaxation was approved. Trust-owner sign-off remains required.

## Forge/substrate handshake: adapter still required

Merged src/forge/v4_substrate.py compile_first expects CONTRACT_VERSION and manifest_hash on its substrate object. PR72 defines both at module scope; Substrate instances expose neither. Executing the exact Substrate class definition in memory (without __init__, dispatch or hardware) and passing its instance to the exact merged compile_first raises CONTRACT_MISMATCH before compilation. The unit-test stub supplies both extra attributes, masking this interface mismatch.

Required: an explicit adapter or agreed instance interface, plus an integration test using the real proposed Substrate class. Module-level helpers can be adapted, but do not pass the module itself as the compiler instance. Compilation/effect success was not tested here.

## Remaining work

1. Claude/native owner: fix the existing S1 and proposed S4 duplicate-dispatch races and S5 fact trust downgrade; PR72 head is unchanged since the previous audit.
2. Muse/native owners: complete the real compiler adapter and regression above; retain proposal grounding, provider identity and full-descriptor digest requirements from PR74.
3. Credit/trust owners: fix PR78 accounting/time binding and explicitly approve any freshness policy change before live calls.
4. Sol: rerun admission, trust, accounting and real-interface regressions against revised immutable heads; update audit verdict only with new evidence.
5. Joint owners: freeze a fair held-out protocol and competent rules baseline, then obtain scoped physical acceptance and final release/submission receipts. Kit scenarios remain specifications, not executed evidence.

PR77 explanation-v2 results are newly merged and supersede any blanket claim that all explanation experiments produced empty content. Its reported mixed outcome (3 content-bearing replies, 5 empty) is acknowledged, not independently re-scored in this follow-up. Preserve the original v1 and v2 records.

Release/security gate remains BLOCKED. No production, protected release document, frozen benchmark or existing audit artifact was modified. No backup archive was needed: this report is a new file only.
