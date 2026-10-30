# Official Android emulator proof (AVD ob-pixel) — 2026-10-30

Pixel 6 AVD, `system-images;android-34;google_apis;x86_64`, booted headless on
E: with WHPX acceleration (`Windows Hypervisor Platform accelerator is
operational`). Driven through the REAL stack: Router skill_routes -> arm ->
invoke -> Executor -> AndroidAdapter -> adb. Tmp journal only.

- `adb devices`: emulator-5556 device (emulator-5554 is a pre-existing ghost).
- `getprop`: ro.serialno readable (stable per AVD), model sdk_gphone64_x86_64,
  release 14, sys.boot_completed=1.
- Discover: EMULATOR transport, stable opaque identity minted.
- screen_capture: EXECUTED, verified=true, PNG 1080x2400 (1370897 bytes),
  sha256 bc1b4c216dbe29cb2ba62b6c042c41bd6c9f4d3ce5fb60d7931d102427f37d2f.
  Frame saved to the owner's shots folder (E:/shots/s12-emulator-capture.png).
- capability_probe: VERIFIED (actions, category, launchable_apps, ranges, screen_px).
- capture_send: EXECUTED, verified=true, on-device sha256sum EQUALS server hash.
- Cleanup: pushed file removed, `ls /sdcard/OpenBridge/` empty.

## Limits (honest)
- Emulator framebuffer, not physical hardware (level 4, never counted as a device).
- Companion APK not installed in the AVD (adb-driven HOST_APP_ADAPTER only).
- No serials beyond the emulator id; no pixels committed to the repo.
