# Release evidence index

Receipts: docs/physical-package-receipt.json, agent-loop-receipt.json, crash-recovery-receipt.json, glimmer-smoke-receipt.json, local-meta-adb-receipt.json, runtime-meta-receipt.json, physical-transaction-attempt.json (refusal). Benchmarks: docs/benchmark/. Screens: docs/jury/screens/. Full chronological log: EVIDENCE_LEDGER.md. Baseline: DEVICE_FABRIC_BASELINE.md. Limitations: KNOWN_LIMITATIONS.md.

## Latest integrated evidence — 28 October

- [Complete TV-to-phone handover](release/COMPLETE_HANDOVER.md), with [export/provenance metadata](release/failover-evidence/complete-handover-20261028.metadata.json), preserving [earlier partial attempts](release/PHYSICAL_FAILOVER_FOLLOWUP.md).
- [Watch hold-to-TV acceptance and limits](release/WATCH_CONTROL_ACCEPTANCE.md).
- [PR57](https://github.com/toskaman/openbridge/pull/57): merged `ad7e2fc`; tested head `48c7275`, 508 local tests and six passing CI checks. Source integration does not assert live deployment.
- [Current release gates](RELEASE_STATUS.md); corrected persistence is integrated through [PR59](https://github.com/toskaman/openbridge/pull/59).

- [Preregistered synthetic routing results](evaluation/routing-v1/RESULTS.md): full inputs/gold/decisions and exact harness; actual Meta Spark design-review receipt, separately attributed from deterministic routing scores.

## Latest integrated evidence — 29 October

- [Sealed held-out skill synthesis](evidence/v4/g3-sealed/attempt3_SUCCESS/REVEAL.md): commit-reveal spec, 2 KILLs retained, final SUCCESS loop on live TV ($0.0203).
- [Companion 0.10.0 release notes](release/COMPANION_0_10_0.md): full-control toggle + popup, uiautomator proof table, wire flag true/false.
- [VM fleet proof](evidence/vm-fleet-29oct.md): agent handshakes on Debian 13 x2, Debian 12, Ubuntu 22.04, ARM64; XP/Win7/x86 honest blockers.
- [Machine-readable device registry](DEVICE_EVIDENCE.json) + generated [hardware matrix](HARDWARE_TEST_MATRIX.md), CI-gated (`tests/unit/test_device_registry.py`).
- Peripheral depth (PR111): full tuya surface, vacuum seek beep + facts on hardware, Freebox leases + 127 hosts.
- Suite: 835 tests green; live server on current main with phone + TV paired.
