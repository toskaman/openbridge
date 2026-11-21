# OpenBridge × ENGO: Integration Architecture & Verification Contract

**Platform:** OpenBridge B2/B3 Runtime  
**Adapter:** `src/adapters/activelook.py`  
**Test Suite:** `tests/unit/test_activelook.py`  
**Document Code:** `ENGO-DOC-05`

---

## 1. Connection Topology & Hybrid Routing

```
+-------------------------------------------------------------+
|                      OpenBridge Server                      |
|                  (PC Host / Local Brain)                    |
+------------------------------+------------------------------+
                               |
                openbridge-relay/1 (HMAC-SHA256)
                               |
+------------------------------v------------------------------+
|                     OpenBridge Companion                    |
|             (Android Phone or Galaxy Watch WearOS)          |
+------------------------------+------------------------------+
                               |
                       Bluetooth 5.4 LE
                     GATT Service ...5CB7
                               |
+------------------------------v------------------------------+
|                   ENGO 2 / ENGO 3 Glasses                   |
|                 (ActiveLook MicroOLED HUD)                  |
+-------------------------------------------------------------+
```

### Why Hybrid Routing Wins
1. **Physical Proximity:** The glasses are on the user's face. The phone or Galaxy Watch is in their pocket or on their wrist (1–2 meters distance max). PC BLE signals drop rapidly across walls.
2. **Foreground Service:** The Companion's `RelayService` runs with `FOREGROUND_SERVICE_CONNECTED_DEVICE`, maintaining an ultra-stable connection.
3. **PC Direct Fallback:** In standalone desktop setups, `ActiveLookAdapter` connects directly via Python `bleak` when a BLE radio is present on the PC.

---

## 2. Fabric Registration & Capabilities Matrix

Compliant with `src/fabric/discovery.py` and `src/fabric/contracts.py`:

- **Device Category:** `'hud'`
- **Public ID Scheme:** `hud-engo-3-01` (opaque salted hash in production)
- **Capabilities Matrix:**
  - `hud_notify` (`write`): Render transient glance cards (action receipts, security alerts).
  - `hud_layout` (`write`): Switch persistent screen layout template (Idle, Dashboard, Radar).
  - `gesture_input` (`observe`): Optical proximity gesture events (swipes, wave-to-abort).
  - `battery_status` (`read`): MicroOLED battery telemetry (0–100%).
  - `video_stream` (`write`): **BLOCKED by policy.** Hardware incompatible; prevents buffer saturation and thermal runaway.

---

## 3. Security Invariants & Consent Safety Gates

1. **Non-Privileged Display Sink:**
   - The glasses are strictly a peripheral optical output and trigger sink.
   - The glasses never authorize a destructive or privileged command on their own.
2. **At-Most-Once Gesture Consent:**
   - Hand gestures (wave past brow) can acknowledge alerts, cycle cards, or **abort** pending operations (`Two-Phase Commit`).
   - Gestures cannot bypass explicit owner approval policies for high-risk actions.
3. **Flow Control Protection (Buffer Guard):**
   - ActiveLook's Cortex-M4 MCU notifies characteristic `...5CB9` with `0x02` when buffer space exceeds 75%.
   - OpenBridge's `ActiveLookAdapter` immediately pauses transmission until `0x01` (drain) is acknowledged, eliminating packet loss.

---

## 4. Hardware Evidence Record (`DEVICE_EVIDENCE.json`)

Upon receipt and pairing of physical hardware, the following entry will be appended to `docs/DEVICE_EVIDENCE.json`:

```json
{
  "commit_sha": "HEAD",
  "companion_version": "0.12.0 (code 12)",
  "device_alias": "ENGO 3 Smart Glasses (ActiveLook MicroOLED)",
  "environment": "REAL_HARDWARE",
  "evidence": [
    "docs/partners/engo/README.md",
    "docs/evidence/activelook-gatt-dump.pcap",
    "docs/jury/screens/companion-hud-paired.png"
  ],
  "independent_oracle": "Android BTSnoop HCI capture validating GATT write to char 0783B03E-8535-B5A0-7140-A304D2495CBA and notification echo from 0783B03E-8535-B5A0-7140-A304D2495CB8",
  "integration": "NATIVE_COMPANION",
  "limitations": [
    "Monochrome/Zone Color 304x256 resolution only",
    "Text limited to 32 characters per line for glanceability",
    "BLE throughput capped at 15 commands/sec to protect MCU buffer"
  ],
  "operations": [
    "companion ble scan discovers ActiveLook advertiser",
    "gatt connect to 0783B03E-8535-B5A0-7140-A304D2495CB7",
    "cccd notify subscription on TX and Gesture characteristics",
    "render status bar layout (Freebox WAN + Watch battery)",
    "push Tuya vacuum docking notification card",
    "capture optical swipe gesture from proximity sensor",
    "route gesture to OpenBridge B3 RemoteControls dispatch"
  ],
  "os_version": "ActiveLook OS v4.2 / Android 13 Host",
  "permissions": [
    "BLUETOOTH_SCAN (neverForLocation)",
    "BLUETOOTH_CONNECT",
    "FOREGROUND_SERVICE_CONNECTED_DEVICE"
  ],
  "platform": "ActiveLook HUD",
  "public_device_id": "hud-engo-3-01",
  "status": "VERIFIED",
  "test_id": "companion-0.12.0-activelook-hud-cycle",
  "test_utc": "2026-11-21T18:00:00Z"
}
```
