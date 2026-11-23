"""Drawing surface for ActiveLook / ENGO glasses: one place that turns shapes into ActiveLook frames.

Every glasses screen in OpenBridge is drawn through a Panel, never with raw commands, so that three things that
depend on the real hardware live in one spot:

- orientation: the panel can be mounted rotated 180° (native ActiveLook coordinates start bottom-right). Set
  ``rotate180=True`` once the calibration screen shows the arrow upside down on the real glasses;
- colour: ENGO 3 draws with a small palette (cyan, green, amber, red, white) scaled by a 0-15 level; ENGO 1/2 only
  have the 0-15 level of their yellow-green panel. Screens ask for *tones*, the panel picks the right commands;
- text metrics: the glasses' fonts are fixed; widths are estimated conservatively so text never overflows.

Black pixels are transparent on the see-through OLED and cost no power, so the design language draws outlines and
type, and fills only small accents.
"""
from __future__ import annotations

from src.adapters import activelook as AL

W, H = 304, 256
SAFE = (14, 12, 290, 244)          # x0, y0, x1, y1 kept clear of the lens edge

# font id -> (glyph height px, average advance px). Conservative: real ActiveLook fonts are a little narrower.
FONTS = {0: (12, 7), 1: (18, 10), 2: (25, 14), 3: (34, 19), 4: (46, 26), 5: (58, 33)}

# tone -> (ENGO 3 palette index, level 0-15). Mono glasses use the level only.
TONES = {
    'primary': (0x0F, 15), 'secondary': (0x0F, 11), 'muted': (0x0F, 8), 'faint': (0x0F, 7),
    'accent': (0x04, 15), 'accent_dim': (0x04, 9), 'ok': (0x01, 15), 'warn': (0x02, 15), 'alert': (0x03, 15),
    'black': (0x00, 0),
}
# Levels 1-6 are avoided on purpose: ENGO 3 firmware (and HUD Studio) read a 0x00-0x06 colour byte as a palette
# index, so a "level 3" would come out red. Dim tones therefore stay at levels 7-11.


def text_width(text: str, font: int) -> int:
    adv = FONTS.get(font, FONTS[1])[1]
    narrow = sum(1 for c in text if c in "il.,:;'!|() ")
    return max(0, len(text) * adv - narrow * adv // 2)


def fit(text: str, font: int, width: int) -> str:
    """Longest prefix that fits, with an ellipsis when cut."""
    text = ' '.join(str(text or '').split())
    if text_width(text, font) <= width:
        return text
    while text and text_width(text + '…', font) > width:
        text = text[:-1]
    return text.rstrip() + '…'


def wrap(text: str, font: int, width: int, max_lines: int) -> list[str]:
    words, lines, cur = ' '.join(str(text or '').split()).split(' '), [], ''
    for w in words:
        trial = (cur + ' ' + w).strip()
        if text_width(trial, font) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = w if text_width(w, font) <= width else fit(w, font, width)
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and ' '.join(lines) != ' '.join(words):
        lines[-1] = fit(lines[-1] + ' …', font, width)
    return lines[:max_lines]


class Panel:
    def __init__(self, colour: bool = True, rotate180: bool = False):
        self.colour, self.rotate180 = colour, rotate180
        self.frames: list[bytes] = []
        self._ink = None

    # -------- output --------
    def to_bytes(self) -> bytes:
        return b''.join(self.frames)

    def begin(self):
        self.frames.append(AL.cmd_hold_flush(0))
        self.frames.append(AL.cmd_clear())
        self._ink = None
        return self

    def end(self):
        self.frames.append(AL.cmd_hold_flush(1))
        return self

    # -------- coordinates and colour --------
    def _p(self, x, y):
        x, y = int(round(x)), int(round(y))
        return (W - 1 - x, H - 1 - y) if self.rotate180 else (x, y)

    def ink(self, tone: str):
        if tone == self._ink:
            return
        idx, level = TONES.get(tone, TONES['primary'])
        self.frames.append(AL.cmd_grey(level))
        if self.colour:
            self.frames.append(AL.cmd_color(idx))
        self._ink = tone

    def _text_colour(self, tone):
        idx, level = TONES.get(tone, TONES['primary'])
        if not self.colour:
            return level
        if level == 15 and idx != 0x0F:
            return idx                      # palette colour at full strength
        self.ink(tone)                      # white at a level: set the ink, then pass the level
        return level

    # -------- primitives --------
    def text(self, x, y, s, font=1, tone='primary', width=None):
        s = fit(s, font, width) if width else ' '.join(str(s).split())
        if not s:
            return 0
        c = self._text_colour(tone)
        if self.rotate180:
            # Anchor the far corner so the rotated string covers the same box.
            x, y = W - 1 - int(x) - text_width(s, font), H - 1 - int(y) - FONTS.get(font, FONTS[1])[0]
        self.frames.append(AL.cmd_text(int(x), int(y), s, font=font, color_or_grey=c))
        return text_width(s, font)

    def text_center(self, cx, y, s, font=1, tone='primary', width=None):
        s = fit(s, font, width) if width else s
        return self.text(cx - text_width(s, font) / 2, y, s, font, tone)

    def text_right(self, xr, y, s, font=1, tone='primary'):
        return self.text(xr - text_width(s, font), y, s, font, tone)

    def line(self, x0, y0, x1, y1, tone='primary'):
        self.ink(tone)
        a, b = self._p(x0, y0), self._p(x1, y1)
        self.frames.append(AL.cmd_line(*a, *b))

    def rect(self, x0, y0, x1, y1, tone='primary', fill=False):
        self.ink(tone)
        a, b = self._p(x0, y0), self._p(x1, y1)
        x0, x1, y0, y1 = min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])
        self.frames.append((AL.cmd_rectf if fill else AL.cmd_rect)(x0, y0, x1, y1))

    def circle(self, cx, cy, r, tone='primary', fill=False):
        self.ink(tone)
        self.frames.append((AL.cmd_circf if fill else AL.cmd_circ)(*self._p(cx, cy), int(r)))

    def arc(self, cx, cy, r, start, end, tone='primary'):
        """Degrees, 0 at 3 o'clock, clockwise."""
        self.ink(tone)
        if self.rotate180:
            start, end = start + 180, end + 180
        self.frames.append(AL.cmd_arc(*self._p(cx, cy), int(r), int(start), int(end)))

    def erase(self, x0, y0, x1, y1):
        """Black fill: black is transparent on the glasses, so this clears what was drawn underneath."""
        self.rect(x0, y0, x1, y1, 'black', True)

    def round_rect(self, x0, y0, x1, y1, r=8, tone='primary', fill=False):
        """Rounded card. Filled cards are drawn as two rects and four discs (cheap on the glasses)."""
        r = max(1, min(r, (x1 - x0) // 2, (y1 - y0) // 2))
        if fill:
            self.rect(x0 + r, y0, x1 - r, y1, tone, True)
            self.rect(x0, y0 + r, x1, y1 - r, tone, True)
            for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
                self.circle(cx, cy, r, tone, True)
            return
        self.line(x0 + r, y0, x1 - r, y0, tone)
        self.line(x0 + r, y1, x1 - r, y1, tone)
        self.line(x0, y0 + r, x0, y1 - r, tone)
        self.line(x1, y0 + r, x1, y1 - r, tone)
        self.arc(x0 + r, y0 + r, r, 180, 270, tone)
        self.arc(x1 - r, y0 + r, r, 270, 360, tone)
        self.arc(x1 - r, y1 - r, r, 0, 90, tone)
        self.arc(x0 + r, y1 - r, r, 90, 180, tone)
