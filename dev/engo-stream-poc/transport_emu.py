"""ENGO/ActiveLook glasses emulator + BLE transport simulation.

- 304x256 1-bit canvas (the real HUD resolution).
- BLE throughput simulation: each sent tile costs
      len(payload)/throughput + n_chunks * chunk_ms + cmd_ms
  (counted as simulated time; also slows wall time via time_scale).
- Realtime display (cv2) + optional recording of what the
  glasses would show (with simulated pacing, at 10 fps).
"""

import time

import cv2
import numpy as np

from protocol import chunk_count

CANVAS_W, CANVAS_H = 304, 256


class EmuGlasses:
    def __init__(self, throughput=15000, mtu_payload=244, cmd_ms=30.0, chunk_ms=5.0,
                 time_scale=1.0, headless=False, show_scale=2, record_path=None):
        self.throughput = throughput
        self.mtu_payload = mtu_payload
        self.cmd_s = cmd_ms / 1000.0
        self.chunk_s = chunk_ms / 1000.0
        self.time_scale = time_scale
        self.headless = headless
        self.show_scale = show_scale
        self.canvas = np.zeros((CANVAS_H, CANVAS_W), dtype=np.uint8)
        # Stats (simulated time = real-hardware prediction)
        self.sim_time = 0.0
        self.sim_bytes = 0
        self.sim_chunks = 0
        self.frames = 0
        self.tiles = 0
        self.clears = 0
        self.texts = 0
        self.wall_start = time.time()
        self.rec = None
        if record_path:
            self.rec = cv2.VideoWriter(
                record_path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (CANVAS_W, CANVAS_H))

    def send_tile(self, x, y, w, h, payload: bytes):
        """Simulate the BLE send of an imgStream tile, then draw it on the canvas."""
        n = chunk_count(len(payload), self.mtu_payload)
        dt = len(payload) / self.throughput + n * self.chunk_s + self.cmd_s
        self.sim_time += dt
        self.sim_bytes += len(payload)
        self.sim_chunks += n
        self.tiles += 1
        if self.time_scale > 0:
            time.sleep(dt * self.time_scale)
        arr = np.frombuffer(payload, dtype=np.uint8).reshape(h, w // 8)
        bits = np.unpackbits(arr, axis=1)[:, :w]
        self.canvas[y:y + h, x:x + w] = bits * 255

    def clear_all(self):
        """Clear the whole screen (CLEAR command, ~5 bytes)."""
        dt = 5 / self.throughput + self.cmd_s
        self.sim_time += dt
        self.sim_bytes += 5
        self.sim_chunks += 1
        if self.time_scale > 0:
            time.sleep(dt * self.time_scale)
        self.canvas[:] = 0

    def send_text(self, x, y, text):
        """Send native 0x37 text (real cost: ~20B + text, 1 command)."""
        n = 20 + len(text.encode("ascii", errors="replace"))
        dt = n / self.throughput + self.cmd_s
        self.sim_time += dt
        self.sim_bytes += n
        self.sim_chunks += 1
        self.texts += 1
        if self.time_scale > 0:
            time.sleep(dt * self.time_scale)
        cv2.putText(self.canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, 255, 1, cv2.LINE_8)

    def clear_tile(self, x, y, w, h):
        """Erase an area (modeled as a single command with no payload,
        the assumed equivalent of a native firmware fillRect/clear)."""
        self.sim_time += self.cmd_s
        self.sim_chunks += 1
        self.tiles += 1
        self.clears += 1
        if self.time_scale > 0:
            time.sleep(self.cmd_s * self.time_scale)
        self.canvas[y:y + h, x:x + w] = 0

    def render(self, overlay_lines, sim_dt):
        if self.rec is not None:
            bgr = cv2.cvtColor(self.canvas, cv2.COLOR_GRAY2BGR)
            for _ in range(max(1, round(sim_dt * 10))):
                self.rec.write(bgr)
        if self.headless:
            return True
        view = cv2.resize(self.canvas, (CANVAS_W * self.show_scale, CANVAS_H * self.show_scale),
                          interpolation=cv2.INTER_NEAREST)
        view = cv2.cvtColor(view, cv2.COLOR_GRAY2BGR)
        for i, line in enumerate(overlay_lines):
            cv2.putText(view, line, (8, 20 + i * 18), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 255, 0), 1, cv2.LINE_AA)
        cv2.imshow("ENGO emulator - q to quit", view)
        return (cv2.waitKey(1) & 0xFF) != ord("q")

    def summary(self):
        wall = time.time() - self.wall_start
        fps = self.frames / self.sim_time if self.sim_time > 0 else 0
        return {
            "frames": self.frames,
            "tiles": self.tiles,
            "clears": self.clears,
            "texts": self.texts,
            "bytes": self.sim_bytes,
            "chunks": self.sim_chunks,
            "sim_time": self.sim_time,
            "sim_fps": fps,
            "sim_latency_ms": (self.sim_time / self.frames * 1000) if self.frames else 0,
            "wall_time": wall,
        }

    def close(self):
        if self.rec is not None:
            self.rec.release()
        if not self.headless:
            cv2.destroyAllWindows()
