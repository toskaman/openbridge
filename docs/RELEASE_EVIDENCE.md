# Release evidence index

Receipts: docs/physical-package-receipt.json, agent-loop-receipt.json, crash-recovery-receipt.json, glimmer-smoke-receipt.json, local-meta-adb-receipt.json, runtime-meta-receipt.json, physical-transaction-attempt.json (refusal). Benchmarks: docs/benchmark/. Screens: docs/jury/screens/. Full chronological log: EVIDENCE_LEDGER.md. Baseline: DEVICE_FABRIC_BASELINE.md. Limitations: KNOWN_LIMITATIONS.md.

## Latest integrated evidence — 28 October

- [Complete TV-to-phone handover](release/COMPLETE_HANDOVER.md), with [export/provenance metadata](release/failover-evidence/complete-handover-20261028.metadata.json), preserving [earlier partial attempts](release/PHYSICAL_FAILOVER_FOLLOWUP.md).
- [Watch hold-to-TV acceptance and limits](release/WATCH_CONTROL_ACCEPTANCE.md).
- [PR57](https://github.com/toskaman/openbridge/pull/57): merged `ad7e2fc`; tested head `48c7275`, 508 local tests and six passing CI checks. Source integration does not assert live deployment.
- [Current release gates](REMAINING_WORK.md); persistence PR56 remains excluded.

- [Preregistered synthetic routing results](evaluation/routing-v1/RESULTS.md): full inputs/gold/decisions and exact harness; actual Meta Spark design-review receipt, separately attributed from deterministic routing scores.
