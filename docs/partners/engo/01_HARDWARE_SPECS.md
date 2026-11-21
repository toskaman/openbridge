# ENGO Eyewear: Hardware Specifications & Teardown Analysis

**Hardware Target:** ENGO Smart Eyewear Family (ENGO 1, ENGO 2, ENGO 3, ENGO 3 Titanium)  
**Display Platform:** MicroOLED ActiveLook® Light AR Engine (Grenoble, France)  
**Document Code:** `ENGO-DOC-01`

---

## 1. Complete Model Comparison Matrix

| Specification | ENGO 1 (2021) | ENGO 2 (Late 2022) | ENGO 3 (Current Generation) | ENGO 3 Titanium (Limited Edition) |
| :--- | :--- | :--- | :--- | :--- |
| **Release Year** | 2021 | 2022 | 2024–2026 | 2024–2026 (500 units worldwide) |
| **Weight** | ~42 g (single frame) | **36 g** (Std) / **41 g** (Large) | **38.5 g** (Std) / **41 g** (Cyclist) | **28.9 g** (Featherweight) |
| **Frame Material** | Grilamid TR90 (full rim) | Grilamid TR90 (frameless shield) | Aerodynamic frameless shield | **3D-Printed Aerospace Titanium** |
| **Display Engine** | ActiveLook 1.0 MicroOLED | ActiveLook 2.0 MicroOLED | **ActiveLook MultiColor MicroOLED** | **ActiveLook MultiColor MicroOLED** |
| **Pixel Resolution** | 304 × 256 pixels | 304 × 256 pixels | 304 × 256 pixels | 304 × 256 pixels |
| **Display Palette** | Monochrome Yellow-Green | Monochrome Yellow (16 levels) | **MultiColor (Green / Amber / Red zones)** | **MultiColor (Green / Amber / Red zones)** |
| **Peak Luminance** | ~1,000–3,000 nits | Up to 10,000 nits (sunlight readable) | Up to 10,000 nits (sunlight readable) | Up to 10,000 nits (sunlight readable) |
| **Field of View (FOV)** | ~10° diagonal (monocular right) | ~10° diagonal (monocular right) | ~10° diagonal (monocular right) | ~10° diagonal (monocular right) |
| **Virtual Focus** | ~3.0 m to infinity | ~3.0 m to infinity | ~3.0 m to infinity | ~3.0 m to infinity |
| **Battery Life** | 10–12 hours continuous | 10–12 hours continuous | **18–20 hours continuous** | **24+ hours continuous** |
| **Battery Capacity** | ~115 mAh LiPo | ~115 mAh cylindrical LiPo | ~180–200 mAh ultra-density cell | ~200 mAh ultra-density cell |
| **Charging Port** | Micro-USB under rubber flap | 2-pin magnetic Pogo-Pin dock | 2-pin magnetic Pogo-Pin dock | 2-pin magnetic Pogo-Pin fast-dock |
| **Charge Time** | ~2.5 hours to 100% | ~2.0 hours to 100% | ~1.5–2.0 hours to 100% | <1.5 hours to 100% |
| **Bluetooth Radio** | BLE 4.2 | Nordic nRF52 (BLE 5.0) | **Bluetooth 5.4 Low Energy** | **Bluetooth 5.4 Low Energy** |
| **Gesture Sensor** | Optical IR proximity on bridge | Optical IR proximity on bridge | Optical IR proximity on bridge | Optical IR proximity on bridge |
| **Touch Control** | App triggers | Capacitive tap on temple | Capacitive tap on temple (double-tap) | Capacitive tap on temple |
| **Ambient Light Sensor** | Photodiode (auto-brightness) | Photodiode (auto-brightness) | Photodiode (auto-brightness) | Photodiode (auto-brightness) |
| **Water / Ingress** | Splashproof / Sweatproof | IP54 equivalent | **IP55 certified** | **IP55 certified** |
| **Prescription Support** | None (contact lenses required) | None (contact lenses required) | None (contact lenses required) | None (contact lenses required) |
| **App Ecosystem** | ActiveLook app | ActiveLook app | **engo Compagnon app** + ActiveLook | **engo Compagnon app** + ActiveLook |

---

## 2. Optical Architecture (MicroOLED Engine)

- **Manufacturer:** Microoled S.A.S. (Grenoble, France).
- **Substrate:** AMOLED-on-Silicon (OLEDoS) micro-display.
- **Micro-display Dimensions:** Less than 0.5-inch diagonal micro-panel embedded inside the right bridge hinge.
- **Prism & Collimator:** Custom free-form glass prism embedded into the upper-inner boundary of the right lens.
- **Collimation Distance:** Virtual image is projected at **3.0 to 5.0 meters** ahead of the eye.
  - *Advantage for Presbyopes:* Users suffering from presbyopia (reading vision degradation) can read the HUD clearly without bifocal or reading glasses because the focal plane sits at athletic distance (road/horizon).
  - *Myopia / Astigmatism Notice:* Nearsighted users must wear contact lenses; ordinary corrective glasses cannot be worn under or over ENGO.
- **Power Consumption:** The micro-display consumes **<1 mW** when rendering sparse typography (OLED black pixels draw 0 mW).

---

## 3. Sensors & Electrical Subsystems

### A. Touchless Gesture Sensor (Optical IR)
- **Position:** Directly in the center of the nose bridge module facing outward.
- **Technology:** Miniaturized Infrared Emitter + Photodiode receiver.
- **Detection Cone:** 3 cm to 10 cm directly in front of the bridge.
- **Trigger Dynamic:** Detects velocity transitions (hand swipe / wave past brow) between 0.2 m/s and 1.2 m/s.
- **Power Profile:** Consumes up to **40% of active power** when polling continuously. OpenBridge enforces an adaptive duty-cycle (sensor enters low-power sleep after 15s of inactivity).

### B. Ambient Light Sensor (ALS)
- **Position:** Right optical block.
- **Behavior:** Samples ambient illumination (0.1 lux to 100,000+ lux). Automatically drives the MicroOLED brightness via the internal AGC circuit unless manual `luma` override is requested.

### C. Magnetic Pogo-Pin Dock
- 2-pin / 4-pin spring-loaded magnetic connector underneath the bridge.
- Eliminates mechanical port failure and guarantees IP55 sealing against sweat and rainwater.
