# OpenBridge — Hardware Compatibility and Evidence

> Generated from `docs/DEVICE_EVIDENCE.json` by `python -m dev.device_registry --render`.
> No entry implies support for all functions. Physical and virtual environments are distinct.

| Device | Environment | Integration | Platform | Result | Validity | Tested operations | Date (UTC) | Evidence |
|---|---|---|---|---|---|---|---|---|
| 32-bit Linux guest | FULL_GUEST_OS | NONE | QEMU i386 guest | UNVERIFIED | CURRENT | guest install | 2026-10-29T19:00:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Debian 12 VM (bookworm) | FULL_GUEST_OS | PROTOCOL_ENDPOINT | QEMU x86_64 guest | VERIFIED | CURRENT | agent handshake mutual PSK, agent sys.ping, agent sys.diag, agent exec.run uname | 2026-10-29T18:25:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Debian 13 VM (ARM64) | FULL_GUEST_OS | PROTOCOL_ENDPOINT | QEMU aarch64 guest (TCG) | VERIFIED | CURRENT | agent handshake mutual PSK, agent sys.ping, agent sys.diag, agent exec.run uname | 2026-10-29T19:53:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Debian 13 VM (first guest) | FULL_GUEST_OS | PROTOCOL_ENDPOINT | QEMU x86_64 guest | VERIFIED | CURRENT | agent handshake mutual PSK, agent sys.ping, agent sys.diag, agent exec.run uname | 2026-10-29T17:00:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Debian 13 VM (second guest) | FULL_GUEST_OS | PROTOCOL_ENDPOINT | QEMU x86_64 guest | VERIFIED | CURRENT | agent handshake mutual PSK, agent sys.ping, agent sys.diag, agent exec.run uname | 2026-10-29T17:05:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Freebox Delta S (owner router) | REAL_HARDWARE | HOST_APP_ADAPTER | Freebox API v8 | VERIFIED | CURRENT | freebox authorized session, freebox static DHCP leases read, freebox LAN hosts inventory | 2026-10-29T18:15:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Galaxy Watch7 44 mm (Wear OS) | REAL_HARDWARE | NATIVE_COMPANION | Wear OS watch | VERIFIED | CURRENT | companion install 0.9.0 on watch, launch shows PAIRED READY on 480x480 UI, relay server LISTEN on device port | 2026-10-29T16:45:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Galaxy Watch7 44 mm (Wear OS) | REAL_HARDWARE | NATIVE_COMPANION | Wear OS watch | UNVERIFIED | CURRENT | signed relay round-trip to watch relay | 2026-10-29T17:00:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Owner Android TV (Android 10) | REAL_HARDWARE | NATIVE_COMPANION | Android TV | VERIFIED | CURRENT | companion install 0.10.0, launch shows PAIRED READY, re-pair after server reload, flag reported false on signed get_status | 2026-10-29T18:00:00Z | [COMPANION_0_10_0.md](release/COMPANION_0_10_0.md), [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Owner phone (rugged model, Android 13) | REAL_HARDWARE | NATIVE_COMPANION | Android phone | VERIFIED | CURRENT | companion install 0.10.0, full-control button shows warning popup, allow sets standing consent flag, revoke clears flag instantly, cancel leaves flag off, flag reported on signed get_status | 2026-10-29T17:45:00Z | [COMPANION_0_10_0.md](release/COMPANION_0_10_0.md), [companion-0-10-phone-main.png](jury/screens/companion-0-10-phone-main.png), [companion-0-10-full-control-popup.png](jury/screens/companion-0-10-full-control-popup.png) |
| Second PC (Windows 11, Intel i5-12600H) | REAL_HARDWARE | HOST_APP_ADAPTER | Windows PC agent v4 | VERIFIED | CURRENT | agent remote exec whoami, agent staged upload with integrity verify, agent binary swap to fixed build, agent remote hash matches fresh sha, agent single CONNECTED log after mutual auth | 2026-10-29T18:05:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Tuya robot vacuum (owner-linked) | REAL_HARDWARE | HOST_APP_ADAPTER | Tuya local robot | VERIFIED | CURRENT | vacuum facts read (status, battery, suction, volume, fault), vacuum seek beep command | 2026-10-29T18:15:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Ubuntu 22.04 VM (server) | FULL_GUEST_OS | PROTOCOL_ENDPOINT | QEMU x86_64 guest | VERIFIED | CURRENT | agent handshake mutual PSK, agent sys.ping, agent sys.diag, agent exec.run uname | 2026-10-29T18:53:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Windows 7 guest | FULL_GUEST_OS | NONE | QEMU x86_64 guest | BLOCKED | CURRENT | guest install | 2026-10-29T19:00:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |
| Windows XP guest (32-bit) | FULL_GUEST_OS | NONE | QEMU x86 guest | BLOCKED | CURRENT | guest install | 2026-10-29T19:00:00Z | [vm-fleet-29oct.md](evidence/vm-fleet-29oct.md) |

## Interpretation

- **VERIFIED**: a specific operation passed a recorded, independent postcondition check; see the cited evidence.
- **FAILED / BLOCKED / UNVERIFIED / STALE**: not a verified working operation; investigate or retest.
- **FULL_GUEST_OS + PROTOCOL_ENDPOINT**: the agent wire protocol was proven in a VM guest — not the Android Companion, not physical hardware.
- **EMULATOR_HOST_BRIDGE**: host controls an emulator, not an original physical console.

---

# Hardware test history (26–28 Oct 2026, archived)

> Historical rows preserved verbatim. Some statements are superseded by the
> generated matrix above (vacuum now owner-linked and commanded, multi-PC
> implemented, Companion 0.10.0, VM fleet proven). See `DEVICE_EVIDENCE.json`.

# Hardware test matrix (archive)

| Scenario | Status | Evidence |
|---|---|---|
| Android USB discovery, inspection (12 facts) | REAL_HARDWARE_VERIFIED | Xiaomi 11T Pro (Android 14); EVIDENCE_LEDGER phase A |
| Android ADB Wi-Fi (classic `adb connect <ip>:5555`) | REAL_HARDWARE_VERIFIED | Android TV, EVIDENCE_LEDGER TV section; wireless-debugging pairing (`_adb-tls-connect`): REAL_HARDWARE_VERIFIED on a Galaxy Watch7 (owner-typed code) |
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

Historical (26 Oct), all since completed — see EVIDENCE_LEDGER. Former pending hardware procedures: (1) enable MIUI "Install via USB", install Companion from the relay panel, turn Bluetooth on, allow "Nearby devices", pair with the on-screen code, enable scans, scan 8 s; (2) on the Android TV enable Developer options > Wireless debugging and pair; (3) unplug the USB cable during the EXECUTING state of an app-state change and verify journal recovery.

## Device Runtime v2 (branch feat/device-runtime-v2)

| Scenario | Status | Evidence / reproduce |
|---|---|---|
| Freebox read-only diagnostics (connection, FTTH optics, system sensors, Wi-Fi state, LAN presence) | REAL_HARDWARE_VERIFIED | commit ed3c0f8, Freebox v7 fw 4.13.1: `python -m dev.freebox_diag` (all findings OBSERVED) |
| Android diagnostics (battery, storage, uptime, Wi-Fi, CPU, memory, patch level) | REAL_HARDWARE_VERIFIED on Android TV and Xiaomi phone | dev/runtime_v2_smoke.py |
| ADB link lost during a read (TV, Wi-Fi) | REAL_HARDWARE_VERIFIED | dev/transport_loss_smoke.py → PARTIAL, DEVICE_UNAVAILABLE, re-attach by identity |
| USB transport lost during a write | REAL_HARDWARE_VERIFIED: physical cable pull (hit the revert phase) and host-side `adb reconnect`; both QUARANTINED → exact recovery | dev/link_loss_write_smoke.py, EVIDENCE_LEDGER |
| Device replaced on the same link/IP | SIMULATED_VERIFIED | `test_device_replaced_under_same_link` → IDENTITY_CHANGED |
| Relay disappears / revoked, TV off, timeout, concurrent requests, inconsistent read-back, server restart | SIMULATED_VERIFIED | `tests/runtime/test_primitives.py` |
| Relay staleness, rotating addresses, anti-spoofing flags | SIMULATED_VERIFIED | `tests/runtime/test_relay_health.py` |
| Windows PC through the owner's BridgeWindows agent (read-only allowlist: sys.diag, proc.list count, 4 registry values) | REAL_HARDWARE_VERIFIED (second PC, Windows 10 build 17763 x64, agent 3.7.1 x86) | `python -m dev.windows_bridge_smoke` + `tests/runtime/test_windows_bridge.py` |

## 27 Oct additions
| Scenario | Status | Evidence |
|---|---|---|
| Galaxy Watch7 44 mm (SM-L310, Android 16) paired over wireless debugging, category `watch`, read_facts 15 findings | REAL_HARDWARE_VERIFIED | PR #15 |
| Crash drill: 5 process-kill points during a real write, journal recovery with exact read-back | REAL_HARDWARE_VERIFIED (phone, 5/5) | PR #12, #13 |
| Windows PC via BridgeWindows agent, read-only; 64-bit agent self-update | REAL_HARDWARE_VERIFIED | PR #8, #11 |
| Live Meta Model API advisory (`muse-spark-1.3`, synthetic facts) | REAL (live API) | PR #16 |
| Tuya robot vacuum | DISCOVERED only (Freebox inventory) | needs the owner's Tuya IoT local key; never bypassed |

## Subsequent hardware updates — 27 October 2026

The original rows above describe their recorded revisions. Newer [device capability sweeps](DEVICE_CAPABILITIES.md) and the [evidence ledger](../EVIDENCE_LEDGER.md) record:

- Android TV keys, app launch, touch and power state exercised while awake; the earlier standby failure is retained.
- Blackview BV9300 Pro: keys, touch, YouTube launch, exact volume and brightness change/restore.
- Galaxy Watch7: direct PC-to-watch ADB actions and exact volume restore while awake; dozing can time out. This is not proof of Watch-to-TV control.
- Xiaomi: input/settings writes remained denied; readable facts and permitted app launch are separate results.
- BridgeWindows v4: mutual authentication and message MACs, without payload encryption; historical v3 rows do not describe the current protocol. OpenBridge multi-PC integration remains unimplemented.

These are existing contributor-recorded hardware results, not newly repeated hardware experiments during this audit. See [remaining work](RELEASE_STATUS.md) for open integration gates.
