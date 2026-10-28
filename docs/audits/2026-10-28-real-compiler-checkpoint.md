# Real compiler checkpoint — 28 October 2026

Latest review supersedes earlier claims of missing adapter/compiler integration tests. Historical reports and receipts are preserved.

## Verified

38 focused tests pass with zero skips:34 tests from merged PR82 at bc488db5c4d768ffda963ccbf461f2ba12af8617 plus4 real Forge/compiler tests from proposed PR72 at7e6196a097a082459e2c4d10f35d2260425e6397. The actual Substrate compiler, registry and contract are loaded from exact Git blobs. Its tests use synthetic Registry observations and a test signing key, not owned hardware.

The four integration tests establish real class helper resolution, compilation with matching manifest hashes, unsupported-primitive engineering escalation, and refusal mapping. These replace the prior fake-compile-only limit for this tested compiler slice. They do not exercise owner approval, signed installation, physical invoke/read-back, persistence or revoke as a complete journey.

PR82 closes the reproduced bare-src-prefix and target-grant-scope proposal gaps at the validator boundary. New source refs require a host-supplied allowlist; requested grants must fit the selected target scope. Host allowlist provenance itself remains a wiring responsibility. Optional model-set pinning is added and tested; echo-only provisioning remains available. Approval of real broker registry/digest/endpoint wiring cannot be inferred from a caller-provided set or the provisioning label alone.

[Immutable receipt and source hashes](compiler-integration-7e6196a-bc488db.json). Reproduce: `python -B -m dev.audit_v4_compiler_integration --output <NEW_PATH>`. Requires the pinned Git objects. Tests ran against the audit checkout f075f45 dependencies; the selected changed modules and schema/test fixtures are explicitly replaced from the pinned heads in disposable temporary source fixtures. The native worktree tool rejected sourceRoot outside this chat's registered workspace, so no managed worktree was created. Temporary fixture files are removed automatically. No shared production file was replaced.

## Still remaining, ordered

1. PR78 canonical ledger independent of output folders, cross-output regression and trust/owner policy acceptance. Head eb2de8b remains blocked; Claude's latest trust review agrees on the cross-output blocker. Do not use live credits through this path before resolution.
2. Merge-ready review of proposed native/command patches with owner integration; narrow tested closures are not proof they are on main or loaded by the live service.
3. Runtime broker provisioning and generator-to-compile-to-approval/install/invoke/revoke wiring, with immutable provenance and failure evidence. No novel physical generated capability is established by these tests.
4. Genuine held-out device/task gold and a competent rules baseline frozen before runtime generation. Preserve independence and distinguish kit specifications from executed tests.
5. Scoped physical acceptance, independently observed read-back/revoke/restart/cleanup, exact running revision, claim review and submission receipt. No video until a new explicit owner request.

Security/release gate remains BLOCKED. No provider calls, credentials, hardware, spend or protected/frozen-file changes. Only new audit collector/receipt/checkpoint files were added; no existing file required a delta backup in this checkpoint.
