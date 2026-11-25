"""Hardware validation on real ENGO/ActiveLook glasses (interactive).

Plays known frames then variants, asking at each step what the user sees
in the glasses. Everything is logged to validation_log.txt (sent frames
+ answers + TX notifications).

Usage:
  python ble_validate.py                  # scan, pick A.LooK*, step-by-step guide
  python ble_validate.py --address <MAC>  # known address
  python ble_validate.py --auto           # no questions (4s pauses), just watch

Prerequisites: glasses charged, powered on, official app closed/disconnected
(a single BLE connection at a time).
"""

import argparse
import asyncio
import time

import numpy as np

from protocol import (ADV_PREFIX, AL_RX, AL_TX, CLEAR, HELLO_DEMO,
                      build_imgstream_frame, build_text)
from transport_ble import BleGlasses, discover


def ask(question, auto):
    if auto:
        print(f"  [auto] {question} -> 4s pause (watch the glasses)")
        time.sleep(4)
        return "auto"
    try:
        return input(f"  {question} ")
    except EOFError:
        return "?"


async def main():
    p = argparse.ArgumentParser(description="ENGO hardware validation")
    p.add_argument("--address", default=None)
    p.add_argument("--auto", action="store_true")
    p.add_argument("--pace-ms", type=float, default=10.0)
    args = p.parse_args()

    log = open("validation_log.txt", "a", encoding="utf-8")
    log.write(f"\n===== session {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")

    address = args.address
    if not address:
        devices = await discover()
        cands = [d for d in devices if (d.name or "").startswith(ADV_PREFIX)]
        if not cands:
            print("No A.LooK* glasses found. Check they are powered on.")
            return
        address = cands[0].address
        print(f"Glasses: {cands[0].name} {address}")

    g = BleGlasses(address, pace_ms=args.pace_ms)
    await g.connect(subscribe=True)
    await asyncio.sleep(1.0)

    async def step(name, frame, question):
        print(f"\n>> {name} ({len(frame)} bytes)")
        print(f"   TX: {frame.hex(' ')}")
        log.write(f">> {name} TX={frame.hex()}\n")
        log.flush()
        await g.write_frame(frame)
        await asyncio.sleep(1.0)
        ans = ask(question + " (y/n + detail)", args.auto)
        log.write(f"   observed: {ans}\n")
        log.flush()
        return ans

    await step("1. CLEAR", CLEAR, "Screen cleared / black?")
    await step("2. HELLO (official demo replay)", HELLO_DEMO,
               "Text 'hello 0' shown? Where?")
    await step("3. Custom TEXT (20,100)", build_text(20, 100, "LINE 1 OK"),
               "'LINE 1 OK' visible near the top?")
    await step("4. Position TEXT (150,200)", build_text(150, 200, "POS2"),
               "'POS2' visible bottom right?")
    await step("5. TEXT (10,40) TOP", build_text(10, 40, "TOP"),
               "'TOP' at the top?")
    await step("6. TEXT (10,230) BOTTOM", build_text(10, 230, "BOTTOM"),
               "'BOTTOM' at the bottom? (Y mapping confirmed?)")

    # Image: 32x32 checkerboard (128 bytes) via candidate-A imgStream
    chk = (np.indices((32, 32)).sum(axis=0) % 2).astype(bool)
    payload = np.packbits(chk, axis=1).tobytes()
    await step("7. IMAGE 32x32 checker @ (100,100)",
               build_imgstream_frame(100, 100, 32, payload),
               "Checker visible in the middle? (if not: candidate A invalid)")

    print(f"\nDone: {g.frames} frames, {g.bytes} bytes, "
          f"{len(g.rx_log)} TX notifications. Log: validation_log.txt")
    log.write(f"done: frames={g.frames} bytes={g.bytes} rx={len(g.rx_log)}\n")
    log.close()
    await g.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
