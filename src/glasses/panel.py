"""Drawing surface for ActiveLook / ENGO glasses: one place that turns shapes into ActiveLook frames.

Every glasses screen in OpenBridge is drawn through a Panel, never with raw commands, so that three things that
depend on the real hardware live in one spot:

- orientation: native ActiveLook coordinates start bottom-right, and upright text needs text rotation 4. Measured on
  a real ENGO 3 Photochromic (26 Nov 2026): logical (x, y) is sent as (W-1-x, H-1-y) and text with rotation 4,
  anchored at its logical top-left. ``rotate180=True`` turns the whole picture by 180° (a display mounted the other
  way round);
- colour: the ENGO 3 shows grey levels as yellow and has 81 red-green colours (no blue, no white), drawn with the
  colour commands 0x3D / 0x3E and the official red-green palette (AL.RG_PALETTE). ENGO 1/2 only
  have the 0-15 level of their panel. Screens ask for *tones*, the panel picks the right commands;
- text: the glasses' fonts are ASCII only; accents are folded (été -> ete) before sending; Screens ask for *tones*, the panel picks the right commands;
- text metrics: the glasses' fonts are fixed; widths are estimated conservatively so text never overflows.

Black pixels are transparent on the see-through OLED and cost no power, so the design language draws outlines and
type, and fills only small accents.
"""
from __future__ import annotations

from src.adapters import activelook as AL

W, H = 304, 256
TEXT_ROT_UPRIGHT = 4               # ActiveLook text rotation that reads upright on the real glasses
# Visible window measured on our ENGO 3 (26 Nov 2026, lines at known positions): x 0 to ~292, y 0 to ~236 of the
# 304 x 256 panel, so no horizontal offset is needed. `openbridge glasses set --x-offset N` moves the picture if a pair
# (or the ENGO app's display position) differs.
X_OFFSET = 0
SAFE = (14, 12, 290, 244)          # x0, y0, x1, y1 kept clear of the lens edge

# font id -> (line height px, average advance px). Measured on a real ENGO 3 on 26 Nov 2026 (fonts 1-3: a word of n
# letters fills n x height/2; heights as reported by fontList on firmware 4.13). 24 px is the smallest text there is.
FONTS = {0: (24, 12), 1: (24, 12), 2: (38, 19), 3: (64, 32), 4: (75, 37), 5: (82, 41)}

# tone -> (ENGO 3 red-green colour value or None, grey level 0-15). Grey tones show yellow on the ENGO 3 panel;
# coloured tones use the red-green commands (0x3D / 0x3E). Mono glasses use the level only.
TONES = {
    'primary': (None, 15), 'secondary': (None, 11), 'muted': (None, 8), 'faint': (None, 7),
    'accent': (AL.RG_COLOURS['lime'], 15), 'accent_dim': (AL.rg(0, 5), 9), 'ok': (AL.RG_COLOURS['green'], 15),
    'warn': (AL.RG_COLOURS['orange'], 15), 'alert': (AL.RG_COLOURS['red'], 15),
    'black': (None, 0),
}
FOLD = {'œ': 'oe', 'Œ': 'OE', 'æ': 'ae', 'Æ': 'AE', 'ß': 'ss', '’': "'", '‘': "'", '“': '"', '”': '"', '«': '"',
        '»': '"', '–': '-', '—': '-', '…': '...', '°': 'o', '€': 'EUR', '×': 'x', '÷': '/', '\u00a0': ' '}


def ascii_fold(text: str) -> str:
    """The glasses' fonts are ASCII only (accents are not drawn, measured 26 Nov 2026): été -> ete, « » -> "."""
    import unicodedata
    out = []
    for ch in str(text or ''):
        if ord(ch) < 128:
            out.append(ch)
            continue
        if ch in FOLD:
            out.append(FOLD[ch])
            continue
        base = ''.join(c for c in unicodedata.normalize('NFKD', ch) if ord(c) < 128 and not unicodedata.combining(c))
        out.append(base)
    return ''.join(out)


def text_width(text: str, font: int) -> int:
    return len(text) * FONTS.get(font, FONTS[1])[1]


def fit(text: str, font: int, width: int) -> str:
    """Longest prefix that fits, with an ellipsis when cut."""
    text = ' '.join(ascii_fold(text).split())
    if text_width(text, font) <= width:
        return text
    while text and text_width(text + '...', font) > width:
        text = text[:-1]
    return text.rstrip() + '...'


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
    def __init__(self, colour: bool = True, rotate180: bool = False, x_offset: int = X_OFFSET):
        self.colour, self.rotate180, self.dx = colour, rotate180, int(x_offset)
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
    @property
    def native(self):
        """True when logical coordinates must be flipped to the ActiveLook native frame (the upright default)."""
        return not self.rotate180

    def _p(self, x, y):
        x, y = int(round(x)) + self.dx, int(round(y))
        return (W - 1 - x, H - 1 - y) if self.native else (x, y)

    def ink(self, tone: str):
        if tone == self._ink:
            return
        rgv, level = TONES.get(tone, TONES['primary'])
        if self.colour and rgv is not None:
            self.frames.append(AL.cmd_color(rgv))        # 0x3D red-green value for the next shapes
        else:
            self.frames.append(AL.cmd_grey(level))
        self._ink = tone

    # -------- primitives --------
    def text(self, x, y, s, font=1, tone='primary', width=None):
        s = fit(s, font, width) if width else ' '.join(ascii_fold(s).split())
        if not s:
            return 0
        rgv, level = TONES.get(tone, TONES['primary'])
        rot = 0
        x = int(x) + self.dx
        if self.native:
            # Upright text: rotation 4, anchored at the text's logical top-left (measured on a real ENGO 3).
            x, y, rot = W - 1 - int(x), H - 1 - int(y), TEXT_ROT_UPRIGHT
        if self.colour and rgv is not None:
            self.frames.append(AL.cmd_text_rg(int(x), int(y), s, font=font, colour=rgv, rot=rot))
        else:
            self.frames.append(AL.cmd_text(int(x), int(y), s, font=font, color_or_grey=level, rot=rot))
        return text_width(s, font)

    def text_center(self, cx, y, s, font=1, tone='primary', width=None):
        s = fit(s, font, width) if width else ascii_fold(s)
        return self.text(cx - text_width(s, font) / 2, y, s, font, tone)

    def text_right(self, xr, y, s, font=1, tone='primary'):
        s = ascii_fold(s)
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
        # Measured on a real ENGO 3: with both axes mirrored, device angles equal logical angles (0 at 3 o'clock,
        # clockwise as seen). The firmware wants the start in 0-359 and end = start + sweep.
        sweep = int(end) - int(start)
        start = int(start) % 360
        end = start + sweep
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
