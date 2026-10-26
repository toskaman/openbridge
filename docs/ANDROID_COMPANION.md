# OpenBridge Companion (Android phone / Android TV)

Native Android app in Java (companion/android), no third-party libraries, built with the official SDK tools only (`python -m dev.build_companion`: javac -> d8 -> aapt2 -> zipalign -> apksigner). Kotlin was preferred by the brief; Java was chosen because it needs no Gradle/Kotlin toolchain download and keeps the build reproducible offline. minSdk 26, targetSdk 34, 33 KB APK.

- TV: LEANBACK_LAUNCHER entry, large focusable buttons, D-pad navigation, no touchscreen requirement.
- Bluetooth: `hasSystemFeature(FEATURE_BLUETOOTH_LE)`; Android 12+ `BLUETOOTH_SCAN` with `neverForLocation`; Android 8–11 legacy BLUETOOTH/ADMIN + ACCESS_FINE_LOCATION (maxSdk 30). Permissions are requested through the system dialog only; never granted silently.
- Runs only while the app is open; scans only on signed PC request, only after the owner enables scans; stop on request; "Remove pairing" revokes.
- Server: TCP 47800, `POST /ob`, 16 KB request cap. Canonical JSON matches Python `json.dumps(sort_keys=True, separators=(',', ':'))`.
Status: REAL_HARDWARE_VERIFIED on the participant Xiaomi (Android 14): install, pairing, refused scan before owner consent, real BLE scans. Android TV companion: NOT TESTED.
