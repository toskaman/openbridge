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
| ISP Router API: generic UPnP-IGD read-only | SIMULATED_VERIFIED | tests/fabric/test_upnp_igd.py; real read: `python -m dev.igd_read` (pending) |
| BLE relay through phone and TV, signed protocol, revoke | REAL_HARDWARE_VERIFIED | docs/RELAY_SECURITY.md |
| Reversible write with exact Undo and read-back | REAL_HARDWARE_VERIFIED | docs/physical-package-receipt.json |
| Crash-recoverable physical workflows (not ACID): 5 kill points | REAL_HARDWARE_VERIFIED | crash drill 5/5, EVIDENCE_LEDGER.md |
| Cross-transport timeline + competing hypotheses + read-only probe | SIMULATED_VERIFIED | tests/runtime/test_timeline.py, drills + independent labels |
| Privacy-preserving cloud escalation (never "zero-knowledge") | SIMULATED_VERIFIED | tests/runtime/test_redact.py (golden corpus), tests/runtime/test_cloud_escalation.py |
| Meta Model API live call (muse-spark-1.3) | REAL (synthetic facts) | docs/runtime-meta-receipt.json, EVIDENCE_LEDGER 27 Oct |
| Registered ablation, rules vs Llama vs Glimmer vs Spark | rules MEASURED; models pending | docs/benchmark/v4/REGISTRATION.md |
| Visual read-back with local Glimmer | SIMULATED_VERIFIED | tests/unit/test_visual_readback.py; `python -m dev.visual_readback_tv` (pending) |
| BLE zone proximity (zones, not positions) | SIMULATED_VERIFIED | tests/runtime/test_ble_zones.py; `python -m dev.ble_zone_calibrate` (pending) |
| Voice command via Muse Voice Transcribe | IMPLEMENTED_UNVERIFIED | tests/unit/test_voice.py (fake WebSocket) |
| Wear OS dynamic manifest | SIMULATED_VERIFIED | tests/fabric/test_wear_manifest.py |
| PC 2 as a client: owner jobs (`pc_job`) and Meta inference worker | SIMULATED_VERIFIED | tests/runtime/test_windows_bridge.py, tests/unit/test_scheduler.py; real job + `python -m dev.benchmark_scheduler` (pending) |
| Tuya vacuum: reads + reversible suction/volume | SIMULATED_VERIFIED | tests/fabric/test_tuya_local.py; owner link `python -m dev.tuya_link` + real run (pending) |
| Meta-only runtime | VERIFIED (static + network trace) | src/ai/registry.py, tests/unit/test_meta_only_network_trace.py |

## Never claimed
ACID transactions; zero-knowledge or anonymous cloud calls; 2D or person location from BLE RSSI; that BLE presence proves interference; fabricated scores; organizer acceptance or bonus eligibility.
