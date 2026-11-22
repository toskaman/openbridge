"""
OpenBridge HUD Studio — professional ActiveLook / ENGO MicroOLED emulator.

    python -m src.adapters.hud_studio                 # full UI (default model ENGO 2)
    python -m src.adapters.hud_studio --model "ENGO 3"
    python -m src.adapters.hud_studio --headless      # CI / automation: ports + control API only

What it gives developers and demo teams
  * Pixel-exact 304×256 renderer (shared HUDCanvas engine) with three views:
    Pixels (raw), OLED (bloom + sub-pixel grid) and Lens (additive see-through optics).
  * Phone link on TCP :7789 (raw ActiveLook frames 0xFF … 0xAA, via `adb reverse`), optical
    gestures pushed back to the phone, OpenBridge feature trigger frame 0xF0 <n>.
  * Live frame inspector with protocol decoding + hex dump, layout bank viewer, throughput metrics.
  * F01–F38 feature library + Showcase mode for company demos.
  * Session record (.obsession, JSON lines) and timed replay, PNG / animated GIF capture.
  * JSON control port on 127.0.0.1:7790 — one request per line, e.g.
        {"cmd":"feature","id":"F07"}   {"cmd":"gesture"}   {"cmd":"screenshot"}   {"cmd":"status"}
    python -m src.adapters.hud_studio --send '{"cmd":"gesture"}'
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import pathlib
import queue
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from src.adapters import hud_features as hf
from src.adapters.activelook import ActiveLookAdapter
from src.adapters.activelook_emulator import DISPLAY_H, DISPLAY_W, Frame, HUDCanvas

VERSION = "2.0"
PHONE_PORT = 7789
CONTROL_PORT = 7790
OB_FEATURE_CMD = 0xF0
MODELS = ["ENGO 1", "ENGO 2", "ENGO 3", "ENGO 3 Titanium"]
MONO_TINT = (255, 214, 10)   # ENGO 1/2 MicroOLED emission colour (monochrome yellow)
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
CAPTURE_DIR = PROJECT_ROOT / "captures"

# ── Protocol knowledge ───────────────────────────────────────────────────────

CMD = {
    0x00: "power", 0x01: "clear", 0x02: "grey", 0x03: "demo", 0x04: "test", 0x05: "battery",
    0x06: "vers", 0x08: "led", 0x09: "shift", 0x0A: "settings", 0x10: "luma", 0x20: "sensor",
    0x21: "gesture", 0x22: "als", 0x30: "color", 0x31: "point", 0x32: "line", 0x33: "rect",
    0x34: "rectf", 0x35: "circ", 0x36: "circf", 0x37: "txt", 0x38: "polyline", 0x39: "hold",
    0x3C: "arc", 0x3D: "colour", 0x41: "imgSave", 0x42: "imgDisplay", 0x46: "imgDelete",
    0x50: "fontList", 0x51: "fontSave", 0x60: "layoutSave", 0x61: "layoutDelete",
    0x62: "layoutDisplay", 0x63: "layoutClear", 0x64: "layoutList", 0x65: "layoutPosition",
    0x66: "layoutDisplayExt", 0x69: "layoutClearDisplay", 0x6B: "layoutSaveColor",
    0x70: "gaugeDisplay", 0x71: "gaugeSave", 0x80: "pageSave", 0x82: "pageDelete",
    0x83: "pageDisplay", 0x86: "pageClearDisplay", 0xD0: "cfgWrite", 0xD2: "cfgSet",
    OB_FEATURE_CMD: "ob.feature",
}


def cmd_group(c: int) -> str:
    if c == OB_FEATURE_CMD:
        return "ob"
    if 0x30 <= c <= 0x3D:
        return "text" if c == 0x37 else "draw"
    if 0x60 <= c <= 0x86:
        return "layout"
    return "system"


def _s16(d: bytes, o: int) -> int:
    return struct.unpack_from(">h", d, o)[0]


def _txt(b: bytes) -> str:
    return b.decode("utf-8", "replace").rstrip("\x00")


def decode(f: Frame) -> str:
    c, d = f.cmd, f.data
    try:
        if c in (0x32, 0x33, 0x34) and len(d) >= 8:
            return f"({_s16(d, 0)},{_s16(d, 2)}) → ({_s16(d, 4)},{_s16(d, 6)})"
        if c in (0x35, 0x36) and len(d) >= 5:
            return f"centre ({_s16(d, 0)},{_s16(d, 2)})  r={d[4]}"
        if c == 0x31 and len(d) >= 4:
            return f"({_s16(d, 0)},{_s16(d, 2)})"
        if c == 0x37 and len(d) >= 7:
            return f"({_s16(d, 0)},{_s16(d, 2)}) font {d[5]} col {d[6]}  “{_txt(d[7:])}”"
        if c == 0x62 and d:
            return f"#{d[0]}  “{_txt(d[1:])}”"
        if c == 0x66 and len(d) >= 4:
            return f"#{d[0]} @({_s16(d, 1)},{d[3]})  “{_txt(d[4:])}”"
        if c in (0x61, 0x63, 0x83, 0x86) and d:
            return f"#{d[0]}"
        if c in (0x60, 0x6B) and len(d) >= 17:
            lid, sub, x, y, w, h = struct.unpack_from(">BBHBHB", d)
            return f"#{lid}  {w}×{h} @({x},{y})  font {d[10]}  +{sub} B sub-cmds"
        if c in (0x00, 0x02, 0x10, 0x20, 0x21, 0x22, 0x30, 0x3D) and d:
            return f"{d[0]}"
        if c == 0x70 and len(d) >= 2:
            return f"gauge #{d[0]} = {d[1]}"
        if c == OB_FEATURE_CMD and d:
            feat = hf.resolve(d[0])
            return f"{feat.fid}  {feat.title}" if feat else f"#{d[0]}"
    except Exception:
        pass
    return d[:24].hex(" ") + (" …" if len(d) > 24 else "")


def hexdump(b: bytes, width: int = 16) -> str:
    rows = []
    for o in range(0, len(b), width):
        chunk = b[o:o + width]
        asc = "".join(chr(x) if 32 <= x < 127 else "·" for x in chunk)
        rows.append(f"{o:04X}  {chunk.hex(' '):<{width * 3}} {asc}")
    return "\n".join(rows) or "(empty payload)"


def frame_bytes(cmd: int, payload: bytes = b"") -> bytes:
    n = len(payload) + 5
    if n <= 255:
        return bytes([0xFF, cmd, 0x00, n]) + payload + b"\xAA"
    n += 1
    return bytes([0xFF, cmd, 0x20, n >> 8, n & 0xFF]) + payload + b"\xAA"


# ── Rendering ────────────────────────────────────────────────────────────────

_grid_cache: dict[int, Image.Image] = {}
_lens_cache: dict[tuple, tuple] = {}


def _grid_mask(scale: int) -> Image.Image:
    """Multiplicative mask that darkens the gaps between OLED pixels (sub-pixel look)."""
    if scale in _grid_cache:
        return _grid_cache[scale]
    tile = Image.new("RGB", (scale, scale), (255, 255, 255))
    dr = ImageDraw.Draw(tile)
    gap = (118, 118, 118) if scale >= 4 else (160, 160, 160)
    dr.line([(0, scale - 1), (scale - 1, scale - 1)], fill=gap)
    dr.line([(scale - 1, 0), (scale - 1, scale - 1)], fill=gap)
    row = Image.new("RGB", (DISPLAY_W * scale, scale))
    for x in range(DISPLAY_W):
        row.paste(tile, (x * scale, 0))
    full = Image.new("RGB", (DISPLAY_W * scale, DISPLAY_H * scale))
    for y in range(DISPLAY_H):
        full.paste(row, (0, y * scale))
    _grid_cache[scale] = full
    return full


def _lens_assets(size: tuple[int, int]):
    """Procedural outdoor scene seen through a tinted sports lens + the lens alpha mask."""
    if size in _lens_cache:
        return _lens_cache[size]
    w, h = size
    scene = Image.new("RGB", size)
    dr = ImageDraw.Draw(scene)
    horizon = int(h * 0.56)
    for y in range(h):
        if y < horizon:
            t = y / horizon
            c = (int(22 + 70 * t), int(34 + 80 * t), int(58 + 92 * t))
        else:
            t = (y - horizon) / max(1, h - horizon)
            c = (int(34 - 20 * t), int(44 - 26 * t), int(36 - 22 * t))
        dr.line([(0, y), (w, y)], fill=c)
    # distant ridge
    pts = [(0, horizon)]
    for i in range(0, 41):
        x = i * w / 40
        pts.append((x, horizon - 18 - 22 * abs(((i * 7) % 11) / 11 - 0.5) - 10 * ((i * 3) % 5) / 5))
    pts.append((w, horizon))
    dr.polygon(pts, fill=(30, 40, 52))
    # road in perspective
    cx = w * 0.5
    dr.polygon([(cx - w * 0.03, horizon), (cx + w * 0.03, horizon), (cx + w * 0.62, h), (cx - w * 0.62, h)],
               fill=(46, 50, 56))
    for k in range(8):
        t0, t1 = (k / 8) ** 1.8, ((k + 0.45) / 8) ** 1.8
        y0, y1 = horizon + t0 * (h - horizon), horizon + t1 * (h - horizon)
        hw0, hw1 = 1 + t0 * w * 0.012, 1 + t1 * w * 0.012
        dr.polygon([(cx - hw0, y0), (cx + hw0, y0), (cx + hw1, y1), (cx - hw1, y1)], fill=(150, 150, 120))
    scene = scene.filter(ImageFilter.GaussianBlur(2.5))
    scene = ImageEnhance.Brightness(scene).enhance(0.62)          # lens tint
    tint = Image.new("RGB", size, (14, 10, 40))                    # violet mirror coating
    scene = ImageChops.add(scene, tint)
    # lens mask (soft rounded shield) + vignette
    mask = Image.new("L", size, 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([w * 0.015, h * 0.02, w * 0.985, h * 0.98], radius=int(min(w, h) * 0.16), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) * 0.012))
    vign = Image.new("L", size, 0)
    vd = ImageDraw.Draw(vign)
    vd.ellipse([-w * 0.25, -h * 0.25, w * 1.25, h * 1.25], fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(min(w, h) * 0.18))
    scene = Image.composite(scene, Image.new("RGB", size, (0, 0, 0)), vign)
    # specular streak
    streak = Image.new("L", size, 0)
    sd = ImageDraw.Draw(streak)
    sd.polygon([(w * 0.08, 0), (w * 0.2, 0), (w * 0.02, h * 0.7), (0, h * 0.7)], fill=26)
    streak = streak.filter(ImageFilter.GaussianBlur(min(w, h) * 0.03))
    _lens_cache[size] = (scene, mask, streak)
    return _lens_cache[size]


def render_hud(src: Image.Image, mode: str = "oled", scale: int = 3, luma: int = 10,
               grid: bool = True, bg=(9, 12, 17), mono: bool = False) -> Image.Image:
    """Render the raw 304×256 frame buffer for display. mode: pixels | oled | lens.
    mono=True reproduces the single-colour (yellow) emission of ENGO 1/2 panels."""
    lvl = max(0.12, min(1.0, luma / 15 * 1.25))
    img = src
    if mono:
        img = ImageOps.colorize(src.convert("L"), black=(0, 0, 0), white=MONO_TINT)
    img = img if lvl >= 0.999 else ImageEnhance.Brightness(img).enhance(lvl)
    size = (DISPLAY_W * scale, DISPLAY_H * scale)
    crisp = img.resize(size, Image.NEAREST)
    if grid and scale >= 3 and mode != "lens":
        crisp = ImageChops.multiply(crisp, _grid_mask(scale))
    if mode == "pixels":
        return crisp
    near = img.filter(ImageFilter.GaussianBlur(1.6)).resize(size, Image.BILINEAR)
    far = img.filter(ImageFilter.GaussianBlur(5.5)).resize(size, Image.BILINEAR)
    # "lighten" for the near halo (an unlit glyph inside a lit banner stays dark, as on the real panel),
    # plus a faint additive far scatter for the optical glow.
    out = ImageChops.lighter(crisp, ImageEnhance.Brightness(near).enhance(0.5))
    out = ImageChops.add(out, ImageEnhance.Brightness(far).enhance(0.2))
    if mode == "lens":
        scene, mask, streak = _lens_assets(size)
        out = ImageChops.add(scene, ImageEnhance.Brightness(out).enhance(0.92))
        out = ImageChops.add(out, Image.merge("RGB", (streak, streak, streak)))
        out = Image.composite(out, Image.new("RGB", size, bg), mask)
    return out


# ── Networking ───────────────────────────────────────────────────────────────

class PhoneLink:
    """TCP server for phones / companion apps speaking raw ActiveLook frames."""

    def __init__(self, on_bytes: Callable, on_status: Callable, host: str = "0.0.0.0", port: int = PHONE_PORT):
        self.on_bytes, self.on_status = on_bytes, on_status
        self.host, self.port = host, port
        self.clients: dict[socket.socket, dict] = {}
        self._lock = threading.Lock()
        self._srv: Optional[socket.socket] = None
        self._running = False
        self.error: Optional[str] = None

    def start(self):
        self._running = True
        threading.Thread(target=self._accept_loop, name="phone-link", daemon=True).start()

    def _accept_loop(self):
        try:
            self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._srv.bind((self.host, self.port))
            self._srv.listen(8)
        except OSError as e:
            self.error = f"port {self.port}: {e}"
            self.on_status("error", self.error)
            return
        self.on_status("listening", self.port)
        while self._running:
            try:
                sock, addr = self._srv.accept()
            except OSError:
                break
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            info = {"addr": f"{addr[0]}:{addr[1]}", "since": time.time(), "rx": 0}
            with self._lock:
                self.clients[sock] = info
            self.on_status("connected", info["addr"])
            threading.Thread(target=self._client_loop, args=(sock, info), daemon=True).start()

    def _client_loop(self, sock: socket.socket, info: dict):
        try:
            while self._running:
                data = sock.recv(8192)
                if not data:
                    break
                info["rx"] += len(data)
                self.on_bytes(info["addr"], data)
        except OSError:
            pass
        finally:
            with self._lock:
                self.clients.pop(sock, None)
            try:
                sock.close()
            except OSError:
                pass
            self.on_status("disconnected", info["addr"])

    def broadcast(self, data: bytes) -> int:
        n = 0
        with self._lock:
            socks = list(self.clients)
        for s in socks:
            try:
                s.sendall(data)
                n += 1
            except OSError:
                pass
        return n

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [dict(v) for v in self.clients.values()]

    def stop(self):
        self._running = False
        try:
            if self._srv:
                self._srv.close()
        except OSError:
            pass


class ControlServer:
    """Line-delimited JSON automation API on 127.0.0.1 (no window focus needed)."""

    def __init__(self, engine: "StudioEngine", port: int = CONTROL_PORT):
        self.engine, self.port = engine, port
        self.error: Optional[str] = None

    def start(self):
        threading.Thread(target=self._loop, name="control", daemon=True).start()

    def _loop(self):
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", self.port))
            srv.listen(8)
        except OSError as e:
            self.error = f"control port {self.port}: {e}"
            return
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _serve(self, c: socket.socket):
        with c:
            f = c.makefile("rwb")
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = self.engine.handle_request(json.loads(line))
                except Exception as e:
                    resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                f.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
                f.flush()


def send_control(req: dict, port: int = CONTROL_PORT, timeout: float = 10.0) -> dict:
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall((json.dumps(req) + "\n").encode())
        f = s.makefile("rb")
        return json.loads(f.readline().decode("utf-8"))


# ── Engine (UI-independent, thread-safe through a single pump) ──────────────

@dataclass
class FrameEvent:
    seq: int
    t: float
    source: str
    cmd: int
    data: bytes

    @property
    def name(self) -> str:
        return CMD.get(self.cmd, f"0x{self.cmd:02X}")


class RateMeter:
    def __init__(self, seconds: int = 90):
        self.buckets = collections.deque([(0, 0)] * seconds, maxlen=seconds)
        self.cur_sec = int(time.time())
        self.cur = [0, 0]

    def add(self, nbytes: int = 0, nframes: int = 0):
        self._roll()
        self.cur[0] += nbytes
        self.cur[1] += nframes

    def _roll(self):
        now = int(time.time())
        while self.cur_sec < now:
            self.buckets.append(tuple(self.cur))
            self.cur = [0, 0]
            self.cur_sec += 1
            if now - self.cur_sec > len(self.buckets):
                self.cur_sec = now

    def series(self):
        self._roll()
        return [b[0] for b in self.buckets], [b[1] for b in self.buckets]


class StudioEngine:
    def __init__(self, model: str = "ENGO 2", phone_port: int = PHONE_PORT, control_port: int = CONTROL_PORT):
        self.model = model
        self.hud = HUDCanvas(model=model)
        self.hud.frame_observer = self._on_frame
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.events: collections.deque[FrameEvent] = collections.deque(maxlen=50000)
        self.ui_events: collections.deque[FrameEvent] = collections.deque(maxlen=5000)
        self.cmd_hist: collections.Counter = collections.Counter()
        self.rate = RateMeter()
        self.seq = 0
        self.bytes_in = 0
        self._source = "studio"
        self.dirty = True
        self.listeners: dict[str, list[Callable]] = collections.defaultdict(list)
        self.adapter = ActiveLookAdapter(transport=lambda b: self.ingest(b, "studio"), model=model)
        self.phone = PhoneLink(on_bytes=lambda a, d: self.q.put(("bytes", f"phone {a}", d)),
                               on_status=lambda *a: self.q.put(("phone",) + a), port=phone_port)
        self.control = ControlServer(self, port=control_port)
        self.phone_state = "starting"
        self.recording: Optional[list] = None
        self._rec_t0 = 0.0
        self._replay: collections.deque = collections.deque()
        self._replay_t0 = 0.0
        self.replay_name = ""
        self.last_feature: Optional[hf.Feature] = None
        self.started = time.time()

    # lifecycle
    def start(self):
        self.phone.start()
        self.control.start()

    def stop(self):
        self.phone.stop()

    def on(self, event: str, fn: Callable):
        self.listeners[event].append(fn)

    def _emit(self, event: str, *args):
        for fn in list(self.listeners[event]):
            try:
                fn(*args)
            except Exception as e:  # never let a UI callback kill the pump
                print(f"[HUD Studio] listener {event} failed: {e}", file=sys.stderr)

    # data path (pump thread only)
    def ingest(self, raw: bytes, source: str):
        if source != "studio" and self.last_feature is not None:
            self.last_feature = None          # the panel now shows someone else's content
            self._emit("external", source)
        self.bytes_in += len(raw)
        self.rate.add(nbytes=len(raw))
        if self.recording is not None:
            self.recording.append((round(time.time() - self._rec_t0, 4), source, raw.hex()))
        prev, self._source = self._source, source
        try:
            self.hud.dispatch(raw)
        finally:
            self._source = prev
        self.dirty = True

    def _on_frame(self, f: Frame):
        self.seq += 1
        ev = FrameEvent(self.seq, time.time(), self._source, f.cmd, bytes(f.data))
        self.events.append(ev)
        self.ui_events.append(ev)
        self.cmd_hist[ev.name] += 1
        self.rate.add(nframes=1)
        if f.cmd == OB_FEATURE_CMD and f.data and self._source.startswith("phone"):
            self.q.put(("feature", f.data[0], "phone"))
        if f.cmd in (0x60, 0x61, 0x6B):
            self._emit("layouts")

    def pump(self, budget_s: float = 0.012) -> None:
        end = time.perf_counter() + budget_s
        if self._replay:
            now = time.time() - self._replay_t0
            while self._replay and self._replay[0][0] <= now:
                _, src, data = self._replay.popleft()
                self.ingest(data, f"replay·{src}")
            if not self._replay:
                self._emit("replay", "done")
        while time.perf_counter() < end:
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break
            kind = item[0]
            if kind == "bytes":
                self.ingest(item[2], item[1])
            elif kind == "phone":
                self.phone_state = item[1]
                self._emit("phone", item[1], item[2] if len(item) > 2 else None)
            elif kind == "feature":
                try:
                    self.run_feature(item[1], origin=item[2])
                except KeyError:
                    pass
            elif kind == "call":
                fn, holder = item[1], item[2]
                try:
                    holder["result"] = fn()
                except Exception as e:
                    holder["error"] = e
                holder["event"].set()

    def call_sync(self, fn: Callable, timeout: float = 8.0):
        holder = {"event": threading.Event()}
        self.q.put(("call", fn, holder))
        if not holder["event"].wait(timeout):
            raise TimeoutError("studio pump did not answer")
        if "error" in holder:
            raise holder["error"]
        return holder.get("result")

    # actions (pump thread)
    def set_model(self, model: str):
        self.model = model
        self.hud.model = model
        self.hud._colour_mode = "3" in model
        self.adapter = ActiveLookAdapter(transport=lambda b: self.ingest(b, "studio"), model=model)
        self.dirty = True
        self._emit("model", model)

    def set_luma(self, luma: int):
        self.hud._luma = max(0, min(15, int(luma)))
        self.dirty = True

    def clear(self):
        self.hud._cmd_clear()
        self.dirty = True

    def run_feature(self, ref, origin: str = "studio") -> hf.Feature:
        feat = hf.resolve(ref)
        if feat is None:
            raise KeyError(f"unknown feature {ref!r}")
        self.hud._cmd_clear()
        hf.run_feature(self.adapter, feat)
        self.last_feature = feat
        self.dirty = True
        self._emit("feature", feat, origin)
        return feat

    def gesture(self, code: int = 0x01) -> int:
        n = self.phone.broadcast(bytes([0xFF, 0x0A, 0x01, code & 0xFF, 0xAA]))
        self._emit("gesture", n)
        return n

    def screenshot(self, path: Optional[str] = None, mode: str = "oled", scale: int = 3) -> str:
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = pathlib.Path(path) if path else CAPTURE_DIR / f"hud_{stamp}_{mode}.png"
        img = self.hud._img.copy() if mode == "raw" else render_hud(self.hud._img, mode, scale, self.hud._luma,
                                                                     mono="3" not in self.model)
        img.save(out)
        return str(out)

    def record_start(self):
        self.recording = []
        self._rec_t0 = time.time()
        self._emit("record", True)

    def record_stop(self, path: Optional[str] = None) -> Optional[str]:
        if self.recording is None:
            return None
        rows, self.recording = self.recording, None
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        out = pathlib.Path(path) if path else CAPTURE_DIR / f"session_{_dt.datetime.now():%Y%m%d_%H%M%S}.obsession"
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"format": "openbridge-hud-session", "version": 1, "model": self.model,
                                 "created": _dt.datetime.now().isoformat(), "chunks": len(rows)}) + "\n")
            for t, src, hx in rows:
                fh.write(json.dumps({"t": t, "src": src, "hex": hx}) + "\n")
        self._emit("record", False, str(out))
        return str(out)

    def replay(self, path: str, speed: float = 1.0) -> int:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
        head = json.loads(lines[0])
        if head.get("format") != "openbridge-hud-session":
            raise ValueError("not an .obsession file")
        self._replay = collections.deque(
            (row["t"] / max(0.05, speed), row["src"], bytes.fromhex(row["hex"]))
            for row in map(json.loads, lines[1:]) if row.get("hex"))
        self._replay_t0 = time.time()
        self.replay_name = pathlib.Path(path).name
        self.clear()
        self._emit("replay", "start")
        return len(self._replay)

    def status(self) -> dict:
        fill = self.hud.compute_pixel_fill()
        pwr = self.hud.estimate_power_mw()
        return {"version": VERSION, "model": self.model, "frames": self.seq, "bytes": self.bytes_in,
                "phones": self.phone.snapshot(), "phone_state": self.phone_state,
                "fill_pct": round(fill, 2), "power_mw": round(pwr, 3),
                "battery_h": int(425 / max(0.1, pwr)), "luma": self.hud._luma,
                "recording": self.recording is not None, "replaying": bool(self._replay),
                "last_feature": self.last_feature.fid if self.last_feature else None,
                "uptime_s": int(time.time() - self.started)}

    # control API (control thread → pump)
    def handle_request(self, req: dict) -> dict:
        cmd = str(req.get("cmd", "")).lower()
        if cmd == "ping":
            return {"ok": True, "version": VERSION}
        if cmd == "features":
            return {"ok": True, "features": [
                {"id": f.fid, "key": f.key, "title": f.title, "category": f.category} for f in hf.FEATURES]}
        actions = {
            "status": lambda: self.status(),
            "gesture": lambda: {"phones": self.gesture(int(req.get("code", 1)))},
            "feature": lambda: {"feature": self.run_feature(req.get("id")).fid},
            "clear": lambda: self.clear(),
            "screenshot": lambda: {"path": self.screenshot(req.get("path"), req.get("mode", "oled"),
                                                            int(req.get("scale", 3)))},
            "record": lambda: (self.record_start() or {"recording": True}) if req.get("action", "start") == "start"
            else {"path": self.record_stop(req.get("path"))},
            "replay": lambda: {"chunks": self.replay(req["path"], float(req.get("speed", 1.0)))},
            "model": lambda: self.set_model(req["model"]),
            "luma": lambda: self.set_luma(req["value"]),
            "inject": lambda: self.ingest(bytes.fromhex(req["hex"]), "control"),
            # UI automation (demos / screenshots): ignored in --headless
            "view": lambda: self._emit("ui", "view", req["mode"]),
            "zoom": lambda: self._emit("ui", "zoom", req["value"]),
            "tab": lambda: self._emit("ui", "tab", req["name"]),
            "showcase": lambda: self._emit("ui", "showcase", bool(req.get("on", True))),
        }
        if cmd not in actions:
            return {"ok": False, "error": f"unknown cmd {cmd!r}", "commands": sorted(list(actions) + ["ping", "features"])}
        res = self.call_sync(actions[cmd])
        out = {"ok": True}
        if isinstance(res, dict):
            out.update(res)
        return out


# ── UI ───────────────────────────────────────────────────────────────────────

THEME = {
    "bg": "#07090D", "panel": "#0D1117", "panel2": "#121822", "raise": "#18202B", "line": "#1F2935",
    "text": "#DCE3EC", "dim": "#8592A3", "faint": "#4D5868", "accent": "#E4F222", "ink": "#0A0D12",
    "cyan": "#22D3EE", "green": "#34D399", "red": "#F43F5E", "amber": "#F59E0B", "violet": "#A78BFA",
}
GROUP_COLOUR = {"draw": "#22D3EE", "text": "#E4F222", "layout": "#A78BFA", "system": "#8592A3", "ob": "#34D399"}


def _mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(x + (y - x) * t):02X}" for x, y in zip(a, b))


class HUDStudioApp:
    def __init__(self, engine: StudioEngine, scale="fit", mode: str = "oled"):
        import tkinter as tk
        from tkinter import font as tkfont, ttk
        self.tk, self.ttk = tk, ttk
        self.e = engine
        self.zoom, self.mode, self.grid = scale, mode, True
        self.s = 3.0          # effective on-screen scale (fractional when zoom == "fit")
        try:  # crisp text on Windows
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.root = tk.Tk()
        self.root.title(f"OpenBridge HUD Studio {VERSION}")
        self.root.configure(bg=THEME["bg"])
        self.root.geometry("1720x1010")
        self.root.minsize(1280, 820)
        self.root.after(80, self._maximise)
        fams = set(tkfont.families())
        ui = next((f for f in ("Segoe UI Variable Display", "Segoe UI", "Inter", "Helvetica") if f in fams), "TkDefaultFont")
        mono = next((f for f in ("Cascadia Code", "Cascadia Mono", "JetBrains Mono", "Consolas", "Courier New") if f in fams), "TkFixedFont")
        self.f_ui = (ui, 10)
        self.f_ui_b = (ui, 10, "bold")
        self.f_small = (ui, 9)
        self.f_title = (ui, 15, "bold")
        self.f_big = (ui, 22, "bold")
        self.f_mono = (mono, 9)
        self.f_mono_b = (mono, 10, "bold")
        self._icon()
        self._style()
        self._photo = None
        self._img_origin = (0, 0)
        self._caption_items: list = []
        self._showcase = None
        self._gif_frames: Optional[list] = None
        self._last_render = 0.0
        self._inspector_paused = False
        self._filter = ""
        self._build()
        self._bind_keys()
        for ev, fn in (("phone", self._on_phone), ("feature", self._on_feature), ("gesture", self._on_gesture),
                       ("record", self._on_record), ("replay", self._on_replay), ("layouts", self._refresh_layouts),
                       ("ui", self._on_ui), ("external", self._on_external)):
            engine.on(ev, fn)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self.root.after(15, self._tick)
        self.root.after(1000, self._tick_slow)

    def _maximise(self, attempt: int = 0):
        try:
            self.root.update_idletasks()
            self.root.state("zoomed")      # Windows: open maximised
        except Exception:
            try:
                self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight() - 80}+0+0")
            except Exception:
                pass
        if attempt < 2 and self.root.state() != "zoomed":
            self.root.after(400, self._maximise, attempt + 1)

    # ---------- look & feel ----------
    def _icon(self):
        try:
            from PIL import ImageTk
            im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.ellipse([2, 2, 62, 62], fill=(228, 242, 34, 255))
            d.ellipse([16, 16, 48, 48], outline=(10, 13, 18, 255), width=6)
            d.rectangle([29, 6, 35, 24], fill=(10, 13, 18, 255))
            self._icon_img = ImageTk.PhotoImage(im)
            self.root.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _style(self):
        st = self.ttk.Style(self.root)
        st.theme_use("clam")
        T = THEME
        st.configure(".", background=T["panel"], foreground=T["text"], fieldbackground=T["panel2"],
                     bordercolor=T["line"], lightcolor=T["panel"], darkcolor=T["panel"], font=self.f_ui)
        st.configure("Treeview", background=T["panel"], fieldbackground=T["panel"], foreground=T["text"],
                     rowheight=22, borderwidth=0, font=self.f_mono)
        st.map("Treeview", background=[("selected", T["raise"])], foreground=[("selected", T["accent"])])
        st.configure("Treeview.Heading", background=T["panel2"], foreground=T["dim"], relief="flat",
                     font=self.f_small, padding=(6, 4))
        st.map("Treeview.Heading", background=[("active", T["raise"])])
        st.configure("TNotebook", background=T["panel"], borderwidth=0, tabmargins=(8, 6, 8, 0))
        st.configure("TNotebook.Tab", background=T["panel"], foreground=T["dim"], padding=(14, 7),
                     borderwidth=0, font=self.f_ui_b)
        st.map("TNotebook.Tab", background=[("selected", T["panel2"])], foreground=[("selected", T["accent"])])
        st.configure("Vertical.TScrollbar", background=T["raise"], troughcolor=T["panel"], bordercolor=T["panel"],
                     arrowcolor=T["dim"], gripcount=0, relief="flat", width=10)
        st.configure("Horizontal.TScale", background=T["panel2"], troughcolor=T["raise"])

    def _btn(self, parent, text, cmd, kind="ghost", width=None, tip=None):
        tk, T = self.tk, THEME
        palette = {"ghost": (T["panel2"], T["text"], T["raise"]), "accent": (T["accent"], T["ink"], "#F2FF55"),
                   "danger": ("#2A1219", "#FF8FA3", "#3A1822"), "on": (T["raise"], T["accent"], T["line"])}
        bg, fg, hov = palette[kind]
        b = tk.Label(parent, text=text, bg=bg, fg=fg, font=self.f_ui_b, padx=12, pady=6, cursor="hand2")
        if width:
            b.configure(width=width)
        b._kind = kind
        b.bind("<Enter>", lambda e: b.configure(bg=palette[b._kind][2]))
        b.bind("<Leave>", lambda e: b.configure(bg=palette[b._kind][0]))
        b.bind("<Button-1>", lambda e: cmd())

        def set_kind(k):
            b._kind = k
            b.configure(bg=palette[k][0], fg=palette[k][1])
        b.set_kind = set_kind
        if tip:
            b.bind("<Enter>", lambda e, t=tip: (b.configure(bg=palette[b._kind][2]), self._status(t)), add="+")
        return b

    def _segmented(self, parent, options, current, on_change):
        tk, T = self.tk, THEME
        frame = tk.Frame(parent, bg=T["line"], padx=1, pady=1)
        labels = {}

        def pick(v):
            for k, l in labels.items():
                l.configure(bg=T["accent"] if k == v else T["panel2"], fg=T["ink"] if k == v else T["dim"])
            on_change(v)
        for v, txt in options:
            l = tk.Label(frame, text=txt, font=self.f_ui_b, padx=11, pady=5, cursor="hand2",
                         bg=T["accent"] if v == current else T["panel2"], fg=T["ink"] if v == current else T["dim"])
            l.pack(side="left", padx=(0, 1))
            l.bind("<Button-1>", lambda e, v=v: pick(v))
            labels[v] = l
        frame.pick = pick
        return frame

    # ---------- layout ----------
    def _build(self):
        tk, ttk, T = self.tk, self.ttk, THEME
        # header
        head = tk.Frame(self.root, bg=T["bg"], height=64)
        head.pack(fill="x", side="top")
        logo = tk.Canvas(head, width=44, height=44, bg=T["bg"], highlightthickness=0)
        logo.pack(side="left", padx=(18, 10), pady=10)
        logo.create_oval(2, 2, 42, 42, fill=T["accent"], outline="")
        logo.create_oval(12, 12, 32, 32, outline=T["ink"], width=4)
        logo.create_rectangle(20, 5, 24, 18, fill=T["ink"], outline="")
        tb = tk.Frame(head, bg=T["bg"])
        tb.pack(side="left")
        tk.Label(tb, text="OpenBridge HUD Studio", font=self.f_title, fg=T["text"], bg=T["bg"]).pack(anchor="w")
        tk.Label(tb, text=f"ActiveLook · ENGO MicroOLED 304×256 emulator  ·  v{VERSION}", font=self.f_small,
                 fg=T["dim"], bg=T["bg"]).pack(anchor="w")
        pills = tk.Frame(head, bg=T["bg"])
        pills.pack(side="right", padx=18)
        self.pill_phone = tk.Label(pills, text="●  Phone link starting…", font=self.f_ui_b, fg=T["amber"],
                                   bg=T["panel2"], padx=12, pady=6)
        self.pill_phone.pack(side="left", padx=4)
        self.pill_ctrl = tk.Label(pills, text=f"API  127.0.0.1:{self.e.control.port}", font=self.f_ui_b,
                                  fg=T["dim"], bg=T["panel2"], padx=12, pady=6)
        self.pill_ctrl.pack(side="left", padx=4)
        self.pill_rec = tk.Label(pills, text="", font=self.f_ui_b, fg=T["red"], bg=T["bg"], padx=8)
        self.pill_rec.pack(side="left", padx=4)

        # toolbar
        bar = tk.Frame(self.root, bg=T["panel"], height=48)
        bar.pack(fill="x", side="top")
        inner = tk.Frame(bar, bg=T["panel"])
        inner.pack(fill="x", padx=14, pady=8)
        self._lbl(inner, "MODEL").pack(side="left", padx=(0, 6))
        self.seg_model = self._segmented(inner, [(m, m.replace("ENGO 3 Titanium", "ENGO 3 Ti")) for m in MODELS],
                                         self.e.model, lambda m: self.e.set_model(m) or self._update_bezel())
        self.seg_model.pack(side="left", padx=(0, 18))
        self._lbl(inner, "VIEW").pack(side="left", padx=(0, 6))
        self.seg_view = self._segmented(inner, [("pixels", "Pixels"), ("oled", "OLED"), ("lens", "Lens")], self.mode,
                                        self._set_mode)
        self.seg_view.pack(side="left", padx=(0, 18))
        self._lbl(inner, "ZOOM").pack(side="left", padx=(0, 6))
        self.seg_zoom = self._segmented(inner, [("fit", "Fit"), (2, "2×"), (3, "3×"), (4, "4×")], self.zoom, self._set_scale)
        self.seg_zoom.pack(side="left", padx=(0, 10))
        self.btn_grid = self._btn(inner, "▦ Grid", self._toggle_grid, "on")
        self.btn_grid.pack(side="left", padx=(0, 18))
        right = tk.Frame(inner, bg=T["panel"])
        right.pack(side="right")
        self._btn(right, "👋  Wave", lambda: self.e.gesture(), "accent", tip="Optical wave to the phone  [G]").pack(side="left", padx=3)
        self._btn(right, "⌫  Clear", self.e.clear, tip="Clear the panel  [C]").pack(side="left", padx=3)
        self._btn(right, "📷  PNG", self._screenshot, tip="Save PNG (current view + raw buffer)  [S]").pack(side="left", padx=3)
        self.btn_gif = self._btn(right, "🎞  GIF", self._toggle_gif, tip="Start / stop animated GIF  [F]")
        self.btn_gif.pack(side="left", padx=3)
        self.btn_rec = self._btn(right, "●  Rec", self._toggle_record, "danger", tip="Record an .obsession  [R]")
        self.btn_rec.pack(side="left", padx=3)
        self.btn_show = self._btn(right, "▶  Showcase", self._toggle_showcase, tip="Auto-tour the visible features  [Space]")
        self.btn_show.pack(side="left", padx=3)

        # body
        body = tk.PanedWindow(self.root, orient="horizontal", bg=T["bg"], sashwidth=4, bd=0, sashrelief="flat")
        body.pack(fill="both", expand=True)
        left = tk.Frame(body, bg=T["panel"], width=330)
        center = tk.Frame(body, bg=T["bg"])
        rightp = tk.Frame(body, bg=T["panel"], width=470)
        body.add(left, minsize=280, width=330)
        body.add(center, minsize=640, stretch="always")
        body.add(rightp, minsize=380, width=470)
        self._build_library(left)
        self._build_viewport(center)
        self._build_tabs(rightp)

        # footer
        foot = tk.Frame(self.root, bg=T["panel"], height=30)
        foot.pack(fill="x", side="bottom")
        self.status_l = tk.Label(foot, text="Ready.", font=self.f_small, fg=T["dim"], bg=T["panel"], anchor="w")
        self.status_l.pack(side="left", padx=14, pady=5)
        self.metrics_l = tk.Label(foot, text="", font=self.f_mono, fg=T["text"], bg=T["panel"], anchor="e")
        self.metrics_l.pack(side="right", padx=14)

    def _lbl(self, parent, text):
        return self.tk.Label(parent, text=text, font=(self.f_small[0], 8, "bold"), fg=THEME["faint"], bg=parent["bg"])

    # ---------- feature library ----------
    def _build_library(self, parent):
        tk, T = self.tk, THEME
        top = tk.Frame(parent, bg=T["panel"])
        top.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(top, text="Feature library", font=self.f_ui_b, fg=T["text"], bg=T["panel"]).pack(side="left")
        tk.Label(top, text=f"{len(hf.FEATURES)} scenarios", font=self.f_small, fg=T["faint"], bg=T["panel"]).pack(side="right")
        sf = tk.Frame(parent, bg=T["line"], padx=1, pady=1)
        sf.pack(fill="x", padx=14, pady=(0, 8))
        self.search_var = tk.StringVar()
        ent = tk.Entry(sf, textvariable=self.search_var, bg=T["panel2"], fg=T["text"], insertbackground=T["accent"],
                       relief="flat", font=self.f_ui)
        ent.pack(fill="x", ipady=6, padx=(8, 0))
        ph = "Search  F01–F38, title, key…"

        def _ph_in(_e):
            if ent.get() == ph:
                ent.delete(0, "end")
                ent.configure(fg=T["text"])

        def _ph_out(_e):
            if not ent.get():
                ent.insert(0, ph)
                ent.configure(fg=T["faint"])
        ent.insert(0, ph)
        ent.configure(fg=T["faint"])
        ent.bind("<FocusIn>", _ph_in)
        ent.bind("<FocusOut>", _ph_out)
        self._search_ph = ph
        self.search_var.trace_add("write", lambda *a: self._draw_library())
        chips = tk.Frame(parent, bg=T["panel"])
        chips.pack(fill="x", padx=12, pady=(0, 8))
        self.cat_filter = None
        self._chip_widgets = {}
        short = {"home": "Home", "sport": "Sport", "pro": "Pro", "safety": "Safety", "ai": "AI"}
        for key, (label, colour) in [(None, ("All", T["text"]))] + list(hf.CATEGORIES.items()):
            c = tk.Label(chips, text=short.get(key, "All"), font=self.f_small, padx=7, pady=3, cursor="hand2",
                         bg=T["panel2"], fg=colour)
            c.pack(side="left", padx=2, pady=2)
            c.bind("<Button-1>", lambda e, k=key: self._set_cat(k))
            self._chip_widgets[key] = c
        self._set_cat(None, redraw=False)
        wrap = tk.Frame(parent, bg=T["panel"])
        wrap.pack(fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        self.lib = tk.Canvas(wrap, bg=T["panel"], highlightthickness=0)
        sb = self.ttk.Scrollbar(wrap, orient="vertical", command=self.lib.yview)
        self.lib.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.lib.pack(side="left", fill="both", expand=True)
        self.lib.bind("<Configure>", lambda e: self._draw_library())
        self.lib.bind("<MouseWheel>", lambda e: self.lib.yview_scroll(int(-e.delta / 120) * 2, "units"))
        self.lib.bind("<Motion>", self._lib_hover)
        self.lib.bind("<Leave>", lambda e: self._lib_hover(None))
        self.lib.bind("<Button-1>", self._lib_click)
        self._lib_rows: list[tuple[int, hf.Feature]] = []
        self._lib_hot = None
        self._lib_active = None
        self._draw_library()

    def _set_cat(self, key, redraw=True):
        self.cat_filter = key
        for k, w in self._chip_widgets.items():
            w.configure(bg=THEME["raise"] if k == key else THEME["panel2"],
                        relief="flat", font=(self.f_small[0], 9, "bold" if k == key else "normal"))
        if redraw:
            self._draw_library()

    def _visible_features(self):
        q = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        if q == getattr(self, "_search_ph", "").lower():
            q = ""
        out = []
        for f in hf.FEATURES:
            if self.cat_filter and f.category != self.cat_filter:
                continue
            if q and q not in f.title.lower() and q not in f.fid.lower() and q not in f.key:
                continue
            out.append(f)
        return out

    def _draw_library(self):
        c, T = self.lib, THEME
        c.delete("all")
        w = max(200, c.winfo_width() - 6)
        y, rh = 2, 46
        self._lib_rows = []
        for f in self._visible_features():
            colour = hf.CATEGORIES[f.category][1]
            hot = f is self._lib_hot
            act = f is self._lib_active
            bg = T["raise"] if (hot or act) else T["panel"]
            c.create_rectangle(4, y, w, y + rh - 4, fill=bg, outline=T["line"] if act else bg, tags=("row",))
            c.create_rectangle(4, y, 7, y + rh - 4, fill=colour, outline="")
            c.create_text(18, y + rh / 2 - 2, text=f.fid, anchor="w", font=self.f_mono_b,
                          fill=T["accent"] if act else T["dim"])
            c.create_text(62, y + rh / 2 - 2, text=f.icon, anchor="w", font=(self.f_ui[0], 13), fill=colour)
            c.create_text(92, y + 13, text=f.title, anchor="w", font=self.f_ui_b, fill=T["text"])
            c.create_text(92, y + 30, text=hf.CATEGORIES[f.category][0], anchor="w", font=self.f_small, fill=T["faint"])
            if hot:
                c.create_text(w - 12, y + rh / 2 - 2, text="▶", anchor="e", font=self.f_ui_b, fill=T["accent"])
            self._lib_rows.append((y, f))
            y += rh
        c.configure(scrollregion=(0, 0, w, y + 6))

    def _row_at(self, event):
        if event is None:
            return None
        y = self.lib.canvasy(event.y)
        for top, f in self._lib_rows:
            if top <= y < top + 42:
                return f
        return None

    def _lib_hover(self, event):
        f = self._row_at(event)
        if f is not self._lib_hot:
            self._lib_hot = f
            self._draw_library()

    def _lib_click(self, event):
        f = self._row_at(event)
        if f:
            self._stop_showcase()
            self.e.run_feature(f.fid)

    # ---------- viewport ----------
    def _build_viewport(self, parent):
        tk, T = self.tk, THEME
        self.view = tk.Canvas(parent, bg=T["bg"], highlightthickness=0)
        self.view.pack(fill="both", expand=True)
        self.view.bind("<Configure>", lambda e: self._layout_view())
        self.view.bind("<Motion>", self._view_motion)
        self.view.bind("<Leave>", lambda e: self.view.itemconfigure(self.v_probe, text=""))
        self.v_shadow = [self.view.create_rectangle(0, 0, 0, 0, outline="", fill=_mix(T["bg"], "#000000", 0.4 + i * 0.2))
                         for i in range(3)]
        self.v_frame = self.view.create_rectangle(0, 0, 0, 0, outline=T["line"], width=1)
        self.v_img = self.view.create_image(0, 0, anchor="nw")
        self.v_bezel = self.view.create_text(0, 0, anchor="sw", font=self.f_small, fill=T["dim"])
        self.v_bezel_r = self.view.create_text(0, 0, anchor="se", font=self.f_small, fill=T["faint"])
        self.v_probe = self.view.create_text(0, 0, anchor="nw", font=self.f_mono, fill=T["dim"])
        self.v_hint = self.view.create_text(0, 0, anchor="ne", font=self.f_small, fill=T["faint"],
                                            text="G wave · C clear · S png · F gif · R record · Space showcase")
        self.v_sensor = self.view.create_oval(0, 0, 0, 0, outline=T["faint"], width=1)
        self._update_bezel()

    def _update_bezel(self):
        m = self.e.model
        colour = "81-colour palette" if "3" in m else "16 grey levels · yellow"
        self.view.itemconfigure(self.v_bezel, text=f"{m}   ·   MicroOLED 304×256   ·   {colour}")

    def _layout_view(self):
        v = self.view
        W, H = v.winfo_width(), v.winfo_height()
        if self.zoom == "fit":
            self.s = max(1.0, min((W - 80) / DISPLAY_W, (H - 200) / DISPLAY_H, 6.0))
        else:
            self.s = float(self.zoom)
        iw, ih = round(DISPLAY_W * self.s), round(DISPLAY_H * self.s)
        ox, oy = max(20, (W - iw) // 2), max(48, (H - ih) // 2 - 10)
        self._img_origin = (ox, oy)
        for i, item in enumerate(self.v_shadow):
            pad = 14 - i * 5
            v.coords(item, ox - pad, oy - pad + 4, ox + iw + pad, oy + ih + pad + 8)
        v.coords(self.v_frame, ox - 1, oy - 1, ox + iw, oy + ih)
        v.coords(self.v_img, ox, oy)
        v.coords(self.v_bezel, ox, oy - 12)
        v.coords(self.v_bezel_r, ox + iw, oy - 12)
        v.coords(self.v_probe, ox, oy + ih + 14)
        v.coords(self.v_hint, ox + iw, oy + ih + 14)
        v.coords(self.v_sensor, ox + iw - 30, oy - 30, ox + iw - 18, oy - 18)
        self.e.dirty = True

    def _view_motion(self, event):
        ox, oy = self._img_origin
        x, y = int((event.x - ox) / self.s), int((event.y - oy) / self.s)
        if 0 <= x < DISPLAY_W and 0 <= y < DISPLAY_H:
            r, g, b = self.e.hud._img.getpixel((x, y))[:3]
            grey = round((0.299 * r + 0.587 * g + 0.114 * b) / 255 * 15)
            self.view.itemconfigure(self.v_probe, text=f"x {x:3d}   y {y:3d}   #{r:02X}{g:02X}{b:02X}   grey {grey:2d}/15")
        else:
            self.view.itemconfigure(self.v_probe, text="")

    def _render(self):
        from PIL import ImageTk
        n = max(1, min(5, int(self.s)))
        img = render_hud(self.e.hud._img, self.mode, n, self.e.hud._luma, self.grid, bg=(7, 9, 13),
                         mono="3" not in self.e.model)
        target = (round(DISPLAY_W * self.s), round(DISPLAY_H * self.s))
        if img.size != target:
            img = img.resize(target, Image.BILINEAR if self.mode != "pixels" else Image.NEAREST)
        self._photo = ImageTk.PhotoImage(img)
        self.view.itemconfigure(self.v_img, image=self._photo)
        if self._gif_frames is not None and len(self._gif_frames) < 900:
            self._gif_frames.append(img.resize((img.width // 2, img.height // 2), Image.BILINEAR))

    # ---------- right tabs ----------
    def _build_tabs(self, parent):
        tk, ttk, T = self.tk, self.ttk, THEME
        nb = ttk.Notebook(parent)
        self.nb = nb
        nb.pack(fill="both", expand=True, padx=(0, 0), pady=(8, 0))
        self._build_inspector(nb)
        self._build_metrics(nb)
        self._build_layouts(nb)
        self._build_session(nb)
        self._build_device(nb)

    def _build_inspector(self, nb):
        tk, ttk, T = self.tk, self.ttk, THEME
        tab = tk.Frame(nb, bg=T["panel2"])
        nb.add(tab, text="Inspector")
        tools = tk.Frame(tab, bg=T["panel2"])
        tools.pack(fill="x", padx=10, pady=8)
        self.btn_pause = self._btn(tools, "❚❚ Pause", self._toggle_pause)
        self.btn_pause.pack(side="left")
        self._btn(tools, "Clear", self._clear_inspector).pack(side="left", padx=6)
        self._btn(tools, "Export CSV", self._export_csv).pack(side="left")
        fv = tk.StringVar()
        fe = tk.Entry(tools, textvariable=fv, bg=T["raise"], fg=T["text"], insertbackground=T["accent"],
                      relief="flat", font=self.f_mono, width=14)
        fe.pack(side="right", ipady=5)
        self._lbl(tools, "FILTER").pack(side="right", padx=6)
        fv.trace_add("write", lambda *a: setattr(self, "_filter", fv.get().strip().lower()))
        cols = ("seq", "time", "src", "cmd", "len", "decoded")
        wrap = tk.Frame(tab, bg=T["panel2"])
        wrap.pack(fill="both", expand=True, padx=10)
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for c, w, anchor in (("seq", 54, "e"), ("time", 92, "w"), ("src", 74, "w"), ("cmd", 118, "w"),
                             ("len", 40, "e"), ("decoded", 380, "w")):
            self.tree.heading(c, text=c.upper(), anchor=anchor)
            self.tree.column(c, width=w, anchor=anchor, stretch=(c == "decoded"))
        for g, colour in GROUP_COLOUR.items():
            self.tree.tag_configure(g, foreground=colour)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._inspect_selected)
        self.detail = tk.Text(tab, height=9, bg=T["panel"], fg=T["text"], relief="flat", font=self.f_mono,
                              insertbackground=T["accent"], padx=10, pady=8)
        self.detail.pack(fill="x", padx=10, pady=10)
        self.detail.insert("1.0", "Select a frame to see its decoded fields and hex dump.")
        self._tree_index: dict[str, FrameEvent] = {}

    def _build_metrics(self, nb):
        tk, T = self.tk, THEME
        tab = tk.Frame(nb, bg=T["panel2"])
        nb.add(tab, text="Metrics")
        cards = tk.Frame(tab, bg=T["panel2"])
        cards.pack(fill="x", padx=10, pady=10)
        self.cards = {}
        for i, (key, label) in enumerate((("fps", "frames / s"), ("bps", "bytes / s"), ("fill", "pixel fill"),
                                          ("pwr", "panel power"), ("bat", "est. battery"), ("total", "frames total"))):
            card = tk.Frame(cards, bg=T["panel"], padx=12, pady=10)
            card.grid(row=i // 3, column=i % 3, sticky="nsew", padx=4, pady=4)
            cards.columnconfigure(i % 3, weight=1)
            v = tk.Label(card, text="—", font=self.f_big, fg=T["text"], bg=T["panel"])
            v.pack(anchor="w")
            tk.Label(card, text=label.upper(), font=(self.f_small[0], 8, "bold"), fg=T["faint"], bg=T["panel"]).pack(anchor="w")
            self.cards[key] = v
        self.chart = tk.Canvas(tab, bg=T["panel"], highlightthickness=0, height=170)
        self.chart.pack(fill="x", padx=14, pady=(6, 6))
        self.hist = tk.Canvas(tab, bg=T["panel"], highlightthickness=0)
        self.hist.pack(fill="both", expand=True, padx=14, pady=(6, 14))

    def _build_layouts(self, nb):
        tk, ttk, T = self.tk, self.ttk, THEME
        tab = tk.Frame(nb, bg=T["panel2"])
        nb.add(tab, text="Layouts")
        tk.Label(tab, text="Layout bank pushed by the app (cmd 0x60 layoutSave)", font=self.f_small,
                 fg=T["dim"], bg=T["panel2"]).pack(anchor="w", padx=12, pady=(10, 4))
        cols = ("id", "x", "y", "w", "h", "font", "fore", "back", "subcmds")
        self.ltree = ttk.Treeview(tab, columns=cols, show="headings")
        for c in cols:
            self.ltree.heading(c, text=c.upper())
            self.ltree.column(c, width=48 if c != "subcmds" else 80, anchor="e")
        self.ltree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _build_session(self, nb):
        tk, T = self.tk, THEME
        tab = tk.Frame(nb, bg=T["panel2"])
        nb.add(tab, text="Session")
        pad = dict(padx=14, pady=6, anchor="w")
        tk.Label(tab, text="Record & replay", font=self.f_ui_b, fg=T["text"], bg=T["panel2"]).pack(**pad)
        tk.Label(tab, text="Every byte from the phone, the control API and the feature library is captured with\n"
                           "its timestamp into an .obsession file (JSON lines) you can replay, diff or attach to a bug.",
                 justify="left", font=self.f_small, fg=T["dim"], bg=T["panel2"]).pack(**pad)
        row = tk.Frame(tab, bg=T["panel2"])
        row.pack(**pad)
        self.btn_rec2 = self._btn(row, "●  Start recording", self._toggle_record, "danger")
        self.btn_rec2.pack(side="left")
        self._btn(row, "▶  Load & replay…", self._load_replay).pack(side="left", padx=6)
        self.speed = 1.0
        self._segmented(row, [(0.5, "0.5×"), (1.0, "1×"), (2.0, "2×"), (4.0, "4×")], 1.0,
                        lambda v: setattr(self, "speed", v)).pack(side="left", padx=6)
        self.session_l = tk.Label(tab, text="Idle.", font=self.f_mono, fg=T["dim"], bg=T["panel2"])
        self.session_l.pack(**pad)
        tk.Label(tab, text="Captures", font=self.f_ui_b, fg=T["text"], bg=T["panel2"]).pack(padx=14, pady=(18, 4), anchor="w")
        self.cap_list = tk.Listbox(tab, bg=T["panel"], fg=T["text"], selectbackground=T["raise"],
                                   selectforeground=T["accent"], relief="flat", font=self.f_mono, height=14,
                                   highlightthickness=0, activestyle="none")
        self.cap_list.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self.cap_list.bind("<Double-Button-1>", self._open_capture)
        row2 = tk.Frame(tab, bg=T["panel2"])
        row2.pack(padx=14, pady=(0, 12), anchor="w")
        self._btn(row2, "Open folder", self._open_capture_dir).pack(side="left")
        self._btn(row2, "Refresh", self._refresh_captures).pack(side="left", padx=6)
        self._refresh_captures()

    def _build_device(self, nb):
        tk, ttk, T = self.tk, self.ttk, THEME
        tab = tk.Frame(nb, bg=T["panel2"])
        nb.add(tab, text="Device")
        pad = dict(padx=14, pady=5, anchor="w")
        tk.Label(tab, text="Display", font=self.f_ui_b, fg=T["text"], bg=T["panel2"]).pack(**pad)
        lrow = tk.Frame(tab, bg=T["panel2"])
        lrow.pack(fill="x", padx=14)
        self._lbl(lrow, "LUMA").pack(side="left")
        self.luma_var = tk.IntVar(value=self.e.hud._luma)
        self.luma_val = tk.Label(lrow, text=str(self.e.hud._luma), font=self.f_mono_b, fg=T["accent"], bg=T["panel2"], width=3)
        sc = ttk.Scale(lrow, from_=0, to=15, orient="horizontal", variable=self.luma_var,
                       command=lambda v: (self.e.set_luma(round(float(v))), self.luma_val.configure(text=str(round(float(v))))))
        sc.pack(side="left", fill="x", expand=True, padx=10)
        self.luma_val.pack(side="left")
        tk.Label(tab, text="Phone link", font=self.f_ui_b, fg=T["text"], bg=T["panel2"]).pack(padx=14, pady=(18, 4), anchor="w")
        self.phones_l = tk.Label(tab, text="No phone connected.", justify="left", font=self.f_mono, fg=T["dim"], bg=T["panel2"])
        self.phones_l.pack(**pad)
        tk.Label(tab, text="Quick start (USB)", font=self.f_ui_b, fg=T["text"], bg=T["panel2"]).pack(padx=14, pady=(18, 4), anchor="w")
        cmds = (f"adb reverse tcp:{self.e.phone.port} tcp:{self.e.phone.port}\n"
                f"python -m src.adapters.hud_studio --send '{{\"cmd\":\"feature\",\"id\":\"F07\"}}'\n"
                f"python -m src.adapters.hud_studio --send '{{\"cmd\":\"gesture\"}}'")
        box = tk.Text(tab, height=4, bg=T["panel"], fg=T["cyan"], relief="flat", font=self.f_mono, padx=10, pady=8)
        box.insert("1.0", cmds)
        box.configure(state="disabled")
        box.pack(fill="x", padx=14, pady=4)
        self._btn(tab, "Copy commands", lambda: (self.root.clipboard_clear(), self.root.clipboard_append(cmds),
                                                 self._status("Commands copied."))).pack(padx=14, pady=4, anchor="w")
        tk.Label(tab, text="Protocol", font=self.f_ui_b, fg=T["text"], bg=T["panel2"]).pack(padx=14, pady=(18, 4), anchor="w")
        tk.Label(tab, text="Phone → PC   0xFF CMD FMT LEN [QID] DATA 0xAA (ActiveLook)\n"
                           "PC → Phone   0xFF 0x0A 0x01 <code> 0xAA   optical gesture\n"
                           "Phone → PC   0xFF 0xF0 0x00 0x06 <n> 0xAA  run OpenBridge feature F<n>",
                 justify="left", font=self.f_mono, fg=T["dim"], bg=T["panel2"]).pack(**pad)

    # ---------- periodic work ----------
    def _tick(self):
        try:
            self.e.pump()
            now = time.time()
            if self.e.dirty and now - self._last_render > 1 / 30:
                self.e.dirty = False
                self._last_render = now
                self._render()
            self._flush_inspector()
        except Exception as ex:
            self._status(f"error: {ex}")
        self.root.after(15, self._tick)

    def _tick_slow(self):
        try:
            st = self.e.status()
            by, fr = self.e.rate.series()
            last_b, last_f = (by[-1] if by else 0), (fr[-1] if fr else 0)
            self.cards["fps"].configure(text=f"{last_f}")
            self.cards["bps"].configure(text=self._human(last_b))
            self.cards["fill"].configure(text=f"{st['fill_pct']:.1f}%")
            self.cards["pwr"].configure(text=f"{st['power_mw']:.2f} mW")
            self.cards["bat"].configure(text=f"{st['battery_h']} h")
            self.cards["total"].configure(text=f"{st['frames']:,}".replace(",", " "))
            self._draw_chart(by, fr)
            self._draw_hist()
            self.metrics_l.configure(text=f"fill {st['fill_pct']:5.1f}%   ·   {st['power_mw']:.2f} mW   ·   ~{st['battery_h']} h"
                                          f"   ·   {st['frames']} frames   ·   {self._human(st['bytes'])}")
            phones = st["phones"]
            if phones:
                self.phones_l.configure(text="\n".join(
                    f"● {p['addr']}   rx {self._human(p['rx'])}   since {time.strftime('%H:%M:%S', time.localtime(p['since']))}"
                    for p in phones), fg=THEME["green"])
            else:
                self.phones_l.configure(text="No phone connected.", fg=THEME["dim"])
        except Exception as ex:
            self._status(f"metrics error: {ex}")
        self.root.after(1000, self._tick_slow)

    @staticmethod
    def _human(n: float) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"

    def _draw_chart(self, by, fr):
        c, T = self.chart, THEME
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50:
            return
        c.create_text(10, 10, text="THROUGHPUT · LAST 90 s", anchor="nw", font=(self.f_small[0], 8, "bold"), fill=T["faint"])
        for series, colour, label, yoff in ((by, T["cyan"], "bytes/s", 0), (fr, T["accent"], "frames/s", 1)):
            mx = max(series) or 1
            n = len(series)
            pts = []
            for i, v in enumerate(series):
                x = 10 + (w - 20) * i / max(1, n - 1)
                y = h - 14 - (h - 46) * v / mx
                pts += [x, y]
            if len(pts) >= 4:
                c.create_line(*pts, fill=colour, width=2, smooth=True)
            c.create_text(w - 10, 10 + yoff * 16, text=f"{label}  peak {self._human(mx) if label == 'bytes/s' else mx}",
                          anchor="ne", font=self.f_small, fill=colour)
        c.create_line(10, h - 13, w - 10, h - 13, fill=T["line"])

    def _draw_hist(self):
        c, T = self.hist, THEME
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        c.create_text(0, 4, text="COMMAND MIX", anchor="nw", font=(self.f_small[0], 8, "bold"), fill=T["faint"])
        top = self.e.cmd_hist.most_common(12)
        if not top:
            c.create_text(w / 2, h / 2, text="No frames yet — connect the phone or run a feature.",
                          font=self.f_small, fill=T["faint"])
            return
        mx = top[0][1]
        y = 24
        inv = {v: k for k, v in CMD.items()}
        for name, cnt in top:
            colour = GROUP_COLOUR[cmd_group(inv.get(name, 0x05))]
            c.create_text(0, y + 8, text=name, anchor="w", font=self.f_mono, fill=T["dim"])
            bw = (w - 190) * cnt / mx
            c.create_rectangle(130, y + 2, 130 + bw, y + 14, fill=colour, outline="")
            c.create_text(136 + bw, y + 8, text=str(cnt), anchor="w", font=self.f_mono, fill=T["text"])
            y += 20

    def _flush_inspector(self):
        if self._inspector_paused:
            self.e.ui_events.clear()
            return
        n = 0
        while self.e.ui_events and n < 300:
            ev = self.e.ui_events.popleft()
            n += 1
            if self._filter and self._filter not in ev.name.lower() and self._filter not in ev.source.lower():
                continue
            src = ev.source.split(" ")[0]
            iid = self.tree.insert("", "end", values=(
                ev.seq, time.strftime("%H:%M:%S", time.localtime(ev.t)) + f".{int(ev.t * 1000) % 1000:03d}",
                src, ev.name, len(ev.data), decode(Frame(ev.cmd, ev.data))), tags=(cmd_group(ev.cmd),))
            self._tree_index[iid] = ev
        if n:
            kids = self.tree.get_children()
            if len(kids) > 3000:
                for iid in kids[:len(kids) - 3000]:
                    self._tree_index.pop(iid, None)
                self.tree.delete(*kids[:len(kids) - 3000])
            self.tree.yview_moveto(1.0)

    # ---------- inspector actions ----------
    def _inspect_selected(self, _e=None):
        sel = self.tree.selection()
        if not sel or sel[0] not in self._tree_index:
            return
        ev = self._tree_index[sel[0]]
        raw = frame_bytes(ev.cmd, ev.data)
        txt = (f"#{ev.seq}   {ev.name}  (0x{ev.cmd:02X}, group {cmd_group(ev.cmd)})   from {ev.source}\n"
               f"decoded   {decode(Frame(ev.cmd, ev.data))}\n"
               f"payload   {len(ev.data)} B   ·   frame {len(raw)} B\n\n{hexdump(raw)}")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", txt)

    def _toggle_pause(self):
        self._inspector_paused = not self._inspector_paused
        self.btn_pause.configure(text="▶ Resume" if self._inspector_paused else "❚❚ Pause")
        self.btn_pause.set_kind("on" if self._inspector_paused else "ghost")

    def _clear_inspector(self):
        self.tree.delete(*self.tree.get_children())
        self._tree_index.clear()

    def _export_csv(self):
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        out = CAPTURE_DIR / f"frames_{_dt.datetime.now():%Y%m%d_%H%M%S}.csv"
        import csv
        with open(out, "w", newline="", encoding="utf-8") as fh:
            wr = csv.writer(fh)
            wr.writerow(["seq", "time", "source", "cmd", "cmd_hex", "len", "decoded", "payload_hex"])
            for ev in self.e.events:
                wr.writerow([ev.seq, f"{ev.t:.3f}", ev.source, ev.name, f"0x{ev.cmd:02X}", len(ev.data),
                             decode(Frame(ev.cmd, ev.data)), ev.data.hex()])
        self._status(f"Exported {len(self.e.events)} frames → {out}")
        self._refresh_captures()

    def _refresh_layouts(self):
        if not hasattr(self, "ltree"):
            return
        self.ltree.delete(*self.ltree.get_children())
        for lid, L in sorted(self.e.hud.active_bank.layouts.items()):
            self.ltree.insert("", "end", values=(lid, L.x, L.y, L.width, L.height, L.font, L.fore_color,
                                                 L.back_color, len(L.sub_commands)))

    # ---------- toolbar actions ----------
    def _set_mode(self, m):
        self.mode = m
        self.e.dirty = True

    def _set_scale(self, s):
        self.zoom = s
        self._layout_view()

    def _toggle_grid(self):
        self.grid = not self.grid
        self.btn_grid.set_kind("on" if self.grid else "ghost")
        self.e.dirty = True

    def _screenshot(self):
        p = self.e.screenshot(mode=self.mode, scale=max(2, min(5, round(self.s))))
        self.e.screenshot(mode="raw")
        self._toast(f"Saved {pathlib.Path(p).name}")
        self._refresh_captures()

    def _toggle_gif(self):
        if self._gif_frames is None:
            self._gif_frames = []
            self.btn_gif.set_kind("on")
            self.btn_gif.configure(text="■  Stop GIF")
            self._status("GIF capture running (max 30 s)…")
            return
        frames, self._gif_frames = self._gif_frames, None
        self.btn_gif.set_kind("ghost")
        self.btn_gif.configure(text="🎞  GIF")
        if not frames:
            self._status("GIF: no frames captured (nothing changed on screen).")
            return
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        out = CAPTURE_DIR / f"hud_{_dt.datetime.now():%Y%m%d_%H%M%S}.gif"
        frames[0].save(out, save_all=True, append_images=frames[1:], duration=66, loop=0, optimize=True)
        self._toast(f"Saved {out.name} ({len(frames)} frames)")
        self._refresh_captures()

    def _toggle_record(self):
        if self.e.recording is None:
            self.e.record_start()
        else:
            self.e.record_stop()

    def _load_replay(self):
        from tkinter import filedialog
        p = filedialog.askopenfilename(initialdir=str(CAPTURE_DIR), filetypes=[("OpenBridge session", "*.obsession")])
        if p:
            n = self.e.replay(p, self.speed)
            self._status(f"Replaying {pathlib.Path(p).name}: {n} chunks at {self.speed}×")

    def _refresh_captures(self):
        if not hasattr(self, "cap_list"):
            return
        self.cap_list.delete(0, "end")
        if CAPTURE_DIR.exists():
            files = sorted(CAPTURE_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:200]
            for f in files:
                self.cap_list.insert("end", f"{time.strftime('%d/%m %H:%M', time.localtime(f.stat().st_mtime))}   {f.name}")

    def _open_capture(self, _e=None):
        sel = self.cap_list.curselection()
        if not sel:
            return
        name = self.cap_list.get(sel[0]).split("   ", 1)[1]
        p = CAPTURE_DIR / name
        if p.suffix == ".obsession":
            n = self.e.replay(str(p), self.speed)
            self._status(f"Replaying {name}: {n} chunks")
        else:
            self._open_path(p)

    def _open_capture_dir(self):
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        self._open_path(CAPTURE_DIR)

    @staticmethod
    def _open_path(p):
        import os
        import subprocess
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # noqa: S606 - opening the user's own capture
        else:
            subprocess.Popen(["xdg-open", str(p)])

    # ---------- showcase ----------
    def _toggle_showcase(self):
        if self._showcase is None:
            feats = self._visible_features() or hf.FEATURES
            self._showcase = {"list": feats, "i": 0}
            self.btn_show.set_kind("on")
            self.btn_show.configure(text="■  Stop showcase")
            self._showcase_step()
        else:
            self._stop_showcase()

    def _stop_showcase(self):
        if self._showcase is not None:
            if self._showcase.get("job"):
                self.root.after_cancel(self._showcase["job"])
            self._showcase = None
            self.btn_show.set_kind("ghost")
            self.btn_show.configure(text="▶  Showcase")

    def _showcase_step(self):
        sc = self._showcase
        if sc is None:
            return
        f = sc["list"][sc["i"] % len(sc["list"])]
        sc["i"] += 1
        self.e.run_feature(f.fid, origin="showcase")
        sc["job"] = self.root.after(3200, self._showcase_step)

    # ---------- engine callbacks ----------
    def _on_phone(self, state, info):
        T = THEME
        if state == "listening":
            self.pill_phone.configure(text=f"○  Waiting for phone on :{info}", fg=T["dim"])
        elif state == "connected":
            self.pill_phone.configure(text=f"●  Phone connected  {info}", fg=T["green"])
            self._toast(f"Phone connected · {info}", T["green"])
        elif state == "disconnected":
            n = len(self.e.phone.snapshot())
            if n:
                self.pill_phone.configure(text=f"●  {n} phone(s) connected", fg=T["green"])
            else:
                self.pill_phone.configure(text=f"○  Waiting for phone on :{self.e.phone.port}", fg=T["dim"])
            self._toast(f"Phone disconnected · {info}", T["amber"])
        elif state == "error":
            self.pill_phone.configure(text=f"✕  {info}", fg=T["red"])

    def _on_feature(self, feat: hf.Feature, origin: str):
        self._lib_active = feat
        self._draw_library()
        self._caption(feat, origin)

    def _on_external(self, source):
        for it in self._caption_items:
            self.view.delete(it)
        self._caption_items = []
        if self._lib_active is not None:
            self._lib_active = None
            self._draw_library()

    def _caption(self, feat, origin):
        v, T = self.view, THEME
        for it in self._caption_items:
            v.delete(it)
        ox, oy = self._img_origin
        iw, ih = round(DISPLAY_W * self.s), round(DISPLAY_H * self.s)
        colour = hf.CATEGORIES[feat.category][1]
        y = oy + ih + 44
        items = [
            v.create_rectangle(ox, y, ox + 4, y + 46, fill=colour, outline=""),
            v.create_text(ox + 16, y + 2, anchor="nw", text=f"{feat.fid}  ·  {feat.title}", font=self.f_title, fill=T["text"]),
            v.create_text(ox + 16, y + 30, anchor="nw", font=self.f_small, fill=colour,
                          text=f"{hf.CATEGORIES[feat.category][0]}   ·   triggered from {origin}"),
        ]
        if self._showcase:
            n = len(self._showcase["list"])
            i = (self._showcase["i"] - 1) % n + 1
            items.append(v.create_text(ox + iw, y + 2, anchor="ne", font=self.f_mono_b, fill=T["dim"], text=f"{i:02d} / {n:02d}"))
            items.append(v.create_rectangle(ox + 16, y + 52, ox + 16 + (iw - 16) * i / n, y + 54, fill=T["accent"], outline=""))
        self._caption_items = items

    def _on_gesture(self, nphones):
        v, T = self.view, THEME
        ox, oy = self._img_origin
        iw = round(DISPLAY_W * self.s)
        cx, cy = ox + iw - 24, oy - 24
        rings = [v.create_oval(cx, cy, cx, cy, outline=T["accent"], width=2) for _ in range(3)]

        def anim(step=0):
            for k, r in enumerate(rings):
                s = max(0, step - k * 4)
                rad = s * 4
                v.coords(r, cx - rad, cy - rad, cx + rad, cy + rad)
                v.itemconfigure(r, outline=_mix(T["accent"], T["bg"], min(1, s / 22)))
            if step < 34:
                v.after(16, anim, step + 1)
            else:
                for r in rings:
                    v.delete(r)
        anim()
        self._toast(f"👋  Wave → {nphones} phone(s)" if nphones else "👋  Wave (no phone connected)",
                    THEME["accent"] if nphones else THEME["amber"])

    def _on_record(self, active, path=None):
        T = THEME
        if active:
            self.btn_rec.configure(text="■  Stop")
            self.btn_rec2.configure(text="■  Stop recording")
            self.pill_rec.configure(text="●  REC", bg=T["bg"])
            self._blink_rec()
        else:
            self.btn_rec.configure(text="●  Rec")
            self.btn_rec2.configure(text="●  Start recording")
            self.pill_rec.configure(text="")
            if path:
                self.session_l.configure(text=f"Saved {pathlib.Path(path).name}")
                self._toast(f"Session saved · {pathlib.Path(path).name}")
                self._refresh_captures()

    def _blink_rec(self, on=True):
        if self.e.recording is None:
            return
        self.pill_rec.configure(fg=THEME["red"] if on else THEME["bg"])
        n = len(self.e.recording)
        self.session_l.configure(text=f"Recording… {n} chunks · {time.time() - self.e._rec_t0:.0f} s")
        self.root.after(500, self._blink_rec, not on)

    def _on_replay(self, state):
        self.session_l.configure(text=f"Replay {state}: {self.e.replay_name}")
        self._status(f"Replay {state}: {self.e.replay_name}")

    def _on_ui(self, what, value):
        if what == "view":
            self.seg_view.pick(value)
        elif what == "zoom":
            self.seg_zoom.pick(value if value == "fit" else int(value))
        elif what == "tab":
            names = [self.nb.tab(t, "text").lower() for t in self.nb.tabs()]
            if str(value).lower() in names:
                self.nb.select(names.index(str(value).lower()))
        elif what == "showcase":
            if bool(value) != (self._showcase is not None):
                self._toggle_showcase()

    # ---------- misc ----------
    def _status(self, text):
        self.status_l.configure(text=text)

    def _toast(self, text, colour=None):
        v, T = self.view, THEME
        colour = colour or T["text"]
        W = v.winfo_width()
        tid = v.create_text(W - 24, 22, anchor="ne", text=text, font=self.f_ui_b, fill=colour)
        bb = v.bbox(tid)
        bg = v.create_rectangle(bb[0] - 14, bb[1] - 8, bb[2] + 14, bb[3] + 8, fill=T["panel2"], outline=T["line"])
        v.tag_raise(tid)
        self._status(text)

        def fade(step=0):
            if step > 14:
                v.delete(tid, bg)
                return
            if step > 8:
                t = (step - 8) / 6
                v.itemconfigure(tid, fill=_mix(colour, T["bg"], t))
                v.itemconfigure(bg, fill=_mix(T["panel2"], T["bg"], t), outline=_mix(T["line"], T["bg"], t))
            v.after(120, fade, step + 1)
        fade()

    def _bind_keys(self):
        def guard(fn):
            def h(event):
                if isinstance(event.widget, (self.tk.Entry, self.tk.Text)):
                    return
                fn()
            return h
        for keys, fn in ((("g", "G"), lambda: self.e.gesture()), (("c", "C"), self.e.clear),
                         (("s", "S"), self._screenshot), (("f", "F"), self._toggle_gif),
                         (("r", "R"), self._toggle_record), (("space",), self._toggle_showcase)):
            for k in keys:
                self.root.bind_all(f"<KeyPress-{k}>", guard(fn))

    def _quit(self):
        if self.e.recording is not None:
            self.e.record_stop()
        self.e.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ── entry point ──────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description="OpenBridge HUD Studio — ActiveLook / ENGO emulator")
    ap.add_argument("--model", default="ENGO 2", choices=MODELS)
    ap.add_argument("--phone-port", type=int, default=PHONE_PORT)
    ap.add_argument("--control-port", type=int, default=CONTROL_PORT)
    ap.add_argument("--scale", default="fit", choices=["fit", "2", "3", "4"])
    ap.add_argument("--view", default="oled", choices=["pixels", "oled", "lens"])
    ap.add_argument("--headless", action="store_true", help="no window: phone link + control API only")
    ap.add_argument("--send", metavar="JSON", help="send one control request to a running studio and print the reply")
    ap.add_argument("--log", metavar="FILE", help="append stdout/stderr to FILE (used by the detached launcher)")
    a = ap.parse_args(argv)
    if a.log or sys.stdout is None:   # pythonw has no console
        fh = open(a.log or (PROJECT_ROOT / "dev" / "hud_studio.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = fh
    if a.send:
        print(json.dumps(send_control(json.loads(a.send), a.control_port), indent=2, ensure_ascii=False))
        return 0
    eng = StudioEngine(model=a.model, phone_port=a.phone_port, control_port=a.control_port)
    eng.start()
    print(f"[HUD Studio {VERSION}] phone link :{a.phone_port}  ·  control API 127.0.0.1:{a.control_port}  ·  {a.model}",
          flush=True)
    if a.headless:
        try:
            while True:
                eng.pump()
                time.sleep(0.005)
        except KeyboardInterrupt:
            return 0
    HUDStudioApp(eng, scale=a.scale if a.scale == "fit" else int(a.scale), mode=a.view).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
