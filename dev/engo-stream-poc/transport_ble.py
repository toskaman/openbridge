"""Real BLE transport to the glasses (phase 2, after emulated validation).

Usage:
  1. python stream.py --transport ble --ble-discover
     -> list visible glasses and their services/characteristics.
  2. Identify the command (write) characteristic with nRF Connect
     if needed, validate the imgStream format (see protocol.py).
  3. python stream.py --transport ble --ble-address <MAC> --ble-write-uuid <UUID> ...

Requires: pip install bleak
"""

import asyncio

from bleak import BleakClient, BleakScanner

from protocol import AL_RX, AL_TX, ADV_PREFIX, build_imgstream, chunk_frame


async def discover(timeout=8.0):
    print(f"BLE scan ({timeout}s)...")
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        mark = "  <-- GLASSES?" if (d.name or "").startswith(ADV_PREFIX) else ""
        print(f"  {d.address}  {d.name}  RSSI={d.rssi}{mark}")
    return devices


async def dump_services(address):
    async with BleakClient(address) as client:
        print(f"Connected to {address}. Services:")
        for svc in client.services:
            print(f"  Service {svc.uuid}  {svc.description}")
            for ch in svc.characteristics:
                print(f"    Char {ch.uuid}  props={','.join(ch.properties)}  {ch.description}")


class BleGlasses:
    def __init__(self, address, write_uuid=None, notify_uuid=None,
                 mtu_payload=244, pace_ms=5.0):
        self.address = address
        self.write_uuid = write_uuid or AL_RX
        self.notify_uuid = notify_uuid or AL_TX
        self.mtu_payload = mtu_payload
        self.pace_s = pace_ms / 1000.0
        self.client = None
        self.tiles = 0
        self.bytes = 0
        self.frames = 0
        self.rx_log = []

    async def connect(self, subscribe=True):
        self.client = BleakClient(self.address)
        await self.client.connect()
        try:
            mtu = self.client.mtu_size  # negotiated by the OS (WinRT: read-only)
            self.mtu_payload = max(20, mtu - 3)
            print(f"Connected to {self.address} (MTU={mtu}, RX={self.write_uuid})")
        except Exception:
            print(f"Connected to {self.address} (MTU unknown, {self.mtu_payload}B chunks)")
        if subscribe:
            try:
                await self.client.start_notify(self.notify_uuid, self._on_notify)
                print(f"Notifications enabled on {self.notify_uuid}")
            except Exception as e:
                print(f"Notifications unavailable on {self.notify_uuid}: {e}")

    def _on_notify(self, _handle, data: bytearray):
        self.rx_log.append(bytes(data))
        print(f"  [TX glasses] {bytes(data).hex(' ')}")

    async def write_frame(self, frame: bytes):
        for chunk in chunk_frame(frame, self.mtu_payload):
            await self.client.write_gatt_char(self.write_uuid, chunk, response=False)
            self.bytes += len(chunk)
            if self.pace_s > 0:
                await asyncio.sleep(self.pace_s)
        self.frames += 1

    async def send_tile(self, x, y, w, h, payload: bytes):
        for chunk in build_imgstream(x, y, w, payload, self.mtu_payload):
            await self.client.write_gatt_char(self.write_uuid, chunk, response=False)
            self.bytes += len(chunk)
            if self.pace_s > 0:
                await asyncio.sleep(self.pace_s)
        self.tiles += 1

    async def clear_tile(self, x, y, w, h):
        # Honest fallback: no confirmed native fillRect, so send a black tile.
        # If the firmware exposes a native filled rectangle, wire it here (1 command).
        await self.send_tile(x, y, w, h, bytes((w // 8) * h))

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            print("Disconnected.")
