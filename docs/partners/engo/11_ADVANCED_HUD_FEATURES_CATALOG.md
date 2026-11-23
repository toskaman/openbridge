# Advanced HUD Feature Catalogue and Ecosystem Synergies

> **R&D dossier: "watch-impossible" features v2.0.**
> 10 immersive use cases that a smartphone or smartwatch cannot deliver, designed for the collimated
> 304×256 MicroOLED display of ENGO glasses.
>
> **Status: design concepts, rendered in the emulator.** Not validated on physical glasses.

---

## 1. Overview of the 10 features

```mermaid
flowchart TD
    subgraph OUTDOOR["Outdoor navigation and biometrics"]
        F1["🧭 F07: AR compass and wayfinder ribbon"]
        F2["🏃 F09: Bio-adaptive pacer and heart-rate zone"]
        F3["📡 F01: Gaze-aligned spatial radar"]
    end

    subgraph SECURITY["Security and smart home"]
        F4["🛡️ F08: Smart-home intrusion shield"]
        F5["👁️ F02: Eyes-on-target action receipt"]
        F6["⏱️ F03: Two-phase wave abort gate"]
    end

    subgraph WORKFLOW["Hands-free productivity and entertainment"]
        F7["📺 F10: Touchless media remote"]
        F8["🛠️ F05: Workshop and cooking prompter"]
        F9["💬 F06: Doorbell intercom subtitles"]
        F10["⚡ F04: Peripheral telemetry stream"]
    end

    ENGO["ENGO glasses (304x256 MicroOLED)"] --> OUTDOOR
    ENGO --> SECURITY
    ENGO --> WORKFLOW
```

---

## 2. Detailed specification of the four new features

### 🧭 Feature F07: AR compass ribbon and outdoor wayfinder (`push_compass_wayfinder`)
* **Problem solved:** find your car in a huge car park, or keep your heading while hiking or trail running,
  without taking out your phone or glancing at your wrist.
* **Visual design:**
  - **360° heading ribbon (y: 0 to 24):** shows the current heading and cardinal point (`[ 285° · W · PARKING B3 ]`).
  - **Relative-angle chevron:** continuously computes the angle between where you look and the target:
    - If $|\Delta| \le 15^\circ$: `▲ STRAIGHT AHEAD (ON TARGET)` (green).
    - If $\Delta > +15^\circ$: `▶ TURN RIGHT (+XX°)` (amber).
    - If $\Delta < -15^\circ$: `◀ TURN LEFT (-XX°)` (amber).
  - **Direction vector and distance gauge:** dynamic 0–100 % gauge showing progress to arrival.
* **Modelled metrics:** 212 BLE bytes, 6.91 % screen fill, **0.51 mW** (continuous display: **838 hours**).

---

### 🛡️ Feature F08: Intrusion shield and real-time network alert (`push_smart_home_security_alert`)
* **Problem solved:** be told immediately about a critical network anomaly (a rogue port scan on the home
  Wi-Fi, a new unidentified device) without sitting at a computer.
* **Behaviour:**
  1. OpenBridge's read-only network monitor (e.g. Freebox inventory) sees a suspicious SYN scan from
     `192.168.1.189`.
  2. The glasses show a bright red alert box:
     - `🛡️ INTRUSION SHIELD ALERT`
     - `THREAT: SYN port scan (port 22 SSH)`
     - `Source IP: 192.168.1.189 | Vendor: Rogue Pi`
  3. **One-gesture follow-up:** the lower box invites a hand wave:
     - `>> [WAVE] REVIEW ON PHONE`
  4. When the IR swipe (`0x01`) arrives, OpenBridge pins the alert and opens the review on the owner's phone.
     **OpenBridge never changes router settings** (blocked by policy): blocking the device stays a decision
     the owner makes in the router's own app.
* **Modelled metrics:** 310 BLE bytes, 2.99 % fill, **0.39 mW** (continuous display: **1,090 hours**).

---

### 🏃 Feature F09: Bio-adaptive pacer and heart-rate zone guard (`push_bio_adaptive_pacer`)
* **Problem solved:** when running or doing intervals, checking a watch every 10 seconds breaks your stride
  and forces a tiring eye refocus (1.85 s).
* **Collimated heads-up display:**
  - **Dynamic heart-rate band:** colour follows the user's physiological zone:
    - Zones 1–2 (recovery / base endurance): cyan.
    - Zone 3 (aerobic): green.
    - Zone 4 (lactate threshold): amber (`ZONE 4: LACTATE THRESHOLD`).
    - Zone 5 (maximum effort): flashing red.
  - **Visual cadence metronome:** shows the actual cadence (e.g. 174 SPM) against the target (180 SPM), with
    a cursor centred at 50 % on gauge `0x70`.
  - **Direct running-form cue:** `▲ SPEED UP (+6 SPM) | SHORTER STEPS`.
* **Modelled metrics:** 258 BLE bytes, 7.68 % fill, **0.53 mW** (continuous display: **801 hours**).

---

### 📺 Feature F10: Touchless glance-to-control media remote (`push_media_remote_hud`)
* **Problem solved:** control the sound or playback of the living-room TV (Kodi, Android TV, soundbar) while
  cooking or doing DIY, with no physical remote or smartphone.
* **Projected interface:**
  - **Playback state:** `▶ MEDIA CONTROL: PLAYING` (green) or `⏸ PAUSED` (amber).
  - **Track metadata:** video / music title and source device (`Living-room Kodi (4K HDR)`).
  - **Dual gauge:**
    - Gauge 0: playback progress (`00:57:00 / 02:46:00`).
    - Gauge 1: room volume (e.g. 45 %).
  - **Gestures:**
    - Hand swipe in front of the eye (`wave`): play / pause.
    - Temple tap (`tap`): volume +5 %.
  - Like every OpenBridge action, these controls only run within capabilities the owner already approved,
    and the TV state is read back after each change.
* **Modelled metrics:** 286 BLE bytes, 9.70 % fill, **0.59 mW** (continuous display: **719 hours**).

---

## 3. Comparison matrix of the 10 implemented features

Figures are computed from the emulator's pixel fill rates (modelled, not measured on hardware).

| Ref | HUD feature | Trigger | BLE bytes | Pixel fill | MicroOLED power | Continuous display |
| :-: | :--- | :--- | :---: | :---: | :---: | :---: |
| **F01** | **Peripheral spatial radar** | IoT event | 340 B | **1.46 %** | **0.34 mW** | **1,235 h** |
| **F02** | **In-situ action receipt (oracle)** | Smart-home command | 274 B | **12.58 %** | **0.68 mW** | **627 h** |
| **F03** | **Two-phase commit abort gate** | Critical routine | 195 B | **19.06 %** | **0.87 mW** | **487 h** |
| **F04** | **Smart-meter peripheral telemetry** | Threshold exceeded | 67 B | **19.06 %** | **0.87 mW** | **487 h** |
| **F05** | **Workshop / recipe prompter** | IR hand swipe | 236 B | **5.33 %** | **0.46 mW** | **923 h** |
| **F06** | **Live intercom subtitles** | Smart doorbell | 160 B | **35.98 %** | **1.38 mW** | **308 h** |
| **F07** | **AR compass and wayfinder ribbon** | GPS heading | 212 B | **6.91 %** | **0.51 mW** | **838 h** |
| **F08** | **Intrusion shield and network alert** | Router inventory | 310 B | **2.99 %** | **0.39 mW** | **1,090 h** |
| **F09** | **Bio-adaptive cadence pacer** | BLE heart-rate sensor | 258 B | **7.68 %** | **0.53 mW** | **801 h** |
| **F10** | **Touchless media remote** | Glance at the screen | 286 B | **9.70 %** | **0.59 mW** | **719 h** |
| **TOTAL** | **10 combined scenarios** | — | **2,338 B** | **avg 12.0 %** | **avg 0.66 mW** | **~780 h** |

---

## 4. Trying them in the emulator

Every feature can be tried right away in the interactive emulator through the **Watch-Impossible** toolbar:
```bash
# Launch the full emulator:
python -m src.adapters.activelook_emulator
```

Buttons available:
- `🧭 AR Compass`: renders the 360° ribbon and computes the relative turn angle.
- `🛡️ Shield Alert`: simulates the network intrusion and the review prompt.
- `🏃 Bio Pacer`: demonstrates the visual metronome and heart-rate zones.
- `📺 Media Remote`: TV remote interface with progress and volume.
