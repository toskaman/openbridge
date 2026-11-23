# ENGO 3 Photochromic: real-hardware validation report

> **Status: not run yet.** This is the procedure and the empty report for the first session with a physical
> ENGO 3 Photochromic pair. Until it is filled in, every result in this folder comes from the HUD Studio emulator,
> the virtual BLE server, the official app bridge or simulated data, and says so.
> Evidence from this report is the only kind allowed to move a feature to `VALIDATED_REAL` in
> [`feature_registry.json`](feature_registry.json) (the registry test enforces it).

## 0. Session record

| Field | Value |
|---|---|
| Date | |
| Operator | |
| Glasses model, colour, serial (last 4 characters only) | ENGO 3 Photochromic, |
| Firmware version (read from the Device Information service) | |
| Phone model, Android version | |
| Companion version (Settings → About) | |
| PC OS, Bluetooth adapter | |
| OpenBridge commit | |
| Command used | `openbridge glasses run --link ble --glasses "ENGO 3"` |

Remove from any shared copy: the full Bluetooth address, serial numbers, tokens, home addresses, contact names and
message text. Keep traces in `captures/engo/<date>/` (git-ignored) and share only redacted extracts.

## 1. First power-on and calibration

1. Charge the pair; note the battery percentage shown by the official ENGO app.
2. Close the official app (one central at a time) and run the hub: `openbridge glasses run --link ble`.
3. Open **Settings → Calibrate display**. Expected: an arrow at the top left, a frame on all four edges, the
   palette ramp readable left to right.
4. If the arrow is not at the top left: `openbridge glasses set --rotate on`, run again, note which setting is right.
5. Read every tone on the palette ramp. On the emulator, grey levels 1–6 act as palette indices, so dim tones use
   7–11; check whether the real ENGO 3 shows the same thing.

| Check | Expected | Result | Notes |
|---|---|---|---|
| Arrow position | top left | | |
| Frame edges visible | all 4 | | |
| Darkest readable tone | level 7 | | |
| Text legible indoors / outdoors (sun, photochromic lens dark) | yes / yes | | |

## 2. GATT discovery

Record the services and characteristics the pair actually exposes (UUIDs only):

| Service | Characteristic | Properties | Seen | Notes |
|---|---|---|---|---|
| ActiveLook `0783B03E-…` | Rx (write without response) | | | |
| ActiveLook | Tx (notify) | | | |
| ActiveLook | Flow control (notify) | | | |
| ActiveLook | Gesture (notify) | | | |
| Device Information `0x180A` | Firmware / model / manufacturer | | | |
| Battery `0x180F` | Level `0x2A19` | | | |

## 3. Link quality and transport

| Measure | Method | Result |
|---|---|---|
| Negotiated MTU | `openbridge glasses status` (transport stats) | |
| Flow-control values seen | log of flow notifications; expected PAUSE `0x02`, RESUME `0x01` (to confirm) | |
| Pauses during a 10-minute menu session | transport stats `pauses` | |
| Late frames dropped / superseded screens | transport stats `dropped_late`, `superseded` | |
| Frame latency (command sent → visible change) | slow-motion phone video of the lens + log timestamps, 20 samples | median / p95: |
| Reconnect after the pair goes out of range for 30 s | walk away, come back | time to screen: |
| Second central refused | open the official app while the hub runs | |

## 4. Gestures

| Gesture | Attempts | Recognised | False triggers in 5 minutes of normal wear |
|---|---|---|---|
| 1 wave → next | 20 | | |
| 2 quick waves → open | 20 | | |
| 3 quick waves → back | 20 | | |

## 5. Features exercised

Fill one row per feature tried; the ID is the one in [the matrix](21_FEATURE_TRACEABILITY_MATRIX.md).

| Feature ID | What was done | Result | Evidence file |
|---|---|---|---|
| CONN-001 | discover and connect | | |
| CONN-004 | battery read | | |
| CONN-005 | model / firmware read | | |
| CONN-008 | calibration screen, palette, gestures | | |
| CONN-009 | latency and throughput | | |
| MSG-* | a Telegram / SMS message shown | | |
| TV-* | volume up / down, app switch (with the grant) | | |
| I18N-* | language switch FR ↔ EN on the HUD | | |
| RUN-* | sport dashboard with real phone GPS | | |

## 6. Battery

| Scenario | Duration | Start % | End % | Notes |
|---|---|---|---|---|
| Menus idle, screen on | 60 min | | | |
| Sport dashboard, 1 update/s | 60 min | | | |

## 7. Conclusions

- What works as on the emulator:
- What differs (orientation, palette, fonts, timings):
- Questions for ENGO / Microoled:
- Registry changes made (`feature_registry.json`), each with `REAL_HARDWARE` evidence pointing to this report:
