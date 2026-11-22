"""
Built-in "ALooK" layout bank for the emulator.

Real ActiveLook glasses ship a firmware configuration named "ALooK" holding the layouts the official
mobile app addresses by id (time = 10, chrono = 11, distance = 12 …). The app never uploads them; it only
calls layoutDisplay(id, value) / layoutDisplayExtended(id, value, x, y). This module reproduces that bank so
the official app renders a faithful sport HUD in HUD Studio.

Coordinates: the app speaks native ActiveLook coordinates — origin at the *bottom-right* of the 304×256
panel (screen rotated 180°), a layout anchored at (x, y) covering x..x+w, y..y+h. Positions come from the
app's computeLayoutXY(): x ∈ {30, 157}, y ∈ {153, 89, 25} (3 rows) / {121, 57} (2 rows) / {89} (1 row).
"""
from __future__ import annotations

from dataclasses import dataclass

W, H = 304, 256
FULL_W, HALF_W, ROW_H = 244, 117, 60


@dataclass(frozen=True)
class Metric:
    label: str
    unit: str
    unit_imp: str = ""
    half: bool = False


_M: dict[int, Metric] = {}


def _reg(ids, label, unit, unit_imp=""):
    """ids = (half, imperial, metric) like the app's getActualLayoutId(); None when absent."""
    half, imp, met = ids
    if met is not None:
        _M[met] = Metric(label, unit, unit_imp or unit)
    if imp is not None:
        _M[imp] = Metric(label, unit_imp or unit, unit_imp or unit)
    if half is not None:
        _M[half] = Metric(label, unit, unit_imp or unit, half=True)


_reg((43, None, 11), "CHRONO", "")
_reg((46, 35, 12), "DIST", "km", "mi")
_reg((44, 33, 13), "SPEED", "km/h", "mph")
_reg((45, 34, 14), "AVG SPD", "km/h", "mph")
_reg((63, 41, 31), "MAX SPD", "km/h", "mph")
_reg((48, 37, 15), "PACE", "/km", "/mi")
_reg((68, 67, 66), "AVG PACE", "/km", "/mi")
_reg((78, 77, 76), "MAX PACE", "/km", "/mi")
_reg((55, None, 16), "CADENCE", "rpm")
_reg((51, None, 23), "AVG CAD", "rpm")
_reg((60, None, 28), "MAX CAD", "rpm")
_reg((50, 38, 18), "ALT", "m", "ft")
_reg((47, 36, 19), "ASCENT", "m", "ft")
_reg((57, 39, 26), "DESCENT", "m", "ft")
_reg((59, 40, 20), "VAM", "m/h", "ft/h")
_reg((49, None, 21), "HEART", "bpm")
_reg((52, None, 24), "AVG HR", "bpm")
_reg((61, None, 29), "MAX HR", "bpm")
_reg((56, None, 22), "POWER", "W")
_reg((53, None, 25), "AVG PWR", "W")
_reg((62, None, 30), "MAX PWR", "W")
_reg((70, None, 69), "NP", "W")

SPECIAL = {7: "battery", 10: "time", 73: "pause", 75: "ready", 98: "pause", 100: "screen_off",
           178: "low_battery", 179: "low_battery", 180: "session_ended", 182: "countdown"}

DEFAULT_ROW_Y = {11: 153, 12: 89, 13: 89}   # used when the app displays without a position


def known(layout_id: int) -> bool:
    return layout_id in _M or layout_id in SPECIAL


def _to_screen(x: int, y: int, w: int, h: int) -> tuple[int, int]:
    """ActiveLook (bottom-right origin) anchor → top-left screen coordinates of the layout box."""
    return W - x - w, H - y - h


def render(hud, layout_id: int, text: str, al_origin: tuple[int, int] | None = None) -> bool:
    """Draw ALooK layout `layout_id` with value `text` on a HUDCanvas. Returns False if unknown."""
    d = hud._draw
    on = hud._resolve_colour(15)
    dim = hud._resolve_colour(8)
    off = (0, 0, 0)
    kind = SPECIAL.get(layout_id)
    if kind is None and layout_id not in _M:
        return False

    def tw(s, fid):
        f = hud._font(fid)
        return int(f.getlength(s)) if hasattr(f, "getlength") else len(s) * 10

    if kind == "time":
        d.rectangle([0, 0, 120, 30], fill=off)
        hud._draw_text_with_ghost(10, 6, text or "--:--", 1, on)
        return True
    if kind in ("battery", "low_battery"):
        d.rectangle([220, 0, W - 1, 30], fill=off)
        x0, y0 = 252, 9
        d.rectangle([x0, y0, x0 + 34, y0 + 15], outline=on, width=2)
        d.rectangle([x0 + 35, y0 + 4, x0 + 38, y0 + 11], fill=on)
        digits = "".join(ch for ch in (text or "") if ch.isdigit())
        pct = int(digits) if digits else (15 if kind == "low_battery" else 100)
        fill_w = max(2, int(30 * min(100, pct) / 100))
        d.rectangle([x0 + 2, y0 + 2, x0 + 2 + fill_w, y0 + 13], fill=on)
        if kind == "low_battery" or pct <= 20:
            hud._draw_text_with_ghost(x0 - 42, y0 - 1, f"{pct}%", 0, on)
        return True
    if kind == "ready":
        cx, cy = W // 2, 140
        d.rectangle([0, 34, W - 1, H - 1], fill=off)
        d.ellipse([cx - 46, cy - 46, cx + 46, cy + 46], outline=on, width=4)
        d.line([(cx - 22, cy + 2), (cx - 6, cy + 18), (cx + 24, cy - 16)], fill=on, width=6)
        label = "READY"
        hud._draw_text_with_ghost(cx - tw(label, 2) // 2, cy + 58, label, 2, on)
        return True
    if kind == "pause":
        cx, cy = W // 2, 140
        d.rectangle([0, 34, W - 1, H - 1], fill=off)
        d.rounded_rectangle([cx - 34, cy - 40, cx - 10, cy + 40], radius=5, fill=on)
        d.rounded_rectangle([cx + 10, cy - 40, cx + 34, cy + 40], radius=5, fill=on)
        hud._draw_text_with_ghost(cx - tw("PAUSE", 2) // 2, cy + 52, "PAUSE", 2, on)
        return True
    if kind == "session_ended":
        cx = W // 2
        d.rectangle([0, 34, W - 1, H - 1], fill=off)
        d.line([(cx - 40, 160), (cx - 40, 80)], fill=on, width=4)
        for i in range(4):
            for j in range(3):
                if (i + j) % 2 == 0:
                    d.rectangle([cx - 38 + i * 18, 80 + j * 14, cx - 20 + i * 18, 94 + j * 14], fill=on)
        msg = "SESSION ENDED"
        hud._draw_text_with_ghost(cx - tw(msg, 2) // 2, 180, msg, 2, on)
        return True
    if kind == "screen_off":
        d.rectangle([0, 0, W - 1, H - 1], fill=off)
        d.line([(W // 2 - 40, H // 2), (W // 2 + 40, H // 2)], fill=dim, width=2)
        return True
    if kind == "countdown":
        d.rectangle([0, 34, W - 1, H - 1], fill=off)
        t = text or "3"
        hud._draw_text_with_ghost(W // 2 - tw(t, 5) // 2, 80, t, 5, on)
        return True

    m = _M[layout_id]
    w = HALF_W if m.half else FULL_W
    ax, ay = al_origin if al_origin else (30, DEFAULT_ROW_Y.get(layout_id, 89))
    sx, sy = _to_screen(ax, ay, w, ROW_H)
    d.rectangle([sx, sy, sx + w - 1, sy + ROW_H - 1], fill=off)
    # label (top-left) and a hairline separator
    hud._draw_text_with_ghost(sx + 2, sy + 1, m.label, 0, dim)
    d.line([(sx + 2, sy + ROW_H - 2), (sx + w - 3, sy + ROW_H - 2)], fill=hud._resolve_colour(3))
    value = (text or "--").strip()
    vfont = 2 if m.half else 3
    unit = m.unit
    for u in (m.unit, m.unit_imp):     # the app may append the unit itself
        if u and value.endswith(u):
            value = value[: -len(u)].strip()
    uw = tw(unit, 0) + 4 if unit else 0
    vw = tw(value, vfont)
    vx = sx + w - 4 - uw - vw
    vy = sy + (14 if m.half else 12)
    hud._draw_text_with_ghost(max(sx + 2, vx), vy, value, vfont, on)
    if unit:
        hud._draw_text_with_ghost(sx + w - uw, sy + ROW_H - 22, unit, 0, dim)
    return True
