# Oracle cards reach the ENGO 3 — 27 November 2026 (REAL_HARDWARE)

Owner wearing the real **ENGO 3 Photochromic** (address ending `D7:B4`), PC
without Bluetooth, phone **Blackview BV9300 Pro** (Android 13) with the
OpenBridge Companion (glasses_link + modules + cards capabilities) on USB
debugging, paired relay over an adb-forwarded signed channel. Code under test:
`b6f6e4c80` (one-line fix: `push_oracle_answer` used the normal `send()` path
instead of the never-defined `_send`).

## What was run

- BLE scans from the watch relay (SM-L310, 6 observations) and the phone
  relay (4 observations): both saw `ENGO 3 061249` at RSSI -53.
- `glasses_connect` to the glasses address: link READY, MTU 247.
- Oracle MATH card builds (199 bytes) + `glasses_write`: batches accepted,
  0 rejected. Brightness set to 13/15 the same way.
- Phone relay counters after the session: written 17, write_errors 0.

## What the owner saw (reported live)

| Check | Result |
|---|---|
| Oracle card `= 12` (2 fois 6) on the glasses | Shown and confirmed. |
| Oracle card `= 56` (7 fois 8) on the glasses | Shown and confirmed. |
| Media + triage demo screens | Transport-accepted (0 rejected), display not visually confirmed. |
| Phone Devices cards (3 pushed, accepted) | Shown and confirmed. |

## Limits

- PC without Bluetooth: phone link only.
- n=1 pair, 1 session. Display auto-sleep not measured; later checks of an
  older screen may show nothing even though the write was accepted.
