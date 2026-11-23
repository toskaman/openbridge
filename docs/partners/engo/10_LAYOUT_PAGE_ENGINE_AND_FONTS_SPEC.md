# ActiveLook Layout, Page, Font and Flash Memory Engine

> **High-fidelity implementation spec.**
> How ActiveLook removes flicker, cuts bandwidth by about 10× and manages persistent flash profiles.
> Implemented in OpenBridge's adapter and the HUD Studio emulator; hardware confirmation pending.

---

## 1. Why the layout / page model?

Sending raw drawing commands (`txt`, `rect`, `line`) at 1 Hz to refresh several values (speed, heart rate,
power, time) causes three major problems:
1. **BLE bandwidth saturation:** four separate fields need about 150 bytes per second.
2. **Perceived latency and flicker:** the microcontroller processes each command one after another.
3. **Radio power drain:** the BLE module stays in high-power transmit mode.

ActiveLook solves this by splitting the interface into two levels:
- **Layouts (`0x60` / `0x6B`):** persistent templates stored in flash (clipping box, text position, font,
  colour, static background elements).
- **Pages (`0x80`):** sets of 1 to 10 layouts on one screen.
- **Multi-slot display (`0x83 pageDisplay`):** a single 15–30-byte BLE frame that carries only the text
  strings, separated by binary zeros (`\0`).

---

## 2. Binary structure of a layout (`layoutSave` `0x60` / `0x6B`)

A layout is defined by a **fixed 17-byte base header**, optionally followed by serialised vector drawing
sub-commands:

```text
+----+------+--------+----+---------+----+-----------+-----------+------+-----------+--------+--------+----------+-----------+
| id | size | x      | y  | width   | h  | foreColor | backColor | font | textValid | textX  | textY  | textRot  | textOpac  |
| 1B | 1B   | 2B(BE) | 1B | 2B(BE)  | 1B | 1B        | 1B        | 1B   | 1B        | 2B(BE) | 1B     | 1B       | 1B        |
+----+------+--------+----+---------+----+-----------+-----------+------+-----------+--------+--------+----------+-----------+
0    1      2        4    5         7    8           9           10     11          12       14       15         16
```

### Header fields (17 bytes)
| Offset | Type | Name | Description |
| :---: | :--- | :--- | :--- |
| `0` | `u8` | `id` | Layout identifier (`0x00` to `0xFF`). |
| `1` | `u8` | `size` | Size in bytes of the static sub-commands that follow (`0` if none). |
| `2..3` | `u16` (BE) | `x` | Top-left X of the clipping area (`0` to `303`). |
| `4` | `u8` | `y` | Top-left Y of the clipping area (`0` to `255`). |
| `5..6` | `u16` (BE) | `width` | Clipping-area width in pixels. |
| `7` | `u8` | `height` | Clipping-area height in pixels. |
| `8` | `u8` | `foreColor` | Foreground colour (grey levels `0..15`, or palette `0x00..0x50` on ENGO 3). |
| `9` | `u8` | `backColor` | Background colour (usually `0` = black, pixels off). |
| `10` | `u8` | `font` | Font ID used for the dynamic text field (`1..5`). |
| `11` | `u8` / `bool`| `textValid` | `1` = the layout accepts dynamic text, `0` = graphics-only widget. |
| `12..13`| `u16` (BE) | `textX` | Text X offset relative to the layout origin. |
| `14` | `u8` | `textY` | Text Y offset relative to the layout origin. |
| `15` | `u8` | `textRotation` | Anchoring and orientation mode (`0` = horizontal LTR, `4` = centred). |
| `16` | `u8` | `textOpacity` | `0` = transparent background, `1` = opaque background. |

### Serialised sub-commands (bytes 17 to 17 + `size`)
If `size > 0`, the header is followed by static drawing commands (icons, separator lines, units) that are
automatically clipped to `(x, y, width, height)`.

---

## 3. Defining and displaying a page (`pageSave` and `pageDisplay`)

### A. Saving a page (`0x80 pageSave`)
A page brings up to 10 layouts together on one screen, each with explicit display coordinates:
- `Byte 0`: `u8 id` (page identifier).
- Sequence of slots (4 bytes per slot):
  `u8 layoutId, u16 x, u8 y`

### B. Atomic display (`0x83 pageDisplay` / `0x86 pageClearAndDisplay`)
To refresh the whole screen, the central sends only the page ID followed by the dynamic strings,
concatenated and separated by zeros (`\x00`):
`[0xFF] [0x83] [Fmt] [Len] [u8 pageId] [String_Layout1\x00] [String_Layout2\x00] ... [String_LayoutN\x00] [0xAA]`

#### Firmware behaviour
1. For each slot $i$ of the page:
   - The target origin is `(page.x_i, page.y_i)`.
   - The clipping box `[ox, oy, ox + layout.width, oy + layout.height]` is cleared to `backColor` (black).
   - The layout's static sub-commands are drawn.
   - If `textValid` is true and `String_Layout_i` is not empty, it is drawn at `(ox + layout.textX, oy + layout.textY)`.
2. Result: no flicker, and no coordinates or fonts sent over BLE.

---

## 4. Built-in fonts and ghost characters

ENGO glasses use the bitmap **SourceSansPro SemiBold** family:

| ID | Height | Character set | Typical use |
| :---: | :---: | :--- | :--- |
| **Font 1** | **24 px** | Full ASCII (`0x20` to `0x7E`) | Unit labels ("km/h", "bpm", "W"), states |
| **Font 2** | **38 px** | Full ASCII (`0x20` to `0x7E`) | Secondary metrics, 3- and 4-field screens |
| **Font 3** | **64 px** | Full ASCII (`0x20` to `0x7E`) | Main metric, heart rate, pace |
| **Font 4** | **75 px** | Digits and punctuation (`0x20` to `0x3B`) | Large numeric speed counters |
| **Font 5** | **82 px** | Digits and punctuation (`0x20` to `0x3B`) | Giant full-screen single field |

### Ghost characters for numeric alignment
To stop numbers from shifting left and right as values change, without forcing a monospace font,
ActiveLook provides two invisible glyphs:
1. **`$` (ASCII `0x24`):** drawn in full black (pixels off, invisible). Its advance width is **exactly the
   width of the digit '0'**.
   *Example:* `$$5` takes exactly the same physical width as `125`.
2. **`&` (ASCII `0x26`):** drawn in full black. Its advance width **matches punctuation** ('.', ':', ',').
   *Example:* reserves space to line up decimal separators in a table.

---

## 5. 3 MB NOR flash manager and configuration profiles

The firmware reserves **3 megabytes** of NOR flash split into **12 configuration containers**:

```text
+---------------------------------------------------------------------+
| NOR flash 3 MB (shared storage pool)                                |
| +---------------------+ +---------------------+ +-----------------+ |
| | Config "ALooK"      | | Config "OpenBridge" | | Config "UserApp"| |
| | - Layouts 0..30     | | - Layouts 0..15     | | - Layouts       | |
| | - Fonts 1..5        | | - Custom fonts      | | - Custom icons  | |
| | - Icons & bitmaps   | | - Bitmaps           | | - Animations    | |
| +---------------------+ +---------------------+ +-----------------+ |
+---------------------------------------------------------------------+
```

### Management commands
- `0xD0 cfgWrite`: opens a write session (`name[12], version, password`). Requires battery $\ge 5\%$.
- `0xD2 cfgSet`: makes a profile active in RAM and loads its templates immediately.
- `0xD6 cfgDeleteLessUsed`: automatic LRU garbage collector that removes the configuration with the lowest
  usage counter (`usgCnt`) when space runs out.
- `0xD7 cfgFreeSpace`: returns the remaining free bytes.
