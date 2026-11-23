# ActiveLook / ENGO: Scripts, Tooling and Wireshark Analysis

> **Field guide and protocol tooling.**
> A ready-to-adapt controller script, a Lua Wireshark dissector, reference hex frames and 10 documented
> hardware and firmware pitfalls.
>
> **Status:** scripts and frames are checked against OpenBridge's encoder and the HUD Studio emulator.
> Confirmation on a physical ENGO pair is pending its arrival.

---

## 1. Complete Python controller script (`bleak`)

This script covers the full lifecycle: BLE discovery, MTU negotiation, sequential notification subscriptions,
flow control with a resume watchdog, and flicker-free atomic rendering (`holdFlush`).

```python
#!/usr/bin/env python3
"""
ActiveLook / ENGO Eyewear controller (Python / Bleak)
Robust handling of the binary protocol, flow control and atomic rendering.
"""

import asyncio
import logging
import struct
from typing import Optional
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ActiveLook")

# ActiveLook GATT UUIDs
SERVICE_ACTIVELOOK = "0783b03e-8535-b5a0-7140-a304d2495cb7"
CHAR_TX            = "0783b03e-8535-b5a0-7140-a304d2495cb8"
CHAR_CONTROL       = "0783b03e-8535-b5a0-7140-a304d2495cb9"
CHAR_RX            = "0783b03e-8535-b5a0-7140-a304d2495cba"
CHAR_GESTURE       = "0783b03e-8535-b5a0-7140-a304d2495cbb"
CHAR_TOUCH         = "0783b03e-8535-b5a0-7140-a304d2495cbc"
CHAR_BATTERY       = "00002a19-0000-1000-8000-00805f9b34fb"


class ActiveLookDevice:
    def __init__(self, client: BleakClient):
        self.client = client
        self.can_send = asyncio.Event()
        self.can_send.set()
        self.flow_watchdog_task: Optional[asyncio.Task] = None
        self.battery_level: int = -1

    def _on_control_event(self, _: BleakGATTCharacteristic, data: bytearray):
        code = data[0]
        if code == 0x01:  # FLOW_OK
            logger.info("[FlowCtrl] OK (0x01): buffer drained, sending resumed")
            if self.flow_watchdog_task and not self.flow_watchdog_task.done():
                self.flow_watchdog_task.cancel()
            self.can_send.set()
        elif code == 0x02:  # FLOW_PAUSE (buffer >= 75%)
            logger.warning("[FlowCtrl] PAUSE (0x02): buffer at 75%, writes suspended")
            self.can_send.clear()
            # Safety workaround: 1000 ms watchdog in case the 0x01 packet is lost
            if self.flow_watchdog_task and not self.flow_watchdog_task.done():
                self.flow_watchdog_task.cancel()
            self.flow_watchdog_task = asyncio.create_task(self._flow_watchdog())
        elif code == 0x03:
            logger.error("[FlowCtrl] Error 0x03: invalid command or corrupt frame")
        elif code == 0x04:
            logger.error("[FlowCtrl] Error 0x04: buffer overflow (packet dropped)")
        elif code == 0x06:
            logger.error("[FlowCtrl] Error 0x06: flash locked (missing cfgWrite 0xD0)")

    async def _flow_watchdog(self):
        await asyncio.sleep(1.0)
        logger.warning("[FlowCtrl] Watchdog expired: forcing can_send=True")
        self.can_send.set()

    def _on_tx_data(self, _: BleakGATTCharacteristic, data: bytearray):
        cmd_id = data[1] if len(data) > 1 else 0
        logger.info(f"[TX notify] opcode 0x{cmd_id:02X}, raw: {data.hex().upper()}")

    def _on_gesture(self, _: BleakGATTCharacteristic, data: bytearray):
        logger.info(f"[Sensor] GESTURE detected (0x{data.hex().upper()})")

    def _on_touch(self, _: BleakGATTCharacteristic, data: bytearray):
        logger.info(f"[Sensor] TEMPLE TOUCH detected (0x{data.hex().upper()})")

    def _on_battery(self, _: BleakGATTCharacteristic, data: bytearray):
        self.battery_level = data[0]
        logger.info(f"[Battery] level: {self.battery_level}%")

    def build_packet(self, cmd_id: int, payload: bytes = b"", query_id: bytes = b"") -> bytes:
        query_len = len(query_id) & 0x0F
        estimated_len = 1 + 1 + 1 + 1 + query_len + len(payload) + 1
        if estimated_len <= 255:
            cmd_format = query_len << 1          # bits 4..1 = query-ID length
            header = struct.pack(">BBBB", 0xFF, cmd_id, cmd_format, estimated_len)
        else:
            cmd_format = 0x20 | (query_len << 1)  # bit 5 = 2-byte length
            header = struct.pack(">BBBH", 0xFF, cmd_id, cmd_format, estimated_len + 1)
        return header + query_id[:query_len] + payload + b"\xAA"

    async def write_command(self, cmd_id: int, payload: bytes = b"", with_response: bool = True):
        packet = self.build_packet(cmd_id, payload)
        await self.can_send.wait()
        await self.client.write_gatt_char(CHAR_RX, packet, response=with_response)

    async def init_subscriptions(self):
        # Subscribe to notification descriptors one after another
        await self.client.start_notify(CHAR_CONTROL, self._on_control_event)
        await self.client.start_notify(CHAR_TX, self._on_tx_data)
        await self.client.start_notify(CHAR_TOUCH, self._on_touch)
        await self.client.start_notify(CHAR_GESTURE, self._on_gesture)
        try:
            await self.client.start_notify(CHAR_BATTERY, self._on_battery)
        except Exception as e:
            logger.warning(f"Battery notification unavailable: {e}")

    # Basic graphics commands
    async def hold_flush(self, action: int):
        """0 = hold (buffer drawing calls), 1 = flush (display atomically)."""
        await self.write_command(0x39, struct.pack("B", action))

    async def clear_atomic(self):
        """Flicker-free clear with a full black rectangle (304x256)."""
        await self.write_command(0x34, struct.pack(">hhhh", 0, 0, 303, 255))

    async def set_luma(self, level: int):
        """Sets the brightness (0-15)."""
        await self.write_command(0x10, struct.pack("B", max(0, min(15, level))))

    async def draw_text(self, x: int, y: int, text: str, font_id: int = 0, grey: int = 15, rot: int = 0):
        """Draws an ASCII string (0x37). ROM fonts are ASCII only (see pitfall 9)."""
        header = struct.pack(">hhBBB", x, y, rot, font_id, grey)
        payload = header + text.encode("ascii", errors="replace") + b"\x00"
        await self.write_command(0x37, payload)

    async def set_config(self, cfg_name: str = "ALooK"):
        """Selects the standard flash configuration profile."""
        name_bytes = cfg_name.encode("ascii")[:12].ljust(12, b"\x00")
        await self.write_command(0xD2, name_bytes)


async def main():
    logger.info("Looking for ActiveLook / ENGO glasses...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: (d.name and any(p in d.name for p in ["ENGO", "ActiveLook", "Activelook"]))
        or SERVICE_ACTIVELOOK.lower() in [s.lower() for s in adv.service_uuids],
        timeout=10.0
    )

    if not device:
        logger.error("No ActiveLook glasses found.")
        return

    logger.info(f"Connecting to {device.name} ({device.address})...")
    async with BleakClient(device.address) as client:
        logger.info(f"Connected. Negotiated MTU: {client.mtu_size}")
        glasses = ActiveLookDevice(client)
        await glasses.init_subscriptions()
        await asyncio.sleep(0.3)

        # Enforce the baseline configuration
        await glasses.set_config("ALooK")
        await asyncio.sleep(0.1)

        # Flicker-free atomic render
        await glasses.hold_flush(0)
        await glasses.clear_atomic()
        await glasses.set_luma(14)

        # Draw an OpenBridge telemetry screen
        await glasses.write_command(0x32, struct.pack(">hhhh", 24, 230, 280, 230))
        await glasses.draw_text(24, 245, "OPENBRIDGE HUD", font_id=0, grey=15)
        await glasses.draw_text(24, 160, "POWER: 2.4 kW", font_id=2, grey=15)
        await glasses.draw_text(24, 90, "VACUUM: DOCKED", font_id=2, grey=15)

        await glasses.hold_flush(1)
        logger.info("Display active. Listening to sensors (Ctrl+C to quit)...")

        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 2. Lua Wireshark dissector (`activelook.lua`)

To inspect the packets exchanged between the smartphone and the glasses in Wireshark (Android HCI snoop
capture), save this file as `activelook.lua` in Wireshark's personal Lua plugins folder
(`Help > About Wireshark > Folders > Personal Lua Plugins`).

```lua
-- activelook.lua - Wireshark dissector for the ActiveLook / ENGO BLE protocol
local p_activelook = Proto("activelook", "ActiveLook Smart Glasses Protocol")

local f_start   = ProtoField.uint8("activelook.start", "Start Delimiter", base.HEX)
local f_cmd     = ProtoField.uint8("activelook.cmd", "Command ID", base.HEX)
local f_format  = ProtoField.uint8("activelook.format", "Command Format", base.HEX)
local f_length  = ProtoField.uint16("activelook.length", "Length", base.DEC)
local f_queryid = ProtoField.bytes("activelook.queryid", "Query ID")
local f_payload = ProtoField.bytes("activelook.payload", "Payload Data")
local f_footer  = ProtoField.uint8("activelook.footer", "End Delimiter", base.HEX)

p_activelook.fields = { f_start, f_cmd, f_format, f_length, f_queryid, f_payload, f_footer }

local cmd_names = {
    [0x00] = "displayPower", [0x01] = "clear", [0x02] = "grey", [0x03] = "demo",
    [0x05] = "battery", [0x06] = "vers", [0x08] = "led", [0x09] = "shift",
    [0x10] = "luma", [0x20] = "sensor", [0x21] = "gesture", [0x22] = "als",
    [0x30] = "grayscale", [0x31] = "point", [0x32] = "line", [0x33] = "rect",
    [0x34] = "rectf", [0x35] = "circ", [0x36] = "circf", [0x37] = "txt",
    [0x38] = "polyline", [0x39] = "holdFlush", [0x3C] = "arc", [0x3D] = "color",
    [0x3E] = "txtColor", [0x41] = "imgSave", [0x42] = "imgDisplay",
    [0x44] = "imgStream", [0x46] = "imgDelete", [0x47] = "imgList", [0x50] = "fontList",
    [0x60] = "layoutSave", [0x62] = "layoutDisplay", [0x63] = "layoutClear",
    [0x70] = "gaugeDisplay", [0x71] = "gaugeSave", [0x80] = "pageSave", [0x83] = "pageDisplay",
    [0xD0] = "cfgWrite", [0xD2] = "cfgSet", [0xE0] = "shutdown", [0xE1] = "reset"
}

function p_activelook.dissector(buffer, pinfo, tree)
    local length = buffer:len()
    if length < 5 then return end

    local start_byte = buffer(0, 1):uint()
    local end_byte = buffer(length - 1, 1):uint()
    if start_byte ~= 0xFF or end_byte ~= 0xAA then return end

    pinfo.cols.protocol = "ActiveLook"

    local cmd_id = buffer(1, 1):uint()
    local cmd_name = cmd_names[cmd_id] or string.format("Unknown (0x%02X)", cmd_id)
    pinfo.cols.info = string.format("Cmd: %s", cmd_name)

    local subtree = tree:add(p_activelook, buffer(), string.format("ActiveLook Packet: %s", cmd_name))
    subtree:add(f_start, buffer(0, 1))
    subtree:add(f_cmd, buffer(1, 1)):append_text(string.format(" (%s)", cmd_name))

    local fmt_byte = buffer(2, 1):uint()
    subtree:add(f_format, buffer(2, 1))

    local is_long = (bit.band(fmt_byte, 0x20) ~= 0)
    local query_len = bit.band(bit.rshift(fmt_byte, 1), 0x0F)
    local offset = 3

    if is_long then
        subtree:add(f_length, buffer(offset, 2))
        offset = offset + 2
    else
        subtree:add(f_length, buffer(offset, 1))
        offset = offset + 1
    end

    if query_len > 0 then
        subtree:add(f_queryid, buffer(offset, query_len))
        offset = offset + query_len
    end

    local payload_len = length - offset - 1
    if payload_len > 0 then
        subtree:add(f_payload, buffer(offset, payload_len))
    end

    subtree:add(f_footer, buffer(length - 1, 1))
end

-- Bind to the ATT handle of the Server RX characteristic in your capture (shown as 0x0000 here).
DissectorTable.get("btatt.handle"):add(0x0000, p_activelook)
```

---

## 3. Reference hex frames

Generated by OpenBridge's encoder ([`src/adapters/activelook.py`](../../../src/adapters/activelook.py)) and
accepted by the HUD Studio emulator. To be compared against a real HCI capture once the pair arrives.

### Central ➔ glasses (`Server RX`)
* **Clear screen (`0x01`)**:
  `FF 01 00 05 AA`
* **Hold rendering (`0x39 holdFlush`, action = 0)**:
  `FF 39 00 06 00 AA`
* **Atomic flush (`0x39 holdFlush`, action = 1)**:
  `FF 39 00 06 01 AA`
* **Set luminance (`0x10 luma`, level = 15)**:
  `FF 10 00 06 0F AA`
* **Filled rectangle (`0x34 rectf`, 0, 0, 303, 255)**:
  `FF 34 00 0D 00 00 00 00 01 2F 00 FF AA`
* **Text ("HELLO", x = 24, y = 128, rot = 0, font = 0, grey = 15)**:
  `FF 37 00 12 00 18 00 80 00 00 0F 48 45 4C 4C 4F 00 AA`
* **Select flash configuration (`0xD2 cfgSet`, "ALooK", padded to 12 bytes)**:
  `FF D2 00 11 41 4C 6F 6F 4B 00 00 00 00 00 00 00 AA`

### Glasses ➔ central
* **Flow control OK (control characteristic)**: `01`
* **Flow control, buffer at 75 % (control characteristic)**: `02`
* **IR gesture (gesture characteristic)**: `01`
* **Temple touch (touch characteristic)**: `01`
* **Battery update (battery characteristic)**: `5F` (95 %)

---

## 4. Ten hardware pitfalls, firmware quirks and workarounds

Collected from the public ActiveLook documentation and community reports; each workaround is implemented in
OpenBridge's adapter or emulator. Hardware confirmation is pending.

| # | Pitfall / quirk | Symptom | Workaround |
| :-: | :--- | :--- | :--- |
| **1** | **Nibble overflow (pure white 255 turns off)** | In 4-bit formats (`0x0` to `0xF`), sending `255` overflows the nibble and wraps to `0` (pixel off). | **Cap luminance at `240`** (`0xF0F0F0`). 240 maps to level 15 without overflow. |
| **2** | **Black flash on clear (`clear()` is not buffered)** | `clear` (`0x01`) runs immediately on the controller and ignores `holdFlush(0)`. 50 ms flicker. | **Never use `0x01` live.** Use `holdFlush(0)`, clear with a black rectangle (`0x34 rectf 0 0 303 255`), draw, then `holdFlush(1)`. |
| **3** | **Slow BLE interval on Android** | Android negotiates a 50 ms interval by default, causing `"Could not write rx"` errors under load. | **Force high priority:** `requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)` drops the interval to 11–15 ms. |
| **4** | **Flow-control deadlock (1000 ms watchdog)** | The glasses send `0x02` (pause) but the `0x01` (resume) packet is lost. The host freezes. | **Arm a 1,000 ms watchdog** when `0x02` arrives. If not cleared after 1 s, force `can_send = true`. |
| **5** | **Gesture sensor double trigger** | The front IR sensor sees the hand enter and leave (2 events within 50–120 ms). | **Apply a software debounce of at least 300–350 ms.** |
| **6** | **Optical overscan and edge blur** | The panel is 304×256 but the optical prism crops the periphery (blurred or hidden within 24 px of the edges). | **Respect the safe zone:** X margin = 24 px, Y margin = 14 px. Sharp usable area = **256 × 228 pixels**. |
| **7** | **Asymmetric coordinate anchoring** | The origin is bottom-left ($X: 0 \to 304, Y: 0 \to 256$), but `txt` anchors top-left and draws downward while `img` anchors bottom-right. | **Apply compensating offsets:** 2 px Y offset on images, and always sort rectangle corners ($x_0 \le x_1, y_0 \le y_1$). |
| **8** | **Flash profile lock (`cfgSet`)** | If a third-party app wrote a custom flash profile, the default fonts may be missing. | **Always send `cfgSet("ALooK")` (`0xD2`)** right after the BLE connection. |
| **9** | **ROM fonts are ASCII only** | Accented characters (é, à, è), cedillas or emoji corrupt the display. | **Transliterate to plain ASCII**, or rasterise on the host into a 1 bpp/4 bpp bitmap and send it with `imgStream` (`0x44`). |
| **10**| **Bandwidth saturation during animation** | Streaming bitmaps continuously saturates the BLE link. | **Use empty placeholder boxes (`layouts`)** and send the final bitmap only once the motion has settled. |
