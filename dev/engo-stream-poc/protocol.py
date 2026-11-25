"""ActiveLook wire protocol (BLE GATT).

Sources:
- UUIDs + demo frames (clear, 0x37 text): Arduino thread "Writing to a BLE
  Characteristic" (commands from the official ActiveLook API).
- img* commands (0x40-0x45): MicroOLED patent EP4090057 / US20240233588.

Observed format: frames start with 0xFF and end with 0xAA.
Commands larger than the MTU go out as several GATT writes; the glasses
reassemble them using the FF...AA framing.

TO VALIDATE on hardware: imgStream (candidate A below) and the meaning
of the 5 text parameter bytes.
"""

import struct

# --- GATT (observed, Arduino thread) ---
AL_SVC = "0783B03E-8535-B5A0-7140-A304D2495CB7"
AL_RX = "0783B03E-8535-B5A0-7140-A304D2495CBA"  # central -> glasses (write)
AL_TX = "0783B03E-8535-B5A0-7140-A304D2495CB8"  # glasses -> central (notify)
AL_CTL = "0783B03E-8535-B5A0-7140-A304D2495CB9"
ADV_PREFIX = "A.LooK"

# --- Known frames (replay verbatim) ---
CLEAR = bytes([0xFF, 0x01, 0x00, 0x05, 0xAA])
HELLO_DEMO = bytes.fromhex("FF3700140098008000020F68656C6C6F203000AA")

CMD_TEXT = 0x37
CMD_IMG_STREAM = 0x44
# Text demo params: X=20, Y=152 then these 5 bytes (exact meaning unknown,
# probably rotation/font/size/color). Replayed verbatim.
TEXT_DEMO_PARAMS = bytes([0x00, 0x80, 0x00, 0x02, 0x0F])


def build_text(x: int, y: int, text: str, params: bytes = TEXT_DEMO_PARAMS) -> bytes:
    """Build a 0x37 text command (ASCII, 00-terminated).

    Assumption (to validate): X and Y as 2 big-endian bytes, as in the demo
    (X=0x0014=20, Y=0x0098=152 fit a 304x256 display).
    """
    asc = text.encode("ascii", errors="replace")
    return (b"\xFF" + bytes([CMD_TEXT]) + struct.pack(">H", x) + struct.pack(">H", y)
            + params + asc + b"\x00\xAA")


def build_imgstream_frame(x: int, y: int, w: int, payload: bytes) -> bytes:
    """CANDIDATE A: patent body (size LE32 + width LE16 + x/y) + FF..AA framing.

    Height deduced by the glasses: h = SIZE * 8 / WIDTH (1bpp).
    """
    body = (bytes([CMD_IMG_STREAM]) + struct.pack("<I", len(payload))
            + struct.pack("<H", w) + struct.pack("<h", x) + struct.pack("<h", y))
    return b"\xFF" + body + payload + b"\xAA"


def build_imgstream(x: int, y: int, w: int, payload: bytes, mtu_payload: int = 244) -> list:
    """Split a candidate imgStream frame into BLE chunks."""
    blob = build_imgstream_frame(x, y, w, payload)
    return [blob[i:i + mtu_payload] for i in range(0, len(blob), mtu_payload)]


def chunk_count(payload_len: int, mtu_payload: int = 244) -> int:
    """Number of BLE chunks needed (11B body + 2B framing + payload)."""
    total = 13 + payload_len
    return (total + mtu_payload - 1) // mtu_payload


def chunk_frame(frame: bytes, mtu_payload: int = 244) -> list:
    """Split any frame (clear, text...) into BLE chunks."""
    return [frame[i:i + mtu_payload] for i in range(0, len(frame), mtu_payload)]
