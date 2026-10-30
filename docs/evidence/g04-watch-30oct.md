# G04 — Native target UI publication on Galaxy Watch7 (REAL_HARDWARE, 30 Oct 2026)

Gate: P30 G04 "native target UI publication visually proven on one connected target".
Verdict: **VERIFIED** — plus a full bidirectional press loop on the same target.

## Setup

- Target: Galaxy Watch7 44 mm (SM-L310), Wear OS, Companion **0.11.0 (code 11)** (verified via `dumpsys package`).
- Transport: watch relay `relay-39f86439fbae` on `192.168.1.14:47800`, paired this session through the
  real protocol: `pair_request` → 6-digit code shown on watch → code read from `uiautomator` dump →
  `derive_key` (PBKDF2 200k) → signed `discover_capabilities` answered `PAIRED` with
  `capabilities: [aead1, ble_scan, command_submit, remote_controls]`.
- PC stack: **real classes only** — `Registry`, `RelayManager.enroll`, `Router._validate_input`,
  `RemoteControls.set_controls`, `aead.encrypting_send` (sealed channel, mirroring `src/server.py` pairing path).
  Driver: `E:\shots\g04_watch.py` (session scratch; no repo code was changed for this run).
- Commit under test: `33ec5e4fd324be5d2884f44e0913eecc90c25a98` (main).

## Transcript

1. `RemoteControls.set_controls({relay_id, consent: True, controls: [Scan room/ble_scan_room,
   Watch facts/device_facts]})` → `INSTALLED controls: ctl-a97523a98e-g1, ctl-cc2b056fe8-g1`, sealed reply
   signature verified (`mac` valid, empty error-free params).
2. Watch screenshot → **QUICK CONTROLS card renders both native buttons** (`docs/jury/screens/g04-watch-quick-controls.png`).
3. `input swipe 240 190 240 190 1500` (adb-injected long-press, the app's "hold to send" gesture) on "Scan room".
4. Signed+sealed `get_requests` → **1 request**: `control_id ctl-a97523a98e-g1`, `gesture long_press`, `seq 6`.
5. Signed+sealed `report_result` (honest text, no skill was dispatched) → watch displays
   "Press recorded (evidence run)" under the controls (`docs/jury/screens/g04-watch-press-ack.png`).

## Oracle (independent of the relay channel)

- `adb screencap` PNGs pulled from the device show the rendered buttons and the ack text.
- `uiautomator` dumps show the pairing code card and (when scrolled into view) the control labels.
- No FakeCompanion, no simulator, no stub transport anywhere in this run.

## Companion evidence (same evening)

- Android TV (Android TV, Android 11), Companion 0.11.0, PAIRED, `relay-dabd2a79`, relay port open:
  `docs/jury/screens/tv-companion-0-11-paired.png`. Install/pairing predates this run (live server);
  this run only launched the app via adb and captured the screenshot. No re-pair was performed,
  so the live-server link was left untouched.
- Owner phone (Android 13), Companion 0.11.0, PAIRED, READY orb, relay port accepts TCP after ~10 s:
  `docs/jury/screens/phone-companion-0-11-paired.png`. Same launch-and-shoot protocol, live link untouched.

## Limitations

- Watch relay sleeps with the screen: the run needs the app in the foreground (`screen_off_timeout`
  raised to 10 min for the session, set back to 30000 ms afterwards via adb).
- The watch was re-paired to the evidence driver, which supersedes its previous live-server pairing;
  re-pair from the live server UI restores it (standard flow, ~10 s).
- Press injection used adb long-press, not a physical finger; the on-device gesture recorded is
  `long_press` either way.
