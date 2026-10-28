# Verified publication plan

Goal: publish a new observation service only after owner consent, independently reread its trusted provider, and remove the new service if that first read fails. This is a provider/lifecycle verification read, not an HTTP transport test or a hardware scan.

Keep the existing low-level publish method for integrations needing staged setup. Add publish_verified to ForgeService and use it from the authenticated standalone host. The service lock covers creation, verification and cleanup so another request cannot observe an unverified intermediate service. Reject an already-published ID rather than replacing/removing an existing service during this flow. Preserve exact consent, immutable binding and current evidence checks.

Return the verified read as evidence in the publication response; the UI displays it automatically. Keep the separate authenticated Test service button for subsequent reads. Failure is explicit and leaves no newly published service. No model requests, hardware mutation or protected runtime files.

Validation: tests first for consent, changed observations, expiry/revocation/provenance loss/provider error, existing-service preservation, concurrent creation, authenticated HTTP failure cleanup and browser recovery. Run appropriate lifecycle and browser suites, independent review, commit, publish a new PR and record the resume checkpoint. No videos without an explicit owner request.

Implemented and reviewed: 294 guarded cross-branch tests, controlled authenticated HTTP lifecycle and seven browser modules pass. Review's archive-provenance issue is fixed and the pinned-commit run passes. See VERIFIED_PUBLICATION.md and verified-publication-test-receipt.json. Publication/CI status is tracked in ../RELEASE_STATUS.md and the new branch PR.
