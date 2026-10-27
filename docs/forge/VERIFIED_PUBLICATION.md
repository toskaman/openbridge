# Verified publication

After owner consent, the Forge host creates an observation service and independently rereads its trusted provider. The successful publication response includes that read as evidence. If it fails, the new service is removed before returning PUBLICATION_VERIFICATION_FAILED. An existing service is never replaced or removed by this flow.

## Contract

`POST /api/publish` keeps its authenticated loopback/Host/Origin/JSON requirements and exact `{"consent":true}` body. Refused consent is checked before source access. A successful response retains service_id, state and simulation, and adds `verification` with state `verified` and the complete observation response in `read`.

The UI displays this read automatically. The separate Test service button performs a subsequent authenticated HTTP read. Publication verification proves current provider/lifecycle checks; it does not test HTTP transport by itself or guarantee future availability.

- PUBLICATION_VERIFICATION_FAILED (409): first read failed; only the newly created service was removed. The UI clears its plan/consent and requires an explicit new attempt.
- SERVICE_ALREADY_PUBLISHED (409): the existing service is preserved. Repeated publication does not replace it; it can still be read or removed.
- Other consent, eligibility, provenance and service-limit errors remain fail-closed.

Low-level `ForgeService.publish` retains its earlier staged, idempotent behavior. `publish_verified` is the all-or-cleanup flow. A reentrant lock prevents concurrent reads/listing of an unverified intermediate service. Those operations can wait while the trusted provider completes; this does not cancel a blocked provider. Pending model work stays outside that lock and retains the separately tested removal behavior.

No hardware scan, device mutation, permission grant, model inference or physical Undo occurs during publication verification. Fixtures remain SIMULATED; an injected physical provider is revalidated with its current authority and evidence.

## Validation

Tests cover changed observations, expired/denied/changed-source evidence, provider exceptions, failure cleanup, existing-service preservation, concurrent creation and prevention of intermediate reads. Browser checks at 390/768/1440/3440 pixels cover evidence display, cleanup, recovery and renewed consent.

The guarded cross-branch run passed 294 unit/integration tests, a controlled authenticated HTTP lifecycle and seven browser modules. Runtime dee5ba1 plus hashed Forge overlays; no real model/hardware calls; zero forbidden I/O attempts recorded. See [receipt](verified-publication-test-receipt.json). This is not a new physical relay or model-performance claim.
