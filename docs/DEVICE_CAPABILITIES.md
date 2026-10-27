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
| Android TV (Android 11) | 43 keys, touch, text, 16 launchable apps, brightness + timeout readable; media volume not readable through `cmd media_session` | wake key, screen state, app list | wake and reads OK. Every later `input` call (keys, taps, app launch, power) **hung**: the TV went into deep standby where ADB still answers but `input` and `dumpsys power` stop responding. Not yet verified: keys, channel, volume, power off/on, touchpad. Re-run when the TV is awake. |
| Phone (Xiaomi, Android 14) | 37 keys, touch, 85 apps, all 3 settings readable | keys, volume, brightness, launch app, swipe, tap | reads and app launch OK (YouTube opened). Key/tap/swipe and setting writes **refused by MIUI**: injecting input or writing settings over ADB needs "USB debugging (Security settings)" enabled on the phone (needs a Mi account). |
| Galaxy Watch7 | — | — | its wireless-debugging link had dropped before the sweep (seen as an unauthorized Android device); re-pair to run the sweep |
| Tuya vacuum | — | water level low → back, work mode back, volume max → exact undo, seek | VERIFIED; `work_mode both_work` refused by the robot (no mop module reported). Earlier: start, pause, manual moves, dock, suction change + undo. Not exercised on purpose: consumable resets (would erase real wear counters), dust emptying (no auto-empty station reported). |
| PC 2 (Windows 10 LTSC, Celeron N3060, 3.9 GB) | — | `hostname`, OS/CPU/RAM query via `pc_job` | VERIFIED, exit 0 |
