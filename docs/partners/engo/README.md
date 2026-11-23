<p align="center">
  <img src="../../assets/readme/partner-engo.svg" width="100%" alt="Official hardware partner: ENGO smart glasses, powered by ActiveLook by Microoled">
</p>

# ENGO Eyewear × OpenBridge: R&D and Integration Hub

> **ENGO and ActiveLook® technical dossier.**
> This folder gathers the hardware, protocol, interaction and software specifications for integrating
> ENGO smart glasses (ENGO 1, ENGO 2, ENGO 3, ENGO 3 Titanium) into OpenBridge.

> [!IMPORTANT]
> **Validation status: emulator only.** The integration was built and tested with the
> [HUD Studio](19_HUD_STUDIO_EMULATOR.md) emulator and the official ActiveLook app (development build) on an
> Android smartphone, **without physical glasses**. Real tests on an ENGO pair (BLE, flow control,
> "ALooK" firmware layouts, optics, gesture sensor, battery life) **are waiting for the pair to arrive**,
> as are the announced hardware benchmarks.

---

## 🗂️ Contents

| Document | Title | Description |
| :--- | :--- | :--- |
| **[01_HARDWARE_SPECS.md](01_HARDWARE_SPECS.md)** | **Hardware specifications** | Full teardown, ENGO 1 / 2 / 3 / Titanium comparison, weight, 24 h battery, 10,000-nit MicroOLED, IR gesture sensor. |
| **[02_BLE_PROTOCOL_REFERENCE.md](02_BLE_PROTOCOL_REFERENCE.md)** | **BLE protocol manual** | Complete GATT reference (service `0783B03E...`), `0xFF...0xAA` binary framing, opcode table, MCU buffer management (flow control). |
| **[03_HUD_FEATURES_SPECIFICATION.md](03_HUD_FEATURES_SPECIFICATION.md)** | **New feature catalogue** | Specifications for 10+ features (action receipts, vacuum radar, gesture carousel, two-phase abort, tri-device synergy). |
| **[04_EMULATOR_AND_TOOLS.md](04_EMULATOR_AND_TOOLS.md)** | **Emulator and tools guide** | Using the 304×256 Tkinter emulator and the Bumble virtual BLE server (`src/adapters/activelook_emulator.py`). |
| **[05_OPENBRIDGE_INTEGRATION_PLAN.md](05_OPENBRIDGE_INTEGRATION_PLAN.md)** | **OpenBridge integration plan** | Fabric architecture, hybrid Companion / PC routing, B2/B3 safety policy and the `DEVICE_EVIDENCE.json` contract. |
| **[06_HUD_VS_SMARTWATCH_ERGONOMICS_BENCHMARK.md](06_HUD_VS_SMARTWATCH_ERGONOMICS_BENCHMARK.md)** | **HUD vs smartwatch ergonomics** | Quantitative human-factors analysis: glance latency (0.2 s vs 2.5 s), collimated optics, 0 mW black pixels, egocentric spatial orientation and UX patterns (Varia-style radar, two-phase abort gate). |
| **[07_PHONE_TETHER_AI_AND_API_ARCHITECTURE.md](07_PHONE_TETHER_AI_AND_API_ARCHITECTURE.md)** | **AI and phone-proxy architecture** | Phone-as-sensory-proxy: touchless voice co-pilot (wave → mic → LLM), multimodal vision (tap → 50 MP camera → HUD), live translated subtitles and API injectors (smart meter, weather, transit). |
| **[08_ACTIVELOOK_FULL_PROTOCOL_AND_OPCODES.md](08_ACTIVELOOK_FULL_PROTOCOL_AND_OPCODES.md)** | **Binary spec and opcodes v4.x** | Full `0x00`–`0xE3` opcode table, bitmask framing, 75 % flow control, Dialog SUOTA `0xFEF5` and parameter formats. |
| **[09_REAL_SCRIPTS_TOOLS_AND_WIRESHARK.md](09_REAL_SCRIPTS_TOOLS_AND_WIRESHARK.md)** | **Scripts, Wireshark and firmware quirks** | Complete Python Bleak script, Lua Wireshark dissector, hex traces and 10 documented firmware workarounds. |
| **[10_LAYOUT_PAGE_ENGINE_AND_FONTS_SPEC.md](10_LAYOUT_PAGE_ENGINE_AND_FONTS_SPEC.md)** | **Layouts, pages, fonts and flash** | 17-byte layout header, multi-slot pages (`pageDisplay`), alignment ghost characters (`$`, `&`) and the 3 MB NOR flash. |
| **[11_ADVANCED_HUD_FEATURES_CATALOG.md](11_ADVANCED_HUD_FEATURES_CATALOG.md)** | **Advanced feature catalogue v2.0** | 10 "watch-impossible" features: AR compass ribbon, network intrusion shield, bio-adaptive heart-rate pacer, touchless media remote. |
| **[12_NEXTGEN_INNOVATIONS_DEEPDIVE.md](12_NEXTGEN_INNOVATIONS_DEEPDIVE.md)** | **Breakthrough concepts v3.0** | Silent Morse temple-tap input, speech-paced teleprompter, spatial energy heatmap and a 60 Hz vector arcade mini-game. |
| **[13_BREAKTHROUGH_INNOVATIONS_V4.md](13_BREAKTHROUGH_INNOVATIONS_V4.md)** | **Breakthrough concepts v4.0** | Peripheral collision radar, discreet meeting briefing, heart-coherence biofeedback (box breathing) and an AR spirit level / wall scanner. |
| **[14_REVOLUTIONARY_INNOVATIONS_V5.md](14_REVOLUTIONARY_INNOVATIONS_V5.md)** | **Breakthrough concepts v5.0** | 110 BPM CPR coach and START disaster triage, occlusion-free spatial subtitles, VLOS drone telemetry and an anti-tracker / cyber-attack sentinel. |
| **[15_MISSION_CRITICAL_INNOVATIONS_V6.md](15_MISSION_CRITICAL_INNOVATIONS_V6.md)** | **Breakthrough concepts v6.0** | Industrial thermal and arc-flash sentinel, allergen and diet scanner, tactical sailing navigation and a multilingual interpreter with cultural cues. |
| **[16_FRONTIER_INNOVATIONS_V7.md](16_FRONTIER_INNOVATIONS_V7.md)** | **Breakthrough concepts v7.0** | Driver vigilance and PERCLOS P80 micro-sleep, hands-free pick-by-vision logistics, 457 kHz avalanche-transceiver search and a circadian light/caffeine optimiser. |
| **[17_APEX_INNOVATIONS_V8.md](17_APEX_INNOVATIONS_V8.md)** | **Breakthrough concepts v8.0** | Firefighter SCBA telemetry and flashover alert, ballistic and cant compensator, sterile surgical monitoring and torque, low-vision overhead-obstacle echo radar. |
| **[18_OPENBRIDGE_NEURAL_SENSORY_EXPANSION.md](18_OPENBRIDGE_NEURAL_SENSORY_EXPANSION.md)** | **OpenBridge neural and sensory expansion** | 38-feature matrix: phone/PC microphone streaming, VAD, sub-120 ms streaming STT, 50 MP multimodal vision proxy, four-quadrant ambient IoT matrix and telemetry priority scheduler. |
| **[19_HUD_STUDIO_EMULATOR.md](19_HUD_STUDIO_EMULATOR.md)** | **HUD Studio: pro emulator and official app** | Next-generation 304×256 emulator (Pixels / OLED / Lens views, frame inspector, metrics, sessions, PNG/GIF, JSON control API), ALooK layout bank, and the official ActiveLook app driving the emulator with the F01–F38 overlay. **Validated in the emulator only.** |

### Product specification and delivery (20–25)

| Document | Title | Description |
| :--- | :--- | :--- |
| **[20_OPENBRIDGE_MASTER_PRODUCT_SPEC.md](20_OPENBRIDGE_MASTER_PRODUCT_SPEC.md)** | **Master product specification (FR)** | Internal reference: architecture, transport, bilingual UI, every feature family (running, cycling, navigation, sensors, home, safety), data contracts and acceptance criteria. |
| **[21_FEATURE_TRACEABILITY_MATRIX.md](21_FEATURE_TRACEABILITY_MATRIX.md)** | **Feature traceability matrix** | Generated from [`feature_registry.json`](feature_registry.json): 334 features, each with status, code, tests, evidence category and limits. `python dev/engo_feature_matrix.py --check` keeps it in sync. |
| **[22_REAL_HARDWARE_VALIDATION_REPORT.md](22_REAL_HARDWARE_VALIDATION_REPORT.md)** | **Real-hardware validation report** | Procedure and empty report for the first ENGO 3 Photochromic session: calibration, GATT, MTU, flow control, gestures, latency, battery. **Not run yet.** |
| **[23_MANUFACTURER_IMPLEMENTATION_PACKAGE.md](23_MANUFACTURER_IMPLEMENTATION_PACKAGE.md)** | **Manufacturer implementation package (FR / EN)** | The document for ENGO / Microoled: what OpenBridge does, factual status, questions and requests, pre-send checklist. |
| **[24_API_AND_DATA_CONTRACTS.md](24_API_AND_DATA_CONTRACTS.md)** | **API and data contracts** | Observation and HUD event schemas, priorities, TTLs, BLE sensor characteristics, transport rules, Companion ops, settings keys, languages. |
| **[25_RELEASE_AND_COMPATIBILITY_MATRIX.md](25_RELEASE_AND_COMPATIBILITY_MATRIX.md)** | **Release and compatibility matrix** | Glasses models, firmware, OpenBridge parts and phones, with the evidence level of each. |

Before sending anything to ENGO, go through the checklist at the end of document 23: factual status, commit and
versions, emulator and real evidence kept apart, licences, no secrets or personal data, and no firmware support
claimed without ENGO's confirmation.

> Documents 11–18 are **design concepts** for discussion with ENGO: they describe what the display
> could do and how OpenBridge would feed it. They are not claims of shipped or hardware-validated features.

---

## 🚀 Quick start

### 1. Launch the visual emulator: HUD Studio (304 × 256 MicroOLED)
See the HUD screens right away, without waiting for physical glasses:
```bash
# HUD Studio (Pixels / OLED / Lens views, inspector, F01–F38, control API on 127.0.0.1:7790):
python -m src.adapters.hud_studio --model "ENGO 2"
# Windows, detached launch + adb reverse for the official app:
powershell -NoProfile -ExecutionPolicy Bypass -File dev\launch_hud_studio.ps1

# Legacy window + virtual Bluetooth Low Energy server (Bumble on TCP port 7788):
python -m src.adapters.activelook_emulator --ble --port 7788
python -m src.adapters.activelook_emulator --classic --model "ENGO 3 Titanium"
```
Full guide: [19_HUD_STUDIO_EMULATOR.md](19_HUD_STUDIO_EMULATOR.md).

### 2. Run the dedicated test suites (82 tests, emulator only)
```bash
python -m unittest tests/unit/test_activelook.py tests/unit/test_engo_killer_features.py tests/unit/test_engo_ai_bridge.py tests/unit/test_engo_openbridge_neural_integration.py tests/unit/test_hud_studio.py -v
```

---

## 📦 Code delivered

- **Protocol adapter:** [`src/adapters/activelook.py`](../../../src/adapters/activelook.py)
- **AI, voice and sensory-proxy bridge:** [`src/adapters/engo_ai_bridge.py`](../../../src/adapters/engo_ai_bridge.py)
- **Visual emulator and virtual BLE server:** [`src/adapters/activelook_emulator.py`](../../../src/adapters/activelook_emulator.py)
- **HUD Studio (pro emulator):** [`src/adapters/hud_studio.py`](../../../src/adapters/hud_studio.py), F01–F38 catalogue [`src/adapters/hud_features.py`](../../../src/adapters/hud_features.py), ALooK bank [`src/adapters/alook_layouts.py`](../../../src/adapters/alook_layouts.py)
- **Official ActiveLook app → emulator bridge:** [`dev/build_activelook_openbridge.py`](../../../dev/build_activelook_openbridge.py), [`dev/repatch_nosplit_bridge.py`](../../../dev/repatch_nosplit_bridge.py)
- **Dedicated test suites (82/82 passing, emulator only):**
  - [`tests/unit/test_activelook.py`](../../../tests/unit/test_activelook.py)
  - [`tests/unit/test_engo_killer_features.py`](../../../tests/unit/test_engo_killer_features.py)
  - [`tests/unit/test_engo_ai_bridge.py`](../../../tests/unit/test_engo_ai_bridge.py)
  - [`tests/unit/test_engo_openbridge_neural_integration.py`](../../../tests/unit/test_engo_openbridge_neural_integration.py)
  - [`tests/unit/test_hud_studio.py`](../../../tests/unit/test_hud_studio.py)

---

## 🔗 External links

- Official store: [engoeyewear.com](https://www.engoeyewear.com) / [fr.engoeyewear.com](https://fr.engoeyewear.com)
- Display platform: [activelook.net](https://www.activelook.net)
- Official GitHub: [ActiveLook organization](https://github.com/ActiveLook)
- Partner page: [ENGO × OpenBridge](../ENGO.md)
