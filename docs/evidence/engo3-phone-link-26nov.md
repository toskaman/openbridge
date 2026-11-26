# ENGO 3 through the phone's Bluetooth — 26 November 2026

Owner wearing a real **ENGO 3 Photochromic** (address ending `D7:B4`), PC without Bluetooth, phone **Blackview
BV9300 Pro** (Android 13) on USB debugging with OpenBridge Companion 0.14.0 (this change), paired relay
`relay-f46b…`. The ENGO app was closed first (the glasses accept one connection).

## What was run

`openbridge glasses run --link phone --address <glasses> --mirror`: the Companion connected to the glasses
(`glasses_connect`, MTU 247, chunk 244 bytes), the PC sent ActiveLook frames with `glasses_write` and received gestures
and flow control with `glasses_events`, over the signed, encrypted relay (adb-forwarded TCP).

## What the owner saw (reported live)

| Check | Result |
|---|---|
| Home menu on the glasses | Shown. Before the fix: upside down (top/bottom swapped). |
| Orientation chart, native coordinates, text rotation 4 | Text readable, all words mirrored. With logical (x, y) sent as (303-x, 255-y) and rotation 4: HAUT top, BAS bottom, GAUCHE left, DROITE right. |
| Colours with grey levels only (`0x30` + `0x37`) | Everything yellow, lighter or darker. |
| Named colours from the API palette with `txtColor` (`0x3E`): red `0x3c`, orange `0x3e`, amber `0xbd`, yellow `0xff`, lime `0x87`, green `0xc3` | All six correct. |
| Text anchor: text at logical y = 200 and a line at y = 200 | Text just below the line (top-left anchor, no font-height offset on this firmware). |
| Visible window: lines at x = 262/272/282/292/302, y = 226/236/246/254, x = 0/4/8 | Visible up to x 292 (302 not), y 236 (246 not), from x 0. An earlier chart with text labels near the edge gave a narrower, wrong estimate. |
| Accents (`été à ça`) in UTF-8 and in Latin-1 | Not drawn in either: fonts are ASCII only. |
| Shapes (filled square, arrow made of lines) in the mirrored frame | Square left of its label, arrow points right: shapes mirror like text. |
| Arc asked for the upper half with device angle = logical angle + 180 | Drawn as the lower half: no offset is needed; rounded-rectangle corners then close correctly. |
| `Messages` in fonts 1, 2, 3 between guide lines n x h/2 wide, h = 24 / 38 / 64 | Fits each frame exactly. |
| Home screen redrawn for these sizes | Icon complete, title centred, nothing overlaps; owner asked for slightly more width to the right (done). |
| Oracle module off from the PC, then "active l'Oracle" / "retire l'Oracle" spoken on the phone | Button disappears, then comes back / goes, at once. |
| Input, events logged with timestamps: 1 tap / double tap / 3 taps / 4 taps, 10 s apart | 1 tap: nothing; double tap: one event (gesture characteristic, value `01`); 3 and 4 taps: one event. Hand wave: nothing. Touch characteristic: nothing. |
| Navigation after the change: double tap = next, home menu opens after 3 s, Companion buttons Next / Open / Back / Home, "retour" / "ouvre" said on the phone | All four work (owner). |
| Oracle: question spoken into the phone (no Android speech service on this phone, so the PC transcribed locally) | Right answer shown on the glasses; sometimes misheard; long answers needed paging and a bigger font (done). |
| HUD Studio mirror | Same picture as the glasses once the emulator draws the native frame. |

## Limits

- One pair of glasses, one phone. The visible width and the picture offset can differ between pairs
  (`openbridge glasses set --x-offset N`).
- Latency was not measured. Input: the hand wave does nothing on this ENGO 3; each double tap on the temple arrives
  as one event on the gesture characteristic (owner: "the quick double tap works"); nothing came through the touch
  characteristic.
- PC-side Bluetooth (`--link ble`) was not tested here: this PC has no Bluetooth adapter.

Sources for the palette and orientation: ActiveLook API documentation (`0x3D color`, `0x3E txtColor`, red-green palette
image `ActiveLook_RRGG_colors.png`); the MIT-licensed `@pranen/activelook` library (ENGO 3 profile: both axes mirrored,
text rotation 4, named colours).
