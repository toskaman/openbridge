"""Line icons for the glasses, drawn from ActiveLook primitives (no bitmaps to upload, crisp at any size).

Every icon is centred on (cx, cy) and fits in a square of side 2*s. They use one tone; the screens decide which.
No brand logos: messaging apps are shown with a lettered badge and their name.
"""
from __future__ import annotations


def chat(p, cx, cy, s, tone):
    p.round_rect(cx - s, cy - s * 0.75, cx + s, cy + s * 0.45, int(s * 0.3), tone)
    p.line(cx - s * 0.45, cy + s * 0.45, cx - s * 0.6, cy + s * 0.9, tone)
    p.line(cx - s * 0.6, cy + s * 0.9, cx - s * 0.1, cy + s * 0.45, tone)
    for dx in (-0.45, 0, 0.45):
        p.circle(cx + s * dx, cy - s * 0.15, max(1, s // 9), tone, True)


def tv(p, cx, cy, s, tone):
    p.round_rect(cx - s, cy - s * 0.7, cx + s, cy + s * 0.5, max(2, s // 6), tone)
    p.line(cx - s * 0.4, cy + s * 0.85, cx + s * 0.4, cy + s * 0.85, tone)
    p.line(cx, cy + s * 0.5, cx, cy + s * 0.85, tone)


def vacuum(p, cx, cy, s, tone):
    p.circle(cx, cy, s, tone)
    p.circle(cx, cy, s * 0.45, tone)
    p.line(cx - s * 0.5, cy - s * 0.72, cx + s * 0.5, cy - s * 0.72, tone)


def mic(p, cx, cy, s, tone):
    p.round_rect(cx - s * 0.35, cy - s, cx + s * 0.35, cy + s * 0.2, int(s * 0.34), tone)
    p.arc(cx, cy - s * 0.05, s * 0.65, 0, 180, tone)
    p.line(cx, cy + s * 0.6, cx, cy + s, tone)
    p.line(cx - s * 0.35, cy + s, cx + s * 0.35, cy + s, tone)


def bulb(p, cx, cy, s, tone):
    p.circle(cx, cy - s * 0.25, s * 0.65, tone)
    p.line(cx - s * 0.3, cy + s * 0.6, cx + s * 0.3, cy + s * 0.6, tone)
    p.line(cx - s * 0.22, cy + s * 0.85, cx + s * 0.22, cy + s * 0.85, tone)


def gear(p, cx, cy, s, tone):
    p.circle(cx, cy, s * 0.6, tone)
    p.circle(cx, cy, s * 0.22, tone)
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (-0.7, -0.7), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7)):
        p.line(cx + dx * s * 0.62, cy + dy * s * 0.62, cx + dx * s * 0.95, cy + dy * s * 0.95, tone)


def volume(p, cx, cy, s, tone):
    x = cx - s * 0.55
    p.rect(x - s * 0.35, cy - s * 0.25, x, cy + s * 0.25, tone)
    p.line(x, cy - s * 0.25, x + s * 0.4, cy - s * 0.6, tone)
    p.line(x, cy + s * 0.25, x + s * 0.4, cy + s * 0.6, tone)
    p.line(x + s * 0.4, cy - s * 0.6, x + s * 0.4, cy + s * 0.6, tone)
    p.arc(x + s * 0.45, cy, s * 0.45, -45, 45, tone)
    p.arc(x + s * 0.45, cy, s * 0.8, -45, 45, tone)


def apps(p, cx, cy, s, tone):
    h = s * 0.42
    for dx in (-1, 1):
        for dy in (-1, 1):
            x, y = cx + dx * s * 0.5, cy + dy * s * 0.5
            p.round_rect(x - h, y - h, x + h, y + h, max(2, int(h * 0.4)), tone)


def dpad(p, cx, cy, s, tone):
    r = max(3, int(s * 0.22))
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        p.circle(cx + dx * s * 0.7, cy + dy * s * 0.7, r, tone)
    p.circle(cx, cy, r, tone, True)


def play(p, cx, cy, s, tone):
    p.line(cx - s * 0.4, cy - s * 0.6, cx - s * 0.4, cy + s * 0.6, tone)
    p.line(cx - s * 0.4, cy - s * 0.6, cx + s * 0.6, cy, tone)
    p.line(cx - s * 0.4, cy + s * 0.6, cx + s * 0.6, cy, tone)


def pause(p, cx, cy, s, tone):
    p.rect(cx - s * 0.5, cy - s * 0.6, cx - s * 0.15, cy + s * 0.6, tone, True)
    p.rect(cx + s * 0.15, cy - s * 0.6, cx + s * 0.5, cy + s * 0.6, tone, True)


def play_pause(p, cx, cy, s, tone):
    play(p, cx - s * 0.35, cy, s * 0.7, tone)
    p.rect(cx + s * 0.35, cy - s * 0.42, cx + s * 0.5, cy + s * 0.42, tone, True)
    p.rect(cx + s * 0.7, cy - s * 0.42, cx + s * 0.85, cy + s * 0.42, tone, True)


def power(p, cx, cy, s, tone):
    p.arc(cx, cy, s * 0.75, -60, 240, tone)
    p.line(cx, cy - s, cx, cy - s * 0.15, tone)


def check(p, cx, cy, s, tone):
    p.line(cx - s * 0.6, cy, cx - s * 0.15, cy + s * 0.5, tone)
    p.line(cx - s * 0.15, cy + s * 0.5, cx + s * 0.65, cy - s * 0.5, tone)


def cross(p, cx, cy, s, tone):
    p.line(cx - s * 0.5, cy - s * 0.5, cx + s * 0.5, cy + s * 0.5, tone)
    p.line(cx - s * 0.5, cy + s * 0.5, cx + s * 0.5, cy - s * 0.5, tone)


def home(p, cx, cy, s, tone):
    p.line(cx - s, cy - s * 0.05, cx, cy - s * 0.85, tone)
    p.line(cx, cy - s * 0.85, cx + s, cy - s * 0.05, tone)
    p.rect(cx - s * 0.65, cy - s * 0.2, cx + s * 0.65, cy + s * 0.8, tone)


def search(p, cx, cy, s, tone):
    p.circle(cx - s * 0.15, cy - s * 0.15, s * 0.55, tone)
    p.line(cx + s * 0.25, cy + s * 0.25, cx + s * 0.8, cy + s * 0.8, tone)


def back(p, cx, cy, s, tone):
    p.line(cx + s * 0.3, cy - s * 0.6, cx - s * 0.3, cy, tone)
    p.line(cx - s * 0.3, cy, cx + s * 0.3, cy + s * 0.6, tone)


def plus(p, cx, cy, s, tone):
    p.line(cx - s * 0.5, cy, cx + s * 0.5, cy, tone)
    p.line(cx, cy - s * 0.5, cx, cy + s * 0.5, tone)


def minus(p, cx, cy, s, tone):
    p.line(cx - s * 0.5, cy, cx + s * 0.5, cy, tone)


def bell(p, cx, cy, s, tone):
    p.arc(cx, cy - s * 0.1, s * 0.6, 180, 360, tone)
    p.line(cx - s * 0.6, cy - s * 0.1, cx - s * 0.7, cy + s * 0.5, tone)
    p.line(cx + s * 0.6, cy - s * 0.1, cx + s * 0.7, cy + s * 0.5, tone)
    p.line(cx - s * 0.8, cy + s * 0.5, cx + s * 0.8, cy + s * 0.5, tone)
    p.circle(cx, cy + s * 0.75, max(1, s // 7), tone, True)


def badge(p, cx, cy, r, letter, tone, font=1):
    """Lettered app badge: a ring and one capital."""
    from src.glasses.panel import FONTS, text_width
    p.circle(cx, cy, r, tone)
    p.text(cx - text_width(letter, font) / 2, cy - FONTS[font][0] / 2 - 1, letter, font, tone)


ICONS = {'chat': chat, 'tv': tv, 'vacuum': vacuum, 'mic': mic, 'bulb': bulb, 'gear': gear, 'volume': volume,
         'apps': apps, 'dpad': dpad, 'play': play, 'pause': pause, 'play_pause': play_pause, 'power': power,
         'check': check, 'cross': cross, 'home': home, 'search': search, 'back': back, 'plus': plus, 'minus': minus,
         'bell': bell}


def draw(p, name, cx, cy, s, tone):
    ICONS.get(name, bell)(p, cx, cy, int(s), tone)
