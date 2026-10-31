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

## Latest integrated evidence — 30 October (PR127–PR154, main `4299343`)

- [P0 hardening](KNOWN_LIMITATIONS.md): pairing attempt limits, supervised STT worker, relay-scan HTTP verification, BridgeWindows plaintext warnings, HTTP/direct idempotency journal claims.
- [Device connect](RELEASE_STATUS.md): hardware agent matrix + auto planner + per-device tutorials (PR133); multi-PC bridge + legacy XP/Win7 QEMU proofs ([legacy](evidence/vm-legacy-xp-win7-30oct.md)); capability explorer, hardware intel, permissions center (PR140–142).
- [Eval-kit baseline](benchmark/EVAL_1000_RULES_BASELINE.md): 1,000-turn replay harness, rules 1.4%.
- [DAG orchestration](evidence/s7-live-usb-30oct.md) + [official AVD](evidence/avd-ob-pixel-30oct.md) (rows 17–18); [relay dashboards](evidence/g04-watch-30oct.md); [RetroArch loopback](evidence/retroarch-loopback-30oct.md) (row 19); [stress report](STRESS_14_REPORT.md) (crash drill 5/5).
- [`openbridge` CLI + jury release](release/P30_GATES_AND_REPORT.md) (PR149 `73cfef5`): tiers, budget, doctor, parity, pack VERIFY OK; 2 Glimmer candidates validated+revoked (row 20); phone+AVD orchestration sha-verified (row 21).
- [G04 watch native UI](evidence/g04-watch-30oct.md): QUICK CONTROLS + long-press loop on Watch7 (row 22); TV/phone 0.11.0 PAIRED shots (rows 23–24).
- [Companion 0.12.0 LAN discovery](evidence/companion-lan-discovery-30oct.md): NSD advert + QU-bit browse + `companion_lan` onboarding, 3/3 devices (row 25); watch UI rescale.
- Vacuum liveness re-verify: facts + seek accepted, docked (row 26).
- Suite: 1150 green (1138 `def test` + 5 assigned + 7 inherited, collection-diff verified); Windows + Ubuntu + browser CI green on main. Live :18765 still on an older commit (reload owner-gated).
