# Device Fabric — baseline audit (HEAD 78b6692, 26 Oct 2026)

Audited before any Device Fabric change: git clean at 78b6692; full unit/integration suite PASS on Windows (Python 3.14); GitHub CI green for 78b6692, 6a36803, 29087f1. Runtime has zero third-party Python dependencies.

Status vocabulary: REAL_HARDWARE_VERIFIED, INTEGRATION_VERIFIED (mocked process/HTTP), SIMULATED_VERIFIED, IMPLEMENTED_UNVERIFIED, NOT_SUPPORTED, BLOCKED.

| Capability | Status | Evidence / gap |
|---|---|---|
| Android USB discovery + live events | REAL_HARDWARE_VERIFIED | One Xiaomi (Android 14); src/adapters/android.py, android_events.py |
| Android Wi-Fi ADB (`ip:port`, `adb-…._adb-tls-connect._tcp`) | NOT_SUPPORTED (bug) | `ip:port` serials skipped; mDNS TLS serials would be mislabelled USB |
| Android identification (manufacturer/model/version/SDK) | REAL_HARDWARE_VERIFIED | One missing/invalid prop aborts the whole inspection (fragility) |
| Android battery / storage facts | REAL_HARDWARE_VERIFIED | df parsing assumes one modern line format; screen timeout not collected |
| Freebox public API identity | REAL_HARDWARE_VERIFIED | src/adapters/freebox.py; fixed host only, no mDNS, no authenticated session |
| Freebox authenticated LAN inventory | NOT_SUPPORTED | Absent |
| Network discovery (mDNS/SSDP/ARP) | NOT_SUPPORTED | Absent |
| Bluetooth discovery (local or relayed) | NOT_SUPPORTED | Absent |
| Connectivity graph / identity merge | NOT_SUPPORTED | Absent; sources are separate lists |
| Meta proposals (Llama 3B, Glimmer, Spark 1.3) | REAL_HARDWARE_VERIFIED (local) / recorded (cloud) | receipts in docs/ |
| Deterministic gate + consent | REAL_HARDWARE_VERIFIED | src/core/gate.py, agent.py |
| Backup / exact Undo (optional-app state) | REAL_HARDWARE_VERIFIED | Writes require USB transport; current Android user not checked; `pm default-state` assumed (absent before Android 9) |
| Crash recovery | REAL_HARDWARE_VERIFIED | docs/crash-recovery-receipt.json |
| Guided UI | SIMULATED_VERIFIED | tests/e2e/guided_smoke.py (USB authorization only) |
| Meta-only runtime registry | INTEGRATION_VERIFIED | src/ai/registry.py |
| Concurrency | INTEGRATION_VERIFIED | SQLite unique active resource, single in-flight inference |

Candidate apps for the agent: 3 allowlisted packages, 2 of them Xiaomi-specific, so on most phones the agent would find no candidate.

## Incremental plan (P0 first)
1. Fix Android regressions without weakening guarantees (transports, tolerant facts, user check, pre-Android-9 block).
2. Typed Device Fabric contracts, registry with conservative identity merge, topology graph.
3. Bounded stdlib mDNS/DNS-SD discovery within an approved scope; Freebox via `_fbx-api._tcp`.
4. Freebox official app authorization + read-only LAN inventory feeding the graph.
5. Local BLE via optional `bleak`.
6. Device Fabric UI section and guided dialogs; then relays/companion (P1).
