# Device capabilities — catalog and what was measured (27 Oct 2026, night)

The catalog is served at `GET /api/v2/catalog`; per-device support is measured with the `device_capabilities` primitive. New features are built by composing catalog actions: `device_macro` (Android, up to 20 steps under one consent that lists them), `tuya_command`/`tuya_setting`, and `pc_job`. Every write needs owner consent; settings with a readable value are restored exactly, everything else is declared irreversible.

## Android (phone, Android TV, Wear OS watch) — `device_action`
| Family | Actions |
|---|---|
| Remote keys | power, wakeup, sleep, home, back, menu, search, app switch, D-pad + OK, volume ±, mute, channel ±, last channel, play/pause, stop, next, previous, rewind, fast-forward, TV input, settings, guide, info, captions, notifications, digits 0–9 (43 keys on TV, 37 elsewhere) |
| Mouse / touch | tap, long press, swipe/drag at screen fractions (touchpad in the UI) |
| Text | type text in the focused field |
| Apps / web | list launchable apps, launch an app, open an http(s) URL |
| Settings (exact undo) | media volume, screen brightness, screen timeout |
| State | screen on/off/screensaver and focused app |

## Measured on the owner's devices
| Device | Probe | Exercised | Result |
|---|---|---|---|
| Android TV (Android 11) | 43 keys, touch, text, 17 launchable apps, brightness + timeout readable; media volume not readable through `cmd media_session` | wake, volume ±, mute ×2, D-pad, home, channel ±, info, back, app list, launch YouTube, touchpad swipe + tap, power off, power on | **all VERIFIED / EXECUTED** (second run, TV awake): YouTube became the focused app; power off → `asleep`, power on → `awake` with the launcher focused. The first run hung only because the TV was in deep standby. |
| Phone (Xiaomi, Android 14) | 37 keys, touch, 85 apps, all 3 settings readable | keys, volume, brightness, launch app, swipe, tap | reads and app launch OK. Even with "USB debugging (Security settings)" switched on, Android still answered `INJECT_EVENTS` / `WRITE_SETTINGS` denied: MIUI applies it only after the USB debugging authorization is renewed (unplug/replug and accept on the phone). Media volume range is read from the device (0..150 here). Still denied after re-plugging (23:20): input and settings writes need the MIUI toggle to take effect (often only after a reboot). |
| Galaxy Watch7 (Wear OS) | 37 keys, touch on 480×480, 29 apps, all 3 settings readable | volume ±, mute, D-pad, home, exact media volume (14 → 13 via volume keys, restored to 14 exactly), launch Settings (focused app read back), swipe, tap | **VERIFIED** over two runs. Keys sent while the watch was dozing can exceed the 8 s ADB timeout; they pass once it is awake. |
| Tuya vacuum | — | water level low → back, work mode back, volume max → exact undo, seek | VERIFIED; `work_mode both_work` refused by the robot (no mop module reported). Earlier: start, pause, manual moves, dock, suction change + undo. Not exercised on purpose: consumable resets (would erase real wear counters), dust emptying (no auto-empty station reported). |
| PC 2 (Windows 10 LTSC, Celeron N3060, 3.9 GB) | — | `hostname`, OS/CPU/RAM query via `pc_job` | VERIFIED, exit 0 |
