# OpenBridge Companion (Android phone / Android TV)

Native Android app in Java (companion/android), no third-party libraries, built with the official SDK tools only (`python -m dev.build_companion`: javac -> d8 -> aapt2 -> zipalign -> apksigner). Kotlin was preferred by the brief; Java was chosen because it needs no Gradle/Kotlin toolchain download and keeps the build reproducible offline. minSdk 26, targetSdk 34, about 0.5 MB without the AI engine, 7.8 MB with it (0.15.0).

- TV: LEANBACK_LAUNCHER entry, large focusable buttons, D-pad navigation, no touchscreen requirement.
- Bluetooth: `hasSystemFeature(FEATURE_BLUETOOTH_LE)`; Android 12+ `BLUETOOTH_SCAN` with `neverForLocation`; Android 8–11 legacy BLUETOOTH/ADMIN. Location (0.15) is asked only when the owner turns the phone sensors on (GPS for the glasses' sport screens) or sets a Wi-Fi rule for a profile. Permissions are requested through the system dialog only; never granted silently.
- Runs only while the app is open; scans only on signed PC request, only after the owner enables scans; stop on request; "Remove pairing" revokes.
- Server: TCP 47800, `POST /ob`, 16 KB request cap. Canonical JSON matches Python `json.dumps(sort_keys=True, separators=(',', ':'))`.
Status: REAL_HARDWARE_VERIFIED on the participant Xiaomi (Android 14): install, pairing, refused scan before owner consent, real BLE scans. Android TV companion: REAL_HARDWARE_VERIFIED (BLE relay over the LAN, 5 advertisers, consumed by Forge; EVIDENCE_LEDGER 27 Oct).


## 0.15.0 (27 November 2026)

New pages, reached from the main screen (Glasses, Devices, Sensors, Settings):

| Page | What it does |
|---|---|
| **Glasses** | What the glasses show right now, redrawn on the phone from the frames written to them (same rules as HUD Studio); big Next / Open / Back / Home; the volume keys as next / back; brightness; reconnect. Optional ongoing notification with the same buttons on the lock screen, where the volume keys keep working with the screen off (media session with remote volume). Quick settings tiles "Glasses: next" and "Oracle", and a home-screen widget. On a watch: four buttons and the crown, sent to the PC. |
| **Devices** | One card per device with what it is doing, pushed by the PC's glasses hub (relay op `set_cards`, display only). |
| **Sensors** | The phone's GPS, compass and a fall alert, and Bluetooth sport sensors (heart rate, running speed, speed / cadence, power, smart trainers), for the glasses' sport and navigation screens (relay op `get_sensors`). Off by default; a visible notification while on. Visual Oracle: a photo and a question, answered by a local vision model on the PC, shown on the glasses. |
| **Settings** | Six modules (Oracle, Messages, Sport, TV, Vacuum, Phone sensors): the PC sees the same switches and the glasses hide the menus that are off. Context profiles (Home, Bike, Work) by hand or automatic (Wi-Fi network, sport sensor, time window). Which apps' messages reach the glasses, sender only, quiet hours. Standalone mode. Diagnostics (relay answer times, link, log; export as text). |
| **AI on this phone** | llama.cpp and whisper.cpp built into the app (`libobai.so`, arm64), running on the phone's CPU with no PC and no network: a general model (Qwen3.5-2B, 4-bit), speech-to-text (whisper base) and the phone's own command model (Qwen3.5-0.8B fine-tuned on the PC, `dev/ai_training/make_phone_dataset.py`). "Auto" answers on the phone only when the PC has been away for a minute. Optional "OK Bridge" wake word (off by default, visible notification) and summaries of long messages. |

**Standalone mode** (off by default): when the PC has not driven the glasses for 20 s, the phone draws a few screens
itself (clock, messages, sport, Oracle answers) with the same display rules as the PC, takes the taps and buttons,
and records sport sessions; when the PC comes back it takes over by itself (event `RESUMED`) and collects the
sessions (relay op `get_sessions`).

Build: `python -m dev.build_companion_ai` (Android NDK 27, llama.cpp and whisper.cpp sources under `OB_AI_SRC`),
then `python -m dev.build_companion` puts the library in the APK. Models: `openbridge companion ai push` (adb).
Without the library or the models, everything else works and the AI page says what is missing.

Measured on a Blackview BV9300 Pro (MediaTek Helio G99, 12 GB, Android 13), 26-27 Nov 2026: pages, translations and
the AI page checked on screen; Qwen3.5-2B (4-bit) answers short questions in 3 to 8 s including model load. The command
model (Qwen3.5-0.8B, LoRA, 32 min on an RTX 4060 Ti) gets 93.5 % of held-out sentences exactly right and 96.2 % in
effect after the phone's own checks, and never takes an order meant for another device. A model this
small gets some facts wrong (it answered that a spider has six legs), which is why Auto prefers the PC. Not yet
tested on hardware: the mirror and standalone mode with the glasses on, phone GPS and a real sport sensor outdoors,
the wake word and the visual Oracle end to end.
