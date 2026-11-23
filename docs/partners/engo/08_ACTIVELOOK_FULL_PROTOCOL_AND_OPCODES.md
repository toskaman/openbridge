# ActiveLook Low-Level Binary Protocol and Complete Opcode Reference

> **ActiveLook® v4.x specification (as implemented by OpenBridge's adapter and emulator).**
> Used by: ENGO 1, ENGO 2, ENGO 3, ENGO 3 Titanium, Julbo EVAD-1, Cosmo Connected.
> SoC architecture: Dialog Semiconductor / Renesas DA1469x ARM Cortex-M4 + 304×256 MicroOLED.
>
> Reference: the public [ActiveLook API documentation](https://github.com/ActiveLook). Behaviour on a physical
> ENGO pair is still to be confirmed (validation so far: emulator only).

---

## 1. BLE GATT architecture and services

ActiveLook exposes a proprietary custom GATT service plus standard services:

| Service / characteristic | UUID | Properties | Role / description |
| :--- | :--- | :--- | :--- |
| **ActiveLook Service** | `0783B03E-8535-B5A0-7140-A304D2495CB7` | — | Main command interface |
| **Server TX** | `0783B03E-8535-B5A0-7140-A304D2495CB8` | `Notify` | Query responses, metadata, state |
| **Control / FlowCtrl** | `0783B03E-8535-B5A0-7140-A304D2495CB9` | `Notify` | Flow control (`0x01` = OK, `0x02` = pause at 75 %) and errors |
| **Server RX** | `0783B03E-8535-B5A0-7140-A304D2495CBA` | `Write`, `WriteWithoutResponse` | Binary write stream (central ➔ glasses) |
| **Gesture Event** | `0783B03E-8535-B5A0-7140-A304D2495CBB` | `Notify` | Notifies `0x01` on an IR optical swipe |
| **Touch Event** | `0783B03E-8535-B5A0-7140-A304D2495CBC` | `Notify` | Notifies `0x01` on a temple touch |
| **Battery Service** | `0000180F-0000-1000-8000-00805F9B34FB` | — | Standard battery service |
| **Battery Level** | `00002A19-0000-1000-8000-00805F9B34FB` | `Read`, `Notify` | Level 0–100 % (auto-notify every 30 s) |
| **Device Information (DIS)** | `0000180A-0000-1000-8000-00805F9B34FB` | — | Model (`0x2A24`), manufacturer (`0x2A29`), firmware (`0x2A26`) |
| **Dialog SUOTA Service** | `0000FEF5-0000-1000-8000-00805F9B34FB` | — | Over-the-air firmware update (DA1469x) |

---

## 2. Anatomy of a binary packet

Every packet on **Server RX** or **Server TX** follows this framing:

```text
+----------+----------+------------+------------+---------------+--------------+----------+
| Start    | Opcode   | Cmd Format | Length     | Query ID      | Data Payload | Footer   |
| 1 byte   | 1 byte   | 1 byte     | 1 or 2 B   | 0..15 bytes   | 0..512 bytes | 1 byte   |
| (0xFF)   | (Cmd ID) | (bitmask)  | (big-end.) | (optional)    | (parameters) | (0xAA)   |
+----------+----------+------------+------------+---------------+--------------+----------+
```

### Fields
1. **Start byte:** always `0xFF`.
2. **Opcode (command ID):** `0x00` to `0xFF`.
3. **Command format (1 byte, bitmask):**
   - **Bit 5 (`0x20`)**: length on 1 byte (`0`) if the total is $\le 255$ bytes, or on 2 bytes (`1`) if the total is $> 255$ bytes (big-endian).
   - **Bits 4..1 (`0x1E`)**: query-ID length (`0` to `15` bytes): `(fmt & 0x1E) >> 1`.
   - **Bits 7, 6, 0**: reserved (0).
   - Usual format without a query ID: `0x00` (1-byte length) or `0x20` (2-byte length).
4. **Length:** total length in bytes of the whole frame, from `0xFF` to `0xAA` inclusive. Maximum = **533 bytes** (1 + 1 + 1 + 2 + 15 + 512 + 1).
5. **Query ID (optional):** arbitrary tracking identifier (0 to 15 bytes). The firmware echoes it in the asynchronous TX response for correlation.
6. **Data payload:** command parameters. **Strictly big-endian (MSB first)** for every 16-bit and 32-bit integer (`s16`, `u16`, `u32`).
7. **Footer byte:** always `0xAA`.
8. **Integrity:** no application-level CRC; the BLE L2CAP link layer has a 24-bit hardware CRC. A frame is validated by `0xFF`, the exact length and `0xAA`.

---

## 3. Hardware flow control (`...5CB9`)

The glasses' microcontroller has a **1,024-byte** receive buffer (room for two maximum frames of 512 data bytes).

Notifications on the `...5CB9` control characteristic:
- `0x01` (`FLOW_OK`): buffer below the safety threshold. The BLE central may send.
- `0x02` (`FLOW_PAUSE`): the buffer reached **75 % capacity** (768 bytes). The host **MUST stop writing immediately**.
- `0x03` (`CMD_ERROR`): corrupt frame (wrong `0xFF`/`0xAA` delimiter, inconsistent length). Command rejected.
- `0x04` (`BUFFER_OVERFLOW`): buffer full (100 %), incoming packet rejected.
- `0x06` (`MISSING_CONFIG`): attempt to modify flash (layout, image, font) without a prior `cfgWrite` (`0xD0`).

> [!WARNING]
> **Flow-control deadlock (field workaround):**
> If the glasses send `0x02` but the resume packet `0x01` is lost in a noisy RF environment, the host can stay
> blocked forever.
> **Production fix:** arm a **1,000 ms** software watchdog when `0x02` arrives. If no `0x01` is received within
> one second, force `can_send = true` and dequeue the next packet.

---

## 4. Complete ActiveLook opcode register

### 4.1 System and hardware configuration (`0x00`–`0x2F`)

| Opcode | Mnemonic | Parameters | Description |
| :---: | :--- | :--- | :--- |
| `0x00` | `displayPower` | `bool en` (1B) | `0x00` = off, `0x01` = on. Switches the MicroOLED power. |
| `0x01` | `clear` | none | Clears the screen memory to full black (0 mW). |
| `0x02` | `grey` | `u8 lvl` (1B, 0..15) | Fills the whole screen with one uniform grey level. |
| `0x03` | `demo` | `u8 id` (1B) | `0` = fill, `1` = alignment target, `2` = stored-image loop. |
| `0x05` | `battery` | none | Battery query. Returns `u8 percent` (0..100 %). |
| `0x06` | `vers` | none | Firmware query. Returns 9 bytes: `fwVersion[4]`, `year`, `week`, `serial[3]`. |
| `0x08` | `led` | `u8 state` (1B) | `0` = off, `1` = on, `2` = toggle, `3` = blink. Drives the internal green test LED. |
| `0x09` | `shift` | `s16 x, s16 y` (4B) | Global optical offset (-128..+127). Saved in flash. |
| `0x0A` | `settings` | none | Active settings query. Returns 5 bytes (`x`, `y`, `luma`, `als`, `gesture`). |
| `0x10` | `luma` | `u8 level` (1B, 0..15) | Manual display luminance (0 = min, 15 = max 10,000 nits). Persistent. |
| `0x20` | `sensor` | `bool en` (1B) | Enables/disables both the ALS and the IR gesture sensor. |
| `0x21` | `gesture` | `bool en` (1B) | Enables/disables the IR swipe sensor only. Persistent. |
| `0x22` | `als` | `bool en` (1B) | Enables/disables the ambient light sensor only. Persistent. |

---

### 4.2 2D graphics primitives and text (`0x30`–`0x3E`)

| Opcode | Mnemonic | Parameters | Description |
| :---: | :--- | :--- | :--- |
| `0x30` | `grayscale` | `u8 lvl` (1B, 0..15) | Sets the active grey level for the next drawing calls. |
| `0x31` | `point` | `s16 x, s16 y` | Draws one pixel at `(x, y)`. |
| `0x32` | `line` | `s16 x0, y0, x1, y1` | Draws a 1 px vector line segment. |
| `0x33` | `rect` | `s16 x0, y0, x1, y1` | Draws a rectangle outline. |
| `0x34` | `rectf` | `s16 x0, y0, x1, y1` | Fills a solid rectangle (pixels lit at the active grey level). |
| `0x35` | `circ` | `s16 x, y, u8 r` | Draws a circle outline of radius `r`. |
| `0x36` | `circf` | `s16 x, y, u8 r` | Fills a solid disc of radius `r`. |
| `0x37` | `txt` | `s16 x, y, u8 rot, font, grey, str text\0` | Draws a `0x00`-terminated UTF-8/ASCII string. |
| `0x38` | `polyline` | `u8 thick, rsvd1, rsvd2, (s16 x, y)...` | Draws a continuous polyline with a pixel thickness. |
| `0x39` | `holdFlush` | `u8 action` (1B) | `0` = hold (buffer), `1` = flush (atomic render to the screen). |
| `0x3C` | `arc` | `s16 x, y, u8 r, s16 start, end, u8 thick` | Draws an arc in degrees (0° = 3 o'clock, clockwise). |
| `0x3D` | `color` | `u8 color_id` (1B) | Selects the active colour on the ENGO 3 MultiColor. |
| `0x3E` | `txtColor` | `s16 x, y, u8 rot, font, color, str text\0` | Draws text directly with a palette colour ID. |

---

### 4.3 Images and fonts (`0x41`–`0x53`)

| Opcode | Mnemonic | Parameters | Description |
| :---: | :--- | :--- | :--- |
| `0x41` | `imgSave` | `u8 id, u32 size, u16 w, u8 fmt` | Saves a compressed 4 bpp bitmap (Heatshrink) to flash. |
| `0x42` | `imgDisplay` | `u8 id, s16 x, s16 y` | Displays a bitmap stored in flash at `(x, y)`. |
| `0x44` | `imgStream` | `u32 size, u16 w, s16 x, y, u8 fmt, data...` | Streams a bitmap to the screen without writing flash. |
| `0x45` | `imgSave1bpp` | `u8 id, u32 size, u16 w` | Saves a 1-bit monochrome image (8 pixels/byte). |
| `0x46` | `imgDelete` | `u8 id` (1B) | Deletes image `id` (`0xFF` = delete all images). |
| `0x47` | `imgList` | none | Returns the stored images `[u8 id, u16 w, u16 h]`. |
| `0x50` | `fontList` | none | Returns the available fonts `[u8 id, u8 height]`. |
| `0x51` | `fontSave` | `u8 id, u16 size` + chunks | Saves a custom font glyph table to flash. |
| `0x52` | `fontSelect` | `u8 id` (1B) | Sets the default active font. |
| `0x53` | `fontDelete` | `u8 id` (1B) | Deletes a custom font (`0xFF` = all). |

---

### 4.4 Widget, layout and page engine (`0x60`–`0x86`)

| Opcode | Mnemonic | Parameters | Description |
| :---: | :--- | :--- | :--- |
| `0x60` | `layoutSave` | 17-byte header + sub-commands | Saves a greyscale widget template (bounding box, font, offset). |
| `0x61` | `layoutDelete` | `u8 id` | Deletes a layout (`0xFF` = all). |
| `0x62` | `layoutDisplay` | `u8 id, str text\0` | Displays dynamic text in the layout's reserved slot. |
| `0x63` | `layoutClear` | `u8 id` | Clears the layout's clipping area. |
| `0x64` | `layoutList` | none | Returns the IDs of saved layouts. |
| `0x65` | `layoutPosition`| `u8 id, u16 x, u8 y` | Permanently moves the layout origin. |
| `0x69` | `layoutClearAndDisplay` | `u8 id, str text\0` | Atomic clear + draw in the layout (no flicker). |
| `0x6B` | `layoutSaveInColor` | 17-byte header + sub-commands | Saves a layout template with colour palettes (ENGO 3). |
| `0x70` | `gaugeDisplay`| `u8 id, u8 value` (2B) | Updates a circular / linear gauge (value 0 to 100 %). |
| `0x71` | `gaugeSave` | 12-byte definition | Creates a gauge (`id, x, y, r, rIn, start_deg, end_deg, clockWise`). |
| `0x80` | `pageSave` | `u8 id, (u8 layoutId, u16 x, u8 y)...` | Binds up to 10 layouts into a multi-slot view. |
| `0x83` | `pageDisplay` | `u8 id, str s1\0 s2\0 ... sN\0` | Updates every layout of the page in a single BLE packet. |
| `0x86` | `pageClearAndDisplay` | `u8 id, str s1\0 s2\0 ... sN\0` | Atomic box clear and text update. |

---

### 4.5 3 MB NOR flash pool management (`0xD0`–`0xD8`)

| Opcode | Mnemonic | Parameters | Description |
| :---: | :--- | :--- | :--- |
| `0xD0` | `cfgWrite` | `str name[12], u32 ver, u32 pwd` | Opens/allocates a configuration container. Requires battery $\ge 5\%$. |
| `0xD1` | `cfgRead` | `str name[12]` | Returns the number of items in the named container. |
| `0xD2` | `cfgSet` / `cfgSelect` | `str name[12]` | Activates the configuration (loads fonts and templates into RAM). |
| `0xD3` | `cfgList` | none | Returns the configuration catalogue: size, version, usage counter. |
| `0xD4` | `cfgRename` | `str old[12], str new[12], u32 pwd` | Renames a configuration container. |
| `0xD5` | `cfgDelete` | `str name[12]` | Deletes a configuration and frees its flash blocks. |
| `0xD6` | `cfgDeleteLessUsed` | none | LRU garbage collector: deletes the least-used configuration. |
| `0xD7` | `cfgFreeSpace` | none | Returns the free flash space in bytes (3 MB pool). |
| `0xD8` | `cfgGetNb` | none | Returns the total number of installed containers (max 12). |

---

### 4.6 Low-level system and diagnostic commands (`0xE0`–`0xE3`)

| Opcode | Mnemonic | Parameters | Description |
| :---: | :--- | :--- | :--- |
| `0xE0` | `shutdown` | `u32 key` (4B) | Magic key `0x6F 0x7F 0xC4 0xEE`. Powers off the MCU. Refused while USB is connected. |
| `0xE1` | `reset` | `u32 key` (4B) | Magic key `0x5C 0x1E 0x2D 0xE9`. Restarts the MCU. Allowed only on USB. |
| `0xE2` | `error` | `u8 cmdId, u8 err, u8 subErr` | Asynchronous notification sent to the central on an execution fault. |
| `0xE3` | `rdDevInfo` | `u8 id` (1B) | Hardware identity query: `0` = platform, `1` = manufacturer, `3` = model, `5` = firmware version, `6` = serial number. |
