# Hardware test matrix

| Scenario | Status | Evidence |
|---|---|---|
| Android USB discovery, inspection (12 facts) | REAL_HARDWARE_VERIFIED | Xiaomi 11T Pro (Android 14); EVIDENCE_LEDGER phase A |
| Android ADB Wi-Fi | IMPLEMENTED_UNVERIFIED | needs owner-paired wireless debugging |
| Optional-app change + exact Undo | REAL_HARDWARE_VERIFIED | physical-package-receipt.json, agent-loop-receipt.json |
| Crash during transaction + recovery | REAL_HARDWARE_VERIFIED | crash-recovery-receipt.json |
| Android TV authorized / not authorized | NOT TESTED (TV visible via mDNS only) | — |
| TV with/without BLE permission | INTEGRATION_VERIFIED (companion status logic) | — |
| Freebox unauthenticated | REAL_HARDWARE_VERIFIED | public API + mDNS |
| Freebox authorized LAN inventory | REAL_HARDWARE_VERIFIED | 127 hosts / 12 active |
| Freebox token revoked | INTEGRATION_VERIFIED | test_freebox_auth.py |
| OpenWrt / unknown router | NOT_SUPPORTED | not implemented |
| BLE local (PC) | NOT_SUPPORTED on this PC (no adapter) | ble_local status BLE_UNAVAILABLE |
| BLE via Android relay | INTEGRATION_VERIFIED; hardware pending install | test_relay.py |
| BLE via ESPHome proxy | NOT_SUPPORTED | not implemented |
| Same device via several transports | REAL_HARDWARE_VERIFIED (Freebox: mDNS ×3 + API) | fabric screenshots |
| Device seen only in LAN inventory | REAL_HARDWARE_VERIFIED | 12 Freebox-only hosts |

Exact pending hardware procedures: (1) enable MIUI "Install via USB", install Companion from the relay panel, turn Bluetooth on, allow "Nearby devices", pair with the on-screen code, enable scans, scan 8 s; (2) on the Android TV enable Developer options > Wireless debugging and pair; (3) unplug the USB cable during the EXECUTING state of an app-state change and verify journal recovery.
