#!/usr/bin/env python3
"""Generate docs/assets/readme/interop-demo.svg

A self-contained, looping animated SVG (CSS keyframes + SMIL, no JS, no external
assets) so it renders inside a GitHub README <img>.

Storyline (one master clock of T seconds):
  1. Eight device-to-device skills (phone/watch/tablet/PC/VR/fridge -> lights,
     coffee machine, plug, TV, other phone, other PC, other VR headset), including
     object-to-object exchanges with no phone in between.
  2. The VR headset generates a control room and drives every device at once.
  3. Smart-glasses HUD: live tags over every device (battery, distance, CPU/RAM),
     live links, and look-and-pinch control.
Edit the data below and re-run:
  python scripts/build/gen_interop_demo.py docs/assets/readme/interop-demo.svg
"""
import sys

W, H = 1280, 760
FONT = "'Segoe UI',Inter,Helvetica,Arial,sans-serif"
CX, CY = 640, 415
LX, RX = 250, 1030
ROWS = [175 + 80 * i for i in range(7)]
R = 32

TEAL, MINT, PURPLE, VIOLET = "#2dd4bf", "#7cf3e1", "#a78bfa", "#8b5cf6"
AMBER, PINK, GREEN, SKY, LILAC = "#fbbf24", "#f472b6", "#34d399", "#38bdf8", "#c084fc"

# ---------------------------------------------------------------- timing
S0, DUR = 1.4, 2.8
EV_S = [S0 + DUR * k for k in range(8)]      # 1.4 ... 21.0  (ends 23.8)
VS = S0 + DUR * 8                            # 23.8  VR control-room scene
GS = 30.0                                    # glasses event
A0 = 31.7                                    # AR HUD fully open
AE = 43.0                                    # fade to black
T = 43.6

# ---------------------------------------------------------------- devices
LEFT = [
    ("phone", "PHONE", "Android 15", "phone"),
    ("tablet", "TABLET", "iPadOS", "tablet"),
    ("laptop", "LAPTOP", "Windows 11", "laptop"),
    ("watch", "WATCH", "Wear OS", "watch"),
    ("vr", "VR HEADSET", "Standalone XR", "vr"),
    ("fridge", "FRIDGE", "Wi-Fi appliance", "fridge"),
    ("glasses", "SMART GLASSES", "HUD display", "glasses"),
]
RIGHT = [
    ("lights", "LIGHTS", "Zigbee", "bulb"),
    ("coffee", "COFFEE MACHINE", "Wi-Fi", "coffee"),
    ("plug", "SMART PLUG", "Matter", "plug"),
    ("tv", "TV", "Android TV", "tv"),
    ("phone2", "PHONE", "iOS", "phone"),
    ("pc2", "DESKTOP PC", "Linux", "monitor"),
    ("vr2", "VR HEADSET", "PC VR", "vr"),
]
DEV = {}
for i, (k, n, s, ic) in enumerate(LEFT):
    DEV[k] = dict(key=k, name=n, sub=s, icon=ic, x=LX, y=ROWS[i], side=-1, dir=1)
for i, (k, n, s, ic) in enumerate(RIGHT):
    DEV[k] = dict(key=k, name=n, sub=s, icon=ic, x=RX, y=ROWS[i], side=1, dir=-1)


def inner(d):
    return (d["x"] + d["dir"] * R, d["y"])


ICONS = {
    "phone": '<rect x="-9" y="-15" width="18" height="30" rx="3.5"/><path d="M-3 10.5h6"/>',
    "tablet": '<rect x="-16" y="-11" width="32" height="22" rx="3"/><path d="M12.5 0h.1"/>',
    "laptop": '<rect x="-13" y="-12" width="26" height="17" rx="2"/><path d="M-18 9h36l-2.5 4h-31z"/>',
    "watch": '<circle r="10"/><path d="M-6 -8l2-9h8l2 9M-6 8l2 9h8l2-9M0 -4.5v4.5l3 2"/>',
    "vr": '<path d="M-17 -9h34a4 4 0 0 1 4 4v10a4 4 0 0 1-4 4h-10l-4-5h-6l-4 5h-10a4 4 0 0 1-4-4v-10a4 4 0 0 1 4-4z"/><path d="M-21 -2h-3M21 -2h3"/>',
    "fridge": '<rect x="-11" y="-17" width="22" height="34" rx="3"/><path d="M-11 -4h22M-6 -12v4M-6 1v7"/>',
    "glasses": '<rect x="-19" y="-7" width="15" height="12" rx="5"/><rect x="4" y="-7" width="15" height="12" rx="5"/><path d="M-4 -3q4-3 8 0M-19 -4l-4-3M19 -4l4-3"/>',
    "bulb": '<path d="M-5 11v-3c0-3-7-5-7-12a12 12 0 0 1 24 0c0 7-7 9-7 12v3z"/><path d="M-4 15h8"/>',
    "coffee": '<rect x="-13" y="-17" width="26" height="34" rx="3"/><path d="M-13 -9h26M-3 -9v4h6v-4M-6 5h10v6a3 3 0 0 1-3 3h-4a3 3 0 0 1-3-3zM4 7h2a2 2 0 0 1 0 4h-2"/>',
    "plug": '<rect x="-14" y="-14" width="28" height="28" rx="8"/><circle cx="-5" cy="3" r="2"/><circle cx="5" cy="3" r="2"/>',
    "tv": '<rect x="-17" y="-12" width="34" height="22" rx="3"/><path d="M-7 15h14"/>',
    "monitor": '<rect x="-16" y="-14" width="32" height="21" rx="2.5"/><path d="M0 7v6M-7 14h14"/>',
}

# ---------------------------------------------------------------- events
EVENTS = [
    dict(src="watch", dst=["coffee"], c=AMBER, chip="WATCH  →  COFFEE MACHINE",
         title="Brew from your wrist",
         desc="The watch never had a coffee button. OpenBridge just created one.",
         spill="Brew espresso", tp={"coffee": "Brewing · 92 °C"}, tl="Coffee"),
    dict(src="coffee", dst=["watch"], c=AMBER, chip="COFFEE MACHINE  →  WATCH",
         title="Coffee's ready. Your wrist knows.",
         desc="Device to device, no phone in between: the machine taps your wrist.",
         spill="Ping my watch", tp={"watch": "Buzz · Coffee ready"}, tl="Ping"),
    dict(src="tablet", dst=["lights", "tv"], c=VIOLET, chip="TABLET  →  LIGHTS + TV",
         title="One tap, movie night",
         desc="Two brands, two protocols, one scene. Lights dim, the TV wakes up.",
         spill="Movie night", tp={"lights": "Violet · 30 %", "tv": "On · Movie"}, tl="Movie"),
    dict(src="tv", dst=["lights"], c=PINK, chip="TV  →  LIGHTS",
         title="The room follows the movie",
         desc="The TV drives the lights on its own. Colors track every scene.",
         spill="Sync lights to screen", tp={"lights": "Live color sync"}, tl="Sync"),
    dict(src="fridge", dst=["phone2"], c=TEAL, chip="FRIDGE  →  PHONE",
         title="Your fridge can text now",
         desc="Milk is running low: the list lands on the other phone in the house.",
         spill="Notify on low stock", tp={"phone2": "Shopping list: + milk"}, tl="Fridge"),
    dict(src="laptop", dst=["plug"], c=GREEN, chip="LAPTOP  →  SMART PLUG",
         title="Render done, power off",
         desc="The PC finishes its job and cuts the plug by itself.",
         spill="Power off when done", tp={"plug": "Off · 0 W"}, tl="Power"),
    dict(src="phone", dst=["pc2"], c=SKY, chip="PHONE  →  DESKTOP PC",
         title="Drop a file on any PC",
         desc="Android to Linux over the local network. No cable, no cloud.",
         spill="Drop to any PC", tp={"pc2": "48 MB in 1.9 s"}, tl="Files"),
    dict(src="vr", dst=["vr2"], c=LILAC, chip="VR HEADSET  →  VR HEADSET",
         title="One room, two headsets",
         desc="Different brands, one shared space, synced in real time.",
         spill="Shared room", tp={"vr2": "Synced · 12 ms"}, tl="Shared VR"),
]
for e, s in zip(EVENTS, EV_S):
    e["s"] = s
    e["r"] = s + 1.1          # target reacts

# VR control room tiles: (device, short name, action)
TILES = [
    ("lights", "Lights", "Scene"), ("coffee", "Coffee", "Brew"), ("plug", "Plug", "On"),
    ("tv", "TV", "Cinema"), ("phone2", "Phone 2", "Ring"), ("pc2", "Desktop", "Wake"),
    ("vr2", "VR 2", "Join"), ("phone", "Phone", "Silence"), ("tablet", "Tablet", "Show"),
    ("laptop", "Laptop", "Lock"), ("watch", "Watch", "Buzz"), ("fridge", "Fridge", "Eco"),
]
PANEL = dict(x=452, y=300, w=376, h=220)
TILE_T = [VS + 1.1 + 0.3 * k for k in range(len(TILES))]

# AR tags: primary [(text, t_from)], line2, line3 [(text, t_from)], bar, battery?
TAGS = {
    "phone": ([("82%", 0)], "1.2 m · Wi-Fi 6", [("CPU 31% · RAM 5.1/8 GB", 0)], .31, True),
    "tablet": ([("64%", 0)], "2.8 m · Wi-Fi", [("CPU 18% · RAM 3.2/6 GB", 0)], .18, True),
    "laptop": ([("AC", 0)], "3.4 m · Ethernet",
               [("CPU 47% · RAM 11/16 GB", 0), ("CPU 63% · RAM 12/16 GB", A0 + 3.0),
                ("CPU 52% · RAM 11/16 GB", A0 + 6.5)], .47, False),
    "watch": ([("71%", 0)], "0.4 m · BLE", [("HR 72 bpm · 6,412 steps", 0)], .71, True),
    "vr": ([("58%", 0)], "4.1 m · Wi-Fi 6E", [("GPU 63% · 90 fps", 0)], .63, True),
    "fridge": ([("3.2 °C", 0)], "5.0 m · Wi-Fi", [("Door closed · 118 W", 0)], .4, False),
    "glasses": ([("88%", 0)], "On your face", [("HUD 60 Hz · 14 tracked", 0)], .88, True),
    "lights": ([("ON", 0)], "2.2 m · Zigbee", [("Color sync · 6 W", 0)], .3, False),
    "coffee": ([("READY", 0), ("BREWING", A0 + 8.3)], "3.9 m · Wi-Fi",
               [("92 °C · water 70%", 0)], .7, False),
    "plug": ([("ON", 0)], "3.1 m · Matter", [("42 W · 1.2 kWh today", 0)], .42, False),
    "tv": ([("ON", 0)], "4.6 m · Ethernet",
           [("HDMI 2 · vol 18", 0), ("HDMI 2 · vol 24", A0 + 3.3),
            ("Cast: Laptop · vol 24", A0 + 5.8)], .18, False),
    "phone2": ([("45%", 0)], "6.7 m · −48 dBm", [("CPU 12% · RAM 2.9/6 GB", 0)], .45, True),
    "pc2": ([("41 °C", 0)], "5.8 m · Ethernet",
            [("CPU 22% · RAM 18/32 GB", 0), ("CPU 35% · RAM 19/32 GB", A0 + 4.0),
             ("CPU 28% · RAM 18/32 GB", A0 + 7.5)], .22, False),
    "vr2": ([("77%", 0)], "7.5 m · Wi-Fi 6E", [("Synced · 12 ms", 0)], .77, True),
}
AR_LINKS = [  # left, right, label, color, t
    ("tablet", "lights", "ZIGBEE · 30%", VIOLET, .5),
    ("watch", "coffee", "BLE · READY", AMBER, .3),
    ("laptop", "plug", "MATTER · 42 W", GREEN, .5),
    ("watch", "tv", "BLE · 12 ms", TEAL, .5),
    ("phone", "pc2", "WI-FI · 48 MB/s", SKY, .35),
    ("fridge", "phone2", "MQTT · ALERT", MINT, .5),
    ("vr", "vr2", "SYNC · 90 Hz", LILAC, .5),
    ("glasses", "pc2", "HUD · 60 Hz", TEAL, .25),
]
LOCKS = [  # device, lock_start, lock_end, chip text
    ("tv", A0 + 2.4, A0 + 4.2, "PINCH  →  Volume up"),
    ("laptop", A0 + 4.9, A0 + 6.7, "PINCH  →  Mirror to TV"),
    ("coffee", A0 + 7.4, A0 + 9.4, "PINCH  →  Brew espresso"),
]

# ---------------------------------------------------------------- css engine
css = []
_n = [0]


def kf(frames, extra=""):
    """frames: [(t_seconds, 'css decls')] -> class name animated on master clock."""
    _n[0] += 1
    name = f"k{_n[0]}"
    fr = sorted(frames, key=lambda f: f[0])
    out, last = [], -1.0
    for t, d in fr:
        t = max(0.0, min(T, t))
        if t <= last:
            t = last + 0.002
        out.append((min(t, T), d))
        last = t
    if out[0][0] > 0:
        out.insert(0, (0, out[0][1]))
    if out[-1][0] < T:
        out.append((T, out[-1][1]))
    body = "".join(f"{t / T * 100:.3f}%{{{d}}}" for t, d in out)
    css.append(f"@keyframes {name}{{{body}}}.{name}{{animation:{name} {T}s linear infinite;{extra}}}")
    return name


FB = "transform-box:fill-box;transform-origin:center;"


def win(t0, t1, fade=.25, hi=1, lo=0):
    return kf([(0, f"opacity:{lo}"), (t0, f"opacity:{lo}"), (t0 + fade, f"opacity:{hi}"),
               (t1 - fade, f"opacity:{hi}"), (t1, f"opacity:{lo}")])


def persist(t0, fade=.3):
    return kf([(0, "opacity:0"), (t0, "opacity:0"), (t0 + fade, "opacity:1"),
               (T - .25, "opacity:1"), (T - .02, "opacity:0")])


def pop(t0, t1, s0=.82):
    a, b = f"opacity:0;transform:scale({s0})", "opacity:1;transform:scale(1)"
    return kf([(0, a), (t0, a), (t0 + .28, b), (t1 - .25, b),
               (t1, "opacity:0;transform:scale(.96)"), (T, a)], FB)


def sx(t):
    return f"{t / T:.5f}"


def tw(s, size, bold=False):
    w = 0
    for ch in s:
        if ch in "il.,:;·|'!I1 ":
            w += .30
        elif ch.isupper() or ch in "mwMW%":
            w += .68
        else:
            w += .55
    return w * size * (1.06 if bold else 1)


# ---------------------------------------------------------------- svg helpers
out = []
add = out.append


def text(x, y, s, size=12, fill="#9fb3d9", weight=400, anchor="start", ls=0, cls="", extra=""):
    c = f' class="{cls}"' if cls else ""
    l = f' letter-spacing="{ls}"' if ls else ""
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    s = s.replace("&", "&amp;").replace("<", "&lt;")
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}"{a}{l}{c}{extra}>{s}</text>')


def via_orb(a, b):
    ax, ay = inner(a)
    bx, by = inner(b)
    da, db = a["dir"], b["dir"]
    return (f"M{ax},{ay} C{ax + da * 170},{ay} {CX - da * 130},{CY} {CX},{CY} "
            f"C{CX - db * 130},{CY} {bx + db * 170},{by} {bx},{by}")


def direct(p, b, k=120):
    px, py = p
    bx, by = inner(b)
    dp = 1 if bx > px else -1
    return f"M{px},{py} C{px + dp * k},{py} {bx - dp * k},{by} {bx},{by}"


def beam(path, t0, t_draw, t_hide, color, width=2.6):
    a = "stroke-dashoffset:1;opacity:0"
    k = kf([(0, a), (t0, a), (t0 + .01, "stroke-dashoffset:1;opacity:1"),
            (t0 + t_draw, "stroke-dashoffset:0;opacity:1"),
            (t_hide - .3, "stroke-dashoffset:0;opacity:1"),
            (t_hide, "stroke-dashoffset:0;opacity:0"), (T, a)])
    return (f'<g class="{k}"><path d="{path}" pathLength="1" stroke-dasharray="1 1" fill="none" '
            f'stroke="{color}" stroke-width="{width * 3.2}" stroke-opacity=".35" filter="url(#blur)"/>'
            f'<path d="{path}" pathLength="1" stroke-dasharray="1 1" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round"/></g>')


def packet(path, t0, t1, color, r=4.2):
    a, b = t0 / T, t1 / T
    e = .002
    return (f'<circle r="{r}" fill="{color}" opacity="0">'
            f'<animateMotion dur="{T}s" repeatCount="indefinite" path="{path}" calcMode="linear" '
            f'keyPoints="0;0;1;1" keyTimes="0;{a:.5f};{b:.5f};1"/>'
            f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" '
            f'values="0;0;1;1;0;0" keyTimes="0;{a:.5f};{a + e:.5f};{b - e:.5f};{b:.5f};1"/></circle>')


def ripple(x, y, t, color, r=R):
    a = "opacity:0;transform:scale(1)"
    k = kf([(0, a), (t, a), (t + .02, "opacity:.9;transform:scale(1)"),
            (t + .85, "opacity:0;transform:scale(1.95)"), (T, a)], FB)
    return (f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="{color}" stroke-width="2" '
            f'class="{k}"/>')


def ring_hl(x, y, t0, t1, color):
    return (f'<circle cx="{x}" cy="{y}" r="{R + 1}" fill="none" stroke="{color}" stroke-width="2.6" '
            f'class="{win(t0, t1, .2)}"/>'
            f'<circle cx="{x}" cy="{y}" r="{R + 6}" fill="none" stroke="{color}" stroke-width="7" '
            f'stroke-opacity=".25" filter="url(#blur)" class="{win(t0, t1, .2)}"/>')


def pill(x, y, label, color, t0, t1, align="start", badge=None, size=13):
    """x,y = anchor point (left or right edge, vertical centre)."""
    bw = tw(badge, 10, True) + 14 if badge else 0
    w = tw(label, size, True) + 24 + (bw + 6 if badge else 0)
    h = 28
    x0 = x if align == "start" else x - w
    k = pop(t0, t1)
    g = [f'<g class="{k}"><rect x="{x0:.1f}" y="{y - h / 2:.1f}" width="{w:.1f}" height="{h}" rx="14" '
         f'fill="#0b1433" fill-opacity=".94" stroke="{color}" stroke-width="1.4"/>']
    tx = x0 + 12
    if badge:
        g.append(f'<rect x="{tx - 4:.1f}" y="{y - 9:.1f}" width="{bw:.1f}" height="18" rx="9" fill="{color}"/>')
        g.append(text(tx + 3, y + 3.6, badge, 10, "#07102a", 800, ls=".08em"))
        tx += bw + 4
    g.append(text(tx, y + 4.6, label, size, "#eef4ff", 600))
    g.append("</g>")
    return "".join(g)


def steam(x, y, windows):
    """windows: [(t0,t1)] -> three rising wisps above (x,y)."""
    res = []
    for i, dx in enumerate((-6, 0, 6)):
        fr = [(0, "opacity:0;transform:translateY(0)")]
        for t0, t1 in windows:
            t = t0 + i * .22
            while t + .9 < t1:
                fr += [(t, "opacity:0;transform:translateY(0)"),
                       (t + .3, "opacity:.9;transform:translateY(-5px)"),
                       (t + .9, "opacity:0;transform:translateY(-13px)")]
                t += .9
        k = kf(fr)
        res.append(f'<path class="{k}" d="M{x + dx},{y} q-3 -4 0 -8 q3 -4 0 -8" fill="none" '
                   f'stroke="#fde68a" stroke-width="2" stroke-linecap="round"/>')
    return "".join(res)


def color_cycle(start, colors, period=1.3):
    """Opacity tracks for N overlapping colour layers, cycling from `start`."""
    n = len(colors)
    tracks = []
    for i in range(n):
        fr = [(0, "opacity:0"), (start, "opacity:0")]
        t, j = start, 0
        while t < T - .4:
            on = (j % n == i)
            fr.append((t + .35, f"opacity:{1 if on else 0}"))
            t += period
            j += 1
        fr += [(T - .25, fr[-1][1]), (T - .02, "opacity:0")]
        tracks.append(kf(fr))
    return tracks


# ================================================================ build
add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
    f'role="img" aria-labelledby="t d" font-family="{FONT}">')
add('<title id="t">OpenBridge interoperability demo</title>'
    '<desc id="d">Animated demo: phones, a tablet, a laptop, a watch, a VR headset, a fridge and smart '
    'glasses gain new skills and drive lights, a coffee machine, a smart plug, a TV, another phone, a '
    'desktop PC and another VR headset. Devices also talk to each other directly. The VR headset '
    'generates a control room for every device, and smart glasses show live battery, distance, CPU and '
    'RAM tags over each device.</desc>')
DEFS = f'''<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#070b1a"/><stop offset=".55" stop-color="#0d1330"/><stop offset="1" stop-color="#1a0f33"/></linearGradient>
<radialGradient id="glow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#7cf3e1" stop-opacity=".42"/><stop offset=".45" stop-color="#8b5cf6" stop-opacity=".14"/><stop offset="1" stop-color="#8b5cf6" stop-opacity="0"/></radialGradient>
<radialGradient id="orb" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="#fff"/><stop offset=".35" stop-color="#b9fff4"/><stop offset=".75" stop-color="#2dd4bf"/><stop offset="1" stop-color="#7c3aed"/></radialGradient>
<linearGradient id="title" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff"/><stop offset=".6" stop-color="#c7fff6"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>
<linearGradient id="idle" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2dd4bf" stop-opacity=".35"/><stop offset=".5" stop-color="#a78bfa" stop-opacity=".18"/><stop offset="1" stop-color="#2dd4bf" stop-opacity=".35"/></linearGradient>
<linearGradient id="tvs" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8b5cf6"/><stop offset="1" stop-color="#2dd4bf"/></linearGradient>
<linearGradient id="bar" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2dd4bf"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>
<linearGradient id="scan" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7cf3e1" stop-opacity="0"/><stop offset=".85" stop-color="#7cf3e1" stop-opacity=".22"/><stop offset="1" stop-color="#7cf3e1" stop-opacity=".7"/></linearGradient>
<radialGradient id="vig" cx=".5" cy=".5" r=".75"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#02040c" stop-opacity=".75"/></radialGradient>
<radialGradient id="hV" cx=".5" cy=".5" r=".5"><stop offset=".35" stop-color="#8b5cf6" stop-opacity=".75"/><stop offset="1" stop-color="#8b5cf6" stop-opacity="0"/></radialGradient>
<radialGradient id="hP" cx=".5" cy=".5" r=".5"><stop offset=".35" stop-color="#f472b6" stop-opacity=".75"/><stop offset="1" stop-color="#f472b6" stop-opacity="0"/></radialGradient>
<radialGradient id="hT" cx=".5" cy=".5" r=".5"><stop offset=".35" stop-color="#2dd4bf" stop-opacity=".75"/><stop offset="1" stop-color="#2dd4bf" stop-opacity="0"/></radialGradient>
<radialGradient id="hA" cx=".5" cy=".5" r=".5"><stop offset=".35" stop-color="#fbbf24" stop-opacity=".6"/><stop offset="1" stop-color="#fbbf24" stop-opacity="0"/></radialGradient>
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#fff" stroke-opacity=".035"/></pattern>
<pattern id="hgrid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#7cf3e1" stroke-opacity=".05"/></pattern>
<filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4"/></filter>
</defs>'''
add(DEFS)
add("<style>@@CSS@@</style>")

# ---------------- background
add(f'<rect width="{W}" height="{H}" fill="url(#bg)"/><rect width="{W}" height="{H}" fill="url(#grid)"/>')
add(f'<circle cx="{CX}" cy="{CY}" r="260" fill="url(#glow)"/>')

# ---------------- idle links (dim during the AR HUD)
idle_k = kf([(0, "opacity:1"), (A0 - .4, "opacity:1"), (A0 + .4, "opacity:.25"), (T, "opacity:.25")])
add(f'<g class="{idle_k}">')
for d in DEV.values():
    x, y = inner(d)
    p = f"M{x},{y} C{x + d['dir'] * 170},{y} {CX - d['dir'] * 130},{CY} {CX},{CY}"
    add(f'<path class="flow" d="{p}" fill="none" stroke="url(#idle)" stroke-width="1.3" stroke-dasharray="3 8"/>')
add("</g>")

# ---------------- orb
orb_k = kf([(0, "opacity:1"), (VS + .6, "opacity:1"), (VS + 1.0, "opacity:.35"), (VS + 5.9, "opacity:.35"),
            (VS + 6.3, "opacity:1"), (A0 - .3, "opacity:1"), (A0 + .4, "opacity:.3"), (T, "opacity:.3")])
add(f'<g class="{orb_k}">'
    f'<g class="ring2"><circle cx="{CX}" cy="{CY}" r="120" fill="none" stroke="#a78bfa" stroke-opacity=".16" stroke-dasharray="2 10"/></g>'
    f'<g class="ring"><circle cx="{CX}" cy="{CY}" r="74" fill="none" stroke="#2dd4bf" stroke-opacity=".28" stroke-dasharray="26 12"/></g>'
    f'<g class="pulse"><circle cx="{CX}" cy="{CY}" r="40" fill="url(#orb)"/>'
    f'<g fill="none" stroke="#fff" stroke-opacity=".7" stroke-width="1.3">'
    f'<ellipse cx="{CX}" cy="{CY}" rx="34" ry="12"/>'
    f'<ellipse cx="{CX}" cy="{CY}" rx="34" ry="12" transform="rotate(60 {CX} {CY})"/>'
    f'<ellipse cx="{CX}" cy="{CY}" rx="34" ry="12" transform="rotate(-60 {CX} {CY})"/></g></g>'
    f'{text(CX, CY + 66, "OPENBRIDGE", 11, "#7cf3e1", 700, "middle", ".3em")}</g>')

# ---------------- persistent glows behind devices
L_ = DEV["lights"]
ev_movie, ev_sync = EVENTS[2], EVENTS[3]
cyc = color_cycle(ev_sync["r"], ["hP", "hT", "hV"])
add(f'<circle cx="{L_["x"]}" cy="{L_["y"]}" r="70" fill="url(#hV)" '
    f'class="{kf([(0, "opacity:0"), (ev_movie["r"], "opacity:0"), (ev_movie["r"] + .4, "opacity:1"), (ev_sync["r"] + .35, "opacity:0"), (T, "opacity:0")])}"/>')
for gid, k in zip(["hP", "hT", "hV"], cyc):
    add(f'<circle cx="{L_["x"]}" cy="{L_["y"]}" r="70" fill="url(#{gid})" class="{k}"/>')
C_ = DEV["coffee"]
cof_windows = [(EVENTS[0]["r"], EVENTS[0]["s"] + DUR), (TILE_T[1] + .35, TILE_T[1] + 2.3), (A0 + 8.3, AE)]
fr = [(0, "opacity:0")]
for a, b in cof_windows:
    fr += [(a, "opacity:0"), (a + .3, "opacity:1"), (b - .3, "opacity:1"), (b, "opacity:0")]
add(f'<circle cx="{C_["x"]}" cy="{C_["y"]}" r="62" fill="url(#hA)" class="{kf(fr)}"/>')
V2 = DEV["vr2"]
ev_vr = EVENTS[7]
add(f'<circle cx="{V2["x"]}" cy="{V2["y"]}" r="58" fill="url(#hP)" opacity=".5" class="{persist(ev_vr["r"])}"/>')

# ---------------- event beams + packets
beams = []
for e in EVENTS:
    a = DEV[e["src"]]
    for j, dk in enumerate(e["dst"]):
        p = via_orb(a, DEV[dk])
        beams.append(beam(p, e["s"] + .1 + j * .12, .95, e["s"] + DUR - .1, e["c"]))
        for i in range(3):
            t0 = e["s"] + .15 + .2 * i + j * .12
            beams.append(packet(p, t0, t0 + 1.1, "#ffffff" if i == 1 else e["c"]))
# VR -> panel -> every device
vr = DEV["vr"]
P = PANEL
vr_p = f"M{inner(vr)[0]},{inner(vr)[1]} C{inner(vr)[0] + 110},{vr['y']} {P['x'] - 90},{P['y'] + 170} {P['x']},{P['y'] + 170}"
beams.append(beam(vr_p, VS + .1, .5, VS + 5.9, LILAC, 3))
for i in range(3):
    beams.append(packet(vr_p, VS + .1 + .15 * i, VS + .7 + .15 * i, "#fff" if i == 1 else LILAC))
tile_pos = []
for k, (dk, nm, act) in enumerate(TILES):
    col, row = k % 4, k // 4
    tx, ty = P["x"] + 14 + col * 90, P["y"] + 40 + row * 58
    tile_pos.append((tx, ty))
    d = DEV[dk]
    start = (P["x"] + P["w"], ty + 25) if d["side"] == 1 else (P["x"], ty + 25)
    p = direct(start, d, 90)
    t = TILE_T[k]
    beams.append(beam(p, t, .35, VS + 5.9, TEAL if d["side"] == 1 else LILAC, 2))
    beams.append(packet(p, t, t + .4, "#fff", 3.5))
# glasses -> everything
gl = DEV["glasses"]
others = [k for k in DEV if k != "glasses"]
for i, dk in enumerate(others):
    p = via_orb(gl, DEV[dk])
    beams.append(beam(p, GS + .15 + .04 * i, .7, GS + 1.6, TEAL, 1.8))
    beams.append(packet(p, GS + .15 + .04 * i, GS + .95 + .04 * i, MINT, 3.2))
add("".join(beams))

# ---------------- AR live links (under devices)
ar_l = []
for i, (lk, rk, lab, col, tt) in enumerate(AR_LINKS):
    a, b = DEV[lk], DEV[rk]
    (x0, y0), (x3, y3) = inner(a), inner(b)
    x1, y1, x2, y2 = x0 + 220, y0, x3 - 220, y3
    p = f"M{x0},{y0} C{x1},{y1} {x2},{y2} {x3},{y3}"
    t0 = A0 + 1.0 + .12 * i
    k = kf([(0, "opacity:0"), (t0, "opacity:0"), (t0 + .4, "opacity:1"), (AE, "opacity:1"), (T, "opacity:0")])
    u = 1 - tt
    mx = u ** 3 * x0 + 3 * u * u * tt * x1 + 3 * u * tt * tt * x2 + tt ** 3 * x3
    my = u ** 3 * y0 + 3 * u * u * tt * y1 + 3 * u * tt * tt * y2 + tt ** 3 * y3
    lw = tw(lab, 10.5, True) + 16
    ar_l.append(f'<g class="{k}"><path d="{p}" fill="none" stroke="{col}" stroke-opacity=".9" stroke-width="1.6" '
                f'stroke-dasharray="5 6" class="flow2"/>'
                + "".join(f'<circle r="3" fill="{col}"><animateMotion dur="{1.8 + .2 * j + .1 * i:.2f}s" begin="{-.6 * j:.1f}s" repeatCount="indefinite" path="{p}"/></circle>' for j in range(2))
                + f'<rect x="{mx - lw / 2:.1f}" y="{my - 10:.1f}" width="{lw:.1f}" height="20" rx="10" fill="#07102a" '
                f'fill-opacity=".92" stroke="{col}" stroke-width="1.1"/>'
                + text(mx, my + 3.8, lab, 10.5, col, 700, "middle", ".05em") + "</g>")
add("".join(ar_l))

# ---------------- devices
REACT = {}  # extra reactions inside device groups, keyed by device


def reactions(d):
    k, x, y = d["key"], d["x"], d["y"]
    s = []
    if k == "tv":
        s.append(f'<rect x="{x - 15}" y="{y - 10}" width="30" height="18" rx="1.5" fill="url(#tvs)" class="{persist(ev_movie["r"])}"/>')
        for col, kk in zip([PINK, TEAL, VIOLET], color_cycle(ev_sync["r"], [1, 2, 3])):
            s.append(f'<rect x="{x - 15}" y="{y - 10}" width="30" height="18" rx="1.5" fill="{col}" fill-opacity=".7" class="{kk}"/>')
        s.append(f'<path d="M{x - 3},{y - 5}l7 4-7 4z" fill="#fff" class="{persist(ev_movie["r"])}"/>')
    if k == "lights":
        s.append(f'<path d="M{x - 5},{y + 11}v-3c0-3-7-5-7-12a12 12 0 0 1 24 0c0 7-7 9-7 12v3z" fill="#f5f3ff" fill-opacity=".55" class="{persist(ev_movie["r"])}"/>')
    if k == "phone2":
        ev = EVENTS[4]
        a, b = "opacity:0;transform:translateY(-5px)", "opacity:1;transform:translateY(0)"
        s.append(f'<rect x="{x - 7}" y="{y - 12}" width="14" height="6" rx="1.5" fill="{TEAL}" '
                 f'class="{kf([(0, a), (ev["r"], a), (ev["r"] + .3, b), (T - .25, b), (T - .02, a)])}"/>')
        s.append(f'<circle cx="{x + 9}" cy="{y - 15}" r="3.5" fill="{PINK}" class="{persist(ev["r"])}"/>')
    if k == "plug":
        ev = EVENTS[5]
        tplug = TILE_T[[t[0] for t in TILES].index("plug")] + .35
        s.append(f'<circle cx="{x}" cy="{y - 7}" r="2.6" fill="#475569"/>')
        s.append(f'<circle cx="{x}" cy="{y - 7}" r="2.6" fill="{GREEN}" class="{kf([(0, "opacity:1"), (ev["r"], "opacity:1"), (ev["r"] + .15, "opacity:0"), (tplug, "opacity:0"), (tplug + .15, "opacity:1"), (T, "opacity:1")])}"/>')
    if k == "pc2":
        ev = EVENTS[6]
        r0 = ev["r"]
        s.append(f'<rect x="{x - 14}" y="{y - 12}" width="28" height="17" rx="1.5" fill="{SKY}" fill-opacity=".18" class="{persist(r0)}"/>')
        z, f1 = "transform:scaleX(0)", "transform:scaleX(1)"
        s.append(f'<g class="{win(r0, ev["s"] + DUR, .15)}"><rect x="{x - 11}" y="{y - 5}" width="22" height="4" rx="2" fill="#1e2a55"/>'
                 f'<rect x="{x - 11}" y="{y - 5}" width="22" height="4" rx="2" fill="{SKY}" '
                 f'class="{kf([(0, z), (r0, z), (r0 + 1.0, f1), (T, f1)], "transform-box:fill-box;transform-origin:0 50%;")}"/></g>')
    if k in ("vr", "vr2"):
        t0 = ev_vr["s"] + .2 if k == "vr" else ev_vr["r"]
        for dx in (-8.5, 8.5):
            s.append(f'<circle cx="{x + dx}" cy="{y - 1}" r="4.2" fill="{LILAC}" class="{persist(t0)}"/>')
    if k == "watch":
        ev = EVENTS[1]
        s.append(f'<circle cx="{x}" cy="{y}" r="8.5" fill="{AMBER}" fill-opacity=".85" class="{win(ev["r"], ev["s"] + DUR, .1)}"/>')
    if k == "glasses":
        s.append(f'<circle cx="{x + 11.5}" cy="{y - 1}" r="2.4" fill="{MINT}" class="blink"/>')
    return "".join(s)


def shake_class(d):
    if d["key"] != "watch":
        return ""
    ev = EVENTS[1]
    fr = [(0, "transform:translateX(0)"), (ev["r"], "transform:translateX(0)")]
    t = ev["r"]
    for i in range(8):
        fr.append((t + .06 * (i + 1), f"transform:translateX({2.5 if i % 2 == 0 else -2.5}px)"))
    fr.append((t + .06 * 9, "transform:translateX(0)"))
    t2 = t + .9
    for i in range(6):
        fr.append((t2 + .06 * (i + 1), f"transform:translateX({2.5 if i % 2 == 0 else -2.5}px)"))
    fr.append((t2 + .06 * 7, "transform:translateX(0)"))
    return kf(fr)


devs = []
for idx, d in enumerate(DEV.values()):
    x, y = d["x"], d["y"]
    intro = .15 + .06 * idx
    a = "opacity:0;transform:scale(.6)"
    k = kf([(0, a), (intro, a), (intro + .5, "opacity:1;transform:scale(1)"), (T - .05, "opacity:1;transform:scale(1)"), (T, a)], FB)
    sh = shake_class(d)
    devs.append(f'<g class="{k}"><g{(" class=%s" % chr(34) + sh + chr(34)) if sh else ""}>'
                f'<circle cx="{x}" cy="{y}" r="{R}" fill="#111a3d" stroke="#2dd4bf" stroke-opacity=".55" stroke-width="1.5"/>'
                f'{reactions(d)}<g class="ico" transform="translate({x} {y})">{ICONS[d["icon"]]}</g></g></g>')
add("".join(devs))

# coffee steam
add(steam(C_["x"], C_["y"] - 36, cof_windows))

# highlights + ripples
fx = []
for e in EVENTS:
    a = DEV[e["src"]]
    fx.append(ring_hl(a["x"], a["y"], e["s"], e["s"] + DUR - .1, e["c"]))
    fx.append(ripple(a["x"], a["y"], e["s"], e["c"]))
    fx.append(ripple(a["x"], a["y"], e["s"] + .45, e["c"]))
    for dk in e["dst"]:
        b = DEV[dk]
        fx.append(ring_hl(b["x"], b["y"], e["r"], e["s"] + DUR - .1, e["c"]))
        fx.append(ripple(b["x"], b["y"], e["r"], e["c"]))
        fx.append(ripple(b["x"], b["y"], e["r"] + .45, e["c"]))
fx.append(ring_hl(vr["x"], vr["y"], VS, VS + 6.1, LILAC))
fx.append(ripple(vr["x"], vr["y"], VS, LILAC))
fx.append(ripple(vr["x"], vr["y"], VS + .45, LILAC))
for k, (dk, _, _) in enumerate(TILES):
    d = DEV[dk]
    t = TILE_T[k] + .35
    c = TEAL if d["side"] == 1 else LILAC
    fx.append(ring_hl(d["x"], d["y"], t, VS + 6.0, c))
    fx.append(ripple(d["x"], d["y"], t, c))
fx.append(ring_hl(gl["x"], gl["y"], GS, A0 + .2, TEAL))
fx.append(ripple(gl["x"], gl["y"], GS, TEAL))
fx.append(ripple(gl["x"], gl["y"], GS + .4, TEAL))
for dk in others:
    d = DEV[dk]
    fx.append(ripple(d["x"], d["y"], GS + .85, MINT))
add("".join(fx))

# ---------------- labels (scene A) -> tags (AR)
lab_k = kf([(0, "opacity:1"), (A0 - .2, "opacity:1"), (A0 + .2, "opacity:0"), (T - .1, "opacity:0"), (T, "opacity:1")])
labs = [f'<g class="{lab_k}">']
for d in DEV.values():
    x, y = d["x"], d["y"]
    if d["side"] == -1:
        lx, an = x - R - 16, "end"
    else:
        lx, an = x + R + 16, "start"
    labs.append(text(lx, y - 1, d["name"], 14, "#e6ecff", 700, an, ".06em"))
    labs.append(text(lx, y + 17, d["sub"], 12, "#8ea3cc", 400, an))
labs.append("</g>")
add("".join(labs))

TAG_W, TAG_H = 196, 66
tags = []
order = []
for i in range(7):
    order += [LEFT[i][0], RIGHT[i][0]]
for k_i, key in enumerate(order):
    d = DEV[key]
    prim, l2, l3, bar, batt = TAGS[key]
    x0 = 12 if d["side"] == -1 else d["x"] + R + 10
    y0 = d["y"] - TAG_H / 2
    tp = A0 + .1 + .07 * k_i
    a = "opacity:0;transform:scale(.7)"
    b = "opacity:1;transform:scale(1)"
    org = f"transform-box:view-box;transform-origin:{d['x']}px {d['y']}px;"
    kk = kf([(0, a), (tp, a), (tp + .3, b), (AE, b), (T, a)], org)
    g = [f'<g class="{kk}">']
    g.append(f'<rect x="{x0}" y="{y0}" width="{TAG_W}" height="{TAG_H}" rx="10" fill="#060d26" fill-opacity=".9" '
             f'stroke="{TEAL}" stroke-opacity=".7" stroke-width="1.2"/>')
    # connector to the device
    cx_ = x0 + TAG_W if d["side"] == -1 else x0
    g.append(f'<circle cx="{cx_}" cy="{d["y"]}" r="2.6" fill="{MINT}"/>')
    g.append(text(x0 + 12, y0 + 20, {"coffee": "COFFEE"}.get(key, d["name"]), 12.5, "#eafffb", 700, ls=".05em"))
    # primary (may swap)
    pr_x = x0 + TAG_W - 12
    for j, (ptxt, pt0) in enumerate(prim):
        pt1 = prim[j + 1][1] if j + 1 < len(prim) else None
        if len(prim) == 1:
            cls = ""
        else:
            if pt0 == 0:
                cls = kf([(0, "opacity:1"), (pt1 - .1, "opacity:1"), (pt1, "opacity:0"), (T - .1, "opacity:0"), (T, "opacity:1")])
            else:
                cls = kf([(0, "opacity:0"), (pt0, "opacity:0"), (pt0 + .1, "opacity:1"), (AE, "opacity:1"), (T, "opacity:0")])
        col = AMBER if ptxt == "BREWING" else MINT
        g.append(text(pr_x, y0 + 20, ptxt, 12.5, col, 800, "end", cls=cls))
    if batt:
        bw = tw(prim[0][0], 12.5, True)
        bx = pr_x - bw - 22
        v = int(prim[0][0].rstrip("%")) / 100
        g.append(f'<rect x="{bx:.1f}" y="{y0 + 11}" width="15" height="8" rx="2" fill="none" stroke="{MINT}" stroke-width="1.1"/>'
                 f'<rect x="{bx + 15.5:.1f}" y="{y0 + 13.5}" width="1.6" height="3" fill="{MINT}"/>'
                 f'<rect x="{bx + 1.5:.1f}" y="{y0 + 12.5}" width="{12 * v:.1f}" height="5" rx="1" fill="{GREEN if v > .5 else AMBER}"/>')
    g.append(text(x0 + 12, y0 + 37, l2, 11.5, "#8ea3cc", 500))
    for j, (ltxt, lt0) in enumerate(l3):
        lt1 = l3[j + 1][1] if j + 1 < len(l3) else None
        if len(l3) == 1:
            cls = ""
        elif lt0 == 0:
            cls = kf([(0, "opacity:1"), (lt1 - .1, "opacity:1"), (lt1, "opacity:0"), (T - .1, "opacity:0"), (T, "opacity:1")])
        elif lt1:
            cls = win(lt0, lt1, .1)
        else:
            cls = kf([(0, "opacity:0"), (lt0, "opacity:0"), (lt0 + .1, "opacity:1"), (AE, "opacity:1"), (T, "opacity:0")])
        g.append(text(x0 + 12, y0 + 53, ltxt, 11.5, "#d7dcff", 600, cls=cls))
    # bar
    bwid = TAG_W - 24
    g.append(f'<rect x="{x0 + 12}" y="{y0 + 58}" width="{bwid}" height="3" rx="1.5" fill="#1b2650"/>')
    z = "transform:scaleX(0)"
    fr = [(0, z), (tp + .2, z), (tp + 1.0, f"transform:scaleX({bar})")]
    t = tp + 1.0
    w_ = 0
    while t < AE - 1:
        t += 1.1
        w_ += 1
        jit = bar + (.06 if w_ % 2 else -.04)
        fr.append((t, f"transform:scaleX({max(.03, min(1, jit)):.3f})"))
    fr.append((T, z))
    g.append(f'<rect x="{x0 + 12}" y="{y0 + 58}" width="{bwid}" height="3" rx="1.5" fill="url(#bar)" '
             f'class="{kf(fr, "transform-box:fill-box;transform-origin:0 50%;")}"/>')
    g.append("</g>")
    tags.append("".join(g))
add("".join(tags))

# ---------------- skill pills (source / target)
pills = []
for e in EVENTS:
    a = DEV[e["src"]]
    if a["side"] == -1:
        pills.append(pill(a["x"] + R + 14, a["y"] - 44, e["spill"], e["c"], e["s"] + .2, e["s"] + DUR - .15, "start", "NEW SKILL"))
    else:
        pills.append(pill(a["x"] - R - 14, a["y"] - 44, e["spill"], e["c"], e["s"] + .2, e["s"] + DUR - .15, "end", "NEW SKILL"))
    for dk, lab in e["tp"].items():
        b = DEV[dk]
        if b["side"] == 1:
            pills.append(pill(b["x"] - R - 14, b["y"] + 44, lab, e["c"], e["r"] + .1, e["s"] + DUR - .15, "end"))
        else:
            pills.append(pill(b["x"] + R + 14, b["y"] + 44, lab, e["c"], e["r"] + .1, e["s"] + DUR - .15, "start"))
pills.append(pill(vr["x"] + R + 14, vr["y"] + 44, "VR control room", LILAC, VS + .2, VS + 5.9, "start", "NEW SKILL"))
pills.append(pill(gl["x"] + R + 14, gl["y"] - 44, "Live device HUD", TEAL, GS + .2, A0, "start", "NEW SKILL"))
add("".join(pills))

# ---------------- VR control-room panel
pk = kf([(0, "opacity:0;transform:scale(.08)"), (VS + .55, "opacity:0;transform:scale(.08)"),
         (VS + .95, "opacity:1;transform:scale(1)"), (VS + 5.7, "opacity:1;transform:scale(1)"),
         (VS + 6.1, "opacity:0;transform:scale(.96)"), (T, "opacity:0;transform:scale(.08)")],
        f"transform-box:view-box;transform-origin:{P['x']}px {P['y'] + 170}px;")
pn = [f'<g class="{pk}">',
      f'<rect x="{P["x"]}" y="{P["y"]}" width="{P["w"]}" height="{P["h"]}" rx="16" fill="#0a1236" fill-opacity=".94" stroke="{LILAC}" stroke-width="1.6"/>',
      f'<rect x="{P["x"]}" y="{P["y"]}" width="{P["w"]}" height="{P["h"]}" rx="16" fill="url(#hgrid)"/>',
      f'<rect x="{P["x"] - 4}" y="{P["y"] - 4}" width="{P["w"] + 8}" height="{P["h"] + 8}" rx="19" fill="none" stroke="{LILAC}" stroke-opacity=".35" stroke-width="6" filter="url(#blur)"/>',
      text(P["x"] + 16, P["y"] + 25, "VR CONTROL ROOM", 12, LILAC, 800, ls=".16em"),
      text(P["x"] + P["w"] - 16, P["y"] + 25, "auto-generated · 12 devices", 11, "#8ea3cc", 500, "end")]
for k, (dk, nm, act) in enumerate(TILES):
    tx, ty = tile_pos[k]
    t = TILE_T[k]
    d = DEV[dk]
    c = TEAL if d["side"] == 1 else LILAC
    pn.append(f'<rect x="{tx}" y="{ty}" width="82" height="50" rx="9" fill="#111a3d" stroke="#2a3870" stroke-width="1"/>')
    pn.append(f'<g class="{win(t, VS + 6.0, .12)}"><rect x="{tx}" y="{ty}" width="82" height="50" rx="9" fill="{c}" fill-opacity=".22" stroke="{c}" stroke-width="1.6"/></g>')
    pn.append(f'<g class="ico" transform="translate({tx + 19} {ty + 25}) scale(.62)">{ICONS[d["icon"]]}</g>')
    pn.append(text(tx + 38, ty + 22, nm, 10.5, "#e6ecff", 700))
    pn.append(text(tx + 38, ty + 37, "Ready", 10, "#6b7cae", 500,
                   cls=kf([(0, "opacity:1"), (t, "opacity:1"), (t + .1, "opacity:0"), (T - .1, "opacity:0"), (T, "opacity:1")])))
    pn.append(text(tx + 38, ty + 37, act + " ✓", 10, c, 800,
                   cls=kf([(0, "opacity:0"), (t, "opacity:0"), (t + .1, "opacity:1"), (VS + 6.0, "opacity:1"), (T, "opacity:0")])))
# pinch hand cursor hopping across tiles
fr = []
for k in range(len(TILES)):
    tx, ty = tile_pos[k]
    fr += [(TILE_T[k] - .18, f"transform:translate({tx + 66}px,{ty + 36}px) scale(1)"),
           (TILE_T[k], f"transform:translate({tx + 66}px,{ty + 36}px) scale(.7)"),
           (TILE_T[k] + .1, f"transform:translate({tx + 66}px,{ty + 36}px) scale(1)")]
first = fr[0][1]
fr = [(0, first)] + fr + [(T, first)]
pn.append(f'<g class="{kf(fr, "transform-box:view-box;transform-origin:0 0;")}"><g class="{win(TILE_T[0] - .3, TILE_T[-1] + .5, .15)}">'
          f'<circle r="9" fill="#fff" fill-opacity=".18" stroke="#fff" stroke-width="1.6"/><circle r="3" fill="#fff"/></g></g>')
pn.append("</g>")
add("".join(pn))

# ---------------- caption card
add(f'<g class="{kf([(0, "opacity:0"), (.5, "opacity:0"), (1.0, "opacity:1"), (AE, "opacity:1"), (T, "opacity:0")])}">'
    f'<rect x="360" y="20" width="560" height="108" rx="18" fill="#0b1433" fill-opacity=".85" stroke="#2dd4bf" stroke-opacity=".28"/></g>')
caps = []


def caption(chip, title, desc, color, t0, t1, tsize=27):
    k = win(t0, t1, .25)
    return (f'<g class="{k}">' + text(640, 49, chip, 12, color, 800, "middle", ".2em")
            + text(640, 86, title, tsize, "#ffffff", 800, "middle")
            + text(640, 112, desc, 14, "#9fb3d9", 400, "middle") + "</g>")


for e in EVENTS:
    caps.append(caption(e["chip"], e["title"], e["desc"], e["c"], e["s"] + .05, e["s"] + DUR - .02))
caps.append(caption("VR HEADSET  →  EVERYTHING", "Your whole home, from VR",
                    "OpenBridge built a VR control room for 12 devices. One pinch each.", LILAC, VS + .05, GS - .02))
caps.append(caption("SMART GLASSES  →  EVERYTHING", "See every device. Live.",
                    "Battery, distance, CPU and RAM, floating over every device.", TEAL, GS + .05, A0 + .5))
caps.append(caption("THROUGH THE GLASSES  ·  SAME HUD IN VR", "Every device, in your field of view",
                    "14 devices · 8 live links · 6 protocols · zero cloud", MINT, A0 + .5, AE + .5, 26))
add("".join(caps))

# ---------------- header: brand + counters
add(f'<g class="{kf([(0, "opacity:0"), (.3, "opacity:0"), (.9, "opacity:1"), (T, "opacity:1")])}">'
    + text(40, 62, "OpenBridge", 30, "url(#title)", 800, ls="-.5")
    + f'<rect x="40" y="76" width="122" height="24" rx="12" fill="#2dd4bf" fill-opacity=".12" stroke="#2dd4bf" stroke-opacity=".45"/>'
    + f'<circle cx="56" cy="88" r="4" fill="#f43f5e" class="blink"/>'
    + text(68, 92.5, "LIVE DEMO", 11, "#c7fff6", 800, ls=".16em") + "</g>")
add(text(1240, 46, "SKILLS CREATED", 11, "#8ea3cc", 700, "end", ".18em"))
counts = [(0, 0)]
for i, e in enumerate(EVENTS):
    counts.append((e["r"], i + 1))
for k in range(len(TILES)):
    counts.append((TILE_T[k] + .35, len(EVENTS) + 1 + k))
counts.append((GS + .9, len(EVENTS) + len(TILES) + 1))
cn = []
for i, (t, v) in enumerate(counts):
    t1 = counts[i + 1][0] if i + 1 < len(counts) else None
    if t == 0:
        cls = kf([(0, "opacity:1"), (t1, "opacity:1"), (t1 + .01, "opacity:0"), (T - .05, "opacity:0"), (T, "opacity:1")])
    elif t1:
        cls = kf([(0, "opacity:0"), (t, "opacity:0"), (t + .01, "opacity:1"), (t1, "opacity:1"), (t1 + .01, "opacity:0")])
    else:
        cls = kf([(0, "opacity:0"), (t, "opacity:0"), (t + .01, "opacity:1"), (T - .05, "opacity:1"), (T, "opacity:0")])
    cn.append(text(1240, 86, f"{v:02d}", 38, "url(#title)", 800, "end", cls=cls))
add("".join(cn))
add(text(1240, 108, "14 DEVICES · 6 PROTOCOLS", 11, "#8ea3cc", 600, "end", ".12em"))

# ---------------- bottom timeline
chap = [(e["tl"], e["s"]) for e in EVENTS] + [("VR control", VS), ("Glasses HUD", GS)]
x_a, x_b, ty = 300, 980, 716
n = len(chap)
xs = [x_a + (x_b - x_a) * i / (n - 1) for i in range(n)]
tl = [f'<rect x="{x_a}" y="{ty - 1}" width="{x_b - x_a}" height="2" rx="1" fill="#1b2650"/>']
fr = [(0, "transform:scaleX(0)")]
for i, (_, t) in enumerate(chap):
    fr.append((t, f"transform:scaleX({i / (n - 1):.4f})"))
fr += [(AE, "transform:scaleX(1)"), (T, "transform:scaleX(1)")]
tl.append(f'<rect x="{x_a}" y="{ty - 1}" width="{x_b - x_a}" height="2" rx="1" fill="url(#bar)" class="{kf(fr, "transform-box:fill-box;transform-origin:0 50%;")}"/>')
for i, (lab, t) in enumerate(chap):
    t1 = chap[i + 1][1] if i + 1 < n else AE
    tl.append(f'<circle cx="{xs[i]:.1f}" cy="{ty}" r="4" fill="#1b2650" stroke="#3b4a80"/>')
    tl.append(f'<circle cx="{xs[i]:.1f}" cy="{ty}" r="5.5" fill="{TEAL}" class="{persist(t)}"/>')
    tl.append(text(xs[i], ty + 22, lab, 11, "#5f719e", 600, "middle"))
    tl.append(text(xs[i], ty + 22, lab, 11, "#e6fffb", 700, "middle", cls=win(t, t1, .15)))
add("".join(tl))

# ---------------- AR visor overlay, scanline, reticle
vis_k = kf([(0, "opacity:0"), (A0 - .3, "opacity:0"), (A0 + .2, "opacity:1"), (AE, "opacity:1"), (T, "opacity:0")])
br = []
for (cx_, cy_, sx_, sy_) in [(14, 14, 1, 1), (W - 14, 14, -1, 1), (14, H - 14, 1, -1), (W - 14, H - 14, -1, -1)]:
    br.append(f'<path d="M{cx_},{cy_ + sy_ * 46} V{cy_} H{cx_ + sx_ * 46}" fill="none" stroke="{MINT}" stroke-width="3" stroke-linecap="round"/>')
add(f'<g class="{vis_k}" pointer-events="none"><rect width="{W}" height="{H}" fill="url(#vig)"/>'
    f'<rect width="{W}" height="{H}" fill="url(#hgrid)"/>'
    f'<rect x="8" y="8" width="{W - 16}" height="{H - 16}" rx="30" fill="none" stroke="{TEAL}" stroke-opacity=".5" stroke-width="1.5"/>'
    + "".join(br)
    + text(W - 34, H - 52, "FOV 52° · 60 Hz · TRACKING 14", 10.5, "#7cf3e1", 700, "end", ".14em")
    + "</g>")
sc0 = "opacity:0;transform:translateY(-120px)"
add(f'<rect x="0" y="0" width="{W}" height="120" fill="url(#scan)" '
    f'class="{kf([(0, sc0), (A0 - .3, sc0), (A0 - .25, "opacity:1;transform:translateY(-120px)"), (A0 + 1.1, f"opacity:1;transform:translateY({H}px)"), (A0 + 1.15, sc0), (T, sc0)])}"/>')

# reticle path
pts = [("c", CX, CY, A0 + 1.6)]
fr = [(0, f"transform:translate({CX}px,{CY}px)"), (A0 + 1.6, f"transform:translate({CX}px,{CY}px)")]
for dk, l0, l1, _ in LOCKS:
    d = DEV[dk]
    fr += [(l0, f"transform:translate({d['x']}px,{d['y']}px)"), (l1, f"transform:translate({d['x']}px,{d['y']}px)")]
fr += [(A0 + 10.2, f"transform:translate({CX}px,{CY}px)"), (T, f"transform:translate({CX}px,{CY}px)")]
ret_move = kf(fr, "transform-box:view-box;transform-origin:0 0;")
ret_vis = win(A0 + 1.4, A0 + 10.4, .3)
pf = [(0, "transform:scale(1)")]
for dk, l0, l1, _ in LOCKS:
    pf += [(l0 + .6, "transform:scale(1)"), (l0 + .7, "transform:scale(.72)"), (l0 + .85, "transform:scale(1)")]
ret_pinch = kf(pf, "transform-box:view-box;transform-origin:0 0;")
dwell = [(0, "stroke-dashoffset:1")]
for dk, l0, l1, _ in LOCKS:
    dwell += [(l0, "stroke-dashoffset:1"), (l0 + .65, "stroke-dashoffset:0"), (l1, "stroke-dashoffset:0"), (l1 + .02, "stroke-dashoffset:1")]
dwell_k = kf(dwell)
rb = []
for sx_, sy_ in [(1, 1), (-1, 1), (1, -1), (-1, -1)]:
    rb.append(f'<path d="M{sx_ * -46},{sy_ * -30} V{sy_ * -46} H{sx_ * -30}" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/>')
add(f'<g class="{ret_move}"><g class="{ret_vis}"><g class="{ret_pinch}">' + "".join(rb)
    + f'<circle r="40" fill="none" stroke="{MINT}" stroke-opacity=".25" stroke-width="3"/>'
    f'<circle r="40" fill="none" stroke="{MINT}" stroke-width="3" pathLength="1" stroke-dasharray="1 1" '
    f'transform="rotate(-90)" class="{dwell_k}"/><circle r="2.5" fill="#fff"/></g></g></g>')
# lock chips
for dk, l0, l1, chip in LOCKS:
    d = DEV[dk]
    if d["side"] == 1:
        add(pill(d["x"] - R - 18, d["y"] + 50, chip, MINT, l0 + .1, l1, "end", "LOOK"))
    else:
        add(pill(d["x"] + R + 18, d["y"] + 50, chip, MINT, l0 + .1, l1, "start", "LOOK"))

# ---------------- visor transition from the glasses
vt0 = "opacity:0;transform:scale(.03)"
add(f'<rect x="8" y="8" width="{W - 16}" height="{H - 16}" rx="30" fill="{TEAL}" fill-opacity=".12" stroke="{MINT}" stroke-width="4" '
    f'class="{kf([(0, vt0), (GS + 1.0, vt0), (GS + 1.05, "opacity:1;transform:scale(.03)"), (A0 - .05, "opacity:1;transform:scale(1)"), (A0 + .5, "opacity:0;transform:scale(1)"), (T, vt0)], f"transform-box:view-box;transform-origin:{gl['x']}px {gl['y']}px;")}"/>')

# ---------------- loop fade
add(f'<rect width="{W}" height="{H}" fill="#05070f" class="{kf([(0, "opacity:1"), (.8, "opacity:0"), (AE, "opacity:0"), (T, "opacity:1")])}"/>')
add("</svg>")

BASE_CSS = (
    ".ico{fill:none;stroke:#c7fff6;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}"
    ".flow{animation:flow 1.6s linear infinite}.flow2{animation:flow 1s linear infinite}"
    "@keyframes flow{to{stroke-dashoffset:-22}}"
    f".pulse{{transform-origin:{CX}px {CY}px;animation:pulse 3.2s ease-in-out infinite}}"
    "@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.1)}}"
    f".ring{{transform-origin:{CX}px {CY}px;animation:spin 18s linear infinite}}"
    f".ring2{{transform-origin:{CX}px {CY}px;animation:spin 26s linear infinite reverse}}"
    "@keyframes spin{to{transform:rotate(360deg)}}"
    ".blink{animation:blink 1.4s ease-in-out infinite}@keyframes blink{50%{opacity:.25}}"
)
svg = "\n".join(out).replace("@@CSS@@", BASE_CSS + "".join(css))
dest = sys.argv[1] if len(sys.argv) > 1 else "interop-demo.svg"
with open(dest, "w", encoding="utf-8") as f:
    f.write(svg)
print(dest, len(svg.encode()), "bytes,", _n[0], "keyframe sets")
