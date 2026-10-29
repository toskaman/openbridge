# Companion 0.10.0 — Allow full control (29 Oct 2026)

APK: `artifacts/companion/openbridge-companion.apk`, 98707 bytes,
sha256 `7543ba63fe779835e1e1798a6906ea6b9917ad53af808b749e846170197e754f`,
versionCode 10 / versionName 0.10.0. Installed on phone (BV9300, Android 13)
and TV (Android 10) via `adb install -r` — both Success.

## What changed

- System section: **Allow full control** button (visible only when paired).
- Tapping it shows a warning popup: *"OpenBridge on your PC will be able to
  send ALL commands to this device's controls without asking you each time.
  Only allow this on your own devices. You can revoke it here at any moment."*
  with Cancel / Allow.
- Allow sets the persisted `full_control` flag; the button becomes
  **Revoke full control** (instant off, no popup); the checklist shows
  "Allowed — the PC may act without asking".
- The flag is reported top-level in `get_status` (`full_control: bool`,
  default false) and cleared on unpair.
- Server side (PR109): `invoke_now()` refreshes the flag through `get_status`
  right before deciding; PC emergency brake via `set_full_control_block()`.

## Live proof (phone, uiautomator dumps, 29 Oct ~18:35)

| Step | Observed |
|---|---|
| Button present | `Allow full control` + `Full control` checklist row on screen |
| Tap button | Dialog `Allow full control?` + `without asking you each time` + Cancel/Allow at (733,1378)/(899,1378) |
| Tap Allow | `Revoke full control`, checklist `Allowed — the PC may act`, feed `Full control allowed on this device` |
| Tap Revoke | Back to `Allow full control`, feed `Full control revoked on this device` |
| Tap button, tap Cancel | Still `Allow full control` (off), no new allow entry |
| Wire, flag on | `relay-pair-confirm` → `declared.full_control: true` (phone relay-c388ba6dafcd) |
| Wire, flag off | `declared.full_control: false` (TV relay-dabd2a796665) |
| Left state | Flag OFF on both devices |

Screenshots: [phone main](../jury/screens/companion-0-10-phone-main.png),
[warning popup](../jury/screens/companion-0-10-full-control-popup.png).

Note: one early tap in the sequence reached the on-state without a captured
dialog frame; the controlled re-test (dialog visible → Cancel → stays off,
dialog → Allow → on) proves the gate. Raw dumps in `%TEMP%\fc10*.xml`.
