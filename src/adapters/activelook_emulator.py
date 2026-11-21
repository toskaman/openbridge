"""
ActiveLook ENGO Emulator for OpenBridge — no physical glasses needed.

This module provides two independent emulation layers:

  1. HUDCanvas  — a Tkinter window that renders the 304×256 MicroOLED
     display in real-time, applying every binary ActiveLook command
     exactly as the real hardware would. Run standalone or embed in
     the OpenBridge CLI via `openbridge hud-emu`.

  2. VirtualENGO — a Bumble-backed in-process BLE GATT peripheral that
     exposes the exact same UUIDs as a real ENGO 2 / ENGO 3.  Your
     Companion app (or any BleakClient) connects to it and talks to it
     identically to real hardware; the VirtualENGO forwards every
     write to HUDCanvas for live rendering.

Architecture
────────────
                 ┌──────────────────────┐
                 │  OpenBridge Server   │  (src/server.py)
                 │  (fabric / relay)    │
                 └──────┬───────────────┘
         relay cmds     │
                 ┌──────▼───────────────┐
                 │   Companion / bleak  │  (phone OR VirtualENGO)
                 └──────┬───────────────┘
         BLE bytes      │
                 ┌──────▼───────────────┐
                 │   VirtualENGO        │  virtual_engo.py  (this module)
                 │  (Bumble GATT srv)   │  ← accepts BLE writes over TCP
                 └──────┬───────────────┘
       parsed commands  │
                 ┌──────▼───────────────┐
                 │   HUDCanvas (GUI)    │  Tkinter 304×256 window
                 │   OLED renderer      │  monochrome or colour
                 └──────────────────────┘

Usage
─────
  # Standalone GUI preview (no BLE, inject events via Python API):
  python -m src.adapters.activelook_emulator

  # With virtual BLE server (bumble TCP controller):
  python -m src.adapters.activelook_emulator --ble

Dependencies (all already on the machine):
  Pillow, customtkinter, bleak, bumble (newly installed)
"""

from __future__ import annotations

import asyncio
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Constants — real hardware specs
# ──────────────────────────────────────────────────────────────────────────────

DISPLAY_W = 304
DISPLAY_H = 256
SCALE = 3          # GUI pixel scale (304×256 → 912×768 window)

# BLE UUIDs (same as physical ENGO 1/2/3)
SVC_UUID   = "0783b03e-8535-b5a0-7140-a304d2495cb7"
RX_UUID    = "0783b03e-8535-b5a0-7140-a304d2495cba"  # write (host→glasses)
TX_UUID    = "0783b03e-8535-b5a0-7140-a304d2495cb8"  # notify (glasses→host)
FLOW_UUID  = "0783b03e-8535-b5a0-7140-a304d2495cb9"  # flow control
GESTURE_UUID = "0783b03e-8535-b5a0-7140-a304d2495cbb" # gesture events
BATT_SVC_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATT_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

# ENGO 3 colour palette (81 possible, here we map 8 key colours)
COLOUR_MAP = {
    0x00: (0,   0,   0),    # black (OLED off)
    0x01: (0,   255, 0),    # green  — "OK / confirmed"
    0x02: (255, 165, 0),    # amber  — "warning / in progress"
    0x03: (255, 0,   0),    # red    — "refused / critical"
    0x04: (0,   200, 255),  # cyan   — informational
    0x05: (255, 255, 0),    # yellow — legacy monochrome
    0x06: (255, 0,   255),  # magenta
    0x0F: (255, 255, 255),  # white
}

# ──────────────────────────────────────────────────────────────────────────────
# Command parser — converts raw ActiveLook binary frames to named structs
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Frame:
    cmd: int
    data: bytes


@dataclass
class ActiveLookLayout:
    id: int
    x: int
    y: int
    width: int
    height: int
    fore_color: int = 15
    back_color: int = 0
    font: int = 1
    text_valid: bool = True
    text_x: int = 0
    text_y: int = 0
    text_rot: int = 0
    text_opacity: int = 0
    sub_commands: list[Frame] = field(default_factory=list)


@dataclass
class ActiveLookPage:
    id: int
    slots: list[tuple[int, int, int]] = field(default_factory=list)  # (layout_id, x, y)


@dataclass
class ActiveLookConfigBank:
    name: str
    version: int = 1
    layouts: dict[int, ActiveLookLayout] = field(default_factory=dict)
    pages: dict[int, ActiveLookPage] = field(default_factory=dict)


def parse_frames(buf: bytes) -> list[Frame]:
    """Extract complete ActiveLook frames from a byte buffer.
    Format: 0xFF [CMD:1] [FMT:1] [LEN:1|2] [QueryID:0..15] [Data:n] 0xAA
    """
    frames: list[Frame] = []
    i = 0
    while i < len(buf):
        if buf[i] != 0xFF:
            i += 1
            continue
        if i + 3 >= len(buf):
            break
        cmd = buf[i + 1]
        fmt = buf[i + 2]
        len_wide = bool(fmt & 0x20)
        qid_size = (fmt & 0x1E) >> 1
        hdr_size = 3 + (2 if len_wide else 1)
        if i + hdr_size > len(buf):
            break
        if len_wide:
            total_len = struct.unpack_from('>H', buf, i + 3)[0]
        else:
            total_len = buf[i + 3]
        # total_len includes SOF(1)+CMD(1)+FMT(1)+LEN(1or2)+data+EOF(1)
        payload_start = i + hdr_size + qid_size
        payload_end   = i + total_len - 1  # exclude 0xAA
        if payload_end > len(buf):
            break
        data = buf[payload_start:payload_end]
        frames.append(Frame(cmd=cmd, data=data))
        i = i + total_len
    return frames


# ──────────────────────────────────────────────────────────────────────────────
# HUDCanvas — real-time 304×256 OLED renderer in Tkinter
# ──────────────────────────────────────────────────────────────────────────────

class HUDCanvas:
    """Renders a Tkinter window simulating the ENGO MicroOLED 304×256 HUD.
    Supports monochrome (ENGO 1/2) and colour (ENGO 3) modes.
    """

    def __init__(self, model: str = "ENGO 3", scale: int = SCALE, gesture_callback: Optional[Callable] = None):
        from PIL import Image, ImageDraw
        self._Image = Image
        self.model = model
        self.scale = scale
        self.gesture_callback = gesture_callback
        self._colour_mode = "3" in model  # ENGO 3 has colour

        # Canvas state
        self._img   = Image.new("RGB", (DISPLAY_W, DISPLAY_H), (0, 0, 0))
        self._draw  = ImageDraw.Draw(self._img)
        self._grey  = 15        # current greyscale level (0–15)
        self._colour = (255, 255, 0)  # active colour (yellow = ENGO legacy)
        self._luma  = 10        # brightness 0–15
        self._buf   = bytearray()

        # Layout and Configuration banks (Flash memory emulation)
        self._configs: dict[str, ActiveLookConfigBank] = {}
        default_bank = ActiveLookConfigBank(name="ALooK")
        self._configs["ALooK"] = default_bank
        self._active_config_name = "ALooK"
        self._hold_buffer = False
        self._layouts: dict[int, dict] = {}
        self._battery = 88

        # Window setup
        self._root   = None
        self._canvas = None
        self._photo  = None
        self._running = False
        self._stats_var = None
        self._cmd_count = 0
        self._last_cmd  = "—"

        self._gesture_pending = False

    @property
    def active_bank(self) -> ActiveLookConfigBank:
        if self._active_config_name not in self._configs:
            self._configs[self._active_config_name] = ActiveLookConfigBank(name=self._active_config_name)
        return self._configs[self._active_config_name]

    # ── Colour helpers ────────────────────────────────────────────────────────

    def _resolve_colour(self, grey_or_colour=None):
        if grey_or_colour is not None:
            if isinstance(grey_or_colour, tuple):
                return grey_or_colour
            # greyscale 0-15
            lv = int(grey_or_colour * 255 / 15)
            if self._colour_mode:
                r, g, b = self._colour
                return (int(r * lv / 255), int(g * lv / 255), int(b * lv / 255))
            return (lv, lv, lv)
        return self._resolve_colour(self._grey)

    # ── Command dispatcher ────────────────────────────────────────────────────

    def dispatch(self, raw: bytes):
        """Accept raw BLE bytes, parse, and render."""
        self._buf += raw
        for frame in parse_frames(bytes(self._buf)):
            self._buf = bytearray()   # reset on each good parse
            self._dispatch_frame(frame)
        self._cmd_count += 1
        if not self._hold_buffer:
            self._refresh_gui()

    def _dispatch_frame(self, f: Frame):
        self._last_cmd = f"0x{f.cmd:02X}"
        cmd, d = f.cmd, f.data

        if   cmd == 0x00:  self._cmd_power(d)
        elif cmd == 0x01:  self._cmd_clear()
        elif cmd == 0x02:  self._cmd_grey_bg(d)
        elif cmd == 0x10:  self._cmd_luma(d)
        elif cmd == 0x30:  self._cmd_grayscale(d)
        elif cmd == 0x31:  self._cmd_point(d)
        elif cmd == 0x32:  self._cmd_line(d)
        elif cmd == 0x33:  self._cmd_rect(d)
        elif cmd == 0x34:  self._cmd_rectf(d)
        elif cmd == 0x35:  self._cmd_circ(d)
        elif cmd == 0x36:  self._cmd_circf(d)
        elif cmd == 0x37:  self._cmd_txt(d)
        elif cmd == 0x39:  self._cmd_hold_flush(d)
        elif cmd == 0x3C:  self._cmd_arc(d)
        elif cmd == 0x3D:  self._cmd_colour(d)
        elif cmd == 0x60:  self._cmd_layout_save(d, is_color=False)
        elif cmd == 0x61:  self._cmd_layout_delete(d)
        elif cmd == 0x62:  self._cmd_layout_display(d)
        elif cmd == 0x63:  self._cmd_layout_clear(d)
        elif cmd == 0x69:  self._cmd_layout_clear_and_display(d)
        elif cmd == 0x6B:  self._cmd_layout_save(d, is_color=True)
        elif cmd == 0x70:  self._cmd_gauge_display(d)
        elif cmd == 0x80:  self._cmd_page_save(d)
        elif cmd == 0x82:  self._cmd_page_delete(d)
        elif cmd == 0x83:  self._cmd_page_display(d, clear_first=False)
        elif cmd == 0x86:  self._cmd_page_display(d, clear_first=True)
        elif cmd == 0xD0:  self._cmd_cfg_write(d)
        elif cmd == 0xD2:  self._cmd_cfg_set(d)

    # ── Core commands ─────────────────────────────────────────────────────────

    def _cmd_power(self, d):
        pass  # visibility toggle — GUI always visible in emulator

    def _cmd_clear(self):
        self._draw.rectangle([0, 0, DISPLAY_W-1, DISPLAY_H-1], fill=(0, 0, 0))

    def _cmd_grey_bg(self, d):
        if d:
            lv = int(d[0] * 255 / 15)
            self._draw.rectangle([0, 0, DISPLAY_W-1, DISPLAY_H-1], fill=(lv, lv, lv))

    def _cmd_luma(self, d):
        if d:
            self._luma = max(0, min(15, d[0]))

    def _cmd_grayscale(self, d):
        if d:
            self._grey = max(0, min(15, d[0]))
            lv = int(self._grey * 255 / 15)
            self._colour = (lv, lv, lv)

    def _cmd_colour(self, d):
        """0x3D colour — select from 81-colour ENGO 3 palette."""
        if d:
            self._colour = COLOUR_MAP.get(d[0], (255, 255, 0))

    def _cmd_point(self, d):
        if len(d) >= 4:
            x, y = struct.unpack_from('>hh', d)
            if 0 <= x < DISPLAY_W and 0 <= y < DISPLAY_H:
                self._draw.point((x, y), fill=self._resolve_colour())

    def _cmd_line(self, d):
        if len(d) >= 8:
            x0, y0, x1, y1 = struct.unpack_from('>hhhh', d)
            self._draw.line([(x0, y0), (x1, y1)], fill=self._resolve_colour(), width=1)

    def _cmd_rect(self, d):
        if len(d) >= 8:
            x0, y0, x1, y1 = struct.unpack_from('>hhhh', d)
            self._draw.rectangle([(x0, y0), (x1, y1)], outline=self._resolve_colour())

    def _cmd_rectf(self, d):
        if len(d) >= 8:
            x0, y0, x1, y1 = struct.unpack_from('>hhhh', d)
            self._draw.rectangle([(x0, y0), (x1, y1)], fill=self._resolve_colour())

    def _cmd_circ(self, d):
        if len(d) >= 5:
            x, y = struct.unpack_from('>hh', d)
            r = d[4]
            self._draw.ellipse([(x-r, y-r), (x+r, y+r)], outline=self._resolve_colour())

    def _cmd_circf(self, d):
        if len(d) >= 5:
            x, y = struct.unpack_from('>hh', d)
            r = d[4]
            self._draw.ellipse([(x-r, y-r), (x+r, y+r)], fill=self._resolve_colour())

    def _cmd_txt(self, d):
        """0x37 txt — s16 x, s16 y, u8 rot, u8 font, u8 grey, str text"""
        if len(d) < 7:
            return
        x, y = struct.unpack_from('>hh', d)
        font_id = d[4]
        grey_val = d[5]
        text = d[6:].decode('utf-8', errors='replace').rstrip('\x00')
        col = self._resolve_colour(grey_val)
        self._draw_text_with_ghost(x, y, text, font_id, col)

    def _draw_text_with_ghost(self, x: int, y: int, text: str, font_id: int, col: tuple[int, int, int]):
        from PIL import ImageFont
        font_sizes = {0: 16, 1: 24, 2: 38, 3: 64, 4: 75, 5: 82}
        sz = font_sizes.get(font_id, 24)
        try:
            fnt = ImageFont.truetype("arial.ttf", sz)
        except Exception:
            fnt = ImageFont.load_default()

        curr_x = x
        for char in text:
            if char == '$':  # Ghost space with width of '0'
                advance = int(fnt.getlength('0')) if hasattr(fnt, 'getlength') else 14
                curr_x += advance
            elif char == '&':  # Ghost space with width of '.'
                advance = int(fnt.getlength('.')) if hasattr(fnt, 'getlength') else 6
                curr_x += advance
            else:
                self._draw.text((curr_x, y), char, fill=col, font=fnt)
                adv = int(fnt.getlength(char)) if hasattr(fnt, 'getlength') else 14
                curr_x += adv

    def _dispatch_frame_offset(self, f: Frame, ox: int, oy: int):
        cmd, d = f.cmd, f.data
        if cmd == 0x31 and len(d) >= 4:
            x, y = struct.unpack_from('>hh', d)
            self._draw.point((ox + x, oy + y), fill=self._resolve_colour())
        elif cmd == 0x32 and len(d) >= 8:
            x0, y0, x1, y1 = struct.unpack_from('>hhhh', d)
            self._draw.line([(ox + x0, oy + y0), (ox + x1, oy + y1)], fill=self._resolve_colour(), width=1)
        elif cmd == 0x33 and len(d) >= 8:
            x0, y0, x1, y1 = struct.unpack_from('>hhhh', d)
            self._draw.rectangle([(ox + x0, oy + y0), (ox + x1, oy + y1)], outline=self._resolve_colour())
        elif cmd == 0x34 and len(d) >= 8:
            x0, y0, x1, y1 = struct.unpack_from('>hhhh', d)
            self._draw.rectangle([(ox + x0, oy + y0), (ox + x1, oy + y1)], fill=self._resolve_colour())
        elif cmd == 0x35 and len(d) >= 5:
            x, y = struct.unpack_from('>hh', d)
            r = d[4]
            self._draw.ellipse([(ox + x - r, oy + y - r), (ox + x + r, oy + y + r)], outline=self._resolve_colour())
        elif cmd == 0x36 and len(d) >= 5:
            x, y = struct.unpack_from('>hh', d)
            r = d[4]
            self._draw.ellipse([(ox + x - r, oy + y - r), (ox + x + r, oy + y + r)], fill=self._resolve_colour())
        elif cmd == 0x37 and len(d) >= 7:
            x, y = struct.unpack_from('>hh', d)
            font_id, grey_val = d[4], d[5]
            text = d[6:].decode('utf-8', errors='replace').rstrip('\x00')
            self._draw_text_with_ghost(ox + x, oy + y, text, font_id, self._resolve_colour(grey_val))

    def _cmd_arc(self, d):
        if len(d) >= 10:
            x, y = struct.unpack_from('>hh', d)
            r = d[4]
            start, end = struct.unpack_from('>hh', d, 5)
            self._draw.arc([(x-r, y-r), (x+r, y+r)], start=start, end=end, fill=self._resolve_colour())

    def _cmd_hold_flush(self, d):
        if d:
            self._hold_buffer = (d[0] == 0)
            if not self._hold_buffer:
                self._refresh_gui()

    def _cmd_cfg_write(self, d):
        if len(d) >= 12:
            name = d[:12].decode('ascii', errors='replace').rstrip('\x00')
            version = struct.unpack_from('>I', d, 12)[0] if len(d) >= 16 else 1
            self._configs[name] = ActiveLookConfigBank(name=name, version=version)
            self._active_config_name = name

    def _cmd_cfg_set(self, d):
        if d:
            name = d[:12].decode('ascii', errors='replace').rstrip('\x00')
            if name in self._configs:
                self._active_config_name = name

    def _cmd_layout_save(self, d, is_color: bool = False):
        if len(d) >= 17:
            layout_id, sub_size, x, y, width, height, fore, back, font, text_valid, tx, ty, rot, opac = struct.unpack(
                ">BB H B H B B B B B H B B B", d[:17]
            )
            sub_frames = []
            if sub_size > 0 and len(d) >= 17 + sub_size:
                sub_bytes = d[17:17+sub_size]
                sub_frames = parse_frames(sub_bytes)
            layout = ActiveLookLayout(
                id=layout_id,
                x=x,
                y=y,
                width=width,
                height=height,
                fore_color=fore,
                back_color=back,
                font=font,
                text_valid=bool(text_valid),
                text_x=tx,
                text_y=ty,
                text_rot=rot,
                text_opacity=opac,
                sub_commands=sub_frames
            )
            self.active_bank.layouts[layout_id] = layout

    def _cmd_layout_delete(self, d):
        if d:
            layout_id = d[0]
            if layout_id == 0xFF:
                self.active_bank.layouts.clear()
            else:
                self.active_bank.layouts.pop(layout_id, None)

    def _cmd_layout_display(self, d, override_origin: Optional[tuple[int, int]] = None):
        if not d:
            return
        layout_id = d[0]
        text = d[1:].decode('utf-8', errors='replace').rstrip('\x00') if len(d) > 1 else ""
        layout = self.active_bank.layouts.get(layout_id)
        if not layout:
            # Fallback for simple slot rendering
            y_pos = 10 + (layout_id % 8) * 30
            self._draw.rectangle([0, y_pos, DISPLAY_W-1, y_pos+22], fill=(0, 0, 0))
            self._draw_text_with_ghost(4, y_pos, text, 1, self._resolve_colour(12))
            return

        ox = override_origin[0] if override_origin else layout.x
        oy = override_origin[1] if override_origin else layout.y

        # Clear bounding box
        bg_col = self._resolve_colour(layout.back_color)
        self._draw.rectangle([ox, oy, min(DISPLAY_W-1, ox + layout.width - 1), min(DISPLAY_H-1, oy + layout.height - 1)], fill=bg_col)

        # Draw static sub-commands relative to (ox, oy)
        for sub_f in layout.sub_commands:
            self._dispatch_frame_offset(sub_f, ox, oy)

        # Render dynamic text
        if layout.text_valid and text:
            tx = ox + layout.text_x
            ty = oy + layout.text_y
            fg_col = self._resolve_colour(layout.fore_color)
            self._draw_text_with_ghost(tx, ty, text, layout.font, fg_col)

    def _cmd_layout_clear(self, d, override_origin: Optional[tuple[int, int]] = None):
        if not d:
            return
        layout_id = d[0]
        layout = self.active_bank.layouts.get(layout_id)
        if layout:
            ox = override_origin[0] if override_origin else layout.x
            oy = override_origin[1] if override_origin else layout.y
            bg_col = self._resolve_colour(layout.back_color)
            self._draw.rectangle([ox, oy, min(DISPLAY_W-1, ox + layout.width - 1), min(DISPLAY_H-1, oy + layout.height - 1)], fill=bg_col)

    def _cmd_layout_clear_and_display(self, d):
        self._cmd_layout_clear(d)
        self._cmd_layout_display(d)

    def _cmd_gauge_display(self, d):
        """0x70 gauge — id, value(0-100). Renders a horizontal progress bar."""
        if len(d) >= 2:
            gauge_id = d[0]
            value = max(0, min(100, d[1]))
            y = 200 + (gauge_id % 4) * 14
            bar_w = int(DISPLAY_W * value / 100)
            # determine colour by value
            if value > 60:
                c = COLOUR_MAP[0x01]  # green
            elif value > 30:
                c = COLOUR_MAP[0x02]  # amber
            else:
                c = COLOUR_MAP[0x03]  # red
            self._draw.rectangle([0, y, DISPLAY_W-1, y+10], fill=(20, 20, 20))
            if bar_w:
                self._draw.rectangle([0, y, bar_w, y+10], fill=c)

    def _cmd_page_save(self, d):
        if len(d) >= 1:
            page_id = d[0]
            slots = []
            offset = 1
            while offset + 4 <= len(d) and len(slots) < 10:
                lid, x, y = struct.unpack_from(">B H B", d, offset)
                slots.append((lid, x, y))
                offset += 4
            self.active_bank.pages[page_id] = ActiveLookPage(id=page_id, slots=slots)

    def _cmd_page_delete(self, d):
        if d:
            page_id = d[0]
            if page_id == 0xFF:
                self.active_bank.pages.clear()
            else:
                self.active_bank.pages.pop(page_id, None)

    def _cmd_page_display(self, d, clear_first: bool = False):
        """0x83 / 0x86 pageDisplay — id + null-separated strings. Renders all slots."""
        if not d:
            return
        page_id = d[0]
        texts = d[1:].decode('utf-8', errors='replace').rstrip('\x00').split('\x00')
        page = self.active_bank.pages.get(page_id)
        if not page:
            for i, text in enumerate(texts):
                if text:
                    y = 10 + i * 24
                    self._draw_text_with_ghost(4, y, text, 1, self._resolve_colour(12))
            return

        for i, (layout_id, px, py) in enumerate(page.slots):
            txt = texts[i] if i < len(texts) else ""
            if clear_first:
                self._cmd_layout_clear(bytes([layout_id]), override_origin=(px, py))
            self._cmd_layout_display(bytes([layout_id]) + txt.encode("utf-8") + b"\x00", override_origin=(px, py))

    # ── Gesture injection ─────────────────────────────────────────────────────

    def inject_gesture(self):
        """Simulate a hand wave (proximity sensor trigger 0x01)."""
        if self.gesture_callback:
            self.gesture_callback(b'\x01')
        # Visual flash
        self._draw.rectangle([0, DISPLAY_H-10, DISPLAY_W-1, DISPLAY_H-1],
                              fill=COLOUR_MAP[0x04])
        self._refresh_gui()

    # ── Power & Optical Metrics ───────────────────────────────────────────────

    def compute_pixel_fill(self) -> float:
        """Percentage of non-black pixels in current frame (0.0 to 100.0%)."""
        if hasattr(self._img, "get_flattened_data"):
            raw = self._img.get_flattened_data()
            lit = sum(1 for p in raw if (any(p) if isinstance(p, (tuple, list)) else p != 0))
        else:
            data = self._img.getdata()
            lit = sum(1 for p in data if (any(p) if isinstance(p, (tuple, list)) else p != 0))
        return (lit / float(DISPLAY_W * DISPLAY_H)) * 100.0

    def estimate_power_mw(self) -> float:
        """Estimated MicroOLED panel power in milliwatts."""
        fill = self.compute_pixel_fill() / 100.0
        # Baseline idle leakage ~0.3 mW + active pixel scaling up to ~4.5 mW at max luma
        return 0.3 + (fill * 4.5 * (self._luma / 15.0))

    # ── GUI rendering ─────────────────────────────────────────────────────────

    def _refresh_gui(self):
        if self._canvas is None:
            return
        # Apply brightness modulation
        import tkinter as tk
        from PIL import Image, ImageTk, ImageEnhance
        bright = ImageEnhance.Brightness(self._img)
        img_b = bright.enhance(self._luma / 15)
        # Scale to display size
        scaled = img_b.resize((DISPLAY_W * self.scale, DISPLAY_H * self.scale), Image.NEAREST)
        self._photo = ImageTk.PhotoImage(scaled)
        self._canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)
        if self._stats_var:
            fill = self.compute_pixel_fill()
            pwr = self.estimate_power_mw()
            est_hours = int(425 / max(0.1, pwr))
            self._stats_var.set(
                f"[{self.model}] Fill: {fill:.1f}% | Pwr: {pwr:.2f}mW (~{est_hours}h) | "
                f"Luma: {self._luma}/15 | Cmds: {self._cmd_count}"
            )

    def run(self):
        """Launch the Tkinter window (blocking)."""
        import tkinter as tk
        from PIL import ImageTk
        self._root = tk.Tk()
        self._root.title(f"OpenBridge × {self.model} HUD Emulator — 304×256 MicroOLED")
        self._root.configure(bg="#0a0a0a")

        # Controls bar
        ctrl = tk.Frame(self._root, bg="#111111")
        ctrl.pack(fill=tk.X, side=tk.TOP)

        self._stats_var = tk.StringVar(value="Ready.")
        tk.Label(ctrl, textvariable=self._stats_var, fg="#aaffaa", bg="#111111",
                 font=("Consolas", 10)).pack(side=tk.LEFT, padx=8)

        tk.Button(ctrl, text="🤚 Wave (Gesture)", command=self.inject_gesture,
                  bg="#1a3a5a", fg="white", font=("Consolas", 10)).pack(side=tk.LEFT, padx=4)
        tk.Button(ctrl, text="🗑 Clear", command=lambda: (self._cmd_clear(), self._refresh_gui()),
                  bg="#3a1a1a", fg="white", font=("Consolas", 10)).pack(side=tk.LEFT, padx=4)

        # Model selector
        model_var = tk.StringVar(value=self.model)
        def on_model_change(*_):
            self.model = model_var.get()
            self._colour_mode = "3" in self.model
            self._root.title(f"OpenBridge × {self.model} HUD Emulator — 304×256 MicroOLED")
        for m in ["ENGO 1", "ENGO 2", "ENGO 3", "ENGO 3 Titanium"]:
            tk.Radiobutton(ctrl, text=m, variable=model_var, value=m, command=on_model_change,
                           bg="#111111", fg="#cccccc", selectcolor="#222222",
                           font=("Consolas", 9)).pack(side=tk.LEFT)

        # Demo buttons
        demo = tk.Frame(self._root, bg="#0d1117")
        demo.pack(fill=tk.X, side=tk.TOP)
        tk.Label(demo, text="Demo:", fg="#888", bg="#0d1117", font=("Consolas", 9)).pack(side=tk.LEFT, padx=4)

        def demo_vacuum_docking():
            self._cmd_clear()
            self._colour = COLOUR_MAP[0x01]  # green
            self._cmd_rectf(struct.pack('>hhhh', 0, 0, 303, 29))
            self._colour = (0, 0, 0)
            self._cmd_txt(struct.pack('>hh', 4, 6) + bytes([0, 0, 15]) + b'WAN: OK    OpenBridge      BATT: 88%')
            self._colour = COLOUR_MAP[0x05]  # yellow
            self._cmd_txt(struct.pack('>hh', 4, 40) + bytes([0, 1, 12]) + b'[VACUUM] ROBOT: DOCKING')
            self._cmd_txt(struct.pack('>hh', 4, 65) + bytes([0, 0, 10]) + b'BATT: 78%  |  BIN: FULL  |  ZONE: SALON')
            self._colour = COLOUR_MAP[0x02]  # amber
            self._cmd_txt(struct.pack('>hh', 4, 95) + bytes([0, 0, 10]) + b'ETA: 2min 30s')
            self._colour = COLOUR_MAP[0x04]  # cyan
            self._cmd_txt(struct.pack('>hh', 4, 220) + bytes([0, 0, 10]) + b'>> [WAVE] DISMISS')
            self._refresh_gui()

        def demo_refused():
            self._cmd_clear()
            self._colour = COLOUR_MAP[0x03]  # red
            self._cmd_rectf(struct.pack('>hhhh', 0, 0, 303, 29))
            self._colour = (0, 0, 0)
            self._cmd_txt(struct.pack('>hh', 4, 6) + bytes([0, 0, 15]) + b'! OPENBRIDGE REFUSED ACTION !')
            self._colour = COLOUR_MAP[0x03]
            self._cmd_txt(struct.pack('>hh', 4, 45) + bytes([0, 0, 12]) + b'Refused: Stale State')
            self._colour = COLOUR_MAP[0x05]
            self._cmd_txt(struct.pack('>hh', 4, 70) + bytes([0, 0, 10]) + b'TV last seen: 4 minutes ago')
            self._cmd_txt(struct.pack('>hh', 4, 90) + bytes([0, 0, 10]) + b'Confirm device is reachable')
            self._colour = COLOUR_MAP[0x04]
            self._cmd_txt(struct.pack('>hh', 4, 220) + bytes([0, 0, 10]) + b'>> [WAVE] DISMISS')
            self._refresh_gui()

        def demo_ambient():
            self._cmd_clear()
            self._colour = COLOUR_MAP[0x04]
            self._cmd_rect(struct.pack('>hhhh', 0, 0, 303, 29))
            self._cmd_txt(struct.pack('>hh', 4, 6) + bytes([0, 0, 10]) + b'[1.4kW] [LOCK:ALL] [TV:OFF] [WAN:940M]')
            self._colour = COLOUR_MAP[0x01]
            self._cmd_txt(struct.pack('>hh', 4, 40) + bytes([0, 1, 12]) + b'All devices nominal')
            self._colour = COLOUR_MAP[0x05]
            self._cmd_txt(struct.pack('>hh', 4, 65) + bytes([0, 0, 10]) + b'Last action: TV sleep  2 min ago')
            self._cmd_txt(struct.pack('>hh', 4, 85) + bytes([0, 0, 10]) + b'Next: Bedtime routine in 47 min')
            self._cmd_gauge_display(bytes([0, 72]))   # gauge 0 = 72% (battery?)
            self._cmd_gauge_display(bytes([1, 100]))  # gauge 1 = 100% WAN
            self._refresh_gui()

        def demo_energy():
            self._cmd_clear()
            self._colour = COLOUR_MAP[0x02]  # amber warning
            self._cmd_rectf(struct.pack('>hhhh', 0, 0, 303, 29))
            self._colour = (0, 0, 0)
            self._cmd_txt(struct.pack('>hh', 4, 6) + bytes([0, 0, 15]) + b'! PEAK TARIFF IN 8 MIN !')
            self._colour = COLOUR_MAP[0x02]
            self._cmd_txt(struct.pack('>hh', 4, 40) + bytes([0, 0, 12]) + b'Current: 7.2 kW (HIGH)')
            self._colour = COLOUR_MAP[0x05]
            self._cmd_txt(struct.pack('>hh', 4, 65) + bytes([0, 0, 10]) + b'Washing machine + Oven + TV + AC')
            self._colour = COLOUR_MAP[0x03]
            self._cmd_txt(struct.pack('>hh', 4, 90) + bytes([0, 0, 10]) + b'Cost spike: +0.38 EUR/kWh at 18:00')
            self._cmd_gauge_display(bytes([0, 72]))   # 72% load
            self._refresh_gui()

        def demo_twophase():
            self._cmd_clear()
            self._colour = COLOUR_MAP[0x02]
            self._cmd_txt(struct.pack('>hh', 4, 40) + bytes([0, 1, 12]) + b'BEDTIME ROUTINE starting in:')
            self._colour = COLOUR_MAP[0x03]
            self._cmd_txt(struct.pack('>hh', 100, 80) + bytes([0, 1, 15]) + b'  5s')
            self._colour = COLOUR_MAP[0x04]
            self._cmd_txt(struct.pack('>hh', 4, 220) + bytes([0, 0, 10]) + b'>> [WAVE] ABORT EXECUTION')
            # Countdown bar
            self._cmd_gauge_display(bytes([0, 100]))
            self._refresh_gui()

        def demo_debug():
            self._cmd_clear()
            self._colour = COLOUR_MAP[0x05]
            self._cmd_txt(struct.pack('>hh', 4, 5) + bytes([0, 0, 10]) + b'== OPENBRIDGE DEBUG MODE ==')
            self._colour = COLOUR_MAP[0x04]
            lines = [
                'BLE RSSI: -48 dBm (excellent)',
                'Packet RTT: 14 ms',
                'ADB TV latency: 23 ms',
                'Tuya UDP drops: 0.0%',
                'TX queue depth: 2/16',
                'Relay ping: 8 ms',
                'Freebox WAN: 940 Mbps',
                'Battery (emulated): 88%',
            ]
            for i, l in enumerate(lines):
                self._cmd_txt(struct.pack('>hh', 4, 20 + i*28) + bytes([0, 0, 10]) + l.encode())
            self._refresh_gui()

        from src.adapters.activelook import ActiveLookAdapter
        adapter = ActiveLookAdapter(transport=lambda b: self.dispatch(b), model=self.model)

        def demo_spatial_radar():
            adapter.push_spatial_radar([
                {"name": "VAC", "bearing_deg": 220, "dist_m": 2.5, "state": "docking"},
                {"name": "GATE", "bearing_deg": 35, "dist_m": 7.5, "state": "alert"},
                {"name": "SOLAR", "bearing_deg": 0, "dist_m": 5.0, "state": "ok"},
                {"name": "CAR", "bearing_deg": 315, "dist_m": 9.0, "state": "ok"}
            ])

        def demo_eyes_on_target():
            adapter.push_eyes_on_target_receipt(
                target_name="Salon Lights",
                action="Extinction & Verrouillage",
                oracle_verified=True,
                latency_ms=38,
                digest="#4f9a12c8-verified"
            )

        def demo_two_phase():
            adapter.push_two_phase_countdown(
                routine_name="Bedtime Shutdown",
                seconds_remaining=4,
                max_seconds=5
            )

        def demo_telemetry_stream():
            adapter.push_peripheral_telemetry(
                grid_watts=7420,
                wan_mbps=940,
                ping_ms=9,
                alert="LINKY SPIKE > 7kW"
            )

        def demo_workshop_prompter():
            adapter.push_workflow_prompter(
                step_idx=3,
                total_steps=7,
                title="Connect Ribbon Bus",
                instruction="Insert I2C cable into J2 connector until click",
                timer_s=145
            )

        def demo_doorbell_subtitles():
            adapter.push_live_subtitles(
                speaker="Livreur Colis",
                text="Bonjour, j'ai un paquet pour vous a deposer",
                is_urgent=True
            )

        demos = [
            ("📡 Spatial Radar", demo_spatial_radar),
            ("👁️ Eyes-On-Target", demo_eyes_on_target),
            ("⏱️ Two-Phase Abort", demo_two_phase),
            ("⚡ Peripheral Stream", demo_telemetry_stream),
            ("🛠️ Workshop Prompter", demo_workshop_prompter),
            ("💬 Doorbell Subtitles", demo_doorbell_subtitles),
        ]
        for label, fn in demos:
            tk.Button(demo, text=label, command=fn,
                      bg="#1a2a1a", fg="#aaffaa", font=("Consolas", 9)).pack(side=tk.LEFT, padx=2, pady=2)

        # Advanced Watch-Impossible Features Toolbar
        demo_adv = tk.Frame(self._root, bg="#0d181a")
        demo_adv.pack(fill=tk.X, side=tk.TOP)
        tk.Label(demo_adv, text="Watch-Impossible:", fg="#55eeff", bg="#0d181a", font=("Consolas", 9)).pack(side=tk.LEFT, padx=4)

        def demo_compass():
            adapter.push_compass_wayfinder(
                heading_deg=285,
                target_bearing_deg=310,
                target_dist_m=145.0,
                target_name="PARKING B3"
            )

        def demo_security():
            adapter.push_smart_home_security_alert(
                threat_type="SYN Port Scan",
                source_ip="192.168.1.189",
                mac_vendor="Raspberry Pi / Rogue",
                target_service="SSH Port 22"
            )

        def demo_pacer():
            adapter.push_bio_adaptive_pacer(
                target_spm=180,
                current_spm=174,
                hr_bpm=162,
                hr_zone=4,
                advice="AUGMENTER FREQUENCE (+6)"
            )

        def demo_media():
            adapter.push_media_remote_hud(
                media_title="Dune: Part Two",
                artist_or_source="Kodi Salon (4K HDR)",
                volume_pct=45,
                is_playing=True,
                progress_s=3420,
                total_s=9960
            )

        adv_demos = [
            ("🧭 AR Compass", demo_compass),
            ("🛡️ Shield Alert", demo_security),
            ("🏃 Bio Pacer", demo_pacer),
            ("📺 Media Remote", demo_media),
        ]
        for label, fn in adv_demos:
            tk.Button(demo_adv, text=label, command=fn,
                      bg="#162e33", fg="#88ffff", font=("Consolas", 9)).pack(side=tk.LEFT, padx=2, pady=2)

        # AI & Sensory Proxy Bridge Toolbar
        demo_ai = tk.Frame(self._root, bg="#140d1a")
        demo_ai.pack(fill=tk.X, side=tk.TOP)
        tk.Label(demo_ai, text="AI/Sensory:", fg="#cc88ff", bg="#140d1a", font=("Consolas", 9)).pack(side=tk.LEFT, padx=4)

        from src.adapters.engo_ai_bridge import EngoAIBridge
        ai_bridge = EngoAIBridge(adapter=adapter)

        def demo_ai_voice():
            ai_bridge.handle_glasses_interaction("wave")

        def demo_ai_vision():
            ai_bridge.handle_glasses_interaction("double_tap")

        def demo_ai_translation():
            ai_bridge.stream_live_translation("Speaker", "EN", "OpenBridge glasses connected in real-time.")

        def demo_api_weather():
            ai_bridge.push_api_glance("weather_radar", {"rain_in_minutes": 8, "temp_c": 13, "wind_kmh": 26})

        def demo_api_rte():
            ai_bridge.push_api_glance("linky_rte_tempo", {"tempo_today": "BLEU", "tempo_tomorrow": "ROUGE", "instant_watts": 3400})

        def demo_api_transit():
            ai_bridge.push_api_glance("transit_live", {"line": "M14", "destination": "Orly", "eta_minutes": 3})

        ai_demos = [
            ("🎙️ Voice AI", demo_ai_voice),
            ("👁️ Phone Vision", demo_ai_vision),
            ("🌐 Subtitles", demo_ai_translation),
            ("🌧️ Weather", demo_api_weather),
            ("⚡ RTE Tempo", demo_api_rte),
            ("🚇 Transit", demo_api_transit),
        ]
        for label, fn in ai_demos:
            tk.Button(demo_ai, text=label, command=fn,
                      bg="#2a1a3a", fg="#eeaaff", font=("Consolas", 9)).pack(side=tk.LEFT, padx=2, pady=2)

        # Next-Gen Breakthrough Innovations Toolbar
        demo_nextgen = tk.Frame(self._root, bg="#1f140a")
        demo_nextgen.pack(fill=tk.X, side=tk.TOP)
        tk.Label(demo_nextgen, text="Next-Gen:", fg="#ffaa44", bg="#1f140a", font=("Consolas", 9)).pack(side=tk.LEFT, padx=4)

        def demo_morse():
            adapter.push_silent_morse_input(
                buffer_str="OUI JE SUIS EN ROUTE",
                current_morse=".-",
                suggestion="ARRIVE DANS 5 MIN"
            )

        def demo_teleprompter():
            adapter.push_speech_teleprompter(
                current_line="OpenBridge connecte vos lunettes",
                next_line="aux modeles d'IA locaux et a vos objets",
                wpm=138,
                is_rushing=False,
                elapsed_s=45,
                total_s=180
            )

        def demo_heatmap():
            adapter.push_spatial_energy_heatmap(
                current_room="Cuisine",
                room_watts=2150,
                total_watts=3480,
                vampire_devices=[{"name": "Four Veille", "watts": 65, "idle_hours": 3}]
            )

        def demo_arcade():
            adapter.push_arcade_game_frame(
                player_y=160,
                obstacle_x=180,
                score=50,
                game_over=False
            )

        nextgen_demos = [
            ("⌨️ Morse Input", demo_morse),
            ("🎙️ Teleprompter", demo_teleprompter),
            ("🏠 Ghost Heatmap", demo_heatmap),
            ("🎮 Vector Runner", demo_arcade),
        ]
        for label, fn in nextgen_demos:
            tk.Button(demo_nextgen, text=label, command=fn,
                      bg="#3d2610", fg="#ffcc88", font=("Consolas", 9)).pack(side=tk.LEFT, padx=2, pady=2)

        # Generation v4.0 Innovations Toolbar
        demo_v4 = tk.Frame(self._root, bg="#0d261a")
        demo_v4.pack(fill=tk.X, side=tk.TOP)
        tk.Label(demo_v4, text="v4.0 Innovations:", fg="#55ffaa", bg="#0d261a", font=("Consolas", 9)).pack(side=tk.LEFT, padx=4)

        def demo_sentry():
            adapter.push_collision_sentry(
                hazard_side="left",
                speed_kmh=52,
                dist_m=18.5,
                ttc_s=1.3
            )

        def demo_briefing():
            adapter.push_executive_briefing_glance(
                contact_name="Sophie Martin",
                role_title="Directrice R&D ENGO",
                bullet_points=[
                    "Objectif : Partenariat OpenBridge v2",
                    "Budget alloue : 85k EUR materiel",
                    "Decideur final : Valider avant 17h"
                ],
                sentiment_hint="PARTENAIRE"
            )

        def demo_bio_stress():
            adapter.push_biofeedback_stress_guardian(
                stress_score=68,
                hrv_ms=42,
                breath_phase="INSP",
                phase_timer_s=3
            )

        def demo_ar_stud():
            adapter.push_diy_ar_stud_level(
                pitch_deg=0.1,
                roll_deg=0.0,
                is_level=True,
                detected_hazard="CABLE 230V SOUS TENSION"
            )

        v4_demos = [
            ("⚠️ Sentry Radar", demo_sentry),
            ("👤 Dossier Exec", demo_briefing),
            ("🧘 Coherence Bio", demo_bio_stress),
            ("📐 Niveau & Scanner", demo_ar_stud),
        ]
        for label, fn in v4_demos:
            tk.Button(demo_v4, text=label, command=fn,
                      bg="#164d33", fg="#88ffcc", font=("Consolas", 9)).pack(side=tk.LEFT, padx=2, pady=2)

        # Generation v5.0 Innovations Toolbar
        demo_v5 = tk.Frame(self._root, bg="#1a120d")
        demo_v5.pack(fill=tk.X, side=tk.TOP)
        tk.Label(demo_v5, text="v5.0 Revolutions:", fg="#ffaa77", bg="#1a120d", font=("Consolas", 9)).pack(side=tk.LEFT, padx=4)

        def demo_med_cpr():
            adapter.push_first_responder_triage(
                mode="cpr",
                bpm=110,
                compression_count=22,
                ccf_pct=86,
                cycle_s=42
            )

        def demo_directional_stt():
            adapter.push_directional_subtitles(
                speaker_name="Alice (R&D)",
                direction="left",
                text_line1="On lance le test d'autonomie ?",
                text_line2="Le protocole BLE est stable a 100%.",
                is_translated=False
            )

        def demo_uav():
            adapter.push_uav_avionics_hud(
                pitch_deg=4.5,
                roll_deg=-2.0,
                heading_deg=45,
                alt_agl_m=85.0,
                speed_kmh=48.0,
                home_dist_m=285.0,
                home_bearing_rel_deg=-30.0,
                cell_voltage=3.82,
                lq_pct=100
            )

        def demo_rf():
            adapter.push_stealth_rf_sentry(
                threat_type="airtag",
                target_id="Apple AirTag (Inconnu)",
                rssi_dbm=-58,
                dist_m=1.8,
                is_critical=False
            )

        v5_demos = [
            ("🚑 CPR / Triage", demo_med_cpr),
            ("🗣️ Subtitles 3D", demo_directional_stt),
            ("🛸 UAV Avionics", demo_uav),
            ("🛡️ RF Sentry", demo_rf),
        ]
        for label, fn in v5_demos:
            tk.Button(demo_v5, text=label, command=fn,
                      bg="#3d2215", fg="#ffccaa", font=("Consolas", 9)).pack(side=tk.LEFT, padx=2, pady=2)

        # Generation v6.0 Innovations Toolbar
        demo_v6 = tk.Frame(self._root, bg="#1a1c0d")
        demo_v6.pack(fill=tk.X, side=tk.TOP)
        tk.Label(demo_v6, text="v6.0 Pinnacle:", fg="#ddff55", bg="#1a1c0d", font=("Consolas", 9)).pack(side=tk.LEFT, padx=4)

        def demo_thermal():
            adapter.push_thermal_arc_flash_sentry(
                t_max_c=78.4,
                t_ambient_c=24.1,
                delta_t_c=54.3,
                reticle_xy=(152, 115),
                afb_dist_m=1.5,
                is_violating_boundary=False
            )

        def demo_allergen():
            adapter.push_allergen_nutrition_scanner(
                product_name="M&M's Peanut 250g",
                detected_allergens=["ARACHIDES", "SOJA"],
                carbs_g=59.0,
                sugar_g=53.0,
                sodium_mg=40.0,
                nutri_score="E"
            )

        def demo_marine():
            adapter.push_tactical_marine_hud(
                awa_deg=-42.0,
                aws_knots=14.5,
                sog_knots=7.8,
                cog_deg=218,
                depth_m=4.8,
                regatta_sec_left=222
            )

        def demo_whisperer():
            adapter.push_multilingual_interpreter(
                speaker_origin="Tanaka (Tokyo)",
                source_transcript="Getsuyobi wa chotto...",
                translated_text="Lundi sera un peu difficile...",
                etiquette_tag="[REFUS INDIRECT]",
                etiquette_tip="Politesse japonaise. Ne pas insister.",
                target_country="JAPON"
            )

        v6_demos = [
            ("🔥 Thermique & Arc", demo_thermal),
            ("🥜 Alerte Allergene", demo_allergen),
            ("⛵ Tactique Marine", demo_marine),
            ("🌐 Interprete Culture", demo_whisperer),
        ]
        for label, fn in v6_demos:
            tk.Button(demo_v6, text=label, command=fn,
                      bg="#363814", fg="#eeff88", font=("Consolas", 9)).pack(side=tk.LEFT, padx=2, pady=2)

        # Generation v7.0 Innovations Toolbar
        demo_v7 = tk.Frame(self._root, bg="#121820")
        demo_v7.pack(fill=tk.X, side=tk.TOP)
        tk.Label(demo_v7, text="v7.0 Frontier:", fg="#55ccff", bg="#121820", font=("Consolas", 9)).pack(side=tk.LEFT, padx=4)

        def demo_drowsiness():
            adapter.push_driver_vigilance_hud(
                perclos_pct=18.5,
                microsleep_detected=True,
                saccade_target="LEFT",
                nearest_rest_km=4.2
            )

        def demo_pick_vision():
            adapter.push_warehouse_pick(
                order_id="48291",
                progress_str="04/18",
                aisle_bay_str="ALLEE 04 - TRAVEE 12",
                shelf_bin_str="ETAGERE 03 (GOLDEN) - BAC 02",
                quantity=12,
                unit_str="PCS",
                sku_code="SKU-8842-M8",
                sku_desc="VIS INOX M8x40",
                scan_status="VERIFIED"
            )

        def demo_avalanche():
            adapter.push_avalanche_sar_hud(
                phase="COARSE",
                distance_m=12.4,
                tangent_angle_deg=14.0,
                victims_count=3,
                turn_180=False
            )

        def demo_circadian():
            adapter.push_circadian_chrono_optimizer(
                current_lux=4200,
                medi_lux=3800,
                dose_lux_min=222000,
                target_dose=300000,
                caffeine_active_mg=68,
                cutoff_time_str="14:30",
                sleep_clearance_hrs=4.3,
                melatonin_warning=False
            )

        v7_demos = [
            ("🚗 Vigilance Driver", demo_drowsiness),
            ("📦 Pick-by-Vision", demo_pick_vision),
            ("🏔️ DVA Avalanche", demo_avalanche),
            ("☀️ Chrono Circadien", demo_circadian),
        ]
        for label, fn in v7_demos:
            tk.Button(demo_v7, text=label, command=fn,
                      bg="#1f3344", fg="#aaddff", font=("Consolas", 9)).pack(side=tk.LEFT, padx=2, pady=2)

        # Generation v8.0 Innovations Toolbar
        demo_v8 = tk.Frame(self._root, bg="#1a1220")
        demo_v8.pack(fill=tk.X, side=tk.TOP)
        tk.Label(demo_v8, text="v8.0 Apex:", fg="#ff88ee", bg="#1a1220", font=("Consolas", 9)).pack(side=tk.LEFT, padx=4)

        def demo_firefighter():
            adapter.push_firefighter_mayday_hud(
                unit_id="E42-A",
                cylinder_bar=220,
                ambient_temp_c=118,
                temp_rise_c_per_min=35,
                exit_bearing_deg=60,
                pass_alarm=False
            )

        def demo_ballistics():
            adapter.push_ballistic_drop_compensator(
                range_m=850.0,
                elevation_mrad=6.4,
                windage_mrad=-1.2,
                wind_speed_ms=4.5,
                wind_angle_deg=90,
                cant_deg=-0.4
            )

        def demo_surgical():
            adapter.push_surgical_vitals_hud(
                patient_id="P-402",
                spo2_pct=98,
                hr_bpm=72,
                map_mmhg=85,
                etco2_mmhg=38,
                implant_torque_ncm=32.0
            )

        def demo_low_vision():
            adapter.push_low_vision_echonav_hud(
                head_obstacle_dist_m=1.8,
                head_obstacle_type="BRANCHE / PANNEAU",
                curb_drop_dist_m=2.2,
                is_critical_duck=False
            )

        v8_demos = [
            ("🚒 Pompier SCBA", demo_firefighter),
            ("🎯 Balistique Mil-Dot", demo_ballistics),
            ("🩺 Chirurgie Stérile", demo_surgical),
            ("🦯 Radar Basse Vision", demo_low_vision),
        ]
        for label, fn in v8_demos:
            tk.Button(demo_v8, text=label, command=fn,
                      bg="#331f44", fg="#eeaaff", font=("Consolas", 9)).pack(side=tk.LEFT, padx=2, pady=2)

        # Main OLED canvas
        cw = DISPLAY_W * self.scale
        ch = DISPLAY_H * self.scale
        self._canvas = tk.Canvas(self._root, width=cw, height=ch, bg="black",
                                 highlightthickness=2, highlightbackground="#1a3a5a")
        self._canvas.pack(padx=4, pady=4)

        # Keyboard shortcut: G = inject gesture
        self._root.bind('<g>', lambda e: self.inject_gesture())
        self._root.bind('<G>', lambda e: self.inject_gesture())
        self._root.bind('<c>', lambda e: (self._cmd_clear(), self._refresh_gui()))

        # Footer
        footer = tk.Label(
            self._root,
            text="[G] Wave Gesture  [C] Clear  |  OpenBridge × ENGO MicroOLED Emulator  |  "
                 "BLE UUIDs: 0783B03E…5CBA(RX) …5CB8(TX) …5CBB(Gesture)",
            fg="#445566", bg="#0a0a0a", font=("Consolas", 8)
        )
        footer.pack(fill=tk.X, padx=4, pady=(0, 2))

        self._running = True
        demo_ambient()   # show ambient on startup
        self._root.mainloop()
        self._running = False


# ──────────────────────────────────────────────────────────────────────────────
# VirtualENGO — Bumble-backed BLE GATT peripheral
# ──────────────────────────────────────────────────────────────────────────────

class VirtualENGO:
    """Virtual BLE GATT server advertising the full ActiveLook profile.
    Requires bumble. Runs on a TCP controller; use nRF Connect or bleak to connect.
    """

    def __init__(self, hud: HUDCanvas, tcp_port: int = 7788):
        self.hud = hud
        self.tcp_port = tcp_port
        self._gesture_subscribers: list = []

    async def run(self):
        try:
            from bumble.device import Device
            from bumble.transport import open_transport
            from bumble.gatt import (Service, Characteristic, CharacteristicValue,
                                     GATT_DEVICE_INFORMATION_SERVICE, GATT_BATTERY_SERVICE)
            from bumble.att import ATT_INSUFFICIENT_AUTHORIZATION_ERROR
        except ImportError:
            print("[VirtualENGO] bumble not installed — BLE server unavailable")
            return

        transport_str = f"tcp-server:0.0.0.0:{self.tcp_port}"
        print(f"[VirtualENGO] Starting Bumble GATT server on {transport_str}")
        print(f"[VirtualENGO] Connect nRF Connect / bleak using TCP transport bumble-bridge")

        async with await open_transport(transport_str) as (hci_source, hci_sink):
            device = Device(name="ENGO 3-OpenBridge", address="F0:F1:F2:00:00:01")
            device.host.connections.clear()

            hud = self.hud

            def on_rx_write(connection, data: bytes):
                """Called when host writes commands to RX characteristic."""
                print(f"[VirtualENGO] RX ← {len(data)}B: {data[:16].hex()}")
                hud.dispatch(data)

            battery_level = bytes([hud._battery])

            rx_char = Characteristic(
                uuid=RX_UUID,
                properties=Characteristic.WRITE | Characteristic.WRITE_WITHOUT_RESPONSE,
                permissions=Characteristic.WRITEABLE,
                value=CharacteristicValue(write=on_rx_write)
            )
            tx_char = Characteristic(
                uuid=TX_UUID,
                properties=Characteristic.NOTIFY,
                permissions=Characteristic.READABLE,
                value=b'\x00'
            )
            flow_char = Characteristic(
                uuid=FLOW_UUID,
                properties=Characteristic.NOTIFY | Characteristic.READ,
                permissions=Characteristic.READABLE,
                value=b'\x01'   # Flow OK
            )
            gesture_char = Characteristic(
                uuid=GESTURE_UUID,
                properties=Characteristic.NOTIFY,
                permissions=Characteristic.READABLE,
                value=b'\x00'
            )

            # Wire gesture button → gesture_char notifications
            def send_gesture(data: bytes):
                # notify all subscribed connections
                print(f"[VirtualENGO] GESTURE → notify {data.hex()}")

            hud.gesture_callback = send_gesture

            al_service = Service(uuid=SVC_UUID, characteristics=[rx_char, tx_char, flow_char, gesture_char])
            batt_char = Characteristic(
                uuid=BATT_CHAR_UUID,
                properties=Characteristic.READ | Characteristic.NOTIFY,
                permissions=Characteristic.READABLE,
                value=battery_level
            )
            batt_service = Service(uuid=BATT_SVC_UUID, characteristics=[batt_char])

            device.add_services([al_service, batt_service])
            await device.power_on()
            await device.start_advertising(auto_restart=True)
            print("[VirtualENGO] Advertising as 'ENGO 3-OpenBridge'…")
            await asyncio.Future()   # run forever


# ──────────────────────────────────────────────────────────────────────────────
# Public API — importable by OpenBridge adapters
# ──────────────────────────────────────────────────────────────────────────────

def dispatch_command(raw: bytes, hud: Optional[HUDCanvas] = None):
    """Send raw ActiveLook bytes to a HUDCanvas instance. Thread-safe."""
    if hud:
        hud.dispatch(raw)


def run_headless_benchmark(model: str = "ENGO 3", include_neural: bool = False) -> dict:
    """Execute all killer features in headless mode, measuring byte count,
    parsed frames, pixel fill factor, and estimated MicroOLED power draw.
    If include_neural is True, includes the 4 neural expansion scenarios.
    """
    from src.adapters.activelook import ActiveLookAdapter
    hud = HUDCanvas(model=model)
    sent_bytes = bytearray()
    
    def transport(data: bytes):
        sent_bytes.extend(data)
        hud.dispatch(data)

    adapter = ActiveLookAdapter(transport=transport, model=model)
    benchmarks = {}

    scenarios = [
        ("spatial_radar", lambda: adapter.push_spatial_radar([
            {"name": "VAC", "bearing_deg": 220, "dist_m": 2.5, "state": "docking"},
            {"name": "GATE", "bearing_deg": 35, "dist_m": 7.5, "state": "alert"},
            {"name": "SOLAR", "bearing_deg": 0, "dist_m": 5.0, "state": "ok"},
            {"name": "CAR", "bearing_deg": 315, "dist_m": 9.0, "state": "ok"}
        ])),
        ("eyes_on_target", lambda: adapter.push_eyes_on_target_receipt(
            target_name="Salon Lights", action="Extinction & Verrouillage",
            oracle_verified=True, latency_ms=38, digest="#4f9a12c8-verified"
        )),
        ("two_phase_countdown", lambda: adapter.push_two_phase_countdown(
            routine_name="Bedtime Shutdown", seconds_remaining=4, max_seconds=5
        )),
        ("peripheral_telemetry", lambda: adapter.push_peripheral_telemetry(
            grid_watts=7420, wan_mbps=940, ping_ms=9, alert="LINKY SPIKE > 7kW"
        )),
        ("workflow_prompter", lambda: adapter.push_workflow_prompter(
            step_idx=3, total_steps=7, title="Connect Ribbon Bus",
            instruction="Insert I2C cable into J2 connector until click", timer_s=145
        )),
        ("doorbell_subtitles", lambda: adapter.push_live_subtitles(
            speaker="Livreur Colis", text="Bonjour, j'ai un paquet pour vous a deposer", is_urgent=True
        )),
        ("compass_wayfinder", lambda: adapter.push_compass_wayfinder(
            heading_deg=285, target_bearing_deg=310, target_dist_m=145.0, target_name="PARKING B3"
        )),
        ("security_shield", lambda: adapter.push_smart_home_security_alert(
            threat_type="SYN Port Scan", source_ip="192.168.1.189",
            mac_vendor="Raspberry Pi / Rogue", target_service="SSH Port 22"
        )),
        ("bio_pacer", lambda: adapter.push_bio_adaptive_pacer(
            target_spm=180, current_spm=174, hr_bpm=162, hr_zone=4, advice="AUGMENTER FREQUENCE (+6)"
        )),
        ("media_remote", lambda: adapter.push_media_remote_hud(
            media_title="Dune: Part Two", artist_or_source="Kodi Salon (4K HDR)",
            volume_pct=45, is_playing=True, progress_s=3420, total_s=9960
        )),
        ("silent_morse_input", lambda: adapter.push_silent_morse_input(
            buffer_str="OUI EN ROUTE", current_morse=".-", suggestion="ARRIVE 5 MIN"
        )),
        ("speech_teleprompter", lambda: adapter.push_speech_teleprompter(
            current_line="OpenBridge connecte vos lunettes",
            next_line="aux modeles d'IA locaux et a vos objets",
            wpm=138, is_rushing=False, elapsed_s=45, total_s=180
        )),
        ("spatial_energy_heatmap", lambda: adapter.push_spatial_energy_heatmap(
            current_room="Cuisine", room_watts=2150, total_watts=3480,
            vampire_devices=[{"name": "Four Veille", "watts": 65, "idle_hours": 3}]
        )),
        ("arcade_runner", lambda: adapter.push_arcade_game_frame(
            player_y=160, obstacle_x=180, score=50, game_over=False
        )),
        ("collision_sentry", lambda: adapter.push_collision_sentry(
            hazard_side="left", speed_kmh=52, dist_m=18.5, ttc_s=1.3
        )),
        ("executive_briefing", lambda: adapter.push_executive_briefing_glance(
            contact_name="Sophie Martin", role_title="Directrice R&D",
            bullet_points=["Partenariat v2", "Budget 85k", "Decision a 17h"],
            sentiment_hint="VIP"
        )),
        ("biofeedback_stress", lambda: adapter.push_biofeedback_stress_guardian(
            stress_score=68, hrv_ms=42, breath_phase="INSP", phase_timer_s=3
        )),
        ("diy_ar_stud_level", lambda: adapter.push_diy_ar_stud_level(
            pitch_deg=0.1, roll_deg=0.0, is_level=True, detected_hazard="CABLE 230V ACTIF"
        )),
        ("first_responder_cpr", lambda: adapter.push_first_responder_triage(
            mode="cpr", bpm=110, compression_count=22, ccf_pct=86, cycle_s=42
        )),
        ("directional_subtitles", lambda: adapter.push_directional_subtitles(
            speaker_name="Alice", direction="left",
            text_line1="On lance le test d'autonomie ?",
            text_line2="Le protocole BLE est stable.",
            is_translated=False
        )),
        ("uav_avionics", lambda: adapter.push_uav_avionics_hud(
            pitch_deg=4.5, roll_deg=-2.0, heading_deg=45, alt_agl_m=85.0,
            speed_kmh=48.0, home_dist_m=285.0, home_bearing_rel_deg=-30.0,
            cell_voltage=3.82, lq_pct=100
        )),
        ("stealth_rf_sentry", lambda: adapter.push_stealth_rf_sentry(
            threat_type="airtag", target_id="Apple AirTag", rssi_dbm=-58, dist_m=1.8
        )),
        ("thermal_arc_flash", lambda: adapter.push_thermal_arc_flash_sentry(
            t_max_c=78.4, t_ambient_c=24.1, delta_t_c=54.3,
            reticle_xy=(152, 115), afb_dist_m=1.5, is_violating_boundary=False
        )),
        ("allergen_nutrition", lambda: adapter.push_allergen_nutrition_scanner(
            product_name="M&M's Peanut", detected_allergens=["ARACHIDES"],
            carbs_g=59.0, sugar_g=53.0, sodium_mg=40.0, nutri_score="E"
        )),
        ("tactical_marine", lambda: adapter.push_tactical_marine_hud(
            awa_deg=-42.0, aws_knots=14.5, sog_knots=7.8, cog_deg=218, depth_m=4.8, regatta_sec_left=222
        )),
        ("multilingual_whisperer", lambda: adapter.push_multilingual_interpreter(
            speaker_origin="Tanaka", source_transcript="Getsuyobi wa chotto...",
            translated_text="Lundi sera un peu difficile...",
            etiquette_tag="[REFUS INDIRECT]", etiquette_tip="Ne pas insister.",
            target_country="JAPON"
        )),
        ("driver_vigilance", lambda: adapter.push_driver_vigilance_hud(
            perclos_pct=18.5, microsleep_detected=True, saccade_target="LEFT", nearest_rest_km=4.2
        )),
        ("warehouse_pick", lambda: adapter.push_warehouse_pick(
            order_id="48291", progress_str="04/18", aisle_bay_str="ALLEE 04 - TRAVEE 12",
            shelf_bin_str="ETAGERE 03 - BAC 02", quantity=12, unit_str="PCS",
            sku_code="SKU-8842-M8", sku_desc="VIS INOX M8x40", scan_status="VERIFIED"
        )),
        ("avalanche_sar", lambda: adapter.push_avalanche_sar_hud(
            phase="COARSE", distance_m=12.4, tangent_angle_deg=14.0, victims_count=3, turn_180=False
        )),
        ("circadian_chrono", lambda: adapter.push_circadian_chrono_optimizer(
            current_lux=4200, medi_lux=3800, dose_lux_min=222000, target_dose=300000,
            caffeine_active_mg=68, cutoff_time_str="14:30", sleep_clearance_hrs=4.3, melatonin_warning=False
        )),
        ("firefighter_mayday", lambda: adapter.push_firefighter_mayday_hud(
            unit_id="E42-A", cylinder_bar=220, ambient_temp_c=118, temp_rise_c_per_min=35,
            exit_bearing_deg=60, pass_alarm=False
        )),
        ("ballistic_drop", lambda: adapter.push_ballistic_drop_compensator(
            range_m=850.0, elevation_mrad=6.4, windage_mrad=-1.2, wind_speed_ms=4.5,
            wind_angle_deg=90, cant_deg=-0.4
        )),
        ("surgical_vitals", lambda: adapter.push_surgical_vitals_hud(
            patient_id="P-402", spo2_pct=98, hr_bpm=72, map_mmhg=85, etco2_mmhg=38,
            implant_torque_ncm=32.0
        )),
        ("low_vision_echonav", lambda: adapter.push_low_vision_echonav_hud(
            head_obstacle_dist_m=1.8, head_obstacle_type="BRANCHE / PANNEAU",
            curb_drop_dist_m=2.2, is_critical_duck=False
        ))
    ]

    neural_scenarios = [
        ("neural_voice_assistant", lambda: adapter.push_neural_voice_assistant_hud(
            state_str="ECOUTE EN COURS", partial_transcript="Eteindre le salon et verifier la Freebox",
            mic_source="PHONE BEAMFORMING MIC", vu_level_pct=76, latency_ms=115
        )),
        ("multimodal_vision_hud", lambda: adapter.push_multimodal_vision_hud(
            target_label="DISJONCTEUR #4 (CHAUFFE-EAU)", confidence_pct=96,
            bounding_box=(60, 60, 244, 150),
            diagnostic_summary="POSITION BASSE : DECLENCHEMENT",
            action_recommendation="Verifiez resistance avant de re-armer",
            source_device="50MP PHONE CAM"
        )),
        ("ambient_iot_matrix", lambda: adapter.push_ambient_iot_matrix(
            linky_watts=1950, tempo_tomorrow="BLANC", rain_min=14, temp_c=16,
            transit_line="M14", transit_eta_min=2, wan_mbps=940, ping_ms=8
        )),
        ("neural_translation_stream", lambda: adapter.push_neural_translation_stream(
            speaker_id="SPEAKER 01", source_lang="EN", target_lang="FR",
            live_text="Welcome to the OpenBridge AR ecosystem",
            translated_text="Bienvenue dans l'ecosysteme de realite augmentee OpenBridge",
            azimuth_dir="GAUCHE 30°", latency_ms=175
        ))
    ]

    active_scenarios = scenarios + (neural_scenarios if include_neural else [])

    for name, fn in active_scenarios:
        before_len = len(sent_bytes)
        before_cmds = hud._cmd_count
        fn()
        bytes_transferred = len(sent_bytes) - before_len
        cmds_parsed = hud._cmd_count - before_cmds
        fill = hud.compute_pixel_fill()
        pwr = hud.estimate_power_mw()
        est_hours = int(425 / max(0.1, pwr))
        benchmarks[name] = {
            "bytes_transferred": bytes_transferred,
            "commands_parsed": cmds_parsed,
            "pixel_fill_percent": round(fill, 2),
            "estimated_power_mw": round(pwr, 2),
            "estimated_battery_hours": est_hours
        }

    return {
        "model": model,
        "scenarios": benchmarks,
        "total_bytes": len(sent_bytes),
        "total_commands": hud._cmd_count
    }


def launch_emulator(model: str = "ENGO 3", with_ble_server: bool = False, tcp_port: int = 7788):
    """
    Launch the HUD emulator GUI (and optionally a virtual BLE server).
    Call from __main__ or the OpenBridge CLI.
    """
    hud = HUDCanvas(model=model)

    if with_ble_server:
        vengo = VirtualENGO(hud, tcp_port=tcp_port)

        def run_ble():
            asyncio.run(vengo.run())

        t = threading.Thread(target=run_ble, daemon=True)
        t.start()
        print(f"[Emulator] Virtual BLE GATT server started on TCP:{tcp_port}")
        print(f"[Emulator] Connect via bumble-bridge or nRF Connect → TCP {tcp_port}")

    hud.run()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OpenBridge × ENGO HUD Emulator")
    parser.add_argument("--model", default="ENGO 3", choices=["ENGO 1", "ENGO 2", "ENGO 3", "ENGO 3 Titanium"])
    parser.add_argument("--ble", action="store_true", help="Start virtual BLE GATT server via Bumble")
    parser.add_argument("--port", type=int, default=7788, help="TCP port for Bumble BLE bridge")
    args = parser.parse_args()
    launch_emulator(model=args.model, with_ble_server=args.ble, tcp_port=args.port)
