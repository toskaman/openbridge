# ActiveLook & ENGO HUD Emulator: Developer Guide

**Module Path:** `src.adapters.activelook_emulator`  
**Location:** `src/adapters/activelook_emulator.py`  
**Document Code:** `ENGO-DOC-04`

> **New:** the default UI is now **HUD Studio**. See [19_HUD_STUDIO_EMULATOR.md](19_HUD_STUDIO_EMULATOR.md).
> The window described below remains available with `--classic`. Validated under emulation only; real-hardware tests are pending until the ENGO pair is received.

---

## 1. Overview

ActiveLook smart glasses do not have an official desktop simulator or developer emulator. Furthermore, Android and iOS mobile emulators lack Bluetooth Low Energy (BLE) peripheral support out-of-the-box.

To enable rapid prototyping, testing, and continuous integration without physical glasses, OpenBridge includes a complete **two-tier emulation platform**:

```
+-------------------------------------------------------------+
|                      OpenBridge Server                      |
|                  (src/server.py / fabric)                   |
+------------------------------+------------------------------+
                               |  relay cmds
+------------------------------v------------------------------+
|            Companion / bleak / external BLE client          |
+------------------------------+------------------------------+
                               |  binary BLE bytes
+------------------------------v------------------------------+
|                 VirtualENGO (Google Bumble)                 |
|             Simulated GATT Server on TCP :7788              |
+------------------------------+------------------------------+
                               |  decoded ActiveLook frames
+------------------------------v------------------------------+
|                      HUDCanvas (Tkinter)                    |
|           304 × 256 MicroOLED Display (Scale 3x)            |
+-------------------------------------------------------------+
```

---

## 2. Launch Commands

### A. Standalone Visual Emulator (No BLE daemon)
Ideal for testing layout generation, color palettes, fonts, and gesture interactions directly on PC:
```bash
python -m src.adapters.activelook_emulator
```

### B. With Virtual BLE GATT Server (Bumble TCP Bridge)
Spins up a full simulated Bluetooth Low Energy GATT server advertising on `0.0.0.0:7788`:
```bash
python -m src.adapters.activelook_emulator --ble --port 7788
```
Centrals (nRF Connect, Bleak clients, or the OpenBridge Companion) can connect over TCP socket and send actual ActiveLook binary frames.

### C. Specific Hardware Model Emulation
Preview how screens look on different hardware targets:
```bash
# ENGO 3 Titanium (MultiColor MicroOLED)
python -m src.adapters.activelook_emulator --model "ENGO 3 Titanium"

# ENGO 2 (Monochrome Yellow MicroOLED)
python -m src.adapters.activelook_emulator --model "ENGO 2"
```

---

## 3. Interactive GUI Features

- **Pixel-Perfect Canvas:** 304 × 256 pixels enlarged by default to 912 × 768. True OLED black background.
- **Wave Gesture Simulation:** 
  - Click the **`🤚 Wave (Gesture)`** button in the header toolbar, OR
  - Press the **`[G]`** keyboard shortcut.
  - Fires the ActiveLook gesture interrupt byte (`0x01`) to connected subscribers.
- **Wipe Canvas:** Press **`[C]`** or click **`🗑 Clear`** to execute opcode `0x01`.
- **Pre-Loaded OpenBridge Demo Scenarios:**
  1. `🤖 Vacuum Docking`: Green verified banner + battery/bin tracker + ETA.
  2. `🚫 Action Refused`: Red high-contrast safety refusal ("Refused: Stale State").
  3. `🏠 Ambient Status`: Top-bar glance (<8% pixel fill) with grid wattage, lock status, WAN link.
  4. `⚡ Energy Alert`: Amber countdown warning before EDF peak tariff spike.
  5. `⏱ Two-Phase Commit`: 5-second countdown with `[WAVE] TO ABORT`.
  6. `🛠 Debug Matrix`: Live protocol diagnostics (RSSI, RTT, drops, TX queue depth).

---

## 4. Programmatic Testing & Python API

You can import and drive the emulator programmatically inside unit tests or external scripts:

```python
from src.adapters.activelook_emulator import parse_frames, cmd_clear, cmd_text

# 1. Parse raw binary frames
raw_bytes = bytes([0xFF, 0x01, 0x00, 0x05, 0xAA])
frames = parse_frames(raw_bytes)
assert len(frames) == 1
assert frames[0].cmd == 0x01

# 2. Run unit tests
# python -m unittest tests/unit/test_activelook.py -v
```
