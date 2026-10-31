"""Rebuild the hero tour GIF from authentic repo captures only.

Usage: python dev/rebuild_tour_gif.py
Overwrites docs/jury/screens/openbridge-tour.gif (previous bytes preserved
in git history + the pre-redesign delta backup). Every frame is a real
capture already committed under docs/jury/screens/; captions state only
what the frame shows.

Palette: Connected Intelligence (navy #0B1020, AI blue, verified teal).
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "jury" / "screens"
OUT = SHOTS / "openbridge-tour.gif"

NAVY = (11, 16, 32)
TEAL = (25, 197, 181)
WHITE = (245, 248, 255)

FRAMES = [
    ("fabric-tv-relay-redacted-1440.png", "One live graph - 24 real home devices"),
    ("ask-openbridge-1440.png", "Ask in plain words - Meta routes, you approve"),
    ("phone-companion-0-12-paired.png", "Phone Companion 0.12 - PAIRED"),
    ("tv-companion-0-11-paired.png", "TV Companion - PAIRED relay"),
    ("g04-watch-quick-controls.png", "Watch7 - native QUICK CONTROLS"),
    ("s5b_pressed.png", "Meta-built TV panel - press dispatched, receipted"),
]

WIDTH, HEIGHT = 960, 540
CAPTION_H = 84


def font():
    for candidate in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, 27)
        except OSError:
            continue
    return ImageFont.load_default()


def frame(path, caption, typeface):
    canvas = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    with Image.open(SHOTS / path).convert("RGB") as shot:
        shot.thumbnail((WIDTH - 24, HEIGHT - CAPTION_H - 24), Image.LANCZOS)
        canvas.paste(shot, ((WIDTH - shot.width) // 2, (HEIGHT - CAPTION_H - shot.height) // 2))
    draw = ImageDraw.Draw(canvas)
    bar_y = HEIGHT - CAPTION_H
    draw.line([(0, bar_y), (WIDTH, bar_y)], fill=TEAL, width=3)
    box = draw.textbbox((0, 0), caption, font=typeface)
    draw.text(((WIDTH - (box[2] - box[0])) / 2, bar_y + 20), caption, font=typeface, fill=WHITE)
    return canvas.quantize(colors=128, method=Image.MEDIANCUT)


def main():
    typeface = font()
    frames = [frame(path, caption, typeface) for path, caption in FRAMES]
    frames[0].save(
        OUT,
        save_all=True,
        append_images=frames[1:],
        duration=1800,
        loop=0,
        optimize=True,
    )
    print("Wrote %s (%d bytes, %d frames)" % (OUT, OUT.stat().st_size, len(frames)))


if __name__ == "__main__":
    main()
