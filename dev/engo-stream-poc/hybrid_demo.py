"""Hybrid demo: pixel graphics + subtitles as native text.

Synthetic scenario (no video needed), native 304x256 resolution:
- a bouncing ball in PIXELS (sparse, delta + skip-black);
- a fixed title + subtitles in NATIVE 0x37 TEXT (1 command each).

Goal: measure the hybrid gain vs all-pixel (see stream.py on
sparse_dark.mp4: 4.36 fps) and validate the target architecture:
live translation -> native text, visual feedback -> sparse pixels.
"""

import argparse
import math
import time

import numpy as np

from convert import plan_tiles
from transport_emu import CANVAS_H, CANVAS_W, EmuGlasses

SUBS = [
    (0.0, 3.0, "Hello, this is a subtitle."),
    (3.0, 6.0, "Sent as native text, not pixels."),
    (6.0, 9.0, "Cost: ~50 bytes per line."),
    (9.0, 12.0, "The ball is pixels, though."),
]
SUB_BAND = (0, 208, 304, 40)  # x, y, w, h
BALL_R = 15


def ball_bitmap(t, seconds):
    bw = np.zeros((CANVAS_H, CANVAS_W), dtype=bool)
    bx = int(CANVAS_W / 2 + (CANVAS_W / 2 - 30) * math.sin(2 * math.pi * t / seconds * 3))
    by = int(100 + 70 * abs(math.sin(2 * math.pi * t / seconds * 5)))
    yy, xx = np.ogrid[:CANVAS_H, :CANVAS_W]
    bw[(yy - by) ** 2 + (xx - bx) ** 2 <= BALL_R ** 2] = True
    return bw


def sub_at(t):
    for t0, t1, s in SUBS:
        if t0 <= t < t1:
            return s
    return SUBS[-1][2]


def main():
    p = argparse.ArgumentParser(description="Hybrid demo: pixels + native text")
    p.add_argument("--seconds", type=float, default=12.0)
    p.add_argument("--src-fps", type=float, default=15.0)
    p.add_argument("--tile", type=int, default=32)
    p.add_argument("--throughput", type=int, default=15000)
    p.add_argument("--mtu", type=int, default=247)
    p.add_argument("--cmd-ms", type=float, default=30.0)
    p.add_argument("--chunk-ms", type=float, default=5.0)
    p.add_argument("--time-scale", type=float, default=1.0)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--show-scale", type=int, default=2)
    p.add_argument("--record", default=None)
    args = p.parse_args()

    emu = EmuGlasses(throughput=args.throughput, mtu_payload=args.mtu - 3,
                     cmd_ms=args.cmd_ms, chunk_ms=args.chunk_ms,
                     time_scale=args.time_scale, headless=args.headless,
                     show_scale=args.show_scale, record_path=args.record)
    emu.clear_all()
    emu.send_text(8, 20, "HYBRID: ball=px, subtitles=txt")
    prev = {}
    cur_sub = None
    n = int(args.seconds * args.src_fps)
    t0 = time.time()
    try:
        for i in range(n):
            t = i / args.src_fps
            sub = sub_at(t)
            if sub != cur_sub:  # subtitle: 1 clear + 1 native text
                emu.clear_tile(*SUB_BAND)
                emu.send_text(8, 232, sub)
                cur_sub = sub
            bw = ball_bitmap(t, args.seconds)
            ops, n_total = plan_tiles(bw, args.tile, 0, 0, prev, "delta", True, False)
            sim_before = emu.sim_time
            n_send = n_clear = 0
            for action, ax, ay, tw, th, payload in ops:
                if action == "send":
                    emu.send_tile(ax, ay, tw, th, payload)
                    n_send += 1
                else:
                    emu.clear_tile(ax, ay, tw, th)
                    n_clear += 1
            emu.frames += 1
            fps = emu.frames / emu.sim_time
            overlay = [
                "HYBRID 304x256 px+native txt",
                f"sim: {fps:.1f} fps | {emu.sim_time / emu.frames * 1000:.0f} ms/f",
                f"px:{n_send}S+{n_clear}C txt:{emu.texts} | {emu.sim_bytes / 1024:.1f} KB",
            ]
            if not emu.render(overlay, emu.sim_time - sim_before):
                break
            if i % 45 == 0:
                print(f"t={t:.1f}s sub='{sub[:30]}...' px={n_send}S+{n_clear}C "
                      f"sim_fps={fps:.2f}")
    finally:
        s = emu.summary()
        emu.close()
    print("\n=== HYBRID SUMMARY ===")
    print(f"frames={s['frames']}  px_tiles={s['tiles']}  texts={s['texts']}  "
          f"bytes={s['bytes']} ({s['bytes'] / 1024:.1f} KB)")
    print(f"simulated time={s['sim_time']:.1f}s -> {s['sim_fps']:.2f} fps, "
          f"latency ~{s['sim_latency_ms']:.0f} ms/frame (wall={s['wall_time']:.1f}s)")


if __name__ == "__main__":
    main()
