"""ActiveLook / ENGO Smart Glasses Adapter for OpenBridge.

Supports ENGO 1, ENGO 2, ENGO 3 (Standard, Photochromic, Titanium).
Operates over Bluetooth Low Energy (BLE 4.2 / 5.0 / 5.4 GATT) directly on PC (bleak),
relayed via OpenBridge Companion (Android / Wear OS), or against the in-process/local
ActiveLook HUD emulator (src.adapters.activelook_emulator).

Display constraints:
- 304 x 256 MicroOLED. True black (0 mW) background.
- Max 32 chars/line for high readability.
- MultiColor on ENGO 3 (0x01=Green, 0x02=Amber, 0x03=Red, 0x04=Cyan, 0x05=Yellow).
- Flow control monitored on characteristic ...5CB9 to prevent MCU queue overflow.
"""
from __future__ import annotations

import math
import struct
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

# ActiveLook GATT Constants
SERVICE_UUID = "0783b03e-8535-b5a0-7140-a304d2495cb7"
RX_CHAR_UUID = "0783b03e-8535-b5a0-7140-a304d2495cba"
TX_CHAR_UUID = "0783b03e-8535-b5a0-7140-a304d2495cb8"
FLOW_CHAR_UUID = "0783b03e-8535-b5a0-7140-a304d2495cb9"
GESTURE_CHAR_UUID = "0783b03e-8535-b5a0-7140-a304d2495cbb"

# Colors for ENGO 3 MultiColor HUD
COLOR_OFF = 0x00
COLOR_GREEN = 0x01   # Confirmed / Nominal / Success
COLOR_AMBER = 0x02   # Warning / Pending / Attention
COLOR_RED = 0x03     # Refused / Safety / Fault
COLOR_CYAN = 0x04    # Information / Peripheral
COLOR_YELLOW = 0x05  # Legacy ENGO 1/2 Monochrome
# Nearest neutral: same subtle gray (0x07) already used for dim UI accents.
# A dedicated pure-white code is unconfirmed on hardware; do not renumber blindly.
COLOR_WHITE = 0x07


def encode_packet(cmd: int, payload: bytes = b"", query_id: bytes = b"") -> bytes:
    """Encode an ActiveLook binary frame: 0xFF [CMD] [FMT] [LEN] [QueryID] [Data] 0xAA."""
    qid_len = len(query_id)
    if qid_len > 15:
        raise ValueError("QueryID cannot exceed 15 bytes")
    
    # Calculate preliminary length (1 byte length first)
    raw_len = 1 + 1 + 1 + 1 + qid_len + len(payload) + 1
    len_wide = raw_len > 255
    if len_wide:
        raw_len += 1  # 2-byte length field
    
    fmt = (1 << 5) if len_wide else 0
    fmt |= (qid_len & 0x0F) << 1
    
    if len_wide:
        header = struct.pack(">BBB H", 0xFF, cmd, fmt, raw_len)
    else:
        header = struct.pack(">BBBB", 0xFF, cmd, fmt, raw_len)
    
    return header + query_id + payload + b"\xAA"


# Command Builders
def cmd_clear() -> bytes:
    """Wipe screen to black."""
    return encode_packet(0x01)


def cmd_luma(level: int) -> bytes:
    """Set brightness (0-15)."""
    return encode_packet(0x10, bytes([max(0, min(15, level))]))


# Red-green palette of ActiveLook colour glasses (ENGO 3, hardware MDP08): 9 red x 9 green levels = 81 colours, no
# blue and no white. Row = red level 0-8, column = green level 0-8. Values from the ActiveLook API documentation
# (resources/ActiveLook_RRGG_colors.png), as tabulated by the MIT-licensed @pranen/activelook library.
RG_PALETTE = (
    (0x00, 0x01, 0x02, 0x41, 0x81, 0x82, 0x43, 0x83, 0xc3),
    (0x04, 0x05, 0x06, 0x45, 0x85, 0x86, 0x47, 0x87, 0xc7),
    (0x20, 0x21, 0x22, 0x61, 0xa1, 0xa2, 0x63, 0xa3, 0xe3),
    (0x14, 0x15, 0x16, 0x55, 0x95, 0x96, 0x57, 0x97, 0xd7),
    (0x18, 0x19, 0x1a, 0x59, 0x99, 0x9a, 0x5b, 0x9b, 0xdb),
    (0x28, 0x29, 0x2a, 0x69, 0xa9, 0xaa, 0x6b, 0xab, 0xeb),
    (0x1c, 0x1d, 0x1e, 0x5d, 0x9d, 0x9e, 0x5f, 0x9f, 0xdf),
    (0x38, 0x39, 0x3a, 0x79, 0xb9, 0xba, 0x7b, 0xbb, 0xfb),
    (0x3c, 0x3d, 0x3e, 0x7d, 0xbd, 0xbe, 0x7f, 0xbf, 0xff),
)
# Named colours calibrated by eye on an ENGO 3 (same source); checked on our pair on 26 Nov 2026.
RG_COLOURS = {'red': 0x3c, 'orange': 0x3e, 'amber': 0xbd, 'yellow': 0xff, 'lime': 0x87, 'green': 0xc3}


def rg(red: int, green: int) -> int:
    """Colour value for red and green levels 0-8 (ENGO 3 red-green palette)."""
    return RG_PALETTE[max(0, min(8, int(red)))][max(0, min(8, int(green)))]


def rg_levels(value: int):
    """(red, green) levels 0-8 of a palette value, or None if the value is not one of the 81 colours."""
    for red, row in enumerate(RG_PALETTE):
        if value in row:
            return red, row.index(value)
    return None


def cmd_text_rg(x: int, y: int, text: str, font: int = 0, colour: int = 0x88, rot: int = 0) -> bytes:
    """0x3E txtColor: text in a red-green colour value (colour glasses only)."""
    clean_text = text.encode("utf-8")[:250] + b"\x00"
    return encode_packet(0x3E, struct.pack(">hh BBB", x, y, rot, font, colour & 0xFF) + clean_text)


def cmd_color(color_id: int) -> bytes:
    """Set active color for ENGO 3 MultiColor (0x01=Green, 0x02=Amber, 0x03=Red, 0x04=Cyan)."""
    return encode_packet(0x3D, bytes([color_id & 0xFF]))


def cmd_grey(level: int) -> bytes:
    """Set active greyscale level (0-15). Level 0 = black / off."""
    return encode_packet(0x30, bytes([max(0, min(15, level))]))


def cmd_text(x: int, y: int, text: str, font: int = 0, color_or_grey: int = 15, rot: int = 0) -> bytes:
    """Draw text at coordinate (x, y)."""
    clean_text = text.encode("utf-8")[:250] + b"\x00"
    payload = struct.pack(">hh BBB", x, y, rot, font, color_or_grey) + clean_text
    return encode_packet(0x37, payload)


def cmd_rectf(x0: int, y0: int, x1: int, y1: int) -> bytes:
    """Draw filled rectangle."""
    return encode_packet(0x34, struct.pack(">hhhh", x0, y0, x1, y1))


def cmd_rect(x0: int, y0: int, x1: int, y1: int) -> bytes:
    """Draw outline rectangle."""
    return encode_packet(0x33, struct.pack(">hhhh", x0, y0, x1, y1))


def cmd_line(x0: int, y0: int, x1: int, y1: int) -> bytes:
    """Draw line between (x0, y0) and (x1, y1)."""
    return encode_packet(0x32, struct.pack(">hhhh", x0, y0, x1, y1))


def cmd_circ(x: int, y: int, r: int) -> bytes:
    """Draw circle outline."""
    return encode_packet(0x35, struct.pack(">hhB", x, y, max(0, min(255, r))))


def cmd_circf(x: int, y: int, r: int) -> bytes:
    """Draw filled circle."""
    return encode_packet(0x36, struct.pack(">hhB", x, y, max(0, min(255, r))))


def cmd_arc(x: int, y: int, r: int, start_ang: int, end_ang: int, thick: int = 1) -> bytes:
    """Draw circular arc."""
    return encode_packet(0x3C, struct.pack(">hhBhhB", x, y, max(0, min(255, r)), start_ang, end_ang, thick))


def cmd_gauge(gauge_id: int, value_pct: int) -> bytes:
    """Update progress gauge (0-100%)."""
    return encode_packet(0x70, bytes([gauge_id & 0xFF, max(0, min(100, value_pct))]))


def cmd_power(on: bool) -> bytes:
    """Turn ActiveLook MicroOLED display on or sleep (0x00)."""
    return encode_packet(0x00, bytes([0x01 if on else 0x00]))


def cmd_shift(x: int, y: int) -> bytes:
    """Set optical alignment X/Y offset in pixels (0x09)."""
    return encode_packet(0x09, struct.pack(">hh", max(-128, min(127, int(x))), max(-128, min(127, int(y)))))


def cmd_gesture_enable(enable: bool) -> bytes:
    """Toggle infrared gesture proximity sensor."""
    return encode_packet(0x21, bytes([0x01 if enable else 0x00]))


def cmd_als_enable(enable: bool) -> bytes:
    """Toggle ambient light sensor auto-brightness (0x22)."""
    return encode_packet(0x22, bytes([0x01 if enable else 0x00]))


def cmd_hold_flush(action: int) -> bytes:
    """Graphic pipeline flush control: 0 = Hold (buffer operations), 1 = Flush (atomic draw)."""
    return encode_packet(0x39, bytes([action & 0xFF]))


def cmd_layout_save(
    layout_id: int,
    x: int,
    y: int,
    width: int,
    height: int,
    fore_color: int = 15,
    back_color: int = 0,
    font: int = 1,
    text_valid: bool = True,
    text_x: int = 0,
    text_y: int = 0,
    text_rot: int = 0,
    text_opacity: int = 0,
    sub_commands: bytes = b"",
    is_color: bool = False
) -> bytes:
    """Save persistent layout template into eyewear flash (0x60 grayscale or 0x6B color)."""
    sub_size = min(255, len(sub_commands))
    header = struct.pack(
        ">BB H B H B B B B B H B B B",
        layout_id & 0xFF,
        sub_size,
        max(0, x),
        max(0, y),
        max(1, width),
        max(1, height),
        fore_color & 0xFF,
        back_color & 0xFF,
        font & 0xFF,
        1 if text_valid else 0,
        max(0, text_x),
        max(0, text_y),
        text_rot & 0xFF,
        text_opacity & 0xFF
    )
    opcode = 0x6B if is_color else 0x60
    return encode_packet(opcode, header + sub_commands[:sub_size])


def cmd_layout_display(layout_id: int, text: str) -> bytes:
    """Populate layout slot with text string (0x62)."""
    return encode_packet(0x62, bytes([layout_id & 0xFF]) + text.encode("utf-8") + b"\x00")


def cmd_layout_clear(layout_id: int) -> bytes:
    """Clear clipping box of layout (0x63)."""
    return encode_packet(0x63, bytes([layout_id & 0xFF]))


def cmd_layout_clear_and_display(layout_id: int, text: str) -> bytes:
    """Atomic clear + display layout slot (0x69)."""
    return encode_packet(0x69, bytes([layout_id & 0xFF]) + text.encode("utf-8") + b"\x00")


def cmd_page_save(page_id: int, slots: list[tuple[int, int, int]]) -> bytes:
    """Save composite page layout into eyewear flash (0x80). Slots: (layout_id, x, y)."""
    payload = bytearray([page_id & 0xFF])
    for layout_id, x, y in slots[:10]:
        payload.extend(struct.pack(">B H B", layout_id & 0xFF, max(0, x), max(0, y)))
    return encode_packet(0x80, bytes(payload))


def cmd_page_display(page_id: int, texts: list[str]) -> bytes:
    """Multicast page update: display multiple strings across all page layout slots in 1 BLE frame (0x83)."""
    payload = bytearray([page_id & 0xFF])
    for t in texts:
        payload.extend(t.encode("utf-8") + b"\x00")
    return encode_packet(0x83, bytes(payload))


def cmd_page_clear_and_display(page_id: int, texts: list[str]) -> bytes:
    """Atomic clear and multicast display across all page layout slots (0x86)."""
    payload = bytearray([page_id & 0xFF])
    for t in texts:
        payload.extend(t.encode("utf-8") + b"\x00")
    return encode_packet(0x86, bytes(payload))


def cmd_cfg_write(name: str, version: int = 1, password: int = 0) -> bytes:
    """Open flash configuration container for modification (0xD0). Requires battery >= 5%."""
    name_bytes = name.encode("ascii")[:12].ljust(12, b"\x00")
    return encode_packet(0xD0, name_bytes + struct.pack(">II", version, password))


def cmd_cfg_set(name: str) -> bytes:
    """Activate flash configuration profile (0xD2)."""
    name_bytes = name.encode("ascii")[:12].ljust(12, b"\x00")
    return encode_packet(0xD2, name_bytes)


# ──────────────────────────────────────────────────────────────────────────────
# Stealth Temple-Tap Morse & Arcade Game Physics Engines
# ──────────────────────────────────────────────────────────────────────────────

MORSE_MAP: Dict[str, str] = {
    ".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E",
    "..-.": "F", "--.": "G", "....": "H", "..": "I", ".---": "J",
    "-.-": "K", ".-..": "L", "--": "M", "-.": "N", "---": "O",
    ".--.": "P", "--.-": "Q", ".-.": "R", "...": "S", "-": "T",
    "..-": "U", "...-": "V", ".--": "W", "-..-": "X", "-.--": "Y",
    "--..": "Z", "-----": "0", ".----": "1", "..---": "2", "...--": "3",
    "....-": "4", ".....": "5", "-....": "6", "--...": "7", "---..": "8",
    "----.": "9", ".-.-.-": ".", "--..--": ",", "..--..": "?"
}


class TempleTapMorseDecoder:
    """Decodes capacitive temple touch taps into characters and commands for zero-voice stealth input."""

    def __init__(self, dot_threshold_s: float = 0.25, letter_pause_s: float = 0.65):
        self.dot_threshold_s = dot_threshold_s
        self.letter_pause_s = letter_pause_s
        self.touch_start_time = 0.0
        self.last_tap_time = 0.0
        self.current_morse = ""
        self.committed_text = ""

    def on_touch_down(self, t: Optional[float] = None) -> None:
        self.touch_start_time = t if t is not None else time.time()

    def on_touch_up(self, t: Optional[float] = None) -> str:
        now = t if t is not None else time.time()
        duration = now - self.touch_start_time
        symbol = "." if duration < self.dot_threshold_s else "-"
        self.current_morse += symbol
        self.last_tap_time = now
        return symbol

    def check_letter_timeout(self, t: Optional[float] = None) -> Optional[str]:
        now = t if t is not None else time.time()
        if self.current_morse and (now - self.last_tap_time >= self.letter_pause_s):
            char = MORSE_MAP.get(self.current_morse, "?")
            self.committed_text += char
            self.current_morse = ""
            return char
        return None

    def backspace(self) -> str:
        if self.current_morse:
            self.current_morse = self.current_morse[:-1]
        elif self.committed_text:
            self.committed_text = self.committed_text[:-1]
        return self.committed_text

    def clear(self) -> None:
        self.current_morse = ""
        self.committed_text = ""


@dataclass
class VectorObstacle:
    x: float
    width: float = 12.0
    height: float = 22.0


class ActiveLookArcadeEngine:
    """MicroOLED 60Hz Vector Runner Arcade Game playable via hand wave IR gestures."""

    def __init__(self, ground_y: int = 190):
        self.ground_y = ground_y
        self.player_x = 35.0
        self.player_y = float(ground_y - 8)
        self.player_vy = 0.0
        self.is_jumping = False
        self.gravity = -24.0
        self.jump_velocity = 12.0
        self.obstacles: List[VectorObstacle] = [VectorObstacle(x=280.0)]
        self.score = 0
        self.game_over = False
        self.speed = 8.0

    def jump(self) -> bool:
        if not self.is_jumping and not self.game_over:
            self.player_vy = self.jump_velocity
            self.is_jumping = True
            return True
        elif self.game_over:
            self.reset()
            return True
        return False

    def reset(self) -> None:
        self.player_y = float(self.ground_y - 8)
        self.player_vy = 0.0
        self.is_jumping = False
        self.obstacles = [VectorObstacle(x=280.0)]
        self.score = 0
        self.game_over = False

    def tick(self, dt: float = 0.1) -> Dict[str, Any]:
        if self.game_over:
            return {"game_over": True, "score": self.score}

        # Physics
        if self.is_jumping:
            self.player_y -= self.player_vy
            self.player_vy += self.gravity * dt
            if self.player_y >= self.ground_y - 8:
                self.player_y = float(self.ground_y - 8)
                self.player_vy = 0.0
                self.is_jumping = False

        # Move obstacles
        for obs in self.obstacles:
            obs.x -= self.speed
            # Collision detection: player circle (r=8) vs obstacle rect
            if abs(obs.x - self.player_x) < 14 and (self.player_y >= self.ground_y - obs.height):
                self.game_over = True
                return {"game_over": True, "score": self.score}

        # Recycle obstacle
        if self.obstacles and self.obstacles[0].x < -20:
            self.obstacles.pop(0)
            self.obstacles.append(VectorObstacle(x=310.0 + (self.score % 4) * 25))
            self.score += 10

        return {"game_over": False, "score": self.score}


NATIVE_W, NATIVE_H = 304, 256
TEXT_ROT_UPRIGHT = 4


def split_packets(stream: bytes):
    """Yield (cmd, query_id, data, raw) for each ActiveLook frame in `stream`; bytes that do not parse as a frame are
    yielded once as (None, b'', b'', raw) so they can be passed through untouched."""
    i, n = 0, len(stream)
    while i < n:
        if stream[i] != 0xFF or i + 4 > n:
            yield None, b"", b"", stream[i:]
            return
        cmd, fmt = stream[i + 1], stream[i + 2]
        wide = bool(fmt & 0x20)
        if wide:
            if i + 5 > n:
                yield None, b"", b"", stream[i:]
                return
            length, head = struct.unpack_from(">H", stream, i + 3)[0], 5
        else:
            length, head = stream[i + 3], 4
        qlen = (fmt >> 1) & 0x0F
        end = i + length
        if length < head + qlen + 1 or end > n or stream[end - 1] != 0xAA:
            yield None, b"", b"", stream[i:]
            return
        qid = stream[i + head:i + head + qlen]
        yield cmd, qid, stream[i + head + qlen:end - 1], stream[i:end]
        i = end


def _flip(x: int, y: int):
    return NATIVE_W - 1 - x, NATIVE_H - 1 - y


# The old demo screens name colours 0x01-0x05 (COLOR_GREEN...). On a real ENGO 3 those bytes are red-green palette
# values close to black, so to_native(colour=True) swaps them for the calibrated colours (no cyan on a red-green panel).
LEGACY_COLOURS = {COLOR_GREEN: RG_COLOURS['green'], COLOR_AMBER: RG_COLOURS['amber'], COLOR_RED: RG_COLOURS['red'],
                  COLOR_CYAN: RG_COLOURS['lime'], COLOR_YELLOW: RG_COLOURS['yellow']}


def to_native(stream: bytes, colour: bool = False) -> bytes:
    """Logical frames (origin top-left, text rotation 0) -> the ActiveLook native frame, as a real ENGO 3 needs them.

    Measured on a real ENGO 3 (26 Nov 2026): both axes are mirrored and upright text uses rotation 4, anchored at the
    text's logical top-left. OpenBridge's display engine (src/glasses/panel.py) already draws in the native frame;
    this converts the older demo screens built with the cmd_* helpers (push_* methods, ENGO AI bridge, HUD Studio
    features) so they show upright too. Arc angles are unchanged (both axes are mirrored). With colour=True (ENGO 3)
    the legacy colour ids become real palette colours, for shapes (0x3D) and for text (0x37 -> 0x3E)."""
    out = []
    for cmd, qid, d, raw in split_packets(stream):
        try:
            if cmd == 0x31 and len(d) >= 4:
                d = struct.pack(">hh", *_flip(*struct.unpack_from(">hh", d))) + d[4:]
            elif cmd in (0x32, 0x33, 0x34) and len(d) >= 8:
                x0, y0, x1, y1 = struct.unpack_from(">hhhh", d)
                (x0, y0), (x1, y1) = _flip(x0, y0), _flip(x1, y1)
                if cmd != 0x32:                      # rectangles keep min / max corners
                    x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
                d = struct.pack(">hhhh", x0, y0, x1, y1) + d[8:]
            elif cmd in (0x35, 0x36, 0x3C) and len(d) >= 4:
                d = struct.pack(">hh", *_flip(*struct.unpack_from(">hh", d))) + d[4:]
            elif cmd == 0x3D and colour and d and d[0] in LEGACY_COLOURS:
                d = bytes([LEGACY_COLOURS[d[0]]]) + d[1:]
            elif cmd in (0x37, 0x3E) and len(d) >= 7:
                x, y = _flip(*struct.unpack_from(">hh", d))
                rot = TEXT_ROT_UPRIGHT if d[4] == 0 else d[4]
                if cmd == 0x37 and colour and d[6] in LEGACY_COLOURS:
                    cmd, d = 0x3E, d[:6] + bytes([LEGACY_COLOURS[d[6]]]) + d[7:]
                d = struct.pack(">hhB", x, y, rot) + d[5:]
            else:
                out.append(raw)
                continue
        except struct.error:
            out.append(raw)
            continue
        out.append(encode_packet(cmd, d, qid))
    return b"".join(out)


class ActiveLookAdapter:
    """OpenBridge Adapter for ActiveLook / ENGO Eyewear.

    The push_* screens draw in logical coordinates (origin top-left); send() converts them to the native frame
    (to_native) unless native_frame is False."""

    def __init__(self, transport: Optional[Callable[[bytes], Any]] = None, model: str = "ENGO 3"):
        self.transport = transport
        self.model = model
        self.is_color = "3" in model
        self.tx_queue_depth = 0
        self.paused_by_flow_control = False
        self.last_gesture_time = 0.0
        self.active_abort_handler: Optional[Callable[[], Any]] = None
        self.status = "READY"
        self.native_frame = True

    def send(self, data: bytes) -> bool:
        """Send command bytes to glasses through transport (converted to the native frame, see to_native)."""
        if self.paused_by_flow_control:
            return False
        if self.transport:
            self.transport(to_native(data, self.is_color) if self.native_frame else data)
            self.tx_queue_depth += 1
            return True
        return False

    def handle_flow_control(self, status_byte: int) -> None:
        """Handle flow control byte from characteristic ...5CB9."""
        if status_byte == 0x01:   # Flow OK (<75% buffer)
            self.paused_by_flow_control = False
            self.tx_queue_depth = max(0, self.tx_queue_depth - 1)
        elif status_byte == 0x02: # Flow Pause (>=75% buffer)
            self.paused_by_flow_control = True

    def handle_gesture(self, gesture_byte: int) -> Dict[str, Any]:
        """Handle optical swipe gesture (0x01) from characteristic ...5CBB."""
        now = time.time()
        # Debounce 350ms
        if now - self.last_gesture_time < 0.35:
            return {"status": "DEBOUNCED", "action": None}
        self.last_gesture_time = now

        # If a two-phase abort is armed, trigger it immediately
        if self.active_abort_handler:
            handler = self.active_abort_handler
            self.active_abort_handler = None
            handler()
            self.push_receipt("EXECUTION ABORTED", "Routine cancelled via gesture", status="refused")
            return {"status": "ABORT_TRIGGERED", "action": "abort"}

        return {"status": "GESTURE_DETECTED", "action": "carousel_cycle"}

    def hold_flush(self, action: int) -> bool:
        """Graphic pipeline flush control: 0 = Hold, 1 = Flush."""
        return self.send(cmd_hold_flush(action))

    def set_config(self, name: str = "ALooK") -> bool:
        """Select persistent flash configuration profile."""
        return self.send(cmd_cfg_set(name))

    def save_layout(
        self,
        layout_id: int,
        x: int,
        y: int,
        width: int,
        height: int,
        fore_color: int = 15,
        back_color: int = 0,
        font: int = 1,
        text_valid: bool = True,
        text_x: int = 0,
        text_y: int = 0,
        sub_commands: bytes = b""
    ) -> bool:
        """Save persistent widget layout into flash."""
        return self.send(cmd_layout_save(
            layout_id=layout_id,
            x=x,
            y=y,
            width=width,
            height=height,
            fore_color=fore_color,
            back_color=back_color,
            font=font,
            text_valid=text_valid,
            text_x=text_x,
            text_y=text_y,
            sub_commands=sub_commands,
            is_color=self.is_color
        ))

    def save_page(self, page_id: int, slots: list[tuple[int, int, int]]) -> bool:
        """Save composite page layout into flash."""
        return self.send(cmd_page_save(page_id, slots))

    def display_page(self, page_id: int, texts: list[str]) -> bool:
        """Multicast update across all page layout slots in 1 BLE frame."""
        return self.send(cmd_page_display(page_id, texts))

    def push_receipt(self, title: str, detail: str, status: str = "ok") -> bool:
        """Feature F02: Heads-Up Action Receipt (ephemeral 3.5s optical verification badge)."""
        color_code = COLOR_GREEN if status == "ok" else (COLOR_RED if status == "refused" else COLOR_AMBER)
        cmds = bytearray()
        cmds += cmd_clear()
        if self.is_color:
            cmds += cmd_color(color_code)
        
        # Header banner
        header_text = f"[{'VERIFIED' if status == 'ok' else 'REFUSED'}] {title}"
        cmds += cmd_rectf(0, 0, 303, 28)
        cmds += cmd_text(4, 6, header_text, font=0, color_or_grey=0)
        
        # Detail body
        detail_color = color_code if self.is_color else 12
        cmds += cmd_text(4, 45, detail[:32], font=0, color_or_grey=detail_color)
        cmds += cmd_text(4, 220, ">> [WAVE] TO DISMISS", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        
        return self.send(bytes(cmds))

    def arm_two_phase_abort(self, routine_name: str, countdown_s: int, on_abort: Callable[[], Any]) -> bool:
        """Feature F04: Two-Phase Commit Safety Gate (Wave to Abort)."""
        self.active_abort_handler = on_abort
        cmds = bytearray()
        cmds += cmd_clear()
        if self.is_color:
            cmds += cmd_color(COLOR_AMBER)
        cmds += cmd_text(4, 30, f"STARTING: {routine_name[:20]}", font=1, color_or_grey=COLOR_AMBER if self.is_color else 14)
        cmds += cmd_text(4, 70, f"COUNTDOWN: {countdown_s}s", font=2, color_or_grey=COLOR_RED if self.is_color else 15)
        cmds += cmd_text(4, 220, ">> WAVE HAND TO ABORT NOW <<", font=0, color_or_grey=COLOR_CYAN if self.is_color else 10)
        cmds += cmd_gauge(0, 100)
        return self.send(bytes(cmds))

    def push_ambient_bar(self, wan: str = "OK", grid_kw: float = 1.4, locks_secured: bool = True, battery_pct: int = 88) -> bool:
        """Feature F03: Ambient Home Status Glance (<8% pixel fill factor)."""
        lock_str = "LOCK:ALL" if locks_secured else "UNLOCK:WARN"
        summary = f"[{grid_kw:.1f}kW] [{lock_str}] [WAN:{wan}] [BATT:{battery_pct}%]"
        cmds = bytearray()
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN if locks_secured else COLOR_RED)
        cmds += cmd_text(4, 4, summary[:38], font=0, color_or_grey=COLOR_CYAN if self.is_color else 10)
        return self.send(bytes(cmds))

    # ──────────────────────────────────────────────────────────────────────────
    # 6 "Watch-Impossible" Killer Features
    # ──────────────────────────────────────────────────────────────────────────

    def push_spatial_radar(self, devices: List[Dict[str, Any]]) -> bool:
        """Killer Feature 1: Gaze-Aligned Spatial Device Radar.
        Renders a polar radar centered at (152, 135) showing smart home devices
        with relative angles and distances matching the user's forward gaze direction.
        """
        cmds = bytearray()
        cmds += cmd_clear()
        
        # Header
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 4, "[SPATIAL PERIMETER RADAR]", font=0, color_or_grey=COLOR_CYAN if self.is_color else 12)
        cmds += cmd_text(250, 4, "⬆ GAZE", font=0, color_or_grey=COLOR_GREEN if self.is_color else 10)

        # Reticle & Range Rings (center = 152, 135)
        cx, cy = 152, 135
        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW if not self.is_color else 0x07) # subtle
        cmds += cmd_circ(cx, cy, 40)   # 5m range ring
        cmds += cmd_circ(cx, cy, 80)   # 10m range ring
        cmds += cmd_line(cx - 85, cy, cx + 85, cy) # horizon line
        cmds += cmd_line(cx, cy - 85, cx, cy + 85) # vertical gaze axis
        cmds += cmd_text(cx + 42, cy - 8, "5m", font=0, color_or_grey=6)
        cmds += cmd_text(cx + 82, cy - 8, "10m", font=0, color_or_grey=6)

        # Plot devices
        for dev in devices[:6]:  # max 6 to prevent cognitive clutter
            name = str(dev.get("name", "DEV"))[:5]
            dist_m = min(10.0, max(0.5, float(dev.get("dist_m", 3.0))))
            bearing_deg = float(dev.get("bearing_deg", 0.0))
            theta = math.radians(bearing_deg)
            
            # (0 deg = North/Gaze, 90 deg = Right, 180 = Behind, 270 = Left)
            radius_px = (dist_m / 10.0) * 80.0
            bx = int(cx + radius_px * math.sin(theta))
            by = int(cy - radius_px * math.cos(theta))
            bx = max(10, min(290, bx))
            by = max(20, min(230, by))

            state = dev.get("state", "ok")
            if state == "alert":
                col = COLOR_RED
            elif state in ("busy", "docking", "moving"):
                col = COLOR_AMBER
            else:
                col = COLOR_GREEN

            if self.is_color:
                cmds += cmd_color(col)
            cmds += cmd_circf(bx, by, 3)
            # Label near blip
            lbl = f"{name} {dist_m:.1f}m"
            cmds += cmd_text(bx + 4, by - 4, lbl[:10], font=0, color_or_grey=col if self.is_color else 14)

        # Footer
        cmds += cmd_text(4, 235, ">> [WAVE] CYCLE SENSORS", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_eyes_on_target_receipt(self, target_name: str, action: str, oracle_verified: bool, latency_ms: int, digest: str = "") -> bool:
        """Killer Feature 2: 'Eyes-on-Target' Action Verification Receipt.
        Overlays verified physical action readback directly while looking at the device.
        """
        cmds = bytearray()
        cmds += cmd_clear()
        
        status_color = COLOR_GREEN if oracle_verified else COLOR_RED
        if self.is_color:
            cmds += cmd_color(status_color)

        # Banner
        cmds += cmd_rectf(0, 0, 303, 26)
        hdr = "[IN-SITU VERIFIED ✓]" if oracle_verified else "[ACTION REFUSED ✗]"
        cmds += cmd_text(4, 6, hdr, font=0, color_or_grey=0)

        # Target & Action
        cmds += cmd_text(4, 40, f"TARGET : {target_name.upper()[:22]}", font=1, color_or_grey=COLOR_YELLOW if self.is_color else 14)
        cmds += cmd_text(4, 68, f"ACTION : {action[:25]}", font=0, color_or_grey=status_color if self.is_color else 15)

        # Independent Oracle Proof
        oracle_msg = f"Oracle : Read-back in {latency_ms}ms"
        cmds += cmd_text(4, 100, oracle_msg, font=0, color_or_grey=COLOR_CYAN if self.is_color else 12)
        if digest:
            cmds += cmd_text(4, 120, f"Digest : {digest[:24]}", font=0, color_or_grey=8)

        # Visual indicator
        cmds += cmd_rect(0, 32, 303, 150)
        cmds += cmd_text(4, 230, ">> [WAVE] DISMISS (AUTO 3.5s)", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_two_phase_countdown(self, routine_name: str, seconds_remaining: int, max_seconds: int = 5) -> bool:
        """Killer Feature 3: Two-Phase Commit Touchless Wave-to-Abort Gate.
        Displays an active countdown where a single hand wave reflexively aborts execution.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Dynamic color transition
        if seconds_remaining > 2:
            phase_color = COLOR_AMBER
        else:
            phase_color = COLOR_RED

        if self.is_color:
            cmds += cmd_color(phase_color)

        cmds += cmd_rectf(0, 0, 303, 26)
        cmds += cmd_text(4, 6, "[TRANSACTION SAFETY GATE]", font=0, color_or_grey=0)

        # Routine label
        cmds += cmd_text(4, 38, f"PENDING : {routine_name[:20]}", font=1, color_or_grey=phase_color if self.is_color else 14)
        
        # Giant Countdown Digits (centered)
        countdown_str = f"ABORT IN: {seconds_remaining}s"
        cmds += cmd_text(50, 75, countdown_str, font=2, color_or_grey=phase_color if self.is_color else 15)

        # Progress bar
        pct = max(0, min(100, int((seconds_remaining / float(max_seconds)) * 100)))
        cmds += cmd_gauge(0, pct)

        # Big Wave Prompt
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_rect(0, 210, 303, 250)
        cmds += cmd_text(16, 222, ">>> WAVE HAND TO ABORT NOW <<<", font=1, color_or_grey=COLOR_CYAN if self.is_color else 15)
        return self.send(bytes(cmds))

    def push_peripheral_telemetry(self, grid_watts: int, wan_mbps: int, ping_ms: int, alert: Optional[str] = None) -> bool:
        """Killer Feature 4: Silent Peripheral Telemetry Stream.
        Draws an ultra-low pixel fill (<3% pixels) telemetry row sitting silently in periphery.
        """
        cmds = bytearray()
        # Wipe only top status row (y: 0-28) to preserve screen: erase in black, not in the active colour
        cmds += cmd_color(COLOR_OFF) if self.is_color else cmd_grey(0)
        cmds += cmd_rectf(0, 0, 303, 26)
        if not self.is_color:
            cmds += cmd_grey(15)

        is_alert = alert is not None or grid_watts > 6000 or ping_ms > 100
        if is_alert:
            col = COLOR_RED
        elif grid_watts > 3500:
            col = COLOR_AMBER
        else:
            col = COLOR_GREEN

        if self.is_color:
            cmds += cmd_color(col)

        if alert:
            telemetry_str = f"! {alert[:18]} ! [{grid_watts}W] [{ping_ms}ms]"
        else:
            telemetry_str = f"GRID:{grid_watts}W | FIBER:{wan_mbps}M ({ping_ms}ms)"

        cmds += cmd_text(4, 6, telemetry_str[:38], font=0, color_or_grey=col if self.is_color else 15)
        return self.send(bytes(cmds))

    def push_workflow_prompter(self, step_idx: int, total_steps: int, title: str, instruction: str, timer_s: Optional[int] = None) -> bool:
        """Killer Feature 5: Hands-Free Workshop / Culinary Prompter.
        Keeps hands on tools/food while advancing steps via optical wave gesture.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header with step gauge
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        step_hdr = f"[STEP {step_idx}/{total_steps}]"
        cmds += cmd_text(4, 5, step_hdr, font=0, color_or_grey=COLOR_CYAN if self.is_color else 12)
        
        if timer_s is not None:
            mins, secs = divmod(max(0, timer_s), 60)
            timer_str = f"⏱ {mins:02d}:{secs:02d}"
            cmds += cmd_text(220, 5, timer_str, font=0, color_or_grey=COLOR_AMBER if self.is_color else 14)

        # Progress bar
        pct = max(0, min(100, int((step_idx / float(total_steps)) * 100)))
        cmds += cmd_gauge(0, pct)

        # Step Title
        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        cmds += cmd_text(4, 35, title[:26], font=1, color_or_grey=COLOR_YELLOW if self.is_color else 15)

        # Instruction body (multi-line wrapping)
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN)
        line1 = instruction[:30]
        line2 = instruction[30:60]
        line3 = instruction[60:90]
        cmds += cmd_text(4, 65, line1, font=0, color_or_grey=14)
        if line2:
            cmds += cmd_text(4, 85, line2, font=0, color_or_grey=14)
        if line3:
            cmds += cmd_text(4, 105, line3, font=0, color_or_grey=14)

        # Gesture prompts
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 225, ">> [WAVE] NEXT STEP | [DOUBLE-TAP] BACK", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_live_subtitles(self, speaker: str, text: str, is_urgent: bool = False) -> bool:
        """Killer Feature 6: Intercom / Doorbell Live Speech-to-Text Subtitles.
        Displays real-time rolling 2-line subtitles from home audio intercom directly in visual field.
        """
        cmds = bytearray()
        # Wipe only subtitle box at bottom of screen to black (y: 165 to 255)
        if self.is_color:
            cmds += cmd_color(0)
        else:
            cmds += cmd_grey(0)
        cmds += cmd_rectf(0, 165, 303, 255)

        border_col = COLOR_RED if is_urgent else COLOR_CYAN
        if self.is_color:
            cmds += cmd_color(border_col)
        cmds += cmd_rect(0, 166, 303, 254)

        # Speaker tag
        spk_tag = f"[{speaker.upper()[:16]}]:"
        cmds += cmd_text(6, 172, spk_tag, font=0, color_or_grey=border_col if self.is_color else 15)

        # Text lines
        clean_text = text.strip()
        line1 = clean_text[:32]
        line2 = clean_text[32:64]
        cmds += cmd_text(6, 192, line1, font=0, color_or_grey=15)
        if line2:
            cmds += cmd_text(6, 212, line2, font=0, color_or_grey=15)

        cmds += cmd_text(6, 235, ">> [WAVE] DISMISS", font=0, color_or_grey=8)
        return self.send(bytes(cmds))

    def push_compass_wayfinder(
        self,
        heading_deg: int,
        target_bearing_deg: int,
        target_dist_m: float,
        target_name: str = "WAYPOINT"
    ) -> bool:
        """Killer Feature 7: Augmented Reality Outdoor Compass & Wayfinder Ribbon.
        Projects moving 360° heading tape, relative bearing chevron, and distance to target.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Top compass tape line
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_line(0, 24, 303, 24)

        # Cardinal labels
        heading = heading_deg % 360
        cardinals = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        card_idx = int((heading + 22.5) / 45.0) % 8
        card_label = cardinals[card_idx]
        compass_str = f"[{heading:03d}° · {card_label} · {target_name.upper()[:12]}]"
        cmds += cmd_text(4, 5, compass_str, font=0, color_or_grey=COLOR_CYAN if self.is_color else 15)

        # Calculate relative bearing (-180 to +180)
        rel_bearing = (target_bearing_deg - heading + 180) % 360 - 180

        # Center target indicator & direction chevron
        if abs(rel_bearing) <= 15:
            nav_msg = "▲ STRAIGHT AHEAD (ON TARGET)"
            nav_col = COLOR_GREEN
        elif rel_bearing > 15:
            nav_msg = f"▶ TURN RIGHT (+{rel_bearing}°)"
            nav_col = COLOR_AMBER
        else:
            nav_msg = f"◀ TURN LEFT ({rel_bearing}°)"
            nav_col = COLOR_AMBER

        if self.is_color:
            cmds += cmd_color(nav_col)
        cmds += cmd_text(4, 45, nav_msg, font=1, color_or_grey=nav_col if self.is_color else 15)

        # Distance formatting
        if target_dist_m >= 1000:
            dist_str = f"{target_dist_m / 1000.0:.2f} KM"
        else:
            dist_str = f"{int(target_dist_m)} M"

        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        cmds += cmd_text(4, 80, f"DISTANCE : {dist_str}", font=2, color_or_grey=COLOR_YELLOW if self.is_color else 15)

        # Vector line towards target
        center_x = 152
        target_x = max(10, min(293, int(center_x + (rel_bearing / 90.0) * 120)))
        cmds += cmd_line(center_x, 150, target_x, 120)
        cmds += cmd_circ(target_x, 120, 6)

        # Gauge representing arrival progress (max 1000m scale)
        arrival_pct = max(0, min(100, int((1.0 - min(target_dist_m, 1000.0) / 1000.0) * 100)))
        cmds += cmd_gauge(0, arrival_pct)

        cmds += cmd_text(4, 230, ">> [WAVE] CLOSE WAYFINDER", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_smart_home_security_alert(
        self,
        threat_type: str,
        source_ip: str,
        mac_vendor: str,
        target_service: str,
        action_hint: str = "ISOLATE ON FREEBOX"
    ) -> bool:
        """Killer Feature 8: Real-Time Network Intrusion & Threat Shield HUD.
        Instantly alerts the user of rogue scans or unauthorized devices with 1-wave isolation gate.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Alert banner
        if self.is_color:
            cmds += cmd_color(COLOR_RED)
        cmds += cmd_line(0, 26, 303, 26)
        cmds += cmd_rect(0, 0, 303, 26)
        cmds += cmd_text(4, 6, "🛡️ INTRUSION SHIELD ALERT", font=0, color_or_grey=COLOR_RED if self.is_color else 15)

        # Threat details
        if self.is_color:
            cmds += cmd_color(COLOR_AMBER)
        cmds += cmd_text(4, 42, f"THREAT : {threat_type[:24]}", font=1, color_or_grey=COLOR_AMBER if self.is_color else 15)

        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        cmds += cmd_text(4, 75, f"IP Source  : {source_ip}", font=0, color_or_grey=14)
        cmds += cmd_text(4, 98, f"Constructeur: {mac_vendor[:20]}", font=0, color_or_grey=14)
        cmds += cmd_text(4, 121, f"Target     : {target_service[:20]}", font=0, color_or_grey=14)

        # Action prompt
        if self.is_color:
            cmds += cmd_color(COLOR_RED)
        cmds += cmd_rect(0, 215, 303, 250)
        cmds += cmd_text(6, 226, f">> [WAVE] {action_hint.upper()[:26]}", font=0, color_or_grey=COLOR_RED if self.is_color else 15)
        return self.send(bytes(cmds))

    def push_bio_adaptive_pacer(
        self,
        target_spm: int,
        current_spm: int,
        hr_bpm: int,
        hr_zone: int,
        advice: str = "MAINTAIN CADENCE"
    ) -> bool:
        """Killer Feature 9: Bio-Adaptive Cadence Metronome & Cardiac Zone Guardian.
        Collimated pacing reticle keeping the runner at peak efficiency with zero glance latency.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Zone color
        if hr_zone >= 5:
            hr_col = COLOR_RED
            zone_desc = "ZONE 5: MAXIMAL"
        elif hr_zone == 4:
            hr_col = COLOR_AMBER
            zone_desc = "ZONE 4: LACTATE THRESHOLD"
        elif hr_zone == 3:
            hr_col = COLOR_GREEN
            zone_desc = "ZONE 3: AEROBIC"
        else:
            hr_col = COLOR_CYAN
            zone_desc = f"ZONE {hr_zone}: RECOVERY"

        # Header with Heart Rate
        if self.is_color:
            cmds += cmd_color(hr_col)
        cmds += cmd_line(0, 26, 303, 26)
        cmds += cmd_text(4, 6, f"❤ {hr_bpm} BPM  [{zone_desc}]", font=0, color_or_grey=hr_col if self.is_color else 15)

        # Cadence Comparison
        spm_delta = current_spm - target_spm
        if abs(spm_delta) <= 2:
            cad_msg = "PARFAIT (CADENCE OPTIMALE)"
            cad_col = COLOR_GREEN
        elif spm_delta < -2:
            cad_msg = f"▲ SPEED UP (+{abs(spm_delta)} SPM)"
            cad_col = COLOR_AMBER
        else:
            cad_msg = f"▼ SLOW DOWN (-{spm_delta} SPM)"
            cad_col = COLOR_AMBER

        if self.is_color:
            cmds += cmd_color(cad_col)
        cmds += cmd_text(4, 42, f"CADENCE: {current_spm} SPM", font=2, color_or_grey=cad_col if self.is_color else 15)
        cmds += cmd_text(4, 85, f"TARGET: {target_spm} SPM | {cad_msg}", font=0, color_or_grey=14)

        # Visual metronome pacing gauge (centered at 50%)
        gauge_val = max(0, min(100, 50 + spm_delta * 5))
        cmds += cmd_gauge(0, gauge_val)

        # Advice
        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        cmds += cmd_text(4, 125, f"TIP: {advice[:26]}", font=1, color_or_grey=COLOR_YELLOW if self.is_color else 15)

        cmds += cmd_text(4, 230, ">> [WAVE] HIDE CADENCE", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_media_remote_hud(
        self,
        media_title: str,
        artist_or_source: str,
        volume_pct: int,
        is_playing: bool,
        progress_s: int,
        total_s: int
    ) -> bool:
        """Killer Feature 10: Touchless Glance-to-Control Media Remote.
        Control living room TV, PC audio or Spotify directly from the eyewear HUD.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Top banner
        status_icon = "▶" if is_playing else "⏸"
        status_text = "PLAYING" if is_playing else "PAUSE"
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN if is_playing else COLOR_AMBER)
        cmds += cmd_line(0, 26, 303, 26)
        cmds += cmd_text(4, 6, f"{status_icon} CONTROLE MEDIA : {status_text}", font=0, color_or_grey=0 if not self.is_color else (COLOR_GREEN if is_playing else COLOR_AMBER))

        # Track and Source
        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        cmds += cmd_text(4, 42, media_title[:24], font=1, color_or_grey=COLOR_YELLOW if self.is_color else 15)
        
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 75, f"Source : {artist_or_source[:26]}", font=0, color_or_grey=14)

        # Time Progress
        m_cur, s_cur = divmod(max(0, progress_s), 60)
        m_tot, s_tot = divmod(max(0, total_s), 60)
        time_str = f"{m_cur:02d}:{s_cur:02d} / {m_tot:02d}:{s_tot:02d}"
        cmds += cmd_text(4, 105, f"Progression : {time_str}", font=0, color_or_grey=14)

        # Track Progress Gauge (Gauge 0)
        pct = max(0, min(100, int((progress_s / float(max(1, total_s))) * 100)))
        cmds += cmd_gauge(0, pct)

        # Volume status (Gauge 1)
        cmds += cmd_text(4, 145, f"Room volume : {volume_pct}%", font=0, color_or_grey=14)
        cmds += cmd_gauge(1, max(0, min(100, volume_pct)))

        # Controls Hint
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 230, ">> [WAVE] PLAY/PAUSE | [TAP] VOL+", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_silent_morse_input(self, buffer_str: str, current_morse: str = "", suggestion: str = "") -> bool:
        """Killer Feature 11: Silent Temple-Tap Morse & Stealth Input Engine.
        Enables invisible, zero-voice text input and home automation control via temple micro-taps.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_line(0, 26, 303, 26)
        cmds += cmd_text(4, 6, "⌨️ SILENT TEMPLE INPUT", font=0, color_or_grey=COLOR_CYAN if self.is_color else 15)

        # Committed text buffer
        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        display_buf = buffer_str[-22:] if len(buffer_str) > 22 else buffer_str
        cmds += cmd_text(4, 42, f"TEXTE: {display_buf}_", font=1, color_or_grey=COLOR_YELLOW if self.is_color else 15)

        # Current Morse Symbol & Pending Character
        morse_disp = current_morse.replace(".", "·").replace("-", "—")
        char_preview = MORSE_MAP.get(current_morse, "")
        symbol_str = f"SYMBOLE: [ {morse_disp} ] ➔ {char_preview}" if current_morse else "SYMBOL: [ WAITING FOR TAP ]"

        if self.is_color:
            cmds += cmd_color(COLOR_GREEN if char_preview else COLOR_AMBER)
        cmds += cmd_text(4, 75, symbol_str, font=1, color_or_grey=COLOR_GREEN if char_preview and self.is_color else 14)

        # Autocomplete or Action Suggestion
        if suggestion:
            if self.is_color:
                cmds += cmd_color(COLOR_CYAN)
            cmds += cmd_text(4, 110, f"SUGGESTION: {suggestion[:22]}", font=0, color_or_grey=14)

        # Cheat-sheet helper
        cmds += cmd_text(4, 150, "A:·- B:-··· C:-·-· E:· T:- O:---", font=0, color_or_grey=8)
        cmds += cmd_text(4, 175, "TAP = POINT(·) | LONG = TRAIT(—)", font=0, color_or_grey=8)

        # Controls hint
        cmds += cmd_text(4, 230, ">> [DOUBLE-TAP] ENVOYER | [WAVE] RETOUR", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_speech_teleprompter(
        self,
        current_line: str,
        next_line: str,
        wpm: int,
        is_rushing: bool,
        elapsed_s: int,
        total_s: int
    ) -> bool:
        """Killer Feature 12: Speech-Synced AR Teleprompter & Gaze Pacing Assistant.
        Advances notes automatically in HUD as user speaks, tracking cadence (WPM) without glance diversion.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Cadence status & WPM Indicator
        if is_rushing or wpm > 165:
            cad_col = COLOR_AMBER
            cad_status = f"⚠️ {wpm} WPM (TOO FAST)"
        elif wpm < 110:
            cad_col = COLOR_CYAN
            cad_status = f"ℹ {wpm} WPM (SLOW PACE)"
        else:
            cad_col = COLOR_GREEN
            cad_status = f"✓ {wpm} WPM (OPTIMAL PACE)"

        # Header with timing
        m_el, s_el = divmod(max(0, elapsed_s), 60)
        m_tot, s_tot = divmod(max(0, total_s), 60)
        time_hdr = f"{cad_status}  [{m_el:02d}:{s_el:02d}/{m_tot:02d}:{s_tot:02d}]"

        if self.is_color:
            cmds += cmd_color(cad_col)
        cmds += cmd_line(0, 24, 303, 24)
        cmds += cmd_text(4, 5, time_hdr[:36], font=0, color_or_grey=cad_col if self.is_color else 15)

        # Elapsed talk gauge (0-100%)
        time_pct = max(0, min(100, int((elapsed_s / float(max(1, total_s))) * 100)))
        cmds += cmd_gauge(0, time_pct)

        # Current line (High contrast large font)
        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        cmds += cmd_text(4, 42, "▶ " + current_line[:26], font=1, color_or_grey=COLOR_YELLOW if self.is_color else 15)
        if len(current_line) > 26:
            cmds += cmd_text(16, 68, current_line[26:54], font=1, color_or_grey=COLOR_YELLOW if self.is_color else 15)

        # Next line preview (Dimmed peripheral font)
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 115, "NEXT :", font=0, color_or_grey=8)
        cmds += cmd_text(4, 135, next_line[:32], font=0, color_or_grey=10)
        if len(next_line) > 32:
            cmds += cmd_text(4, 155, next_line[32:64], font=0, color_or_grey=10)

        cmds += cmd_text(4, 230, ">> [WAVE] NEXT LINE | [TAP] PAUSE", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_spatial_energy_heatmap(
        self,
        current_room: str,
        room_watts: int,
        total_watts: int,
        vampire_devices: list[dict]
    ) -> bool:
        """Killer Feature 13: Spatial Home Energy Ghost Overlay & Vampire Drain Eliminator.
        Projects active room energy consumption based on beacon location with 1-wave smart plug toggle.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header: Room & Instant Watts
        if self.is_color:
            cmds += cmd_color(COLOR_AMBER if room_watts > 1000 else COLOR_GREEN)
        cmds += cmd_line(0, 26, 303, 26)
        hdr_str = f"🏠 [{current_room.upper()[:10]}] : {room_watts} W (TOTAL: {total_watts}W)"
        cmds += cmd_text(4, 6, hdr_str[:36], font=0, color_or_grey=0 if not self.is_color else (COLOR_AMBER if room_watts > 1000 else COLOR_GREEN))

        # Room consumption gauge (relative to 3kW house budget)
        pct = max(0, min(100, int((room_watts / 3000.0) * 100)))
        cmds += cmd_gauge(0, pct)

        # Breakdown or Vampire Alert
        if vampire_devices:
            vamp = vampire_devices[0]
            v_name = vamp.get("name", "Inconnu")
            v_watts = vamp.get("watts", 45)
            v_idle = vamp.get("idle_hours", 2)

            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rect(0, 42, 303, 115)
            cmds += cmd_text(4, 48, "⚠️ PHANTOM STANDBY DETECTED!", font=1, color_or_grey=COLOR_RED if self.is_color else 15)
            cmds += cmd_text(4, 75, f"Device : {v_name[:20]} ({v_watts} W)", font=0, color_or_grey=14)
            cmds += cmd_text(4, 95, f"Idle for : {v_idle} hours", font=0, color_or_grey=14)

            # Wave action to cut plug
            cmds += cmd_text(4, 215, f">> [WAVE] ASK TO SWITCH OFF : {v_name[:14].upper()}", font=0, color_or_grey=COLOR_RED if self.is_color else 15)
        else:
            if self.is_color:
                cmds += cmd_color(COLOR_GREEN)
            cmds += cmd_text(4, 55, "ALL DEVICES IN OPTIMAL STANDBY", font=1, color_or_grey=COLOR_GREEN if self.is_color else 15)
            cmds += cmd_text(4, 85, "Aucune deperdition electrique detectee", font=0, color_or_grey=14)
            cmds += cmd_text(4, 215, ">> [WAVE] RETOUR AMBIANT", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)

        cmds += cmd_text(4, 235, "OpenBridge Eco-Sense • Linky + Tuya", font=0, color_or_grey=6)
        return self.send(bytes(cmds))

    def push_arcade_game_frame(
        self,
        player_y: int,
        obstacle_x: int,
        score: int,
        game_over: bool = False
    ) -> bool:
        """Killer Feature 14: MicroOLED Vector Runner Arcade Mini-Game.
        Ultra-low-power vector game playable via IR wave gestures while waiting.
        """
        cmds = bytearray()
        # Hold graphic pipeline for atomic single-frame swap
        cmds += cmd_hold_flush(0)
        cmds += cmd_clear()

        # Score & Header
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 6, f"ARCADE RUNNER | SCORE: {score}", font=0, color_or_grey=COLOR_CYAN if self.is_color else 15)
        cmds += cmd_line(0, 22, 303, 22)

        # Ground line (y = 190)
        ground_y = 190
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN)
        cmds += cmd_line(0, ground_y, 303, ground_y)

        # Player: circle at x=35, y=player_y (r=8)
        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        cmds += cmd_circf(35, max(30, min(ground_y - 8, player_y)), 8)

        # Obstacle: filled rectangle at x=obstacle_x
        if 0 <= obstacle_x <= 303:
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rectf(obstacle_x, ground_y - 22, obstacle_x + 12, ground_y)

        # Game Over Banner or Controls Hint
        if game_over:
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rect(40, 80, 264, 130)
            cmds += cmd_text(75, 95, "GAME OVER !", font=2, color_or_grey=COLOR_RED if self.is_color else 15)
            cmds += cmd_text(4, 225, ">> [WAVE] REJOUER", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)
        else:
            cmds += cmd_text(4, 225, ">> [WAVE] SAUTER L'OBSTACLE", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)

        # Flush buffer to screen
        cmds += cmd_hold_flush(1)
        return self.send(bytes(cmds))

    def push_collision_sentry(
        self,
        hazard_side: str,
        speed_kmh: int,
        dist_m: float,
        ttc_s: float
    ) -> bool:
        """Killer Feature 15: Peripheral Collision Sentry & Blind-Spot Radar.
        High-contrast peripheral reticle warning cyclists/pedestrians of approaching vehicles.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header Alert Banner
        if self.is_color:
            cmds += cmd_color(COLOR_RED)
        cmds += cmd_rectf(0, 0, 303, 24)
        hdr = f"⚠️ SENTRY ALERT [TTC {ttc_s:.1f}s]"
        cmds += cmd_text(4, 5, hdr[:32], font=0, color_or_grey=0)

        # Peripheral Side Visual Brackets
        side = hazard_side.lower()
        if self.is_color:
            cmds += cmd_color(COLOR_RED)

        if side == "left":
            # Left edge high-intensity peripheral bar & arrow
            cmds += cmd_rectf(0, 28, 14, 215)
            cmds += cmd_line(14, 120, 35, 120)
            cmds += cmd_line(35, 120, 25, 110)
            cmds += cmd_line(35, 120, 25, 130)
        elif side == "right":
            # Right edge high-intensity peripheral bar & arrow
            cmds += cmd_rectf(289, 28, 303, 215)
            cmds += cmd_line(289, 120, 268, 120)
            cmds += cmd_line(268, 120, 278, 110)
            cmds += cmd_line(268, 120, 278, 130)
        else:
            # Rear / Front alert - bottom edge bar
            cmds += cmd_rectf(40, 205, 263, 218)

        # Center Telemetry Box
        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        cmds += cmd_rect(24, 40, 279, 155)
        cmds += cmd_text(30, 48, f"VEHICULE APROCHANT : {hazard_side.upper()}", font=1, color_or_grey=COLOR_RED if self.is_color else 15)
        cmds += cmd_text(30, 78, f"Distance : {dist_m:.1f} m  |  Speed : {speed_kmh} km/h", font=0, color_or_grey=14)
        cmds += cmd_text(30, 98, f"Estimated impact in : {ttc_s:.1f} seconds", font=0, color_or_grey=COLOR_RED if self.is_color else 14)

        # Proximity Gauge (0-100%, closer = higher)
        pct = max(0, min(100, int((1.0 - min(50.0, dist_m) / 50.0) * 100)))
        cmds += cmd_gauge(0, pct)

        # Footer
        cmds += cmd_text(4, 230, ">> [WAVE] ACQUITTER SENTRY", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_executive_briefing_glance(
        self,
        contact_name: str,
        role_title: str,
        bullet_points: List[str],
        sentiment_hint: str = "VIP"
    ) -> bool:
        """Killer Feature 16: Executive Dossier & Meeting Briefing Glance.
        Subtle micro-dossier providing key meeting talking points in private peripheral vision.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header: Name, Role, Badge
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_line(0, 26, 303, 26)
        hdr = f"👤 {contact_name.upper()[:16]} [{sentiment_hint[:6]}]"
        cmds += cmd_text(4, 6, hdr[:36], font=0, color_or_grey=COLOR_CYAN if self.is_color else 15)

        # Subtitle: Role & Organization
        cmds += cmd_text(4, 32, f"Titre : {role_title[:32]}", font=0, color_or_grey=COLOR_YELLOW if self.is_color else 12)

        # Frame for talking points
        if self.is_color:
            cmds += cmd_color(0x07) # subtle blue/gray
        cmds += cmd_rect(0, 48, 303, 215)

        # Talking Points (up to 3 bullets)
        for idx, pt in enumerate(bullet_points[:3]):
            y = 56 + idx * 48
            clean_pt = pt.strip()
            cmds += cmd_text(6, y, f"• {clean_pt[:28]}", font=0, color_or_grey=15)
            if len(clean_pt) > 28:
                cmds += cmd_text(16, y + 18, f"  {clean_pt[28:56]}", font=0, color_or_grey=12)

        # Footer
        cmds += cmd_text(4, 232, ">> [WAVE] NEXT BRIEF / HIDE", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_biofeedback_stress_guardian(
        self,
        stress_score: int,
        hrv_ms: int,
        breath_phase: str,
        phase_timer_s: int
    ) -> bool:
        """Killer Feature 17: Biometric Stress Guardian & Box Breathing Pacer.
        Paces cardiac coherence & box breathing with an expanding/contracting vector reticle.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header: Stress index & HRV
        col_stress = COLOR_RED if stress_score > 70 else (COLOR_AMBER if stress_score > 40 else COLOR_GREEN)
        if self.is_color:
            cmds += cmd_color(col_stress)
        cmds += cmd_text(4, 6, f"STRESS: {stress_score}/100", font=0, color_or_grey=col_stress if self.is_color else 15)
        cmds += cmd_text(205, 6, f"HRV: {hrv_ms}ms", font=0, color_or_grey=COLOR_CYAN if self.is_color else 12)
        cmds += cmd_line(0, 24, 303, 24)

        # Stress level gauge
        cmds += cmd_gauge(0, stress_score)

        # Circular Pacer Center
        cx, cy = 152, 115
        phase_up = breath_phase.upper()
        
        if "INSP" in phase_up:
            phase_label = "BREATHE IN"
            radius = 18 + int(max(1, min(4, phase_timer_s)) * 10)  # 28 to 58
            ring_col = COLOR_CYAN
        elif "HOLD" in phase_up or "BLOQ" in phase_up:
            phase_label = "MAINTENIR"
            radius = 58
            ring_col = COLOR_AMBER
        elif "EXP" in phase_up:
            phase_label = "BREATHE OUT"
            radius = max(18, 58 - int(max(1, min(4, phase_timer_s)) * 10))
            ring_col = COLOR_GREEN
        else: # REST / PAUSE
            phase_label = "PAUSE VUIDE"
            radius = 18
            ring_col = COLOR_CYAN

        # Target boundary circle (58px)
        if self.is_color:
            cmds += cmd_color(0x07)
        cmds += cmd_circ(cx, cy, 58)

        # Dynamic breathing reticle
        if self.is_color:
            cmds += cmd_color(ring_col)
        cmds += cmd_circ(cx, cy, radius)
        cmds += cmd_circf(cx, cy, 3)

        # Phase label & timer under reticle
        cmds += cmd_text(cx - 45, cy + 64, f"{phase_label} ({phase_timer_s}s)", font=1, color_or_grey=ring_col if self.is_color else 15)

        # Footer
        cmds += cmd_text(4, 232, ">> [WAVE] STOP HEART COHERENCE", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_diy_ar_stud_level(
        self,
        pitch_deg: float,
        roll_deg: float,
        is_level: bool,
        detected_hazard: Optional[str] = None
    ) -> bool:
        """Killer Feature 18: AR Digital Inclinometer & Stud/Pipe Wireframe Scanner.
        Precision heads-up bubble level and in-wall hazard detector for hands-free DIY work.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN if is_level else COLOR_YELLOW)
        cmds += cmd_text(4, 6, "AR SPIRIT LEVEL & WALL SCANNER", font=0, color_or_grey=COLOR_GREEN if is_level else 15)
        cmds += cmd_text(4, 26, f"PITCH: {pitch_deg:+.1f}° | ROLL: {roll_deg:+.1f}°", font=0, color_or_grey=12)
        cmds += cmd_line(0, 42, 303, 42)

        cx, cy = 152, 115

        # Crosshairs at center
        if self.is_color:
            cmds += cmd_color(0x07)
        cmds += cmd_line(cx - 12, cy, cx + 12, cy)
        cmds += cmd_line(cx, cy - 12, cx, cy + 12)
        cmds += cmd_circ(cx, cy, 26)

        # Artificial horizon / Tilt bar
        if is_level or abs(roll_deg) < 0.5:
            if self.is_color:
                cmds += cmd_color(COLOR_GREEN)
            cmds += cmd_line(cx - 75, cy, cx + 75, cy)
            cmds += cmd_rect(cx - 48, cy - 10, cx + 48, cy + 10)
            cmds += cmd_text(cx - 42, cy - 6, "0.0° LOCKED ✓", font=0, color_or_grey=COLOR_GREEN if self.is_color else 15)
        else:
            if self.is_color:
                cmds += cmd_color(COLOR_AMBER)
            rad = math.radians(roll_deg)
            dx = int(65 * math.cos(rad))
            dy = int(65 * math.sin(rad))
            pitch_off = int(max(-25, min(25, pitch_deg * 2.0)))
            cmds += cmd_line(cx - dx, cy + pitch_off - dy, cx + dx, cy + pitch_off + dy)
            cmds += cmd_circf(cx + int(roll_deg * 2), cy + pitch_off, 4)

        # In-Wall Stud & Pipe Hazard Detection Box
        if detected_hazard:
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rect(10, 160, 293, 215)
            cmds += cmd_text(16, 168, f"⚡ DANGER : {detected_hazard.upper()[:24]}", font=1, color_or_grey=COLOR_RED if self.is_color else 15)
            cmds += cmd_text(16, 194, "⚠️ DO NOT DRILL ALONG THIS LINE!", font=0, color_or_grey=COLOR_RED if self.is_color else 14)
        else:
            if self.is_color:
                cmds += cmd_color(COLOR_GREEN)
            cmds += cmd_text(30, 180, "Wall scan : clear (no cables or pipes)", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)

        # Footer
        cmds += cmd_text(4, 232, ">> [WAVE] TARE ZERO RELATIF", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_first_responder_triage(
        self,
        mode: str = "cpr",
        bpm: int = 110,
        compression_count: int = 22,
        ccf_pct: int = 86,
        cycle_s: int = 42,
        triage_level: Optional[str] = None,
        step_prompt: Optional[str] = None
    ) -> bool:
        """Killer Feature 19: Emergency First Responder CPR & START Triage HUD.
        Hands-free 100-120 BPM CPR visual pacer & mass casualty triage protocol without looking down.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        if mode == "triage" or triage_level:
            # START Triage Mode
            level = (triage_level or "IMMEDIATE").upper()
            if "IMM" in level or "RED" in level:
                col = COLOR_RED
                badge = "[ ! IMMEDIATE / RED ! ]"
            elif "DEL" in level or "YEL" in level:
                col = COLOR_AMBER
                badge = "[ || DELAYED / YELLOW || ]"
            elif "MIN" in level or "GRN" in level:
                col = COLOR_GREEN
                badge = "[ ✓ MINOR / GREEN ]"
            else:
                col = COLOR_WHITE
                badge = "[ † EXPECTANT / BLACK ]"

            if self.is_color:
                cmds += cmd_color(col)
            cmds += cmd_text(4, 6, "[START TRIAGE] CASUALTY ASSESS", font=0, color_or_grey=col if self.is_color else 15)
            cmds += cmd_line(0, 24, 303, 24)

            # Triage Priority Box
            cmds += cmd_rect(10, 40, 293, 85)
            cmds += cmd_text(24, 54, badge, font=1, color_or_grey=col if self.is_color else 15)

            # Diagnostic Step & Question
            prompt_str = step_prompt or "RESPIRATIONS: >30 BPM OU ABSENTES"
            cmds += cmd_text(12, 105, f"Step : {prompt_str[:28]}", font=0, color_or_grey=14)
            cmds += cmd_text(12, 128, "Protocole : Degager voies / Tourniquet", font=0, color_or_grey=12)

            # Total tally
            cmds += cmd_text(12, 160, "MCI triage : 2 RED | 4 YELLOW | 9 GREEN", font=0, color_or_grey=8)
            cmds += cmd_text(4, 232, ">> [WAVE] NEXT RPM STEP / CONFIRM", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)

        else:
            # CPR Visual Metronome Mode (100-120 BPM, 50% duty cycle)
            if self.is_color:
                cmds += cmd_color(COLOR_GREEN if ccf_pct >= 80 else COLOR_AMBER)
            cmds += cmd_text(4, 6, "[MED-HUD: CPR PACER]", font=0, color_or_grey=COLOR_CYAN if self.is_color else 15)
            cmds += cmd_text(220, 6, f"T+{cycle_s:02d}s", font=0, color_or_grey=12)
            cmds += cmd_line(0, 24, 303, 24)

            # Central cadence & stroke count
            cmds += cmd_text(85, 42, f"{bpm} BPM", font=2, color_or_grey=COLOR_GREEN if self.is_color else 15)
            cmds += cmd_text(70, 80, f"COMPRESSION {compression_count}/30", font=0, color_or_grey=14)

            # Recoil & Compression Indicator Circle (center = 152, 115)
            cx, cy = 152, 115
            if self.is_color:
                cmds += cmd_color(COLOR_YELLOW)
            cmds += cmd_circ(cx, cy, 22)
            cmds += cmd_circf(cx, cy, 7)

            # Chest Compression Fraction (CCF) Gauge
            cmds += cmd_text(12, 155, f"CCF: {ccf_pct}% (OBJECTIF >80%)", font=0, color_or_grey=COLOR_GREEN if ccf_pct >= 80 else COLOR_AMBER)
            cmds += cmd_gauge(0, ccf_pct)

            cmds += cmd_text(4, 232, ">> [WAVE] CHECK PULSE / RHYTHM (2 MIN)", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)

        return self.send(bytes(cmds))

    def push_directional_subtitles(
        self,
        speaker_name: str,
        direction: str = "center",
        text_line1: str = "",
        text_line2: str = "",
        is_translated: bool = False
    ) -> bool:
        """Killer Feature 20: Directional Multi-Speaker Speech Transcription.
        Anchors live subtitles to the speaker's physical direction (Left/Center/Right)
        while preserving 100% of the upper field of view for natural lip-reading.
        """
        cmds = bytearray()
        # Clean subtitle box at bottom (y: 162..254)
        cmds += cmd_rect(0, 162, 303, 254)

        dir_lower = direction.lower()
        if "left" in dir_lower or "gauche" in dir_lower:
            tag = f"[◀ {speaker_name.upper()}]:"
            col = COLOR_CYAN
            cmds += cmd_line(0, 162, 0, 254) # left side border notch
        elif "right" in dir_lower or "droite" in dir_lower:
            tag = f"[{speaker_name.upper()} ▶]:"
            col = COLOR_AMBER
            cmds += cmd_line(303, 162, 303, 254) # right side border notch
        else:
            tag = f"[▲ {speaker_name.upper()}]:"
            col = COLOR_GREEN

        if self.is_color:
            cmds += cmd_color(col)
        cmds += cmd_text(6, 168, tag[:24], font=0, color_or_grey=col if self.is_color else 15)

        # Translated badge if applicable
        if is_translated:
            cmds += cmd_text(220, 168, "[EN TRANSL]", font=0, color_or_grey=COLOR_CYAN if self.is_color else 10)

        # Rolling transcription lines
        if text_line1:
            cmds += cmd_text(8, 192, text_line1[:34], font=0, color_or_grey=15)
        if text_line2:
            cmds += cmd_text(8, 214, text_line2[:34], font=0, color_or_grey=14)

        # Footer
        cmds += cmd_text(4, 238, ">> [WAVE] CLOSE SUBTITLES", font=0, color_or_grey=8)
        return self.send(bytes(cmds))

    def push_uav_avionics_hud(
        self,
        pitch_deg: float,
        roll_deg: float,
        heading_deg: int,
        alt_agl_m: float,
        speed_kmh: float,
        home_dist_m: float,
        home_bearing_rel_deg: float = 0.0,
        cell_voltage: float = 3.82,
        lq_pct: int = 100
    ) -> bool:
        """Killer Feature 21: UAV / Drone Avionics VLOS Flight HUD.
        Maintains transparent boresight deadband so the pilot never loses line-of-sight
        with the real drone while reading altitude, speed, return chevron, and telemetry.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Top Bar: Battery Cell + Heading + Radio Link
        col_batt = COLOR_GREEN if cell_voltage >= 3.65 else (COLOR_AMBER if cell_voltage >= 3.50 else COLOR_RED)
        if self.is_color:
            cmds += cmd_color(col_batt)
        cmds += cmd_text(4, 4, f"{cell_voltage:.2f}V", font=0, color_or_grey=col_batt if self.is_color else 15)

        # Heading Tape in Center Top
        hdg_norm = int(heading_deg) % 360
        cmds += cmd_text(110, 4, f"[ {hdg_norm:03d}° ]", font=0, color_or_grey=COLOR_CYAN if self.is_color else 14)
        cmds += cmd_text(225, 4, f"LQ {lq_pct}%", font=0, color_or_grey=COLOR_GREEN if lq_pct > 80 else COLOR_AMBER)
        cmds += cmd_line(0, 22, 303, 22)

        # Left Tape: Speed (Groundspeed)
        cmds += cmd_line(56, 65, 56, 175)
        cmds += cmd_rect(2, 105, 54, 128)
        cmds += cmd_text(6, 110, f"{int(speed_kmh)}kmh", font=0, color_or_grey=15)
        cmds += cmd_text(6, 134, "SPD", font=0, color_or_grey=10)

        # Right Tape: AGL Altitude (Ceiling alert if >120m)
        alt_col = COLOR_RED if alt_agl_m > 120.0 else COLOR_GREEN
        cmds += cmd_line(248, 65, 248, 175)
        cmds += cmd_rect(250, 105, 302, 128)
        cmds += cmd_text(254, 110, f"{int(alt_agl_m)}m", font=0, color_or_grey=alt_col if self.is_color else 15)
        cmds += cmd_text(254, 134, "ALT", font=0, color_or_grey=10)

        # Central Split Pitch Ladder (leaving center 105..195 100% transparent for drone sighting!)
        pitch_off = int(max(-20, min(20, pitch_deg * 1.5)))
        cy = 120 + pitch_off
        cmds += cmd_line(74, cy, 98, cy)    # Left winglet
        cmds += cmd_line(206, cy, 230, cy)  # Right winglet
        cmds += cmd_line(74, cy, 74, cy + 4)
        cmds += cmd_line(230, cy, 230, cy + 4)

        # Bottom Center: Home Direction Chevron & Distance
        cx_h, cy_h = 152, 215
        rad_h = math.radians(home_bearing_rel_deg)
        dx_h = int(14 * math.sin(rad_h))
        dy_h = int(14 * math.cos(rad_h))
        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        cmds += cmd_circ(cx_h, cy_h, 16)
        cmds += cmd_line(cx_h, cy_h, cx_h + dx_h, cy_h - dy_h)
        cmds += cmd_text(118, 236, f"HOME: {int(home_dist_m)}m", font=0, color_or_grey=15)

        # Bottom Left Flight Mode
        cmds += cmd_text(4, 236, "POSHOLD", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)
        return self.send(bytes(cmds))

    def push_stealth_rf_sentry(
        self,
        threat_type: str = "airtag",
        target_id: str = "Apple AirTag",
        rssi_dbm: int = -58,
        dist_m: float = 1.8,
        is_critical: bool = False
    ) -> bool:
        """Killer Feature 22: Stealth Counter-Surveillance & RF / BLE Sentry.
        Discreet HUD seeker radar for rogue AirTags, unknown BLE beacons, and WiFi deauth floods.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        ttype = threat_type.lower()
        if "deauth" in ttype or is_critical:
            # 802.11 Deauth Flood Alert (Emergency Mode)
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rectf(0, 0, 12, 45)
            cmds += cmd_rectf(291, 0, 303, 45)
            cmds += cmd_text(18, 6, "⚠️ RF THREAT: DEAUTH FLOOD", font=1, color_or_grey=COLOR_RED if self.is_color else 15)
            cmds += cmd_line(18, 28, 285, 28)

            cmds += cmd_text(18, 38, f"Target : {target_id[:24]}", font=0, color_or_grey=14)
            cmds += cmd_text(18, 60, "Debit : 84 trames/s [ATTAQUE CRITIQUE]", font=0, color_or_grey=COLOR_RED if self.is_color else 15)
            cmds += cmd_text(18, 85, "Vecteur : Capture WPA handshake / Evil Twin", font=0, color_or_grey=12)
            cmds += cmd_text(18, 110, "Advice : switch to 4G/5G cellular", font=0, color_or_grey=12)

            cmds += cmd_rect(14, 135, 289, 175)
            cmds += cmd_text(24, 148, "[!] PROTECTION PMF 802.11w REQUISE", font=0, color_or_grey=COLOR_YELLOW if self.is_color else 14)

            cmds += cmd_text(4, 232, ">> [WAVE] HIDE ALERT & SAVE PCAP", font=0, color_or_grey=8)

        else:
            # BLE Tracking Beacon Seeker (AirTag / SmartTag)
            if self.is_color:
                cmds += cmd_color(COLOR_AMBER)
            cmds += cmd_text(4, 6, "[RF SENTRY: BLE TRACKER]", font=0, color_or_grey=COLOR_AMBER if self.is_color else 15)
            cmds += cmd_text(200, 6, "P-224 BEACON", font=0, color_or_grey=8)
            cmds += cmd_line(0, 24, 303, 24)

            # Target & RSSI Readout
            cmds += cmd_text(8, 34, f"TARGET: {target_id.upper()[:22]}", font=1, color_or_grey=COLOR_YELLOW if self.is_color else 15)
            cmds += cmd_text(8, 64, f"Signal : {rssi_dbm} dBm  |  Est. dist : {dist_m:.1f} m", font=0, color_or_grey=14)

            # Hot-Cold Seeker Bar Meter
            # Map RSSI (-95 to -35 dBm) to 0..100%
            pct = max(0, min(100, int(((rssi_dbm + 95) / 60.0) * 100)))
            cmds += cmd_text(8, 92, "RADAR DIRECTIONNEL (BLINDAGE CORPS) :", font=0, color_or_grey=10)
            cmds += cmd_gauge(0, pct)

            cmds += cmd_text(30, 140, "Turn 360° to find the bearing", font=0, color_or_grey=12)
            cmds += cmd_text(30, 160, "Strongest signal = beacon ahead", font=0, color_or_grey=COLOR_GREEN if self.is_color else 10)

            cmds += cmd_text(4, 232, ">> [WAVE] ACTIVER BIPPER AIRTAG / SILENCE", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)

        return self.send(bytes(cmds))

    def push_thermal_arc_flash_sentry(
        self,
        t_max_c: float,
        t_ambient_c: float,
        delta_t_c: float,
        reticle_xy: Tuple[int, int] = (152, 115),
        afb_dist_m: float = 1.5,
        is_violating_boundary: bool = False
    ) -> bool:
        """Killer Feature 23: Industrial Thermal & High-Voltage Arc-Flash Safety Sentry.
        Non-contact LWIR thermography hotspot reticle and NFPA 70E arc-flash approach boundary warnings.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Severity per ANSI/NETA MTS 100.18:
        # >15C = Critical (Red), 4-15C = Probable (Amber), <4C = Minor (Green)
        if delta_t_c > 15.0 or is_violating_boundary:
            col_status = COLOR_RED
            status_text = "CRITIQUE (REPARATION IMM.)"
        elif delta_t_c >= 4.0:
            col_status = COLOR_AMBER
            status_text = "ANOMALIE (SURVEILLER)"
        else:
            col_status = COLOR_GREEN
            status_text = "NOMINAL (EQUILIBRE)"

        if self.is_color:
            cmds += cmd_color(col_status)

        # Header
        cmds += cmd_text(4, 4, "[THERMAL & ARC-FLASH SENTRY]", font=0, color_or_grey=col_status if self.is_color else 15)
        cmds += cmd_text(220, 4, "LWIR 9Hz", font=0, color_or_grey=8)
        cmds += cmd_line(0, 22, 303, 22)

        # Telemetry Left Column
        cmds += cmd_text(4, 30, f"T_MAX : {t_max_c:.1f}°C", font=1, color_or_grey=col_status if self.is_color else 15)
        cmds += cmd_text(4, 58, f"T_AMB : {t_ambient_c:.1f}°C", font=0, color_or_grey=10)
        cmds += cmd_text(4, 76, f"ΔT    : +{delta_t_c:.1f}°C", font=0, color_or_grey=col_status if self.is_color else 14)
        cmds += cmd_text(4, 96, f"ETAT  : {status_text[:20]}", font=0, color_or_grey=col_status if self.is_color else 12)

        # 4-Corner Bracket Hotspot Reticle around (rx, ry)
        # Leaving center transparent to inspect physical wire/terminal!
        rx, ry = reticle_xy
        rw, rh = 28, 28
        x0, y0 = rx - rw // 2, ry - rh // 2
        x1, y1 = rx + rw // 2, ry + rh // 2
        arm = 8
        if self.is_color:
            cmds += cmd_color(col_status)
        # Top-left corner
        cmds += cmd_line(x0, y0, x0 + arm, y0)
        cmds += cmd_line(x0, y0, x0, y0 + arm)
        # Top-right corner
        cmds += cmd_line(x1, y0, x1 - arm, y0)
        cmds += cmd_line(x1, y0, x1, y0 + arm)
        # Bottom-left corner
        cmds += cmd_line(x0, y1, x0 + arm, y1)
        cmds += cmd_line(x0, y1, x0, y1 - arm)
        # Bottom-right corner
        cmds += cmd_line(x1, y1, x1 - arm, y1)
        cmds += cmd_line(x1, y1, x1, y1 - arm)
        cmds += cmd_text(rx - 16, ry - 6, f"{int(t_max_c)}°", font=0, color_or_grey=col_status if self.is_color else 15)

        # Arc-Flash Safety Boundary (NFPA 70E)
        if is_violating_boundary:
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rect(10, 155, 293, 205)
            cmds += cmd_text(16, 162, "⚠️ DANGER : ARC-FLASH BOUNDARY CROSSED!", font=1, color_or_grey=COLOR_RED if self.is_color else 15)
            cmds += cmd_text(16, 186, f"Required safety distance : {afb_dist_m:.1f} m", font=0, color_or_grey=14)
        else:
            cmds += cmd_text(16, 175, f"Limite Arc-Flash (NFPA 70E) : {afb_dist_m:.1f} m ✓ OK", font=0, color_or_grey=COLOR_GREEN if self.is_color else 10)

        # Footer
        cmds += cmd_text(4, 232, ">> [WAVE] VERROUILLER RETICULE / TARE", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_allergen_nutrition_scanner(
        self,
        product_name: str,
        detected_allergens: List[str],
        carbs_g: float = 0.0,
        sugar_g: float = 0.0,
        sodium_mg: float = 0.0,
        nutri_score: str = "A"
    ) -> bool:
        """Killer Feature 24: Real-Time Allergen & Nutritional Triage Scanner.
        Sub-200ms scan-to-HUD triage for lethal allergens (EU 1169/2011) and diabetic/renal metrics.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        if detected_allergens:
            # Lethal Allergen Triggered (High-Contrast Red Alert Banner)
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rectf(0, 0, 303, 56)
            cmds += cmd_text(12, 6, "[!] LIFE-THREATENING ALLERGEN", font=1, color_or_grey=0)
            al_str = ", ".join(detected_allergens).upper()
            cmds += cmd_text(12, 32, f"DETECTE : {al_str[:22]}", font=1, color_or_grey=0)

            # Product and Risk Warning
            if self.is_color:
                cmds += cmd_color(COLOR_AMBER)
            cmds += cmd_text(4, 68, f"PRODUCT : {product_name[:24]}", font=0, color_or_grey=15)
            cmds += cmd_text(4, 92, "STATUT  : ⛔ CHOC ANAPHYLACTIQUE", font=1, color_or_grey=COLOR_RED if self.is_color else 15)

            # Nutrition summary
            cmds += cmd_line(0, 140, 303, 140)
            cmds += cmd_text(4, 148, f"GLUCIDES: {carbs_g:.1f}g (Sucre: {sugar_g:.1f}g)", font=0, color_or_grey=14)
            cmds += cmd_text(4, 170, f"SODIUM  : {sodium_mg:.0f}mg | NUTRI-SCORE {nutri_score.upper()}", font=0, color_or_grey=14)

        else:
            # Safe Product & Nutritional Triage Mode
            if self.is_color:
                cmds += cmd_color(COLOR_GREEN)
            cmds += cmd_text(4, 6, "[✓ ALLERGENES : AUCUN DETECTE]", font=0, color_or_grey=COLOR_GREEN if self.is_color else 15)
            cmds += cmd_text(4, 26, f"PRODUCT : {product_name[:26]}", font=1, color_or_grey=15)
            cmds += cmd_line(0, 52, 303, 52)

            # 2-Column Diabetic & Renal Triage
            cmds += cmd_text(4, 60, "DIABETE (GLUCIDES)", font=0, color_or_grey=COLOR_CYAN if self.is_color else 12)
            cmds += cmd_text(160, 60, "RENAL (SEL/REINS)", font=0, color_or_grey=COLOR_YELLOW if self.is_color else 12)

            cmds += cmd_text(4, 82, f"GLUCIDES: {carbs_g:.1f}g", font=1, color_or_grey=15)
            cmds += cmd_text(160, 82, f"SODIUM: {sodium_mg:.0f}mg", font=1, color_or_grey=COLOR_AMBER if sodium_mg > 400 else 15)

            cmds += cmd_text(4, 112, f"Sucres  : {sugar_g:.1f}g", font=0, color_or_grey=COLOR_AMBER if sugar_g > 15 else 14)
            cmds += cmd_text(160, 112, f"Sel     : {(sodium_mg * 2.5 / 1000.0):.2f}g", font=0, color_or_grey=14)

            cmds += cmd_line(0, 145, 303, 145)
            cmds += cmd_text(4, 155, f"SCORE SANTE : NUTRI-SCORE {nutri_score.upper()} (CONFORME ✓)", font=0, color_or_grey=COLOR_GREEN if self.is_color else 10)

        # Footer
        cmds += cmd_text(4, 232, ">> [WAVE] CLOSE FOOD SCAN", font=0, color_or_grey=8)
        return self.send(bytes(cmds))

    def push_tactical_marine_hud(
        self,
        awa_deg: float,
        aws_knots: float,
        sog_knots: float,
        cog_deg: int,
        depth_m: float,
        regatta_sec_left: int
    ) -> bool:
        """Killer Feature 25: Marine Navigation & Regatta Tactical Sailing HUD.
        NMEA 2000 polar wind rose, apparent wind angle needle, depth alarm (<2.0m), and ISAF regatta start timer.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Left Sector: Polar Wind Rose & AWA Needle
        cx, cy = 70, 125
        r = 45
        if self.is_color:
            cmds += cmd_color(0x07) # subtle gray/blue
        cmds += cmd_circ(cx, cy, r)
        # Center boat centerline (bow up)
        cmds += cmd_line(cx, cy - 40, cx, cy + 40)
        cmds += cmd_line(cx - 6, cy - 32, cx, cy - 40)
        cmds += cmd_line(cx + 6, cy - 32, cx, cy - 40)

        # Layline ticks (40 deg upwind, 140 deg downwind)
        cmds += cmd_line(cx - 30, cy - 30, cx - 22, cy - 22)
        cmds += cmd_line(cx + 30, cy - 30, cx + 22, cy - 22)

        # Dynamic Apparent Wind Needle (Red on Port < 0, Green on Starboard >= 0)
        awa_rad = math.radians(awa_deg)
        nx = int(cx + r * math.sin(awa_rad))
        ny = int(cy - r * math.cos(awa_rad))
        needle_col = COLOR_RED if awa_deg < 0 else COLOR_GREEN
        if self.is_color:
            cmds += cmd_color(needle_col)
        cmds += cmd_line(cx, cy, nx, ny)
        cmds += cmd_circf(nx, ny, 3)

        # AWA Label under rose
        side_char = 'P' if awa_deg < 0 else 'S'
        cmds += cmd_text(30, 185, f"AWA {abs(int(awa_deg))}°{side_char} {aws_knots:.1f}kt", font=0, color_or_grey=needle_col if self.is_color else 15)

        # Right Sector: Flight Data & Regatta Timer
        # Divider
        cmds += cmd_line(142, 10, 142, 215)

        # Regatta Countdown Timer (ISAF Rule 26)
        m = regatta_sec_left // 60
        s = regatta_sec_left % 60
        timer_col = COLOR_RED if regatta_sec_left < 60 else COLOR_AMBER
        if self.is_color:
            cmds += cmd_color(timer_col)
        cmds += cmd_text(148, 12, f"START: {m:02d}:{s:02d}", font=1, color_or_grey=timer_col if self.is_color else 15)
        cmds += cmd_line(148, 40, 303, 40)

        # SOG & COG
        cmds += cmd_text(148, 48, f"SOG: {sog_knots:.1f} kt", font=1, color_or_grey=COLOR_GREEN if self.is_color else 15)
        cmds += cmd_text(148, 78, f"COG: {int(cog_deg):03d}°", font=0, color_or_grey=14)
        cmds += cmd_text(148, 100, "POLAR: 104% (OPTIMAL)", font=0, color_or_grey=COLOR_GREEN if self.is_color else 10)

        # Depth Gauge & Shallow Water Alarm (< 2.0m)
        if depth_m < 2.0:
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rect(148, 130, 298, 175)
            cmds += cmd_text(154, 138, f"⚠️ SHALLOWS : {depth_m:.1f} m!", font=1, color_or_grey=COLOR_RED if self.is_color else 15)
            cmds += cmd_text(154, 160, "RISQUE TALONNEMENT", font=0, color_or_grey=14)
        else:
            cmds += cmd_text(148, 140, f"FONDS: {depth_m:.1f} m (SECURITE ✓)", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)

        # Footer
        cmds += cmd_text(4, 232, ">> [WAVE] SYNC RACE TIMER (RULE 26)", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_multilingual_interpreter(
        self,
        speaker_origin: str,
        source_transcript: str,
        translated_text: str,
        etiquette_tag: str = "[TIP]",
        etiquette_tip: str = "Stay attentive and polite.",
        target_country: str = "JAPON"
    ) -> bool:
        """Killer Feature 26: Live Multilingual Interpreter & Cultural Etiquette Whisperer.
        Real-time conversational streaming translation + nonverbal cultural etiquette advice on HUD.
        Preserves center foveal sightline (y:30..155) completely transparent for direct eye contact.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Top Header: Target Country & Etiquette Badge
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 4, f"[INTERPRETE: {target_country.upper()}]", font=0, color_or_grey=COLOR_CYAN if self.is_color else 15)
        cmds += cmd_text(175, 4, etiquette_tag[:16], font=0, color_or_grey=COLOR_AMBER if self.is_color else 12)
        cmds += cmd_line(0, 22, 303, 22)

        # SAFE FOVEAL ZONE (y: 24 to 155): 100% transparent black for human face contact!

        # Lower Third Subtitle & Dialogue Box (y: 160..255)
        cmds += cmd_line(0, 160, 303, 160)
        cmds += cmd_text(4, 164, f"{speaker_origin[:14]} : \"{source_transcript[:26]}\"", font=0, color_or_grey=10)

        # Translated Line (Font 1 / High legibility)
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN)
        cmds += cmd_text(4, 186, f"└► \"{translated_text[:24]}\"", font=1, color_or_grey=COLOR_GREEN if self.is_color else 15)

        # Etiquette Advice Box
        if self.is_color:
            cmds += cmd_color(COLOR_AMBER)
        cmds += cmd_rect(0, 214, 303, 230)
        cmds += cmd_text(4, 217, f"💡 {etiquette_tip[:36]}", font=0, color_or_grey=COLOR_AMBER if self.is_color else 14)

        # Footer
        cmds += cmd_text(4, 236, ">> [WAVE] NEXT SPEAKER TURN", font=0, color_or_grey=8)
        return self.send(bytes(cmds))

    def push_driver_vigilance_hud(
        self,
        perclos_pct: float,
        microsleep_detected: bool = False,
        saccade_target: Optional[str] = None,
        nearest_rest_km: float = 4.2
    ) -> bool:
        """Killer Feature 27: Driver Drowsiness & PERCLOS Microsleep Guardian.
        Tracks PERCLOS P80 and microsleep eye closures (>400ms) with non-blinding night cues
        and interactive lateral saccade reaction verification.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Severity triage
        if microsleep_detected or perclos_pct >= 20.0:
            col = COLOR_RED
            hdr = "⚠️ MICROSLEEP ALERT!"
        elif perclos_pct >= 12.0:
            col = COLOR_AMBER
            hdr = "⚠️ FATIGUE DETECTEE (PERCLOS)"
        else:
            col = COLOR_GREEN
            hdr = "[VIGILANCE CONDUCTEUR : OK]"

        if self.is_color:
            cmds += cmd_color(col)

        # Top Header
        cmds += cmd_text(4, 4, hdr[:28], font=0, color_or_grey=col if self.is_color else 15)
        cmds += cmd_text(220, 4, f"AIRE {nearest_rest_km:.1f}k", font=0, color_or_grey=10)
        cmds += cmd_line(0, 22, 303, 22)

        # Gauge PERCLOS P80
        gauge_val = max(0, min(100, int(perclos_pct * 3.3)))
        cmds += cmd_gauge(0, gauge_val)

        # Peripheral Magnocellular Ticks (Left & Right margins)
        if microsleep_detected or perclos_pct >= 15.0:
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rectf(0, 40, 10, 180)
            cmds += cmd_rectf(293, 40, 303, 180)

        # Saccade Test or Road Telemetry
        if saccade_target == "LEFT":
            if self.is_color:
                cmds += cmd_color(COLOR_CYAN)
            cmds += cmd_rect(16, 100, 76, 140)
            cmds += cmd_text(20, 114, "◀ FIXER", font=1, color_or_grey=COLOR_CYAN if self.is_color else 15)
        elif saccade_target == "RIGHT":
            if self.is_color:
                cmds += cmd_color(COLOR_CYAN)
            cmds += cmd_rect(227, 100, 287, 140)
            cmds += cmd_text(231, 114, "FIXER ▶", font=1, color_or_grey=COLOR_CYAN if self.is_color else 15)
        else:
            # Center foveal deadband kept completely transparent for night vision!
            cmds += cmd_text(20, 75, f"PERCLOS P80 : {perclos_pct:.1f}%", font=1, color_or_grey=col if self.is_color else 15)
            if microsleep_detected:
                cmds += cmd_text(20, 110, "FERMETURE YEUX > 400ms !", font=1, color_or_grey=COLOR_RED if self.is_color else 15)
            else:
                cmds += cmd_text(20, 105, "Surveillance clignements active", font=0, color_or_grey=12)

        # Footer
        cmds += cmd_text(4, 232, ">> [WAVE] SNOOZE / SACCADE TEST PASSED", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_warehouse_pick(
        self,
        order_id: str,
        progress_str: str,
        aisle_bay_str: str,
        shelf_bin_str: str,
        quantity: int,
        unit_str: str = "PCS",
        sku_code: str = "SKU-8842-M8",
        sku_desc: str = "STAINLESS SCREW M8x40",
        scan_status: str = "VERIFIED"
    ) -> bool:
        """Killer Feature 28: Warehouse Logistics & Pick-by-Vision HUD.
        Bilateral hands-free picking guidance with jumbo quantity callouts,
        golden zone shelf indicators, and <0.1% barcode verification.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header: Order & Progress
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 4, f"CMD #{order_id[:8]} [{progress_str}]", font=0, color_or_grey=COLOR_CYAN if self.is_color else 15)
        cmds += cmd_line(0, 22, 303, 22)

        # Location Frame (Aisle - Bay - Shelf - Bin)
        cmds += cmd_rect(0, 26, 303, 72)
        cmds += cmd_text(6, 30, aisle_bay_str[:30], font=0, color_or_grey=12)
        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        cmds += cmd_text(6, 48, shelf_bin_str[:26], font=1, color_or_grey=COLOR_YELLOW if self.is_color else 15)

        # Central Quantity Callout (Jumbo Font 2)
        cmds += cmd_text(10, 85, f"x {quantity} {unit_str.upper()}", font=2, color_or_grey=COLOR_GREEN if self.is_color else 15)
        cmds += cmd_text(160, 88, sku_code[:14], font=1, color_or_grey=15)
        cmds += cmd_text(160, 114, sku_desc[:18], font=0, color_or_grey=12)

        # Verification Box
        status_up = scan_status.upper()
        if "VERIF" in status_up or "OK" in status_up:
            col_v = COLOR_GREEN
            txt_v = "[ ✓ SKU MATCH - BIN 02 ]"
        elif "MIS" in status_up or "ERR" in status_up:
            col_v = COLOR_RED
            txt_v = "[ ⛔ SKU ERROR: SCANNED 8840 ]"
        else:
            col_v = COLOR_AMBER
            txt_v = "[ WAITING FOR BARCODE SCAN ]"

        if self.is_color:
            cmds += cmd_color(col_v)
        cmds += cmd_rect(4, 160, 299, 205)
        cmds += cmd_text(12, 175, txt_v, font=1, color_or_grey=col_v if self.is_color else 15)

        # Footer
        cmds += cmd_text(4, 232, ">> [WAVE] CONFIRM NEXT BIN", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_avalanche_sar_hud(
        self,
        phase: str,
        distance_m: float,
        tangent_angle_deg: float,
        victims_count: int = 1,
        turn_180: bool = False,
        depth_probe_m: Optional[float] = None
    ) -> bool:
        """Killer Feature 29: Mountain Avalanche SAR & 457 kHz Vector Finder.
        Hands-free avalanche transceiver guidance with tangent flux vectors,
        orthogonal fine bracket crosshairs, and optical wave-to-mark.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header
        if self.is_color:
            cmds += cmd_color(COLOR_AMBER)
        cmds += cmd_text(4, 4, f"[AVALANCHE 457kHz] {victims_count} VICTIM(S)", font=0, color_or_grey=COLOR_AMBER if self.is_color else 15)
        # 1 Hz pulse indicator dot
        cmds += cmd_circf(290, 10, 3)
        cmds += cmd_line(0, 22, 303, 22)

        phase_up = phase.upper()
        if turn_180:
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_text(20, 80, "↩ DEMI-TOUR (180°)", font=2, color_or_grey=COLOR_RED if self.is_color else 15)
            cmds += cmd_text(20, 130, "FLOW LINE REVERSED!", font=1, color_or_grey=COLOR_RED if self.is_color else 14)

        elif "FINE" in phase_up:
            # Fine Search Orthogonal Bracket (<3m)
            if self.is_color:
                cmds += cmd_color(COLOR_AMBER)
            cmds += cmd_line(152, 50, 152, 170)
            cmds += cmd_line(92, 110, 212, 110)
            cmds += cmd_circ(152, 110, 24)
            cmds += cmd_text(115, 30, f"MIN: {distance_m:.2f}m", font=1, color_or_grey=COLOR_AMBER if self.is_color else 15)
            cmds += cmd_text(85, 180, "RECHERCHE CROIX 2D", font=0, color_or_grey=12)

        elif "PINPOINT" in phase_up:
            # Pinpoint Search (<0.8m)
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_circ(152, 105, 32)
            cmds += cmd_circ(152, 105, 16)
            cmds += cmd_circf(152, 105, 4)
            cmds += cmd_text(75, 150, f"SONDEZ : {depth_probe_m or 0.65:.2f} m", font=1, color_or_grey=COLOR_RED if self.is_color else 15)
            cmds += cmd_text(95, 178, "SPIRALE 25 cm", font=0, color_or_grey=14)

        else:
            # Coarse Search (3-50m): Tangent steering chevron
            if self.is_color:
                cmds += cmd_color(COLOR_YELLOW)
            cx, cy = 152, 95
            rad = math.radians(tangent_angle_deg)
            dx = int(24 * math.sin(rad))
            dy = int(24 * math.cos(rad))
            cmds += cmd_line(cx - dx, cy + dy, cx, cy)
            cmds += cmd_line(cx + dx, cy + dy, cx, cy)
            cmds += cmd_circf(cx, cy, 3)

            cmds += cmd_text(115, 130, f"{distance_m:.1f} m", font=2, color_or_grey=COLOR_YELLOW if self.is_color else 15)
            cmds += cmd_text(105, 175, f"HEADING : {tangent_angle_deg:+.0f}°", font=0, color_or_grey=12)

        # Footer
        cmds += cmd_text(4, 232, ">> [WAVE] MARK VICTIM (EXCLUDE SIGNAL)", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_circadian_chrono_optimizer(
        self,
        current_lux: int,
        medi_lux: int,
        dose_lux_min: int,
        target_dose: int = 300000,
        caffeine_active_mg: int = 68,
        cutoff_time_str: str = "14:30",
        sleep_clearance_hrs: float = 4.3,
        melatonin_warning: bool = False
    ) -> bool:
        """Killer Feature 30: Circadian Light Exposure & Chrono-Productivity Optimizer.
        CIE S 026:2018 melanopic EDI tracking, morning light dosage accumulator,
        and caffeine metabolic clearance cutoff before sleep.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 4, "☀️ CIRCADIAN CHRONO OPTIMIZER", font=0, color_or_grey=COLOR_CYAN if self.is_color else 15)
        cmds += cmd_line(0, 22, 303, 22)

        # Morning Light Exposure Dose
        pct = max(0, min(100, int((dose_lux_min / float(max(1, target_dose))) * 100)))
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN)
        cmds += cmd_text(4, 28, f"DOSE LUMIERE : {pct}% ({dose_lux_min // 1000}k / {target_dose // 1000}k lx*m)", font=0, color_or_grey=COLOR_GREEN if self.is_color else 15)
        cmds += cmd_gauge(0, pct)
        cmds += cmd_text(4, 70, f"mEDI : {medi_lux} lx (sensor : {current_lux} lx)", font=0, color_or_grey=12)

        # Caffeine Pharmacokinetics
        cmds += cmd_line(0, 95, 303, 95)
        if self.is_color:
            cmds += cmd_color(COLOR_AMBER)
        cmds += cmd_text(4, 102, f"CAFFEINE CUTOFF : {cutoff_time_str} | ACTIVE: {caffeine_active_mg}mg", font=1, color_or_grey=COLOR_AMBER if self.is_color else 15)
        cmds += cmd_text(4, 130, f"Sleep-safe level : in {sleep_clearance_hrs:.1f}h (<25mg)", font=0, color_or_grey=14)

        # Melatonin Evening Alert
        if melatonin_warning:
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rect(4, 155, 299, 210)
            cmds += cmd_text(10, 162, "⚠️ INHIBITION MELATONINE !", font=1, color_or_grey=COLOR_RED if self.is_color else 15)
            cmds += cmd_text(10, 186, "mEDI > 10 lx pre-sommeil. Tamisez ecrans.", font=0, color_or_grey=14)
        else:
            if self.is_color:
                cmds += cmd_color(COLOR_GREEN)
            cmds += cmd_text(16, 170, "Phase circadienne : Vigilance optimale", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)

        # Footer
        cmds += cmd_text(4, 232, ">> [WAVE] +1 CAFE (65mg) | [TAP] VITALS", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_firefighter_mayday_hud(
        self,
        unit_id: str = "E42-A",
        cylinder_bar: int = 220,
        ambient_temp_c: int = 118,
        temp_rise_c_per_min: int = 35,
        exit_bearing_deg: int = 60,
        pass_alarm: bool = False
    ) -> bool:
        """Killer Feature 31: Firefighter / Hazmat Thermal-Nav & Mayday Air Management HUD.
        NFPA 1404 Rule of Thirds (work/exit/reserve), flashover rate-of-rise thermal detection,
        and PASS Mayday acoustic/RF vectoring under heavy zero-visibility smoke.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header / Status banner
        if pass_alarm:
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rect(0, 0, 303, 26)
            cmds += cmd_text(6, 4, f"MAYDAY / PASS ACTIVE [{unit_id}]", font=1, color_or_grey=COLOR_RED if self.is_color else 15)
        else:
            if self.is_color:
                cmds += cmd_color(COLOR_AMBER)
            cmds += cmd_text(4, 4, f"SCBA BREATHING APPARATUS [{unit_id}]", font=0, color_or_grey=COLOR_AMBER if self.is_color else 15)
        cmds += cmd_line(0, 26, 303, 26)

        # SCBA Cylinder Air & NFPA 1404 Rule of Thirds
        air_pct = max(0, min(100, int((cylinder_bar / 300.0) * 100)))
        rem_min = max(0, int(cylinder_bar / 5.5))
        air_color = COLOR_GREEN if cylinder_bar >= 200 else (COLOR_AMBER if cylinder_bar >= 100 else COLOR_RED)
        if self.is_color:
            cmds += cmd_color(air_color)
        status_air = "TRAVAIL" if cylinder_bar >= 200 else ("REPLI" if cylinder_bar >= 100 else "EMERGENCY RESERVE")
        cmds += cmd_text(4, 32, f"AIR : {cylinder_bar} BAR ({rem_min} min) - {status_air}", font=1, color_or_grey=air_color if self.is_color else 15)
        cmds += cmd_gauge(0, air_pct)

        # Thermal Environment & Flashover Rate-of-Rise
        cmds += cmd_line(0, 95, 303, 95)
        flashover_risk = temp_rise_c_per_min >= 100 or ambient_temp_c >= 250
        temp_color = COLOR_RED if flashover_risk else (COLOR_AMBER if ambient_temp_c >= 100 else COLOR_GREEN)
        if self.is_color:
            cmds += cmd_color(temp_color)
        cmds += cmd_text(4, 102, f"THERMIQUE : {ambient_temp_c}C (dT/dt : +{temp_rise_c_per_min}C/min)", font=1, color_or_grey=temp_color if self.is_color else 15)
        if flashover_risk:
            cmds += cmd_text(4, 128, "FLASHOVER ALERT / FULL ROOM IGNITION!", font=0, color_or_grey=COLOR_RED if self.is_color else 15)
        else:
            cmds += cmd_text(4, 128, "Thermal stability : within limits", font=0, color_or_grey=12)

        # Exit Vector Navigation (Zero-visibility egress)
        cmds += cmd_line(0, 150, 303, 150)
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 156, f"EVACUATION GUIDE (LIFELINE) : HEADING {exit_bearing_deg} DEG", font=0, color_or_grey=COLOR_CYAN if self.is_color else 14)

        # Draw tactical arrow at right (x=250, y=185)
        rad = math.radians(exit_bearing_deg - 90)
        cx, cy = 250, 185
        dx, dy = int(22 * math.cos(rad)), int(22 * math.sin(rad))
        cmds += cmd_circ(cx, cy, 24)
        cmds += cmd_line(cx, cy, cx + dx, cy + dy)
        cmds += cmd_circf(cx + dx, cy + dy, 3)
        cmds += cmd_text(16, 182, "Follow the lifeline to the north airlock", font=0, color_or_grey=13)
        cmds += cmd_text(16, 202, "Estimated distance to exit : ~24m", font=0, color_or_grey=11)

        # Footer
        cmds += cmd_text(4, 234, ">> [WAVE] ACQUITTER ALARME | [TEMPLE] DETRESSE MAYDAY", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_ballistic_drop_compensator(
        self,
        range_m: float = 850.0,
        elevation_mrad: float = 6.4,
        windage_mrad: float = -1.2,
        wind_speed_ms: float = 4.5,
        wind_angle_deg: int = 90,
        cant_deg: float = -0.4
    ) -> bool:
        """Killer Feature 32: Precision Ballistic Drop & Mil-Dot Windage Compensator.
        G1/G7 Doppler ballistic trajectory calculation, crosswind jump, optical cant indicator,
        and real-time optical reticle aiming pip offset directly in scope vision.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header with Range & Ambient Crosswind
        if self.is_color:
            cmds += cmd_color(COLOR_AMBER)
        cmds += cmd_text(4, 4, f"MIL-DOT BALLISTICS | RANGE : {range_m:.0f}m", font=1, color_or_grey=COLOR_AMBER if self.is_color else 15)
        cmds += cmd_line(0, 24, 303, 24)

        # Wind & Atmospheric status
        wind_dir = "D" if windage_mrad > 0 else "G"
        moa_elev = elevation_mrad * 3.4377
        cmds += cmd_text(4, 28, f"WIND: {wind_speed_ms:.1f}m/s @ {wind_angle_deg} DEG | CORR: {abs(windage_mrad):.1f} MIL {wind_dir}", font=0, color_or_grey=14)

        # Central Optical Reticle (Scope Crosshairs with optical foveal transparent center)
        cx, cy = 152, 115
        cmds += cmd_line(cx - 50, cy, cx - 12, cy)
        cmds += cmd_line(cx + 12, cy, cx + 50, cy)
        cmds += cmd_line(cx, cy - 40, cx, cy - 10)
        cmds += cmd_line(cx, cy + 10, cx, cy + 40)
        for tick in [-30, -20, 20, 30]:
            cmds += cmd_line(cx + tick, cy - 3, cx + tick, cy + 3)
            cmds += cmd_line(cx - 3, cy + tick, cx + 3, cy + tick)

        # Dynamic Aiming Pip Offset (Holdover position)
        pip_x = cx + int(windage_mrad * 8)
        pip_y = cy + int(min(35, elevation_mrad * 4))
        if self.is_color:
            cmds += cmd_color(COLOR_RED)
        cmds += cmd_circ(pip_x, pip_y, 4)
        cmds += cmd_line(pip_x - 6, pip_y, pip_x + 6, pip_y)
        cmds += cmd_line(pip_x, pip_y - 6, pip_x, pip_y + 6)

        # Ballistic Solution Cards (Left / Right)
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN)
        cmds += cmd_text(4, 75, f"ELEV: +{elevation_mrad:.1f} MIL", font=1, color_or_grey=COLOR_GREEN if self.is_color else 15)
        cmds += cmd_text(4, 100, f"({moa_elev:.1f} MOA)", font=0, color_or_grey=12)

        cmds += cmd_text(210, 75, f"WIND: {windage_mrad:+.1f} MIL", font=1, color_or_grey=COLOR_CYAN if self.is_color else 15)
        cmds += cmd_text(210, 100, f"({windage_mrad * 3.4377:+.1f} MOA)", font=0, color_or_grey=12)

        # Rifle Cant Level Indicator (Spirit Bubble)
        cmds += cmd_line(0, 175, 303, 175)
        cant_offset = int(max(-40, min(40, cant_deg * 20)))
        bubble_x = 152 + cant_offset
        bubble_color = COLOR_GREEN if abs(cant_deg) <= 0.5 else COLOR_RED
        if self.is_color:
            cmds += cmd_color(bubble_color)
        cmds += cmd_rect(152 - 45, 185, 152 + 45, 200)
        cmds += cmd_line(152, 185, 152, 200)
        cmds += cmd_circf(bubble_x, 192, 4)
        cmds += cmd_text(4, 188, f"DEVERS : {cant_deg:+.1f} DEG", font=0, color_or_grey=bubble_color if self.is_color else 14)
        if abs(cant_deg) > 0.5:
            cmds += cmd_text(215, 188, "INCLINE !", font=0, color_or_grey=COLOR_RED if self.is_color else 15)
        else:
            cmds += cmd_text(215, 188, "LEVEL OK", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)

        # Footer
        cmds += cmd_text(4, 234, ">> [WAVE] NEXT BALLISTIC PROFILE | [TAP] ZERO REF", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_surgical_vitals_hud(
        self,
        patient_id: str = "P-402",
        spo2_pct: int = 98,
        hr_bpm: int = 72,
        map_mmhg: int = 85,
        etco2_mmhg: int = 38,
        implant_torque_ncm: float = 32.0
    ) -> bool:
        """Killer Feature 33: Surgical & Dental Sterile Patient Vitals & Torque HUD.
        IEC 60601-1-8 visual alarm compliance, intraoperative vital signs (SpO2, HR, MAP, EtCO2),
        and precision motor torque feedback keeping surgeon eyes 100% sterile on operative field.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 4, f"OPERATING ROOM [{patient_id}] - STERILE MONITORING", font=0, color_or_grey=COLOR_CYAN if self.is_color else 15)
        cmds += cmd_line(0, 22, 303, 22)

        # Vital Signs Grid (2x2)
        hr_alert = hr_bpm < 50 or hr_bpm > 115
        hr_color = COLOR_RED if hr_alert else COLOR_GREEN
        if self.is_color:
            cmds += cmd_color(hr_color)
        cmds += cmd_text(8, 28, f"FC: {hr_bpm} BPM", font=1, color_or_grey=hr_color if self.is_color else 15)
        cmds += cmd_text(8, 52, "Regular sinus rhythm", font=0, color_or_grey=12)

        spo2_alert = spo2_pct < 94
        spo2_color = COLOR_RED if spo2_alert else COLOR_GREEN
        if self.is_color:
            cmds += cmd_color(spo2_color)
        cmds += cmd_text(160, 28, f"SpO2: {spo2_pct}%", font=1, color_or_grey=spo2_color if self.is_color else 15)
        cmds += cmd_text(160, 52, "Normoxie stable", font=0, color_or_grey=12)

        # Line separator
        cmds += cmd_line(0, 72, 303, 72)

        # MAP (Mean Arterial Pressure) & EtCO2
        map_alert = map_mmhg < 65 or map_mmhg > 110
        map_color = COLOR_RED if map_alert else COLOR_CYAN
        if self.is_color:
            cmds += cmd_color(map_color)
        cmds += cmd_text(8, 78, f"PAM: {map_mmhg} mmHg", font=1, color_or_grey=map_color if self.is_color else 15)
        cmds += cmd_text(8, 102, "Perfusion cerebrale OK", font=0, color_or_grey=12)

        etco2_alert = etco2_mmhg < 30 or etco2_mmhg > 45
        etco2_color = COLOR_AMBER if etco2_alert else COLOR_GREEN
        if self.is_color:
            cmds += cmd_color(etco2_color)
        cmds += cmd_text(160, 78, f"EtCO2: {etco2_mmhg} mmHg", font=1, color_or_grey=etco2_color if self.is_color else 15)
        cmds += cmd_text(160, 102, "Ventilation alveolaire", font=0, color_or_grey=12)

        # Implant / Bone Screwing Dynamic Torque Meter
        cmds += cmd_line(0, 126, 303, 126)
        torque_pct = max(0, min(100, int((implant_torque_ncm / 50.0) * 100)))
        torque_alert = implant_torque_ncm > 45.0
        torque_sweet_spot = 30.0 <= implant_torque_ncm <= 40.0
        torque_color = COLOR_RED if torque_alert else (COLOR_GREEN if torque_sweet_spot else COLOR_AMBER)
        if self.is_color:
            cmds += cmd_color(torque_color)
        status_torque = "RISQUE OSTEONECROSE" if torque_alert else ("OPTIMAL TORQUE" if torque_sweet_spot else "IN PROGRESS")
        cmds += cmd_text(4, 132, f"MOTOR TORQUE : {implant_torque_ncm:.1f} N.cm ({status_torque})", font=1, color_or_grey=torque_color if self.is_color else 15)
        cmds += cmd_gauge(0, torque_pct)
        cmds += cmd_text(4, 172, "Implant target : 30 - 35 N.cm (auto stop at 40 N.cm)", font=0, color_or_grey=13)

        # Operating Field Gaze Center Note (Foveal transparent deadband 120x120 preserved)
        cmds += cmd_line(0, 196, 303, 196)
        cmds += cmd_text(8, 204, "Central field of view 100% sterile and clear", font=0, color_or_grey=10)

        # Footer
        cmds += cmd_text(4, 234, ">> [WAVE SANS CONTACT] CHANGER VUE | [TEMPLE] SAISIR TRACE", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_low_vision_echonav_hud(
        self,
        head_obstacle_dist_m: Optional[float] = 1.8,
        head_obstacle_type: str = "BRANCHE / PANNEAU",
        curb_drop_dist_m: Optional[float] = 2.2,
        is_critical_duck: bool = False
    ) -> bool:
        """Killer Feature 34: Low-Vision Head-Height Obstacle Echo-Radar & Curb Alert.
        Fills the white-cane blind spot (>0.8m chest/head height) via high-contrast sonar/LiDAR wireframe,
        warning of hanging signs, low branches, scaffolding, and negative curb drop-offs.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header / Status
        if is_critical_duck:
            if self.is_color:
                cmds += cmd_color(COLOR_RED)
            cmds += cmd_rect(0, 0, 303, 30)
            cmds += cmd_text(6, 6, "MIND YOUR HEAD! DUCK!", font=1, color_or_grey=COLOR_RED if self.is_color else 15)
        else:
            if self.is_color:
                cmds += cmd_color(COLOR_CYAN)
            cmds += cmd_text(4, 4, "NAVIGATION BASSE VISION - ECHO RADAR", font=0, color_or_grey=COLOR_CYAN if self.is_color else 15)
        cmds += cmd_line(0, 30, 303, 30)

        # Head-Height Hazard Section
        if head_obstacle_dist_m is not None:
            hazard_color = COLOR_RED if (head_obstacle_dist_m < 1.5 or is_critical_duck) else COLOR_AMBER
            if self.is_color:
                cmds += cmd_color(hazard_color)
            cmds += cmd_text(6, 38, f"OVERHEAD OBSTACLE : {head_obstacle_dist_m:.1f}m", font=1, color_or_grey=hazard_color if self.is_color else 15)
            cmds += cmd_text(6, 62, f"Type detecte : {head_obstacle_type}", font=0, color_or_grey=14)

            # High-contrast bracket overlay in upper visual field
            bx1, by1, bx2, by2 = 60, 80, 244, 140
            cmds += cmd_rect(bx1, by1, bx2, by2)
            cmds += cmd_line(bx1 - 10, by1, bx1 + 10, by1)
            cmds += cmd_line(bx1, by1 - 5, bx1, by1 + 5)
            cmds += cmd_line(bx2 - 10, by1, bx2 + 10, by1)
            cmds += cmd_line(bx2, by1 - 5, bx2, by1 + 5)
            cmds += cmd_text(85, 105, "[ OVERHEAD HAZARD ]", font=1, color_or_grey=hazard_color if self.is_color else 15)
        else:
            if self.is_color:
                cmds += cmd_color(COLOR_GREEN)
            cmds += cmd_text(6, 38, "HEAD HEIGHT : NO OBSTACLE DETECTED", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)
            cmds += cmd_text(6, 60, "Corridor aerien libre (> 2.5m)", font=0, color_or_grey=10)

        # Ground / Curb Drop-Off Alert (Negative Obstacle)
        cmds += cmd_line(0, 155, 303, 155)
        if curb_drop_dist_m is not None:
            curb_color = COLOR_AMBER if curb_drop_dist_m > 1.5 else COLOR_RED
            if self.is_color:
                cmds += cmd_color(curb_color)
            cmds += cmd_text(6, 162, f"SOL / MARCHES : DESCENTE a {curb_drop_dist_m:.1f}m", font=1, color_or_grey=curb_color if self.is_color else 15)
            # Draw ground hazard line
            cmds += cmd_line(30, 190, 274, 190)
            cmds += cmd_line(30, 190, 45, 205)
            cmds += cmd_line(274, 190, 259, 205)
            cmds += cmd_text(60, 195, "v CURB / GROUND EDGE v", font=0, color_or_grey=curb_color if self.is_color else 13)
        else:
            if self.is_color:
                cmds += cmd_color(COLOR_GREEN)
            cmds += cmd_text(6, 162, "SOL CONTINU : Trottoir regulier", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)

        # Footer with Sonar Sync
        cmds += cmd_text(4, 234, ">> [WAVE] TOGGLE BEEP | [TAP] RECALIBRATE GROUND", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_neural_voice_assistant_hud(
        self,
        state_str: str = "STREAMING LISTEN",
        partial_transcript: str = "Turn on the living room lights",
        mic_source: str = "PHONE BEAMFORMING MIC",
        vu_level_pct: int = 72,
        latency_ms: int = 120,
        is_speaking: bool = True
    ) -> bool:
        """Killer Feature 35 / Neural Expansion: Real-time Voice Assistant & Streaming ASR HUD.
        Renders live microphone audio VU level, partial speech transcription hypothesis,
        input latency badge, and gesture dismissal instructions.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Top banner with latency badge
        state_color = COLOR_GREEN if is_speaking else COLOR_CYAN
        if self.is_color:
            cmds += cmd_color(state_color)
        cmds += cmd_text(4, 4, f"🎙 {state_str[:16]}", font=0, color_or_grey=state_color if self.is_color else 15)
        cmds += cmd_text(210, 4, f"⚡ {latency_ms}ms", font=0, color_or_grey=COLOR_AMBER if latency_ms > 250 else (COLOR_GREEN if self.is_color else 12))
        cmds += cmd_line(0, 24, 303, 24)

        # Microphone source and acoustic VU meter bar
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 30, f"SOURCE : {mic_source[:24]}", font=0, color_or_grey=COLOR_CYAN if self.is_color else 12)
        
        # Audio VU-meter (wireframe box + filled bar)
        vu_w = max(4, min(290, int(290 * (vu_level_pct / 100.0))))
        cmds += cmd_rect(4, 50, 298, 64)
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN if vu_level_pct < 80 else COLOR_RED)
        cmds += cmd_rectf(6, 52, 6 + vu_w, 62)

        # Dynamic transcription hypothesis section
        cmds += cmd_line(0, 72, 303, 72)
        if self.is_color:
            cmds += cmd_color(COLOR_YELLOW)
        cmds += cmd_text(4, 78, "LIVE TRANSCRIPT (WHISPER) :", font=0, color_or_grey=COLOR_CYAN if self.is_color else 10)

        # Multi-line word wrap for transcript
        words = partial_transcript.split()
        lines = []
        cur_line = ""
        for w in words:
            if len(cur_line) + len(w) + 1 <= 28:
                cur_line += (" " if cur_line else "") + w
            else:
                lines.append(cur_line)
                cur_line = w
                if len(lines) >= 4:
                    break
        if cur_line and len(lines) < 4:
            lines.append(cur_line)

        for i, line in enumerate(lines):
            cmds += cmd_text(4, 102 + i * 22, line, font=1, color_or_grey=15)

        # Prompt hint & wave control
        cmds += cmd_line(0, 210, 303, 210)
        cmds += cmd_text(4, 216, "OpenBridge Neural Pipeline: Local Llama 3.2", font=0, color_or_grey=10)
        cmds += cmd_text(4, 234, ">> [WAVE] CONFIRM & SEND | [DOUBLE TAP] CANCEL", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_multimodal_vision_hud(
        self,
        target_label: str = "BREAKER #4 (WATER HEATER)",
        confidence_pct: int = 96,
        bounding_box: Optional[tuple[int, int, int, int]] = (60, 60, 244, 150),
        diagnostic_summary: str = "POSITION BASSE : DECLENCHEMENT THERMIQUE",
        action_recommendation: str = "Check the heating element before resetting",
        source_device: str = "SMARTPHONE 50MP CAM"
    ) -> bool:
        """Killer Feature 36 / Neural Expansion: Sight-Through-Phone Optical Reticle HUD.
        Draws collimated AR targeting brackets around physical objects captured by phone camera,
        presenting multimodal visual QA diagnostics in real time.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header with source camera & confidence
        if self.is_color:
            cmds += cmd_color(COLOR_AMBER)
        cmds += cmd_text(4, 4, f"👁 {source_device[:18]}", font=0, color_or_grey=COLOR_AMBER if self.is_color else 15)
        cmds += cmd_text(220, 4, f"{confidence_pct}% CONF", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)
        cmds += cmd_line(0, 24, 303, 24)

        # Target label
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN)
        cmds += cmd_text(4, 30, f"TARGET: {target_label[:28]}", font=1, color_or_grey=COLOR_GREEN if self.is_color else 15)

        # Optical Reticle / Bounding box
        if bounding_box:
            bx0, by0, bx1, by1 = bounding_box
            if self.is_color:
                cmds += cmd_color(COLOR_CYAN)
            cmds += cmd_rect(bx0, by0, bx1, by1)
            # Corner markers
            c_len = 8
            cmds += cmd_line(bx0, by0, bx0 + c_len, by0)
            cmds += cmd_line(bx0, by0, bx0, by0 + c_len)
            cmds += cmd_line(bx1, by0, bx1 - c_len, by0)
            cmds += cmd_line(bx1, by0, bx1, by0 + c_len)
            cmds += cmd_line(bx0, by1, bx0 + c_len, by1)
            cmds += cmd_line(bx0, by1, bx0, by1 - c_len)
            cmds += cmd_line(bx1, by1, bx1 - c_len, by1)
            cmds += cmd_line(bx1, by1, bx1, by1 - c_len)

        # Diagnostic findings
        cmds += cmd_line(0, 160, 303, 160)
        if self.is_color:
            cmds += cmd_color(COLOR_RED if any(k in diagnostic_summary.upper() for k in ("DECLENCHEMENT", "TRIPPED", "DANGER")) else COLOR_AMBER)
        cmds += cmd_text(4, 166, diagnostic_summary[:32], font=1, color_or_grey=15)
        cmds += cmd_text(4, 190, action_recommendation[:34], font=0, color_or_grey=14)

        # Footer
        cmds += cmd_text(4, 234, ">> [WAVE] CLOSE VISION | [TAP] NEW CAPTURE", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_ambient_iot_matrix(
        self,
        linky_watts: int = 1850,
        tempo_tomorrow: str = "BLANC",
        rain_min: int = 12,
        temp_c: int = 15,
        transit_line: str = "M14",
        transit_eta_min: int = 3,
        wan_mbps: int = 940,
        ping_ms: int = 7
    ) -> bool:
        """Killer Feature 37 / Neural Expansion: 4-Quadrant Ambient IoT & Peripheral Matrix.
        Projects all vital living infrastructure into a single collimated glance.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Top Header
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 4, "🌐 OPENBRIDGE AMBIENT FABRIC", font=0, color_or_grey=COLOR_CYAN if self.is_color else 15)
        cmds += cmd_text(220, 4, "SYNC NOMINAL", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)
        cmds += cmd_line(0, 24, 303, 24)

        # Dividing grid axes: Vertical at x=151, Horizontal at y=125
        cmds += cmd_line(151, 24, 151, 226)
        cmds += cmd_line(0, 125, 303, 125)

        # Quadrant 1 (Top-Left): RTE Linky Grid & Power
        tempo_col = COLOR_RED if tempo_tomorrow == "ROUGE" else (COLOR_AMBER if tempo_tomorrow == "BLANC" else COLOR_GREEN)
        if self.is_color:
            cmds += cmd_color(tempo_col)
        cmds += cmd_text(6, 30, f"⚡ LINKY: {linky_watts} W", font=1, color_or_grey=tempo_col if self.is_color else 15)
        cmds += cmd_text(6, 56, f"Tomorrow: {tempo_tomorrow}", font=0, color_or_grey=tempo_col if self.is_color else 14)
        cmds += cmd_text(6, 78, "HC: 22h00 - 06h00", font=0, color_or_grey=10)

        # Quadrant 2 (Top-Right): Weather Radar & Rain
        rain_col = COLOR_RED if rain_min <= 10 else (COLOR_AMBER if rain_min <= 20 else COLOR_CYAN)
        if self.is_color:
            cmds += cmd_color(rain_col)
        cmds += cmd_text(158, 30, f"🌧 RAIN: {rain_min}m", font=1, color_or_grey=rain_col if self.is_color else 15)
        cmds += cmd_text(158, 56, f"Temp: {temp_c}°C Ext", font=0, color_or_grey=14)
        cmds += cmd_text(158, 78, "Radar: Averse imminente", font=0, color_or_grey=10)

        # Quadrant 3 (Bottom-Left): Public Transit Real-Time
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN)
        cmds += cmd_text(6, 132, f"🚇 {transit_line}: IN {transit_eta_min}m", font=1, color_or_grey=COLOR_GREEN if self.is_color else 15)
        cmds += cmd_text(6, 158, "To Chatelet", font=0, color_or_grey=14)
        cmds += cmd_text(6, 180, "Trafic: 100% Fluide", font=0, color_or_grey=10)

        # Quadrant 4 (Bottom-Right): Network & Freebox WAN
        wan_col = COLOR_GREEN if wan_mbps > 500 else COLOR_AMBER
        if self.is_color:
            cmds += cmd_color(wan_col)
        cmds += cmd_text(158, 132, f"📶 FIBRE: {wan_mbps}M", font=1, color_or_grey=wan_col if self.is_color else 15)
        cmds += cmd_text(158, 158, f"Ping: {ping_ms} ms (LAN/WAN)", font=0, color_or_grey=14)
        cmds += cmd_text(158, 180, "Freebox: Connectee", font=0, color_or_grey=10)

        # Footer
        cmds += cmd_line(0, 226, 303, 226)
        cmds += cmd_text(4, 234, ">> [WAVE] CYCLE VUE | [DOUBLE TAP] RAFRAICHIR", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def push_neural_translation_stream(
        self,
        speaker_id: str = "SPEAKER 01",
        source_lang: str = "EN",
        target_lang: str = "FR",
        live_text: str = "Can you show me the OpenBridge glasses demo?",
        translated_text: str = "Can you show me the OpenBridge glasses demo?",
        azimuth_dir: str = "LEFT 45°",
        latency_ms: int = 165
    ) -> bool:
        """Killer Feature 38 / Neural Expansion: Spatial Directional Speech Translation Stream.
        Projects acoustic azimuth, original speech snippet, and French translation onto lower third.
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Azimuth direction and speaker tag
        if self.is_color:
            cmds += cmd_color(COLOR_AMBER)
        cmds += cmd_text(4, 4, f"🗣️ {speaker_id} [{azimuth_dir}]", font=0, color_or_grey=COLOR_AMBER if self.is_color else 15)
        cmds += cmd_text(220, 4, f"⚡ {latency_ms}ms", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)
        cmds += cmd_line(0, 24, 303, 24)

        # Source speech (subtle cyan)
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 32, f"[{source_lang.upper()}] {live_text[:30]}", font=0, color_or_grey=COLOR_CYAN if self.is_color else 10)

        # Lower-third translated box
        cmds += cmd_line(0, 140, 303, 140)
        cmds += cmd_rect(0, 140, 303, 225)
        if self.is_color:
            cmds += cmd_color(COLOR_GREEN)
        cmds += cmd_text(6, 148, f"➔ [{target_lang.upper()} AI TRANSLATION] :", font=0, color_or_grey=COLOR_GREEN if self.is_color else 12)

        # Word wrap translated text
        words = translated_text.split()
        lines = []
        cur_line = ""
        for w in words:
            if len(cur_line) + len(w) + 1 <= 28:
                cur_line += (" " if cur_line else "") + w
            else:
                lines.append(cur_line)
                cur_line = w
                if len(lines) >= 3:
                    break
        if cur_line and len(lines) < 3:
            lines.append(cur_line)

        for i, line in enumerate(lines):
            cmds += cmd_text(6, 168 + i * 20, line, font=1, color_or_grey=15)

        # Footer
        cmds += cmd_text(4, 234, ">> [WAVE] CLOSE SUBTITLES | [TAP] PAUSE LISTENING", font=0, color_or_grey=COLOR_CYAN if self.is_color else 8)
        return self.send(bytes(cmds))

    def discover(self) -> Dict[str, Any]:
        """OpenBridge discovery contract."""
        return {
            "status": "READY",
            "devices": [{
                "id": f"hud-{self.model.lower().replace(' ', '-')}-01",
                "name": f"{self.model} Heads-Up Display",
                "platform": "ActiveLook OS 4.2",
                "category": "hud",
                "transport": "BLE GATT",
                "simulated": False,
                "facts": {
                    "resolution": "304x256",
                    "display_type": "MicroOLED",
                    "color_support": self.is_color,
                    "gesture_sensor": True,
                    "battery_percent": 88
                },
                "capabilities": ["hud_notify", "hud_layout", "gesture_input", "battery_status",
                                  "voice_oracle"]
            }]
        }

    # ------------------------------------------------------------------
    # Voice AI Oracle HUD  (OpenBridge mod — VoiceAI Oracle v1)
    # ------------------------------------------------------------------
    def push_oracle_answer(
        self,
        query_class: str = "GENERAL",   # MATH | LOCATE | GENERAL
        transcript: str = "",
        answer: str = "",
        source: str = "ollama",
        latency_ms: int = 0,
    ) -> bool:
        """Display an Oracle AI answer card on the ENGO 3 HUD.

        Layout (304x256 MicroOLED):
          Row 0-20  : header bar  [ORACLE]  [Nms]
          Row 24    : separator line
          Row 26-48 : transcript echo (truncated, grey/cyan)
          Row 50    : separator line
          Row 56-96 : answer text (up to 3 lines, GREEN / AMBER)
          Row 112   : source badge (small)
          Row 240   : [WAVE dismiss]
        """
        cmds = bytearray()
        cmds += cmd_clear()

        # Header: colour by query class
        hdr_color = {
            'MATH': COLOR_CYAN,
            'LOCATE': COLOR_AMBER,
            'GENERAL': COLOR_GREEN,
        }.get(query_class, COLOR_GREEN)

        icon = {'MATH': 'MATH', 'LOCATE': 'GPS', 'GENERAL': 'AI'}.get(query_class, 'AI')
        hdr_text = f"ORACLE {icon}"[:16]

        if self.is_color:
            cmds += cmd_color(hdr_color)
        cmds += cmd_text(4, 4, hdr_text, font=0, color_or_grey=hdr_color if self.is_color else 15)
        lat_color = COLOR_AMBER if latency_ms > 1500 else COLOR_GREEN
        cmds += cmd_text(210, 4, f"~{latency_ms}ms", font=0,
                         color_or_grey=lat_color if self.is_color else 12)
        cmds += cmd_line(0, 20, 303, 20)

        # Transcript echo (truncated to 30 chars)
        tq = transcript[:30]
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 26, f"> {tq}", font=0, color_or_grey=COLOR_CYAN if self.is_color else 10)
        cmds += cmd_line(0, 50, 303, 50)

        # Answer block (up to 3 lines x 32 chars)
        ans_lines = answer.strip().split('\n')[:3]
        ans_color = COLOR_GREEN if query_class != 'LOCATE' else COLOR_AMBER
        if self.is_color:
            cmds += cmd_color(ans_color)
        y = 56
        for ln in ans_lines:
            cmds += cmd_text(4, y, ln[:32], font=0,
                             color_or_grey=ans_color if self.is_color else 15)
            y += 20

        # Source badge
        src_map = {
            'math_eval': 'CALC LOCAL',
            'offline_kb': 'BASE LOCAL',
            'gemini_search': 'GEMINI+WEB',
            'groq+web': 'GROQ+WEB',
            'groq': 'GROQ FAST',
            'ollama+web': 'QWEN+WEB',
            'ollama': 'QWEN LOCAL',
            'llamacpp+web': 'LLAMA+WEB',
            'llamacpp': 'LLAMA CPP',
            'unavailable': 'INDISPONIBLE',
        }
        src_txt = src_map.get(source, source.upper())[:18]
        if self.is_color:
            cmds += cmd_color(COLOR_CYAN)
        cmds += cmd_text(4, 112, f"src:{src_txt}", font=0,
                         color_or_grey=COLOR_CYAN if self.is_color else 8)

        # Bottom dismiss hint
        if self.is_color:
            cmds += cmd_color(COLOR_AMBER)
        cmds += cmd_text(4, 240, "~ WAVE  dismiss", font=0,
                         color_or_grey=COLOR_AMBER if self.is_color else 10)

        return self._send(bytes(cmds))
