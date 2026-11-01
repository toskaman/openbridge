# OpenBridge platform summary

OpenBridge runs on Windows, Linux, and macOS on x64 and ARM64. The
application runtime is Python 3.14 standard library only — no third-party
packages to install, no compiler needed (CI-pinned 3.14.4; older versions
untested and unsupported). Use `python3` where a guide writes
`python` on Linux/macOS.

## CI coverage (what is proven, not just claimed)

- `verify.yml`: full unit suite (`python -m unittest discover -s tests`) plus
  `compileall` on Windows, Ubuntu, and macOS runners.
- `cleanroom.yml` (manual dispatch, heavy): builds ARTIFACT A once, then
  installs and runs the 8-check clean-room lab
  (`scripts/verify/clean_install_check.py`: isolated venv, stdlib-only
  imports, start → CLI → UI → offline demo → diagnostics → clean shutdown
  with orphan check) on 6 hosted targets — `windows-2025`, `ubuntu-24.04`,
  `macos-15-intel`, `macos-26`, `ubuntu-24.04-arm`, `windows-11-arm` — plus a
  Debian container. Latest green run and per-target evidence are referenced
  from [RELEASE_STATUS.md](RELEASE_STATUS.md).
- Browser CI: Playwright Chromium on Ubuntu plus Chromium and WebKit on
  macOS (`tests/e2e/*_smoke.py`).
- `android.yml`: Companion APK build and device/emulator checks.

macOS GUI first-run is CI-covered, not hand-tested.

## Per-platform notes

| Area | Windows | Linux | macOS |
|---|---|---|---|
| Runtime | Supported, primary dev host | Supported | Supported |
| Server bind | Loopback-only `127.0.0.1:18765` (or `--port`) on all platforms |
| Secret store | Windows DPAPI (per-user encryption) | No OS store wired: Freebox authorization disabled | Same as Linux |
| PC Bluetooth | `bleak` + Windows BLE projections | `bleak` | `bleak` (adapter-dependent) |
| Companion relay | Any platform: a paired Android relay replaces the PC adapter |
| `adb` | Platform-tools on PATH on all platforms | | |

## Android companion

Native Java app (`companion/android`), no third-party libraries, built with
SDK tools only (`python -m dev.build_companion`). `minSdk 26`, `targetSdk 34`.
Verified on a real phone (Android 14), Android TV 11, and Galaxy Watch7; see
[ANDROID_COMPANION.md](ANDROID_COMPANION.md) and the release notes in
`docs/release/COMPANION_0_*.md`. Emulator coverage (official AVD images) is
labeled EMULATOR wherever it appears and never presented as hardware proof.

## Models by platform

Local Meta models run wherever Ollama runs (all three desktop platforms).
Glimmer 30B needs roughly 14 GB of VRAM for GPU offload and host-specific
tuning (see [TROUBLESHOOTING.md](TROUBLESHOOTING.md)); Llama 3.2 3B runs on
CPU. Hosted Muse Spark calls work from any platform once the key and budget
are configured. Model digests are pinned in `config/runtime_models.json` and
verified before any inference on every platform.
