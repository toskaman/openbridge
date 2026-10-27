# Hardware test matrix

| Scenario | Status | Evidence |
|---|---|---|
| Android USB discovery, inspection (12 facts) | REAL_HARDWARE_VERIFIED | Xiaomi 11T Pro (Android 14); EVIDENCE_LEDGER phase A |
| Android ADB Wi-Fi (classic `adb connect <ip>:5555`) | REAL_HARDWARE_VERIFIED | Android TV, EVIDENCE_LEDGER TV section; phone wireless-debugging pairing (`_adb-tls-connect`): NOT TESTED |
| Optional-app change + exact Undo | REAL_HARDWARE_VERIFIED | physical-package-receipt.json, agent-loop-receipt.json |
| Crash during transaction + recovery | REAL_HARDWARE_VERIFIED | crash-recovery-receipt.json |
| Android TV over ADB Wi-Fi (authorized after on-screen prompt) | REAL_HARDWARE_VERIFIED | EVIDENCE_LEDGER TV section |
| Android TV as BLE relay over LAN | REAL_HARDWARE_VERIFIED (6 advertisers) | fabric-tv-relay-redacted-1440.png |
| TV with/without BLE permission | INTEGRATION_VERIFIED (companion status logic) | — |
| Freebox unauthenticated | REAL_HARDWARE_VERIFIED | public API + mDNS |
| Freebox authorized LAN inventory | REAL_HARDWARE_VERIFIED | 127 hosts / 12 active |
| Freebox token revoked | INTEGRATION_VERIFIED | test_freebox_auth.py |
| OpenWrt / unknown router | NOT_SUPPORTED | not implemented |
| BLE local (PC) | NOT_SUPPORTED on this PC (no adapter) | ble_local status BLE_UNAVAILABLE |
| BLE via Android relay | REAL_HARDWARE_VERIFIED (Xiaomi phone, 9–13 advertisers) | EVIDENCE_LEDGER relay section |
| BLE via ESPHome proxy | NOT_SUPPORTED | not implemented |
| Same device via several transports | REAL_HARDWARE_VERIFIED (Freebox: mDNS ×3 + API) | fabric screenshots |
| Device seen only in LAN inventory | REAL_HARDWARE_VERIFIED | 12 Freebox-only hosts |

Exact pending hardware procedures: (1) enable MIUI "Install via USB", install Companion from the relay panel, turn Bluetooth on, allow "Nearby devices", pair with the on-screen code, enable scans, scan 8 s; (2) on the Android TV enable Developer options > Wireless debugging and pair; (3) unplug the USB cable during the EXECUTING state of an app-state change and verify journal recovery.

## Device Runtime v2 (branch feat/device-runtime-v2)

| Scenario | Status | Evidence / reproduce |
|---|---|---|
| Freebox read-only diagnostics (connection, FTTH optics, system sensors, Wi-Fi state, LAN presence) | REAL_HARDWARE_VERIFIED | commit ed3c0f8, Freebox v7 fw 4.13.1: `python -m dev.freebox_diag` (all findings OBSERVED) |
| Android diagnostics (battery, storage, uptime, Wi-Fi, CPU, memory, patch level) | REAL_HARDWARE_VERIFIED on Android TV and Xiaomi phone | dev/runtime_v2_smoke.py |
| ADB link lost during a read (TV, Wi-Fi) | REAL_HARDWARE_VERIFIED | dev/transport_loss_smoke.py → PARTIAL, DEVICE_UNAVAILABLE, re-attach by identity |
| USB transport lost during a write | REAL_HARDWARE_VERIFIED as host-side `adb reconnect` (QUARANTINED → exact recovery); physical cable pull NOT TESTED | dev/link_loss_write_smoke.py, EVIDENCE_LEDGER |
| Device replaced on the same link/IP | SIMULATED_VERIFIED | `test_device_replaced_under_same_link` → IDENTITY_CHANGED |
| Relay disappears / revoked, TV off, timeout, concurrent requests, inconsistent read-back, server restart | SIMULATED_VERIFIED | `tests/runtime/test_primitives.py` |
| Relay staleness, rotating addresses, anti-spoofing flags | SIMULATED_VERIFIED | `tests/runtime/test_relay_health.py` |
