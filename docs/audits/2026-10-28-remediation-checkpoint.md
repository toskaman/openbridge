# Remediation checkpoint — 28 October 2026

## Independently verified closures

PR72 exact proposed revision366784fcbf039f18de26b3c7be60813eb70a76f6 closes narrow findings S4 (concurrent operation replay) and S5 (unverified/downgraded signed facts) in the retained isolated probes. Before8a73b8f:2 mocked effects,2 grant uses, no replay error; both fact gaps accepted. After366784f:1 mocked effect,1 grant use,1 replay rejection; both fact gaps rejected.

Reproduce with `python -B -m dev.audit_v4_remediation --output <NEW_OUTPUT_PATH>`. Requires both pinned PR72 Git objects. See [immutable receipt](pr72-366784f-remediation.json). The same bounded compile delay is used on both revisions; the original two-party compile barrier would block a correct pre-compile rejection. Real contract/schema, grant signing/admission, invoke and fact checks; compiler, device lookup and executor mocked. Five assertions pass. This is not a full PR72 suite or physical acceptance.

## Merged PR79 acknowledgement

At fcbe8e069cfce9e0e2318283ffa9aa5ee65deda6,31 focused tests pass independently. The three changed production module Git blobs were executed in fresh in-memory modules, followed by the exact test_v4_layer.py Git blob. No checkout production files changed.

Prompt projection now exposes bounded opaque targets and citable fact descriptors. Registry digest now hashes full descriptors, not only IDs. Model response echo mismatches are rejected. These improve earlier findings; historical receipts remain descriptions of their original revisions.

Residual proposal validation: validate_candidate accepts `src:nonexistent-uninspected-file` solely by prefix, and accepts required_grants=['control'] against an observe-only bundle when targeting a known opaque ID. No inspected-source allowlist or target permission binding is checked. This was reproduced with synthetic evidence and a read_facts chain. The local model factory still accepts an arbitrary requested model ID; matching the caller-supplied ID is not independently checking the approved Meta registry/digest. Its documentation requires broker-verified provisioning, so verify that boundary before runtime wiring. These are proposal/provisioning gaps, not proven live execution escapes.

The real Forge/Substrate instance adapter mismatch from the prior follow-up remains unresolved in the inspected code. PR78 remains unchanged at a6f194f4c851f7b530509f93780d36f1a4e28042; its cross-output accounting and canonical-time findings remain open. Main runtime S1 is not closed by the separate PR72 fix.

## Validation and next gates

Current audit checkout866a9b0 full suite:631 tests,42.075 seconds,OK. ResourceWarnings appeared for existing HTTPError/file cleanup; no failures. This does not include the full newer main/PR72 suite. New remediation collector:5 assertions pass. PR79 focused battery:31 pass.

Next owner actions: native owner S1; credit/trust owner PR78; Muse/native actual adapter; Muse bounded inspected-source provenance and approved model provisioning. Then Sol repeats exact-head probes. Held-out gold freeze, fair rules baseline, scoped physical demonstrations and final release/submission receipts remain separate gates.

Release remains BLOCKED. No provider or hardware calls, private key access or spend. New audit files only; no existing file replacements, so no delta backup required. Earlier reports remain historical and must be read with this checkpoint.
