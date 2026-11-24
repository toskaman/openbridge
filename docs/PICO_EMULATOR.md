# Testing on the PICO emulator

The official [PICO emulator](https://developer.picoxr.com/document/spatial-toolkit/install-pico-emulator/)
runs PICO OS 6 (Android 16, x86_64) on a PC. OpenBridge uses it to test the Companion app on a PICO headset
without owning one. Last run: 24 November 2026, PICO Emulator 6.2.1, PICO OS 6.2.0. [Evidence](evidence/pico-emulator-24nov.md)

## Set it up (Windows)

1. Install the PICO CLI (needs Node.js 18+) and turn off its telemetry:

   ```powershell
   npm install -g @picoxr/pico-cli
   setx PICO_CLI_NO_TELEMETRY 1
   setx ANDROID_HOME D:\Android\Sdk
   setx PICO_HOME D:\PICO
   ```

2. Install the Android SDK parts the emulator needs. The `.bat` launcher splits arguments on `;`, so pass them in a file:

   ```powershell
   "platforms;android-35`nsources;android-35" | Set-Content sdk35.txt
   & $env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat --package_file=sdk35.txt
   ```

3. Install the emulator, create an AVD and start it:

   ```powershell
   pico-cli doctor --fix
   pico-cli emulator install
   pico-cli emulator create          # we named ours OpenBridge_PICO
   pico-cli emulator start --avd OpenBridge_PICO
   pico-cli emulator status
   ```

   Note: `pico-cli doctor --fix` also installs PICO's own "knowledge runtime" (uv and graphify) for its AI-assistant
   features. OpenBridge does not use it.

4. Check it with `adb devices`: the emulator shows up as `emulator-5554` or `emulator-5556`.

## Run the end-to-end pairing test

The emulator's x86_64 image crashes hardware-accelerated apps (see below), so build the Companion with software
rendering for this test only:

```powershell
python -m dev.build_companion --software-rendering
$env:ANDROID_SERIAL = 'emulator-5556'      # the PICO emulator, if several devices are connected
python scripts\verify\cloud_e2e.py --apk artifacts\companion\openbridge-companion-software-rendering.apk --out D:\PICO\e2e
```

`cloud_e2e.py` installs the APK, pairs it with a code read from the headset's screen, sends a signed command, checks it
with an independent oracle (the Android service and the adb forward), then revokes the relay and checks that it is
refused. The verdict is in `D:\PICO\e2e\verdict.json`.

Never ship the software-rendering APK: real headsets run the normal build.

## What we found (for PICO)

- **Hardware-accelerated apps crash on the emulator.** About 2 seconds after launch, HWUI's spatial support loads
  `SpatialRuntimeService.apk!/lib/arm64-v8a/libspatial_client.so` and aborts (`SIGABRT`) because the library is built
  for `EM_AARCH64`, not `EM_X86_64`. This happens to any app with hardware acceleration on (the default), not only
  OpenBridge. Real PICO headsets are arm64 and are not affected. Workaround: `android:hardwareAccelerated="false"`
  in test builds.
- **The headset has several displays.** `dumpsys window` lists one `mCurrentFocus` per display; the test accepts any
  line that names the Companion.
- **System dialogs take the focus.** The "Turn on Bluetooth?" dialog sits on top of the Companion; the test taps its
  allow button through `uiautomator dump`.
- **Bluetooth is off on the emulator**, so a Bluetooth scan is refused with a signed error. That still proves the
  signed round trip.

## Limits

- An emulator, not a headset: it counts as an official platform emulator, never as tested hardware.
- OpenBridge sees the headset as a phone (category `phone`). A separate headset category is future work.
