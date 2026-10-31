"""Procedural launcher icon for the OpenBridge Companion: the VoiceOrb sphere.

Generates (deterministic, no network, no assets):
  companion/android/res/mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher.png
  companion/android/res/mipmap-{...}/ic_launcher_round.png
  companion/android/res/drawable/ic_launcher_foreground.png   (432px, adaptive)
  companion/android/res/drawable/tv_banner.png               (320x180, leanback)
plus mipmap-anydpi-v26/ic_launcher.xml + ic_launcher_round.xml (adaptive).

Design: glowing cyan->violet sphere with three satellite dots on deep navy,
matching the in-app VoiceOrb (CYAN/VIOLET) and the FLOWS glyph language.
"""
import math
import random
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    sys.exit('PIL required: pip install pillow')

RES = Path('companion/android/res')
NAVY_TOP = (11, 16, 32)
NAVY_BOT = (24, 30, 58)
CORE = (255, 255, 255)
CYAN = (34, 211, 238)
VIOLET = (139, 92, 246)
DENS = {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192}


def lerp(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def navy_bg(size):
    img = Image.new('RGB', (size, size))
    px = img.load()
    for y in range(size):
        c = lerp(NAVY_TOP, NAVY_BOT, y / max(1, size - 1))
        for x in range(size):
            px[x, y] = c
    return img.convert('RGBA')


def sphere_layer(size, diameter, glow=1.0):
    """RGBA layer: glow halo + gradient sphere + 3 satellite dots. Centered."""
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    px = layer.load()
    c = size / 2
    r = diameter / 2
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - c + 0.5, y - c + 0.5) / r
            if d >= 2.2:
                continue
            if d <= 1.0:
                # core -> cyan -> violet rim
                col = lerp(CORE, CYAN, min(1.0, d * 1.6)) if d < 0.55 else lerp(CYAN, VIOLET, (d - 0.55) / 0.45)
                a = 255
            else:
                t = (d - 1.0) / 1.2  # halo falloff
                col = lerp(VIOLET, (20, 28, 60), t)
                a = int(140 * (1 - t) ** 1.8 * glow)
                if a <= 0:
                    continue
            px[x, y] = col + (a,)
    rng = random.Random(0x0B1D)
    dr = ImageDraw.Draw(layer)
    dot_r = max(2.0, size * 0.012)
    margin = dot_r + 2
    for _ in range(3):
        ang = rng.uniform(0, math.tau)
        dist = r * rng.uniform(1.3, 1.55)
        x = min(max(c + math.cos(ang) * dist, margin), size - margin)
        y = min(max(c + math.sin(ang) * dist, margin), size - margin)
        dr.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r], fill=CYAN + (230,))
    return layer


def legacy_icon(size):
    return Image.alpha_composite(navy_bg(size), sphere_layer(size, size * 0.62)).convert('RGB')


def round_icon(size):
    sq = Image.alpha_composite(navy_bg(size), sphere_layer(size, size * 0.62))
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    sq.putalpha(mask)
    return sq


def banner():
    w, h = 320, 180
    img = Image.new('RGB', (w, h))
    px = img.load()
    for y in range(h):
        c = lerp(NAVY_TOP, NAVY_BOT, y / (h - 1))
        for x in range(w):
            px[x, y] = c
    img = img.convert('RGBA')
    sph = sphere_layer(180, 92)
    img.alpha_composite(sph, (2, 0))
    dr = ImageDraw.Draw(img)
    try:
        size = 40
        while size > 10:
            fb = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', size)
            if dr.textlength('OpenBridge', font=fb) <= 178:
                break
            size -= 2
        fr = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 22)
    except OSError:
        fb = fr = ImageFont.load_default()
    dr.text((132, 56), 'OpenBridge', font=fb, fill=(255, 255, 255))
    dr.text((134, 112), 'COMPANION', font=fr, fill=CYAN)
    return img.convert('RGB')


ADAPTIVE = ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
            '    <background android:drawable="@color/ic_launcher_background" />\n'
            '    <foreground android:drawable="@drawable/ic_launcher_foreground" />\n'
            '</adaptive-icon>\n')
COLORS = ('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
          '    <color name="ic_launcher_background">#0B1020</color>\n</resources>\n')


def main():
    for d, px in DENS.items():
        m = RES / ('mipmap-%s' % d)
        m.mkdir(parents=True, exist_ok=True)
        legacy_icon(px).save(m / 'ic_launcher.png')
        round_icon(px).save(m / 'ic_launcher_round.png')
    dw = RES / 'drawable'
    dw.mkdir(parents=True, exist_ok=True)
    sphere_layer(432, 250).save(dw / 'ic_launcher_foreground.png')
    banner().save(dw / 'tv_banner.png')
    (RES / 'values').mkdir(exist_ok=True)
    (RES / 'values' / 'colors.xml').write_text(COLORS, encoding='utf-8')
    anydpi = RES / 'mipmap-anydpi-v26'
    anydpi.mkdir(exist_ok=True)
    (anydpi / 'ic_launcher.xml').write_text(ADAPTIVE, encoding='utf-8')
    (anydpi / 'ic_launcher_round.xml').write_text(ADAPTIVE, encoding='utf-8')
    print('icon res written under', RES)


if __name__ == '__main__':
    main()
