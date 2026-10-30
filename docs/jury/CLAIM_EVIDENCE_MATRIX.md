# Claim / evidence matrix (V4-02)

Every public claim, its status and where to check it. A claim without evidence is listed as pending, never implied.

## Status vocabulary (repo ↔ V4 pack)
| Repo status | V4 pack equivalent | Meaning |
|---|---|---|
| REAL_HARDWARE_VERIFIED | IMPLEMENTED_HARDWARE_TESTED | ran on the author's real device(s); receipt with commit and date |
| INTEGRATION_VERIFIED | IMPLEMENTED_HARDWARE_TESTED (partial) | end-to-end through real services, not every device |
| SIMULATED_VERIFIED | IMPLEMENTED_SIMULATED | CI tests with fakes / synthetic data, labelled SIMULATED |
| IMPLEMENTED_UNVERIFIED | IMPLEMENTED_SIMULATED (no test of the external part) | code exists; the external service was not exercised |
| NOT_IMPLEMENTED | DOCUMENTED_NOT_IMPLEMENTED | design only |
| BLOCKED | — | refused by policy |

## Claims
| Claim | Status | Evidence |
|---|---|---|
| Discovers mDNS, SSDP, ADB USB/Wi-Fi, Freebox OS (authorized), BLE via relays | REAL_HARDWARE_VERIFIED | EVIDENCE_LEDGER.md, README screenshot |
| One graph, strong-ID merge only, grants per link | REAL_HARDWARE_VERIFIED | TV mDNS+ADB merge in EVIDENCE_LEDGER.md |
| ISP Router API (e.g., Freebox OS / UPnP-IGD): Freebox inventory | REAL_HARDWARE_VERIFIED | docs/FREEBOX_INTEGRATION.md |
| ISP Router API: generic UPnP-IGD read-only | REAL_HARDWARE_VERIFIED (status fields; IGD bit-rate defaults flagged) | tests/fabric/test_upnp_igd.py; real read: `python -m dev.igd_read` (pending) |
| BLE relay through phone and TV, signed protocol, revoke | REAL_HARDWARE_VERIFIED | docs/RELAY_SECURITY.md |
| Reversible write with exact Undo and read-back | REAL_HARDWARE_VERIFIED | docs/physical-package-receipt.json |
| Crash-recoverable physical workflows (not ACID): 5 kill points | REAL_HARDWARE_VERIFIED | crash drill 5/5, EVIDENCE_LEDGER.md |
| Cross-transport timeline + competing hypotheses + read-only probe | REAL_HARDWARE_VERIFIED (10-min capture, induced link drop) + CI drills | tests/runtime/test_timeline.py, drills + independent labels |
| Privacy-preserving cloud escalation (never "zero-knowledge") | LIVE VERIFIED (one consented muse-spark-1.3 call, EVIDENCE_LEDGER) + golden corpus | tests/runtime/test_redact.py (golden corpus), tests/runtime/test_cloud_escalation.py |
| Meta Model API live call (muse-spark-1.3) | REAL (synthetic facts) | docs/runtime-meta-receipt.json, EVIDENCE_LEDGER 27 Oct |
| Registered ablation, rules vs Llama vs Glimmer vs Spark | MEASURED: rules 0.833, Llama 0.833, Glimmer 0.722; Spark not run (budget) | docs/benchmark/v4/REGISTRATION.md |
| Visual read-back with local Glimmer | REAL_HARDWARE_VERIFIED (TV run: INCONCLUSIVE, Glimmer misread a screensaver) | tests/unit/test_visual_readback.py; `python -m dev.visual_readback_tv` (pending) |
| BLE zone proximity (zones, not positions) | SIMULATED_VERIFIED | tests/runtime/test_ble_zones.py; `python -m dev.ble_zone_calibrate` (pending) |
| Voice command via Muse Voice Transcribe | LIVE VERIFIED (synthetic speech clip, exact transcript) | tests/unit/test_voice.py (fake WebSocket) |
| Wear OS dynamic manifest | REAL_HARDWARE_VERIFIED (Galaxy Watch7) | tests/fabric/test_wear_manifest.py |
| PC 2 as a client: owner jobs (`pc_job`) and Meta inference worker | jobs REAL_HARDWARE_VERIFIED (EVIDENCE_LEDGER); inference worker SIMULATED_VERIFIED | tests/runtime/test_windows_bridge.py, tests/unit/test_scheduler.py; real job + `python -m dev.benchmark_scheduler` (pending) |
| Tuya vacuum: reads, reversible suction/volume, full robot commands | REAL_HARDWARE_VERIFIED (reads, suction + exact Undo, seek, start/pause/moves/dock) | tests/fabric/test_tuya_local.py; live re-verify 30 Oct (facts + seek accepted, row 26) |
| Meta-only runtime | VERIFIED (static + network trace) | src/ai/registry.py, tests/unit/test_meta_only_network_trace.py |
| Capability explorer: UI schemas matched to live device capabilities | SIMULATED_VERIFIED + live discovery smoke (2 cards/118 widgets) | tests/fabric/test_capability_explorer.py, tests/runtime/test_explorer_api.py (§6 `5224d99`) |
| Hardware intelligence: PC facts + task rankers + micro-benchmarks | REAL_HARDWARE_VERIFIED (PC1 + BV9300 live) | tests/fabric/test_hardware_intel.py, tests/runtime/test_hardware_api.py (§9 `2ad4688`) |
| Permissions center: 13-entry catalog, measured states, grant flow | REAL_HARDWARE_VERIFIED (BV9300 live re-verify) | tests/fabric/test_permissions.py, tests/runtime/test_permissions_api.py (§10 `f1c460c`) |
| 1,000-turn eval kit: rules baseline, 200/200 convs, 0 crashes/sends | MEASURED (rules 1.4%; model tiers pending, oracles sealed) | docs/benchmark/EVAL_1000_RULES_BASELINE.md (§11 `070392a`) |
| Multi-device orchestration: DAG workflows, 9 scenarios, 9 new skills | SIMULATED_VERIFIED + live USB capture/send/montage | tests/runtime/test_workflows.py, docs/evidence/s7-live-usb-30oct.md (§7 `1e8066a`) |
| Official Android emulator driven via adb (level 4, no companion) | EMULATOR_VERIFIED (capture/probe/send + cleanup) | docs/evidence/avd-ob-pixel-30oct.md (registry row 18) |
| Relay dashboards: generated/patched/saved/restored UIs, reconnect repush | SIMULATED_VERIFIED + live watch run 30 Oct | tests/unit/test_dashboards*.py (§8 `972b545`); docs/evidence/g04-watch-30oct.md (registry row 22) |
| RetroArch loopback control (VERSION/GET_STATUS verified; VOLUME_UP sent-unverified) | REAL_HARDWARE_VERIFIED (localhost, menu-state only) | docs/evidence/retroarch-loopback-30oct.md (registry row 19, §13 `db5dedf`) |
| Stress hardening: locks, byte cap, typed IO, crash drill | SIMULATED_VERIFIED + crash drill 5/5 | docs/STRESS_14_REPORT.md (§14 `ef58712`) |
| CLI + headless + GUI/CLI parity + jury pack | REAL_HARDWARE_VERIFIED (CLI live runs) + SIMULATED_VERIFIED (parity) | docs/CLI_REFERENCE.md, docs/P30_MODEL_MATRIX.md, docs/release/P30_GATES_AND_REPORT.md (§P30 `73cfef5`) |
| Glimmer-synthesized capabilities validated + published + revoked (2) | REAL_HARDWARE_VERIFIED (live phone bundle; pending-kernel staging) | docs/evidence/p30-glimmer-synthesis-30oct.md (registry row 20) |
| Phone+AVD orchestration via CLI, sha-verified montage | REAL_HARDWARE_VERIFIED (phone) + EMULATOR_VERIFIED (AVD) | docs/evidence/p30-cli-orchestration-30oct.md (registry row 21) |
| Native controls on real Watch7 + long-press loop; TV 0.11.0 PAIRED | REAL_HARDWARE_VERIFIED (SM-L310 + Android TV) | docs/evidence/g04-watch-30oct.md (registry rows 22-23, G04 PASS) |
| Phone 0.11.0 PAIRED READY + relay probe | REAL_HARDWARE_VERIFIED (BV9300) | docs/evidence/g04-watch-30oct.md (registry row 24) |
| Companion found over Wi-Fi with no adb address (QU-bit browse + NSD) | REAL_HARDWARE_VERIFIED (SM-L310, adb disconnected) | docs/evidence/companion-lan-discovery-30oct.md (registry row 25) |
| Paid Meta cloud end-to-end | BLOCKED (no key, no spend order) | preflight + budget guard unit-tested; $0 spent |

## Never claimed
ACID transactions; zero-knowledge or anonymous cloud calls; 2D or person location from BLE RSSI; that BLE presence proves interference; fabricated scores; organizer acceptance or bonus eligibility.
