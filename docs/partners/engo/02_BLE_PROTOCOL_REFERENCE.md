# ActiveLook® BLE Protocol Technical Reference Manual
**Hardware Platform: ENGO Smart Glasses (MicroOLED ActiveLook® HUD)**
**Architecture: Bluetooth Low Energy (BLE) Custom GATT Command Interface**

---

## 1. BLE GATT Service and Characteristic Architecture

The ActiveLook® architecture operates over standard Bluetooth Low Energy (Bluetooth 4.2 / 5.0). All display manipulation, layout orchestration, graphics streaming, and device telemetry flow through a proprietary primary GATT service, supplemented by standard Bluetooth SIG services.

### 1.1 Primary Custom Service: ActiveLook Commands Interface
* **Service UUID:** `0783B03E-8535-B5A0-7140-A304D2495CB7`

| Characteristic Name | UUID | Properties | Descriptors | Function & Payload Details |
| :--- | :--- | :--- | :--- | :--- |
| **RX ActiveLook** (Glasses Rx / Host Tx) | `0783B03E-8535-B5A0-7140-A304D2495CBA` | `Write`, `Write Without Response` | `0x2901` ("RX ActiveLook") | Primary command injection pipe. The host (phone, watch, OpenBridge gateway) writes binary-encoded command frames here. |
| **TX ActiveLook** (Glasses Tx / Host Rx) | `0783B03E-8535-B5A0-7140-A304D2495CB8` | `Notify` | `0x2901` ("TX ActiveLook"), `0x2902` (CCCD) | Asynchronous response pipe. Returns query outputs (e.g. `layoutList`, `fontList`, `pageGet`), command responses with matching Query IDs, and telemetry. |
| **Control / Flow Control** | `0783B03E-8535-B5A0-7140-A304D2495CB9` | `Notify`, `Read` | `0x2901` ("Control"), `0x2902` (CCCD) | Hardware flow control and buffer health monitoring. Prevents buffer saturation in the glasses' low-power MCU. |
| **Gesture Event** | `0783B03E-8535-B5A0-7140-A304D2495CBB` | `Notify` | `0x2901` ("Gesture Event"), `0x2902` (CCCD) | Optical touchless gesture sensor trigger. Notifies host when a hand wave or swipe occurs across the bridge. |
| **Touch Event** | `0783B03E-8535-B5A0-7140-A304D2495CBC` | `Notify` | `0x2901` ("Touch Event"), `0x2902` (CCCD) | Capacitive touch sensor trigger from frame/temple interactions. |

### 1.2 Complementary Standard GATT Services

#### Battery Service (`0x180F`)
* **Service UUID:** `0000180F-0000-1000-8000-00805F9B34FB`
* **Battery Level Characteristic UUID:** `00002A19-0000-1000-8000-00805F9B34FB` (`0x2A19`)
* **Properties:** `Read`, `Notify` (`0x2902` CCCD)
* **Cadence:** Automatically notifies battery percentage (`u8`, `0x00` - `0x64` = 0% to 100%) every 30 seconds once subscribed.
* **Firmware Safety Gate:** ActiveLook firmware rejects persistent flash writes (`cfgWrite`) if battery status is below 5%.

#### Device Information Service (`0x180A`)
* **Service UUID:** `0000180A-0000-1000-8000-00805F9B34FB`
* Contains standard characteristics:
  * Manufacturer Name (`0x2A29`): `"Microoled"`
  * Model Number (`0x2A24`): `"ENGO 1"` / `"ENGO 2"` / `"ENGO 3"`
  * Serial Number (`0x2A25`)
  * Firmware Revision (`0x2A26`)
  * Hardware Revision (`0x2A27`)

#### Firmware OTA Update Service (SUOTA)
* **Service UUID:** `0000FEF5-0000-1000-8000-00805F9B34FB`
* Used for Over-The-Air firmware updates and configuration profile migrations.

---

## 2. Command Packet Framing & Binary Wire Format

All commands sent to the **RX ActiveLook** characteristic (`...5CBA`) follow a deterministic binary framing structure.

### 2.1 Packet Frame Layout

```text
+----------+----------+----------+--------------------+-------------------+---------------+----------+
|   SOF    |  CMD ID  |   FMT    |       LENGTH       |     QUERY ID      |    PAYLOAD    |   EOF    |
| (1 Byte) | (1 Byte) | (1 Byte) | (1 or 2 Bytes MSB) | (0 to 15 Bytes)   |   (m Bytes)   | (1 Byte) |
|   0xFF   |  0xXX    |  0xXX    |       0xXX(XX)     |  [user defined]   | [params / data|   0xAA   |
+----------+----------+----------+--------------------+-------------------+---------------+----------+
```

### 2.2 Field Definitions & Byte Semantics

1. **SOF (Start of Frame):** Fixed sentinel byte `0xFF`.
2. **Command ID (CMD):** 1-byte opcode identifying the instruction (e.g. `0x01` = clear, `0x62` = layoutDisplay).
3. **Command Format (FMT):** 1-byte bitfield configuring frame header dimensions:
   * **Bit 5 (`0x20`):** Length field size selector:
     * `0`: Length is **1 byte** (`u8`, max frame length 255 bytes).
     * `1`: Length is **2 bytes** (`u16`, Big-Endian / Network byte order, frame length > 255 bytes).
   * **Bits 4..1 (`0x1E`):** Query ID size `n` in bytes (0 to 15 bytes):
     * Value encoded as `(n & 0x0F) << 1`.
   * **Bits 7, 6, 0:** Reserved (must be `0`).
   * *Common standard value:* `0x00` (1-byte Length, 0-byte Query ID).
4. **Length (LEN):** Total size of the frame in bytes, including `SOF`, `CMD`, `FMT`, `LEN`, `Query ID`, `Payload`, and `EOF`.
   * Minimum frame length: `5` bytes (`0xFF CMD FMT 0x05 0xAA`).
5. **Query ID (Optional):** User-defined token (`n` bytes, $0 \le n \le 15$).
   * Enables asynchronous correlation of requests and responses over BLE.
   * When present, the glasses echo this exact token in the response packet sent on the TX characteristic (`...5CB8`).
6. **Payload / Data:** Command-specific parameters.
   * Endianness: **Big-Endian (Most Significant Byte first)** for all numeric scalar types (`u16`, `s16`, `u32`, `s32`).
7. **EOF (End of Frame / Footer):** Fixed sentinel byte `0xAA`.

### 2.3 Concrete Wire Encoding Examples

#### Example 1: `clear` command (No Query ID)
* Command ID: `0x01`
* FMT: `0x00` (1-byte length, 0-byte Query ID)
* Total Length: 5 bytes (`0x05`)
* Payload: None
```text
Raw Hex: FF 01 00 05 AA
```

#### Example 2: `luma 12` (Set brightness to level 12)
* Command ID: `0x10`
* FMT: `0x00`
* Total Length: 6 bytes (`0x06`)
* Payload: `0x0C` (12)
```text
Raw Hex: FF 10 00 06 0C AA
```

#### Example 3: `layoutDisplay` (ID 20, Text "85")
* Command ID: `0x62`
* FMT: `0x00`
* Total Length: 9 bytes (`0x09`)
* Payload: `0x14` (ID 20), `'8'` (`0x38`), `'5'` (`0x35`), `'\0'` (`0x00`)
```text
Raw Hex: FF 62 00 09 14 38 35 00 AA
```

### 2.4 BLE ATT MTU Fragmentation & Reassembly
* BLE ATT standard MTU is typically 23 bytes (20-byte payload), but modern BLE controllers negotiate 247 or 512 bytes.
* If a command packet exceeds the negotiated MTU (e.g., bitmap uploads or bulk layout saves), the client splits the packet into sequential chunks across multiple `Write` operations.
* ActiveLook firmware maintains an internal reassembly buffer, accumulating incoming bytes until `Length` matches the received count and terminating with `0xAA`.

---

## 3. Flow Control & Memory Protection Protocol

To protect the ultra-low-power embedded ARM Cortex MCU and prevent Rx buffer overflow, ActiveLook enforces a hardware flow control loop via the **Control** characteristic (`0783B03E-8535-B5A0-7140-A304D2495CB9`).

### 3.1 Control Notification Byte Codes

| Byte Value | Meaning | Host Action Required |
| :---: | :--- | :--- |
| **`0x01`** | **Flow Control OK** | Safe buffer condition. Host is clear to transmit commands. |
| **`0x02`** | **Flow Control PAUSE** | Glasses Rx buffer has reached **75% capacity**. Host **MUST HALT** transmission immediately. |
| **`0x03`** | **Frame Error** | Message was corrupt, incomplete, or framing failed. Glasses dropped the packet. |
| **`0x04`** | **Queue Overflow Error** | Host continued writing during a PAUSE state; buffer overflowed. Commands lost. |
| **`0x05`** | **Reserved** | Internal system diagnostic. |
| **`0x06`** | **Permission Error** | Host attempted a flash configuration edit without issuing `cfgWrite` first. |

### 3.2 Host Implementation Rules
1. Subscribe to notifications on characteristic `0783B03E-8535-B5A0-7140-A304D2495CB9` immediately upon connection.
2. Maintain a local queue of outgoing BLE packets.
3. If notification `0x02` is received, suspend outgoing writes.
4. When notification `0x01` arrives, resume streaming from the queue.

---

## 4. Optical Display Specifications & Coordinate System

ENGO 1 and ENGO 2 glasses integrate a MicroOLED monochrome or dual-color high-efficiency AMOLED micro-display projecting into the user's field of view through a prism beam-splitter.

* **Native Resolution:** **304 pixels (Width) × 256 pixels (Height)**.
* **Coordinate Origin `(0, 0)`:** Top-left corner of the display matrix.
* **X-Axis:** Horizontal axis, extending from `0` (left) to `303` (right).
* **Y-Axis:** Vertical axis, extending from `0` (top) to `255` (bottom).
* **Primitive Coordinate Ranges:** Graphic primitives accept signed 16-bit integers (`s16`: `-32768` to `+32767`), enabling objects to be positioned partially off-screen without clipping crashes.
* **Layout Coordinate Ranges:** Layout bounding boxes require strictly positive unsigned values (`u16 x`, `u8 y`), strictly within `[0..303]` and `[0..255]`.
* **Grayscale Depth:** 16 discrete levels (`0` = black / off, `15` = maximum white / peak luminance).
* **Color Depth (on color variants):** 8-bit Red-Green color palette (81 distinct shades).

---

## 5. Core Command Set Reference

### 5.1 System & Power Control (Section 4.3)

| ID | Command | Parameters | Description |
| :---: | :--- | :--- | :--- |
| **`0x00`** | `displayPower` | `bool en` (1B) | `0x00`: Turn off display panel; `0x01`: Turn on display panel. |
| **`0x01`** | `clear` | None | Erases entire 304×256 frame buffer to black. |
| **`0x02`** | `grey` | `u8 lvl` (1B) | Sets default background gray level (0–15). |

### 5.2 Display Luminance / Brightness (Section 4.4)

| ID | Command | Parameters | Description |
| :---: | :--- | :--- | :--- |
| **`0x10`** | `luma` | `u8 level` (1B) | Sets display brightness level from `0` (dimmest) to `15` (brightest). Stored in non-volatile memory across reboots. When Ambient Light Sensor is active, this value acts as an offset. |

### 5.3 Sensor Configuration (Section 4.5)

| ID | Command | Parameters | Description |
| :---: | :--- | :--- | :--- |
| **`0x20`** | `sensor` | `bool en` (1B) | Enables (`0x01`) or disables (`0x00`) the Ambient Light Sensor (ALS) for auto-brightness adjustment. |
| **`0x21`** | `gesture` | `bool en` (1B) | Enables (`0x01`) or disables (`0x00`) the optical proximity gesture sensor. |

### 5.4 Graphic Drawing Primitives (Section 4.6)

All coordinate values are `s16` (2 bytes, Big-Endian).

| ID | Command | Parameters | Data Size | Description |
| :---: | :--- | :--- | :---: | :--- |
| **`0x30`** | `grayscale` | `u8 lvl` | 1 B | Sets active drawing gray level (0 to 15). |
| **`0x31`** | `point` | `s16 x`, `s16 y` | 4 B | Sets a single pixel at `(x, y)`. |
| **`0x32`** | `line` | `s16 x0`, `s16 y0`, `s16 x1`, `s16 y1` | 8 B | Draws a 1-pixel vector line between `(x0, y0)` and `(x1, y1)`. |
| **`0x33`** | `rect` | `s16 x0`, `s16 y0`, `s16 x1`, `s16 y1` | 8 B | Draws an empty outline rectangle. |
| **`0x34`** | `rectf` | `s16 x0`, `s16 y0`, `s16 x1`, `s16 y1` | 8 B | Draws a solid filled rectangle. |
| **`0x35`** | `circ` | `s16 x`, `s16 y`, `u8 r` | 5 B | Draws an empty circle centered at `(x, y)` with radius `r`. |
| **`0x36`** | `circf` | `s16 x`, `s16 y`, `u8 r` | 5 B | Draws a solid filled circle. |
| **`0x37`** | `txt` | `s16 x`, `s16 y`, `u8 rot`, `u8 font`, `u8 grey`, `str text` | $\ge 7$ B | Draws dynamic text string at `(x, y)` with rotation, font index, and gray level. |
| **`0x38`** | `polyline` | `u8 thickness`, `u8 rsvd1`, `u8 rsvd2`, `s16 pts[]` | Var | Draws contiguous connected vector lines. |
| **`0x3C`** | `arc` | `s16 x`, `s16 y`, `u8 r`, `s16 start_ang`, `s16 end_ang`, `u8 thick` | 10 B | Draws circular arc. Angles in degrees starting at 3 o'clock clockwise. |
| **`0x3D`** | `color` | `u8 col` | 1 B | Sets active drawing color (for color-enabled hardware). |

### 5.5 Bitmaps & Images (Section 4.7)

* **`0x41` — `imgSave`:** Stores an image asset into flash memory under an assigned ID (`u8 id`, `u32 size`, `u16 width`, `u8 format`, followed by binary payload chunks). Requires `cfgWrite` session.
* **`0x42` — `imgDisplay`:** Instantly renders stored bitmap `u8 id` at coordinates `s16 x`, `s16 y`.
* **`0x44` — `imgStream`:** Streams an uncompressed or compressed bitmap directly to screen without persistent storage (`u32 size`, `u16 width`, `s16 x`, `s16 y`, `u8 format` + data).
* **Supported Formats:**
  * `0x00`: 4-bit per pixel (16 levels of gray)
  * `0x01`: 1-bit per pixel (monochrome bitmask)
  * `0x02` / `0x03`: Heatshrink-compressed grayscale / monochrome bitmaps
  * `0x08`: 8-bit color with 4-bit alpha transparency

### 5.6 Font Management (Section 4.8)

* **`0x50` — `fontList`:** Queries list of installed fonts. Glasses return pairs of `(u8 fontId, u8 fontHeight)`.
* **`0x51` — `fontSave`:** Uploads custom font package to device flash (`u8 id`, `u16 size`, followed by glyph bitmask chunks). Max package size: 8,192 bytes.
* **`0x52` — `fontSelect`:** Sets default font ID (`u8 id`) used by subsequent text commands.
* **`0x53` — `fontDelete`:** Deletes font ID from flash (`0xFF` deletes all custom fonts).

---

## 6. Layouts and Widgets System (High-Efficiency HUD Engine)

To maximize battery autonomy and reduce BLE packet overhead, ActiveLook discourages redrawing raw primitives during live operation. Instead, it uses a **Declarative Layout and Widget Architecture**.

### 6.1 Architectural Principle
1. **Pre-configuration Phase:** Complex UI templates (widgets, labels, gauge arcs, icons, static units) are compiled and stored in glasses flash memory via `layoutSave` (`0x60`) or JSON configuration tools (`Config-Generator`).
2. **Runtime Execution Phase:** Host sends minimal dynamic updates (e.g. 2 to 6 bytes) targeting specific layout IDs via `layoutDisplay` (`0x62`) or `gaugeDisplay` (`0x70`).
3. **Automatic Delta Clipping:** The glasses MCU automatically clears only the widget's registered bounding box and repaints the new value, eliminating full-screen redraw flicker and saving radio bandwidth.

### 6.2 Layout Commands (Section 4.9)

| ID | Command | Parameters | Description |
| :---: | :--- | :--- | :--- |
| **`0x60`** | `layoutSave` | `layout parameters` ($\ge 17$ B) | Defines and saves a layout widget with bounding box, font, and style in flash memory. |
| **`0x61`** | `layoutDelete` | `u8 id` | Deletes layout `id` (`0xFF` deletes all). |
| **`0x62`** | `layoutDisplay` | `u8 id`, `str text[255]` | Injects dynamic text string into layout template `id`. |
| **`0x63`** | `layoutClear` | `u8 id` | Clears the screen bounding box associated with layout `id`. |
| **`0x64`** | `layoutList` | None | Returns array of all saved layout IDs. |
| **`0x65`** | `layoutPosition` | `u8 id`, `u16 x`, `u8 y` | Permanently moves layout widget origin. |
| **`0x66`** | `layoutDisplayExtended` | `u8 id`, `u16 x`, `u8 y`, `str text`, `extraCmd[]` | Renders text at temporary position with inline supplementary graphic commands. |
| **`0x67`** | `layoutGet` | `u8 id` | Retrieves layout parameters from glasses. |
| **`0x68`** | `layoutClearExtended` | `u8 id`, `u16 x`, `u8 y` | Clears layout bounding box at overridden position. |
| **`0x69`** | `layoutClearAndDisplay` | `u8 id`, `str text` | Atomic clear and redraw of layout widget. |
| **`0x6A`** | `layoutClearAndDisplayExtended` | `u8 id`, `u16 x`, `u8 y`, `str text`, `extraCmd[]` | Atomic clear and redraw at overridden coordinates. |
| **`0x6B`** | `layoutSaveInColor` | `layout parameters` ($\ge 17$ B) | Saves layout with RGB color parameters (color models). |

### 6.3 Anatomy of `layoutSave` Parameters ($\ge 17$ Bytes)

A layout definition structure encodes the following contiguous byte fields:
1. `u8 id`: Unique Layout Identifier (1..254).
2. `u16 x`: Top-left horizontal coordinate (`0` to `303`).
3. `u8 y`: Top-left vertical coordinate (`0` to `255`).
4. `u16 width`: Bounding box width for auto-clipping.
5. `u8 height`: Bounding box height for auto-clipping.
6. `u8 foreColor`: Foreground gray level (`0` to `15`) or color index.
7. `u8 backColor`: Background fill color/gray level.
8. `u8 font`: Font ID index to use for dynamic text.
9. `bool textValid`: Whether text rendering is enabled.
10. `u8 textRotation`: Text orientation (`0` = 0°, `1` = 90°, `2` = 180°, `3` = 270°).
11. `u16 textX`: Offset X within layout bounding box.
12. `u8 textY`: Offset Y within layout bounding box.
13. `u8 extraCmds[]`: Optional concatenated graphic primitives (e.g., static outline box, icon, or label).

### 6.4 Gauges System (Section 4.10)

* **`0x71` — `gaugeSave`:** `u8 id, s16 x, s16 y, u16 r, u16 rIn, u8 start_angle, u8 end_angle, bool clockwise` (12 bytes). Defines an arc or donut gauge in flash memory.
* **`0x70` — `gaugeDisplay`:** `u8 id, u8 value` (2 bytes). Sets and animates gauge fill percentage (`0` to `100%`).
* **`0x72` — `gaugeDelete`:** Deletes gauge ID.
* **`0x73` — `gaugeList`:** Queries installed gauges.

### 6.5 Pages System (Multi-Widget Dashboard Grouping - Section 4.11)

A Page allows grouping up to 10 independent layouts into an active full-screen dashboard screen.

* **`0x80` — `pageSave`:** `u8 id`, followed by `n` tuples of `(u8 layoutId, u16 x, u8 y)`. Binds multiple layouts into a unified screen layout.
* **`0x83` — `pageDisplay`:** `u8 id, str text1 \0 text2 \0 ... textN`.
  * **Critical Performance Feature:** Allows updating all dynamic widgets on the screen (e.g. Speed, Heart Rate, Battery, Cadence) **inside a single BLE packet**, separated by null characters (`\0`).
* **`0x84` — `pageClear`:** Erases all widgets belonging to page `id`.
* **`0x86` — `pageClearAndDisplay`:** Atomic clear and repaint of all page widgets.

---

## 7. Sensors & Real-Time Event Telemetry

ENGO glasses integrate hardware sensors designed for hands-free, touchless athletic and operational interaction.

### 7.1 Optical Proximity Gesture Sensor
* **Hardware:** Infrared optical distance/proximity sensor situated on the bridge / inner frame adjacent to the nose pad.
* **Detection Principle:** Detects physical objects passing through the optical emitter/detector cone within 5 to 15 cm of the frame.
* **Activation Command:** Host sends `0x21 0x01` (`gesture true`) to activate the sensor.
* **BLE Notification:**
  * **Characteristic UUID:** `0783B03E-8535-B5A0-7140-A304D2495CBB` (CCCD `0x2902` must be set to `0x0001`).
  * **Payload:** Emits single byte `0x01` upon detecting a hand wave or swipe across the front of the glasses.
* **HUD UX Paradigm:**
  * Used in sports and technical work to toggle between display Pages (e.g. Page 1: Navigation $\rightarrow$ Wave $\rightarrow$ Page 2: Metrics $\rightarrow$ Wave $\rightarrow$ Page 3: Device Alerts) without needing buttons or smartphone interaction.

### 7.2 Capacitive Frame Touch Sensor
* **Characteristic UUID:** `0783B03E-8535-B5A0-7140-A304D2495CBC`
* Notifies host of physical taps or touches on the eyewear temples, providing secondary physical interaction telemetry.

### 7.3 Ambient Light Sensor (ALS)
* **Activation Command:** Host sends `0x20 0x01` (`sensor true`).
* Automatically adjusts OLED micro-display drive currents based on real-time ambient lux, ensuring high contrast in direct sunlight and preventing glare in dark indoor environments.
* The `luma` command (`0x10`) acts as a calibrated user brightness offset when ALS is running.

### 7.4 Battery Telemetry & Power Management
* **Service:** Battery Service `0x180F`, Characteristic `0x2A19`.
* **Behavior:** Pushes `u8` percentage every 30 seconds.
* **Thresholds:**
  * $> 15\%$: Normal high-contrast operation.
  * $5\% - 15\%$: Low battery state; recommendation to disable ALS and throttle refresh rates.
  * $< 5\%$: Critical threshold. ActiveLook firmware locks out persistent flash writes (`cfgWrite`, `layoutSave`, `fontSave`) to prevent flash corruption during brownout.

---

## 8. OpenBridge Integration Blueprint

For the OpenBridge ecosystem, ENGO glasses act as an ultra-glanceable heads-up peripheral adapter (`src/adapters/engo.py`).

```text
+-----------------------+                    +------------------------------------+
|  OpenBridge Runtime   |                    |       ENGO Smart Glasses           |
| (Gateway / PC / Host) |                    | (MicroOLED ActiveLook Firmware)    |
+-----------------------+                    +------------------------------------+
           |                                                   |
           |----- Connect BLE (Device Info / Services) ------->|
           |<---- Services Discovered (0783B03E...5CB7) -------|
           |                                                   |
           |----- Subscribe CCCD (Control ...5CB9) ----------->|
           |----- Subscribe CCCD (TX Data ...5CB8) ----------->|
           |----- Subscribe CCCD (Gesture ...5CBB) ----------->|
           |----- Subscribe CCCD (Battery 0x2A19) ------------>|
           |                                                   |
           |===== SETUP PHASE (Flash / Layout Upload) ========|
           |----- Write: cfgWrite Start ---------------------->|
           |----- Write: layoutSave ID 1 (Device Status) ----->|
           |----- Write: layoutSave ID 2 (Alert Toast) ------->|
           |----- Write: pageSave ID 1 [Layout 1, Layout 2] -->|
           |                                                   |
           |===== RUNTIME STREAMING ==========================|
           |----- Write: pageDisplay ID 1 "Vacuum · Clean\0" ->|
           |                                                   |
           |<---- Notify Gesture Event: 0x01 (Hand Wave) ------|
           | [OpenBridge cycles HUD view: Page 1 -> Page 2]    |
           |----- Write: pageDisplay ID 2 "Lights · 4 ON\0" -->|
           |                                                   |
           |<---- Notify Control: 0x02 (Buffer 75% Full) ------|
           | [OpenBridge halts outbound BLE writes]            |
           |<---- Notify Control: 0x01 (Buffer Drained) -------|
           | [OpenBridge resumes normal transmission]          |
```

---
*Reference Author: ActiveLook BLE Protocol Analyst (OpenBridge Team)*  
*Verified against ActiveLook API Documentation v4.12 & MicroOLED Technical Specifications.*
