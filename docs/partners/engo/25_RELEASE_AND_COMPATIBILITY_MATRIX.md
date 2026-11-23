# ENGO release and compatibility matrix

> State on 23 November 2026. "Tested" means tested in the category written next to it; **nothing has run on
> physical ENGO glasses yet.** Firmware support is never claimed without ENGO confirmation.

## Glasses

| Model | Rendering target | Emulator (HUD Studio) | Real hardware |
|---|---|---|---|
| ENGO 3 / ENGO 3 Photochromic | 304 × 256, colour | Tested (`--model "ENGO 3"`) | **Not tested**: pair on its way |
| ENGO 3 Titanium | 304 × 256, colour | Tested as ENGO 3 | Not tested |
| ENGO 2 | 304 × 256, monochrome | Tested (`--model "ENGO 2"`) | Not tested |
| ENGO 1 | 304 × 256, monochrome | Not tested separately | Not tested |

| Firmware | Status |
|---|---|
| Any ENGO / ActiveLook firmware | Unknown until read from the pair (Device Information service). Command set assumed from the public ActiveLook API documentation; to confirm with ENGO / Microoled. |

## OpenBridge parts

| Part | Version | Runs on | Status |
|---|---|---|---|
| Glasses hub (`openbridge glasses run`) | Unreleased (branch after v0.5.0) | Windows 10/11 with Python, `bleak` for Bluetooth | Emulator end to end; BLE link unit-tested only |
| Transport core | Unreleased | any | Unit tests |
| Sport, workout, Ghost, GPX navigation | Unreleased | any | Unit tests on simulated data |
| BLE sensor decoders | Unreleased | any | Unit tests on specification byte layouts |
| Companion (Android) | built from this branch | Android 8+ | Builds; notification access, voice and language switch to try on the phone |
| Language (Français / English) | Unreleased | hub, HUD, Companion | Tests; PC web interface still English-only |
| Command model `openbridge-intent` v3 | GGUF q8_0 | Ollama on the PC | Voice → command verified on the emulator |

## Phones

| Phone | Status |
|---|---|
| Android with the OpenBridge Companion | Messages relay and voice built; phone-held BLE link to the glasses not built yet (the PC holds it today) |
| iPhone | Not supported |

## Evidence categories

Results are filed under exactly one of `EMULATOR`, `VIRTUAL_BLE`, `OFFICIAL_APP_BRIDGE`, `SIMULATED`,
`REAL_HARDWARE`, and never merged. Per-feature detail: [21_FEATURE_TRACEABILITY_MATRIX.md](21_FEATURE_TRACEABILITY_MATRIX.md).
The first `REAL_HARDWARE` results will come from [22_REAL_HARDWARE_VALIDATION_REPORT.md](22_REAL_HARDWARE_VALIDATION_REPORT.md).
