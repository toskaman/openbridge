# ENGO × OpenBridge: Heads-Up Display (HUD) Feature Catalog & Interaction Specification

> **Document Version:** 1.0.0  
> **Target Hardware:** ENGO 1, ENGO 2, ENGO 3 (Standard, Photochromic, Titanium) Smart Eyewear (ActiveLook Platform by Microoled, Grenoble, France)  
> **Display Engine:** 304 × 256 Ultra-Low Power Micro-OLED (Monochrome Yellow/Green on ENGO 1/2; MultiColor Green/Amber/Red on ENGO 3) (<1 mW)  
> **Input Interface:** Front/Temple Infrared Proximity Gesture Sensor (Touchless Hand Wave) & Temple Tap  
> **Connectivity:** Bluetooth Low Energy (BLE 4.2 / 5.0 / 5.4 GATT)  
> **Safety Invariant:** Peripheral optical sink & non-privileged input trigger; all state mutations strictly adhere to OpenBridge transaction consensus, approval policies, and read-back verification.

---

## 1. Executive Summary & Hardware Grounding

OpenBridge unifies disconnected consumer ecosystems (Android TV, Wear OS watches, Tuya IoT, Freebox gateways, Windows endpoints) into a single verifiable fabric. Bringing **ENGO smart glasses** into this ecosystem adds an unprecedented dimension: **zero-effort, ambient awareness**. Information reaches the user's peripheral field of view without breaking posture, pulling out a phone, or raising a wrist.

### ActiveLook Hardware Constraints & Operating Parameters
- **Optical Engine:** Micro-OLED monochrome micro-display (high-contrast yellow/amber or emerald green), visible in direct outdoor sunlight.
- **Resolution:** 304 pixels (horizontal) × 256 pixels (vertical).
- **MCU & Memory:** Embedded ARM Cortex-M0 processor with ~1 MB flash allocation for pre-compiled layout descriptors, bitmap glyphs, and custom font tables.
- **Communication Protocol:** Binary framing `[0xFF] [CmdID] [Format] [Length] [QueryID] [Data] [0xAA]` over a custom BLE GATT characteristic.
- **Layout Architecture:** Rather than pushing streaming framebuffers over BLE, the host transmits layout activation (`layoutClearAndDisplay`) and formatted text update commands, reducing payload size to 8–24 bytes per screen transition.
- **Touchless Gesture Sensor:** Integrated infrared proximity sensor embedded in the frame/temple. When a hand moves within 3–10 cm of the frame, the glasses asynchronously broadcast a `Gesture Detection Notification` (byte value `0x01`) across the BLE Sensor characteristic.
- **Power Budget:** Total system consumption is <1 mW for display-only rendering (12+ hours continuous runtime). Keeping the IR proximity sensor continuously polling increases power draw; therefore, OpenBridge applies an adaptive sensor duty cycle policy.

### Research Gate Verification
- **Primary Source:** ActiveLook API Specification & SDKs (`github.com/ActiveLook/Activelook-API-Documentation`, `Microoled S.A.S.`).
- **Date Checked:** 2026-11-21.
- **Key Findings:** Layout indices (`0x64` to `0x67`), bitmap stream caching (`imgSave`), font indices (Fonts 1–4: 8px to 28px), and asynchronous gesture interrupts provide the foundation for sub-60ms glass response times without draining battery or overflowing the Cortex-M0 packet buffer.

---

## 2. Catalog of 10 High-Value Features

```
+----------------------------------------------------------------------------------------------------+
|                                    ENGO × OPENBRIDGE FEATURE MATRIX                                 |
+----+------------------------------------+--------------------------+-----------------+-------------+
| ID | Feature Name                       | Primary Value            | Input Trigger   | Category    |
+----+------------------------------------+--------------------------+-----------------+-------------+
| F1 | Touchless Card Carousel            | Rapid card cycling       | Single Wave     | Navigation  |
| F2 | Heads-Up Action Receipts           | Instant action readback  | Event-driven    | Safety/UX   |
| F3 | Ambient Home Status Glance         | Peripheral home vitals   | Always/Interval | Dashboard   |
| F4 | Live Robot Vacuum Telemetry Radar  | Hands-free robot monitor | Context/Wave    | IoT Telemetry|
| F5 | Tri-Device Synergy (Eyes+Voice)    | Fluid cross-device flow  | Voice + Glance  | Ecosystem   |
| F6 | Touchless Critical Alert & Disarm  | Urgent safety receipts   | Wave to ACK     | Security    |
| F7 | Dynamic Energy & Peak Tariff HUD   | Cost & load awareness    | Ambient trigger | Energy      |
| F8 | Developer & Debugger Telemetry HUD | Live protocol metrics    | Double Wave     | Diagnostics |
| F9 | Proximity-Aware Room Switching     | Contextual cards         | Room Beacon/BLE | Spatial UI  |
| F10| Two-Phase Commit Safety Gate       | Undo before execution    | Wave to Abort   | Transaction |
+----+------------------------------------+--------------------------+-----------------+-------------+
```

---

### Feature 1: Touchless Card Carousel (Wave-to-Cycle HUD)
* **Problem Solved:** When a user's hands are wet, dirty, or occupied (cooking, cycling, working with tools), physical buttons or phone touchscreens cannot be used to inspect home state.
* **Mechanism:** OpenBridge maintains a stack of 4–5 glance cards in memory. When the user waves their hand past the temple proximity sensor, the BLE gesture notification (`0x01`) fires. OpenBridge advances the active index (`card_idx = (card_idx + 1) % card_count`) and issues a lightweight `layoutClearAndDisplay` command.
* **Deck Structure:**
  1. *Card 0: Ambient Home Summary* (Time, locks, power, climate)
  2. *Card 1: Climate & HVAC* (Zone temps, target setpoint, humidity)
  3. *Card 2: Robot Cleaner Status* (State, battery %, ETA, cleaning zone)
  4. *Card 3: Network & Security* (Connected devices, WAN bandwidth, gate lock)
* **Power Optimization:** The gesture sensor is only enabled when the HUD is awake. An inactivity timer (default 15 seconds) blanks the micro-OLED and puts the IR sensor in low-power idle. A double wave or head tilt re-wakes the HUD.

---

### Feature 2: Heads-Up Action Receipts (Zero-Latency Optical Verification)
* **Problem Solved:** When a user triggers an action (via voice, watch, or scheduled automation), they must look at a phone screen or walk into another room to ensure the command took effect.
* **Mechanism:** As soon as OpenBridge's `transactions.py` completes a hardware verification read-back, it broadcasts an ephemeral receipt overlay directly to the glasses for 3.5 seconds:
  - `"Vacuum: Docked ✓"` (Tuya vacuum reached base station)
  - `"Salon: Lights Off ✓"` (Tuya relay confirmed zero wattage)
  - `"TV: YouTube Launched ✓"` (Android TV focused app confirmed)
  - `"Action Refused: Stale State ⚠"` (Precondition failed; reason highlighted)
* **Safety Benefit:** Users get instant visual confidence. If an action fails or is refused by OpenBridge policy, the refusal reason is displayed immediately in their visual field without digging into log consoles.

---

### Feature 3: Ambient Home Status Glance (Persistent Micro-Widgets)
* **Problem Solved:** Smart home apps require pulling out a phone and opening an app. Wall panels require walking over. The ambient glance lives quietly in the corner of the eye.
* **Mechanism:** A persistent 24-pixel top bar with minimal pixel fill factor (<8% of pixels illuminated) displays four dynamic micro-glyphs:
  - **Grid Load:** `[1.4kW]` (Real-time household consumption from Tuya/meter).
  - **Perimeter Lock:** `[🔒 ALL]` or `[🔓 GARAGE]` (Red/flashing inverted bitmap if unlocked).
  - **Active Media:** `[TV: ▶ 12]` (TV playing, current volume level).
  - **Gateway Health:** `[WAN: 940M]` (Freebox fiber link status).
* **Cognitive Ergonomics:** Rendered in low-intensity monochrome at the top-right periphery, ensuring zero occlusion of the user's focal visual axis.

---

### Feature 4: Live Robot Vacuum Telemetry Radar
* **Problem Solved:** Robot vacuums make noise, get stuck on rugs, or need bin emptying, often out of line of sight.
* **Mechanism:** The Tuya vacuum adapter streams state changes to OpenBridge. While cleaning is active, the glasses render a dedicated tracker card:
  - Status: `"VACUUM: CLEANING (LIVING ROOM)"`
  - Battery & Bin: `"BATT: 78% | BIN: OK | WATER: HIGH"`
  - Current Action: `"DOCKING IN 4 MIN"`
  - Spatial Indicator: Directional ASCII beacon indicating relative distance or room partition.
  - Obstacle Alarm: If the vacuum encounters a roller brush jam or bumper error, an alert flashes: `"⚠ VACUUM STUCK: BEDROOM RUG"`. A single wave dismisses the alert.

---

### Feature 5: Tri-Device Synergy (Eyes + Voice + Watch + Fabric)
* **Problem Solved:** Smart glasses lack a microphone in ultra-light models (like ENGO 2 at 36g), while smartwatches have small displays that are awkward to read while walking or carrying objects.
* **Mechanism:** OpenBridge acts as the master conductor across three modalities:
  1. **Input (Voice / Watch):** User taps Galaxy Watch7 or speaks to phone mic: *"Turn on Espresso Machine"*.
  2. **Orchestration (OpenBridge Core):** Gateway validates policy, checks interlocks, and issues the relay command.
  3. **Visual Confirmation (ENGO Glasses):** Instant confirmation appears in the glasses: `"Espresso: Warming Up (92°C in 2m) ✓"`.
  4. **Hands-Free Approval:** If a privileged action requires confirmation (e.g., unlocking front door), the glasses display: `"Unlock Front Door? Wave to Confirm"`. A deliberate double-wave authorizes the action.

---

### Feature 6: Touchless Critical Alert & Emergency Disarm
* **Problem Solved:** When an alarm or water leak occurs, audio sirens cause panic, and finding a phone to read the notification takes precious seconds.
* **Mechanism:** High-priority events in OpenBridge (water sensor triggered, smoke detected, exterior gate opened during armed mode) immediately interrupt any active HUD layout:
  - Layout switches to high-contrast inverse video (inverted background block).
  - Text: `"ALERT: LEAK DETECTED (LAUNDRY) [FLOW: 12L/m]"`.
  - Subtitle: `"Wave 1x: Acknowledge | Wave 2x: Shut Valve"`.
* **Execution:** A single wave acknowledges the alert, silencing the local chime. A second wave within 2 seconds issues an immediate OpenBridge transaction to close the main water valve, followed by a verified receipt: `"Main Valve: CLOSED ✓"`.

---

### Feature 7: Dynamic Energy & Peak Tariff HUD
* **Problem Solved:** Users unintentionally run high-draw appliances (dishwasher, dryer, EV charging) during peak electricity hours (e.g., Tempo Rouge in France, or dynamic hourly spot rates).
* **Mechanism:** OpenBridge monitors the home utility meter and scheduled tariff windows:
  - 15 minutes before a peak tariff window begins: HUD displays a subtle warning badge: `"⚡ PEAK TARIFF IN 15m (0.73 €/kWh)"`.
  - When instantaneous load exceeds a user threshold (e.g., >6.0 kW): Top-bar energy micro-widget pulses inverted: `"⚡ 6.8 kW [HIGH]"`.
  - Provides actionable tips: `"Oven (2.2kW) + Dryer (2.5kW) active"`.

---

### Feature 8: Developer & Debugger Telemetry HUD (Hacker Mode)
* **Problem Solved:** IoT developers, smart home integrators, and hackathon testers currently carry a laptop around the house to inspect MQTT topics, ADB wireless logs, or Tuya socket timeouts.
* **Mechanism:** A double-wave gesture toggles **Developer Telemetry Mode**. The HUD transforms into a high-density diagnostic console:
  - Line 1: `OB-CORE: v2.4 | UPTIME: 14h22m | TASKS: 3 RUN`
  - Line 2: `BLE ENGO: RSSI -58dBm | PKT_RT: 28ms | MTU: 247`
  - Line 3: `ADB TV: 192.168.1.45:5555 | LAT: 34ms | OK`
  - Line 4: `TUYA UDP: 10.0.0.88 | DPS_VERIFY: PASS | 0 DROPS`
  - Line 5: `TX QUEUE: 0 PEND | LAST_OP: tv_volume_up (18ms)`
* **Utility:** Provides engineers with hands-free, real-time wireless diagnostics while physically moving through the house testing device ranges and mesh repeater handoffs.

---

### Feature 9: Proximity-Aware Room Context Switching
* **Problem Solved:** Manually selecting rooms on a menu is tedious.
* **Mechanism:** Using BLE beacon RSSI from stationary OpenBridge nodes (Android TV in living room, Freebox in hallway, PC in office) or phone trilateration:
  - As the user walks into the **Kitchen**: HUD automatically flips to the Kitchen card (Espresso machine status, recipe timer, under-cabinet lighting toggle).
  - As the user enters the **Living Room**: HUD switches to Home Theater status (TV volume, HDMI source, ambient light preset).
  - As the user steps into the **Garage**: HUD surfaces Door & EV Charger state.
  - A single hand wave locks the current card in place to prevent accidental room re-switching.

---

### Feature 10: Two-Phase Commit Safety Gate (Wave-to-Abort)
* **Problem Solved:** Automations or bulk macros (e.g. "Bedtime Mode: Turn Off All Lights, Lock Doors, Arm Sensors") can accidentally plunge a room into darkness while someone is still in it.
* **Mechanism:** When a bulk or irreversible macro is triggered:
  - The HUD immediately renders an active countdown progress bar:
    ```
    [====================]
    BEDTIME ROUTINE IN 5s
    >>> WAVE HAND TO CANCEL <<<
    ```
  - The progress bar drains over 5 seconds.
  - If the user waves their hand before 0s: The macro is instantly aborted, and the HUD confirms: `"Routine Cancelled ✓"`.
  - If no wave is detected: The transaction proceeds to execution with full verification.

---

## 3. Interaction Specifications & Layout Architecture

### 3.1 Gesture Interaction Engine

```
       +-----------------------------------------------------------+
       |               INFRARED PROXIMITY SENSOR                   |
       |               (Operating Zone: 3 - 10 cm)                 |
       +-----------------------------------------------------------+
                                     |
                          [Hand Swipes Across Temple]
                                     |
                                     v
                       +---------------------------+
                       |   IR Pulse Width Filter   |
                       |   (150 ms < Pulse < 600 ms)|
                       +---------------------------+
                                     |
                 +-------------------+-------------------+
                 |                                       |
                 v (Single Pulse)                        v (Double Pulse < 600ms)
       +-------------------+                   +-------------------+
       |    SINGLE WAVE    |                   |    DOUBLE WAVE    |
       |  - Cycle HUD Card |                   |  - Toggle Dev HUD |
       |  - Dismiss Receipt|                   |  - Emergency ACK  |
       |  - Cancel Pending |                   |  - Wake HUD       |
       +-------------------+                   +-------------------+
                 |                                       |
                 +-------------------+-------------------+
                                     |
                                     v
                     +-------------------------------+
                     |  Debounce Guard (Lockout 350ms)|
                     |  Prevents accidental retrig   |
                     +-------------------------------+
```

#### Gesture Grammar & Timing Rules:
1. **Single Wave (Standard Swipe):**
   - *Detection criteria:* Hand passes within 3–10 cm of the frame.
   - *Velocity range:* 0.2 m/s to 1.2 m/s (rejects slow head movement or walking close to door frames).
   - *Action:* Advance active carousel card, dismiss an active receipt, or cancel a pending countdown.
2. **Double Wave (Quick Succession):**
   - *Detection criteria:* Two wave pulses detected within an interval of 200 ms to 650 ms.
   - *Action:* Toggle Developer Diagnostics Mode (Feature 8) or confirm high-privilege emergency action.
3. **Wave & Hold (Proximity Shield):**
   - *Detection criteria:* Hand held within 5 cm of sensor for > 1.2 seconds.
   - *Action:* Blank display immediately (Privacy/Stealth Mode) and put BLE display to sleep.

---

### 3.2 Micro-OLED Screen Layout Specifications (304 × 256)

#### Coordinate Frame:
- `(X: 0, Y: 0)` = Top-Left
- `(X: 303, Y: 255)` = Bottom-Right
- **Safe Zone:** `X: 8 to 296`, `Y: 8 to 248` (to account for optical prism refraction at lens borders).

---

#### Layout Layout-01: Default Ambient Status Glance
```
0-------------------------------------------------------------------303
| [14:32]      [⚡ 1.2kW]       [🔒 LOCKED]       [WAN: 940M]        |  Y: 0-24
|-------------------------------------------------------------------|  Y: 25
|                                                                   |
|   LIVING ROOM                                                     |  Y: 40-58  (Font 3: 18px Bold)
|   Temp: 21.5°C  |  Target: 21.0°C                                  |  Y: 65-80  (Font 2: 12px)
|   Lights: 2/5 ON                                                  |  Y: 85-100 (Font 2: 12px)
|                                                                   |
|   +-------------------------------------------------------------+ |
|   | VACUUM: CLEANING (KITCHEN)            [BATT: 84%]           | |  Y: 120-155 (Box container)
|   | Est. remaining: 14 min                [||||||||||..]        | |
|   +-------------------------------------------------------------+ |
|                                                                   |
|   TV: Playing YouTube ("OpenBridge Demo")                         |  Y: 175-195 (Font 2: 12px)
|   Vol: 14/100                                                     |  Y: 200-215 (Font 2: 12px)
|-------------------------------------------------------------------|  Y: 235
| CARD 1/4 (HOME)                                      WAVE: NEXT > |  Y: 240-255 (Font 1: 8px)
+-------------------------------------------------------------------+
```

---

#### Layout Layout-02: Instantaneous Action Receipt Overlay
```
0-------------------------------------------------------------------303
|                                                                   |
|         +-----------------------------------------------+         |  Y: 45
|         |                 ACTION RECEIPT                |         |  Y: 60  (Header inverted)
|         |===============================================|         |
|         |                                               |         |
|         |              VACUUM: DOCKED  ✓                |         |  Y: 95-120 (Font 4: 24px Bold)
|         |                                               |         |
|         |   Verified: Charging contacts engaged         |         |  Y: 135 (Font 2: 12px)
|         |   Battery: 42% (Charging...)                  |         |  Y: 155 (Font 2: 12px)
|         |   Latency: 18ms | Source: Tuya Local          |         |  Y: 175 (Font 1: 8px)
|         |                                               |         |
|         |   [Auto-dismiss in 3.5s or WAVE to close]     |         |  Y: 200 (Font 1: 8px dim)
|         +-----------------------------------------------+         |  Y: 215
|                                                                   |
+-------------------------------------------------------------------+
```

---

#### Layout Layout-03: Two-Phase Commit Safety Abort
```
0-------------------------------------------------------------------303
|                                                                   |
|         +-----------------------------------------------+         |
|         | ! ! !        PENDING AUTOMATION         ! ! ! |         |  Y: 50 (Inverted block)
|         |===============================================|         |
|         |                                               |         |
|         |             BEDTIME ROUTINE IN 4s             |         |  Y: 85-110 (Font 3: 18px Bold)
|         |                                               |         |
|         |   [==============================............] |         |  Y: 130-145 (Animated countdown)
|         |                                               |         |
|         |   Actions: Turn off 14 lights, arm alarm      |         |  Y: 160 (Font 2: 12px)
|         |                                               |         |
|         |   >>> WAVE HAND TO CANCEL EXECUTION <<<       |         |  Y: 185-200 (Flashing highlight)
|         +-----------------------------------------------+         |
|                                                                   |
+-------------------------------------------------------------------+
```

---

#### Layout Layout-04: Developer Diagnostics Matrix (Hacker Mode)
```
0-------------------------------------------------------------------303
| DEV-HUD | v2.4-PROD | MEM: 42MB | TASKS: 3 ACT | IP: 192.168.1.100|  Y: 0-16 (Font 1: 8px inverted)
|-------------------------------------------------------------------|  Y: 20
| BLE: ENGO-2_A4F1     | RSSI: -54 dBm   | MTU: 247 | Q-DEPTH: 0    |  Y: 28-42
| GATT STREAM: 48 pkts/s| CHR: 0xFF02 RX  | DROP: 0  | LAT: 16ms    |  Y: 46-60
|-------------------------------------------------------------------|  Y: 64
| ADAPTER METRICS:                                                  |  Y: 72-84 (Font 2: 12px underline)
| - ANDROID TV (ADB): 192.168.1.45:5555  -> RTT: 22ms [CONNECTED]   |  Y: 90-104
| - TUYA LOCAL (UDP): 10.0.0.88          -> DPS: 4/4  [SYNCED]      |  Y: 108-122
| - FREEBOX V6 (REST): mafreebox.free.fr -> 200 OK    [PING: 4ms]   |  Y: 126-140
| - GALAXY WATCH (BT): WEAR-OS-7         -> SYNCED    [BAT: 88%]    |  Y: 144-158
|-------------------------------------------------------------------|  Y: 164
| LAST TX: [0x1402] tuya_set_dp(101, 'dock') -> CONFIRMED (14ms)    |  Y: 172-190
| CORE STATUS: EVENT_LOOP_TICK: 1.8ms | MEM_PRESSURE: NOMINAL       |  Y: 196-210
|-------------------------------------------------------------------|  Y: 236
| DOUBLE-WAVE: EXIT DEV MODE                           FPS: 20 Hz   |  Y: 242-255 (Font 1: 8px)
+-------------------------------------------------------------------+
```

---

## 4. Latency Budget & BLE Transport Architecture

To deliver an interface that feels instantaneous and physical, the total latency from a hand wave to the visual update on the glasses must remain strictly **under 70 milliseconds**.

### End-to-End Latency Waterfall
```
Step 1: IR Sensor Hardware Detection & Internal Filter            ~10 ms
Step 2: BLE GATT Notification Packet over Radio (Glasses -> Host) ~14 ms
Step 3: Host OS Bluetooth Driver & Asyncio Event Loop Dispatch     ~6 ms
Step 4: OpenBridge State Router & Layout Payload Serializer        ~3 ms
Step 5: BLE GATT Command Packet over Radio (Host -> Glasses)      ~16 ms
Step 6: Cortex-M0 Command Parser & Memory Pointer Shift            ~4 ms
Step 7: Micro-OLED Pixel Refresh & Optical Latch                   ~4 ms
-------------------------------------------------------------------------
TOTAL ROUND-TRIP LATENCY (WAVE TO SCREEN RENDER):                 ~57 ms (EXCELLENT)
```

### Flow Control & Cortex-M0 Protection
ActiveLook devices use a low-power Cortex-M0 microcontroller with limited input buffers. If a host floods commands over BLE faster than the display engine can latch them, the glasses return a `FLOW CONTROL CMD ERROR` (`0x04`).
To guarantee 100% reliability:
1. **Pre-Cached Layouts:** Screen structures (frames, boxes, labels) are compiled into layout IDs during pairing (`imgSave` and `layoutSave`). Runtime updates send only the layout ID + string values (average 16 bytes per message).
2. **Leaky Bucket Rate Limiter:** OpenBridge clamps outgoing HUD updates to a maximum of 25 commands/second (40ms minimum inter-packet spacing), completely eliminating buffer overflows.
3. **Queue Prioritization:** Action Receipts (Priority 0) preempt ambient carousel updates (Priority 2).

---

## 5. Multi-Device Synergy (Glasses + Watch + Voice + Core)

```
                       +-------------------------------+
                       |   OPENBRIDGE ORCHESTRATOR     |
                       +-------------------------------+
                         /            |             \
                        /             |              \
                       v              v               v
            +----------------+ +---------------+ +---------------+
            |  GALAXY WATCH  | |  ANDROID TV   | |  ENGO GLASSES |
            |  (Wrist Audio) | |  (Big Screen) | |  (HUD Eyes)   |
            +----------------+ +---------------+ +---------------+
                    |                 |                 |
                    | (1) "Turn off   |                 |
                    |      Living     |                 |
                    |      Lights"    |                 |
                    +---------------->|                 |
                                      |                 |
                                      | (2) Executed    |
                                      +---------------->|
                                                        | (3) Visual Receipt:
                                                        | "Salon: Lights
                                                        |  OFF ✓" in view!
```

### Operational Workflows:
1. **The "Look & Confirm" Flow:**
   - User looks at a smart device (e.g. coffee maker).
   - User speaks into watch mic: *"Brew Lungo"*.
   - Watch STT sends text to OpenBridge.
   - Glasses instantly show brewing status: `"Coffee: Brewing Lungo [25s] ✓"`.
   - The user never breaks eye contact with their conversation or workspace.

2. **The "Non-Intrusive TV Assistant" Flow:**
   - While someone is watching a movie on Android TV, an alert arrives (e.g., package courier at gate).
   - Displaying an on-screen banner on the TV would disturb other viewers.
   - OpenBridge routes the alert exclusively to the user's ENGO glasses: `"Gate: Delivery Person Detected"`.
   - The user subtly waves their hand once to unlock the gate, without interrupting the movie.

---

## 6. Implementation & Priority Roadmap

```
+----------------------------------------------------------------------------------------------------+
|                                    PHASED DEPLOYMENT ROADMAP                                        |
+---------+------------------------------------------+--------------------+--------------------------+
| Phase   | Milestone                                | Focus Deliverables | Target Complexity        |
+---------+------------------------------------------+--------------------+--------------------------+
| PHASE 1 | Instant Receipts & Touchless Dismiss     | Features F2, F6    | Core BLE GATT & Receipt  |
| PHASE 2 | Ambient Status Glance & Wave Carousel    | Features F1, F3    | Layout Engine & Cycling  |
| PHASE 3 | IoT Radar & Tri-Device Synergy           | Features F4, F5    | Device Cross-Talk        |
| PHASE 4 | Developer Telemetry & Predictive Safety  | Features F8, F10   | Diagnostics & Two-Phase  |
+---------+------------------------------------------+--------------------+--------------------------+
```

### Phase 1: Minimal Action Receipt & Touchless Dismissal (Immediate Hackathon Milestone)
- Establish BLE GATT connection via ActiveLook Python adapter (`adapters/activelook.py`).
- Implement the basic binary command framer (`0xFF ... 0xAA`).
- Bind OpenBridge `transactions.py` event bus to push 3.5s optical confirmation overlays on action success/refusal.
- Map proximity wave interrupt to immediately dismiss receipts.

### Phase 2: Ambient Status Cards & Wave Carousel
- Register Layouts 01–04 into glasses flash memory.
- Implement the 4-card state machine with 350ms gesture debounce filtering.
- Connect Tuya vacuum, Freebox router, and Android TV state pollers to the HUD widget cache.
- Implement adaptive sleep timer (15s inactivity timeout for OLED and IR sensor).

### Phase 3: IoT Live Telemetry & Multi-Device Synergy
- Implement continuous robot vacuum tracker with battery, bin, and room status updates.
- Wire Wear OS watch voice commands and phone companion app events to trigger heads-up feedback.
- Deliver the "Non-Intrusive TV Assistant" notification routing policy.

### Phase 4: Developer Telemetry HUD & Two-Phase Commit Safety Gate
- Implement real-time packet roundtrip and RSSI telemetry matrix for smart home hackers.
- Implement the 5-second countdown progress bar with wave-to-abort for batch macros.
- Final validation against physical ENGO hardware and physical evidence ledger.

---

## 7. Compliance & Safety Verification

1. **Non-Privileged Input Safety:** The wave gesture alone cannot trigger destructive or irreversible changes (e.g. factory reset, unlocking high-security vaults) without a secondary confirmation factor (voice PIN or watch biometric confirmation).
2. **Visual Occlusion & Ergonomics:** All status layouts occupy <12% total pixel illumination and avoid central visual axis placement, maintaining strict compliance with road safety and eye-strain guidelines.
3. **Fail-Safe Disconnect Behavior:** If the BLE connection to OpenBridge is lost, the glasses display a small, discrete disconnected icon `[✕ OB]` for 5 seconds before clearing the screen and sleeping, preventing persistent stale data from misleading the user.
