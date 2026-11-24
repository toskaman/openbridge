"""Builds the static README illustrations in docs/assets/readme/ (light and dark variants).

The two animated concept pieces (hero.svg, interop-demo.svg) are hand-made and are not touched here.

Fonts are the site's own (Bricolage Grotesque, Instrument Sans, SIL OFL 1.1, see site/fonts/).
Each SVG embeds a subset of only the glyphs it uses, so it renders the same on every OS and
inside GitHub's <img> sandbox, which blocks external font requests.

Run:  python scripts/site/build_readme_art.py      (needs: pip install fonttools brotli)
"""
import base64
import io
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs' / 'assets' / 'readme'
FONTS = ROOT / 'site' / 'fonts'

THEMES = {
    'dark': dict(bg='#0d1117', surface='#151b23', border='#2a313c', text='#f0f3f6', muted='#9198a1',
                 accent='#2dd4bf', accent_ink='#0d1117', soft='#1b2b2e'),
    'light': dict(bg='#ffffff', surface='#f6f8fa', border='#d1d9e0', text='#1f2328', muted='#59636e',
                  accent='#0f766e', accent_ink='#ffffff', soft='#e6f4f2'),
}

FACES = {
    'display': ('BricolageGrotesque.woff2', {'wght': 700, 'opsz': 48, 'wdth': 100}),
    'body': ('InstrumentSans.woff2', {'wght': 400, 'wdth': 100}),
    'strong': ('InstrumentSans.woff2', {'wght': 600, 'wdth': 100}),
}


def font_face(face, chars):
    file, axes = FACES[face]
    font = TTFont(FONTS / file)
    font = instancer.instantiateVariableFont(font, axes)
    opts = subset.Options()
    opts.flavor = 'woff2'
    opts.layout_features = ['kern', 'liga']
    opts.name_IDs = []
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(text=''.join(sorted(set(chars))) + ' ')
    sub.subset(font)
    font.flavor = 'woff2'
    buf = io.BytesIO()
    font.save(buf)
    data = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face{{font-family:ob-{face};src:url(data:font/woff2;base64,{data}) format('woff2')}}"


class Svg:
    def __init__(self, w, h, label, theme):
        self.w, self.h, self.label, self.t = w, h, label, THEMES[theme]
        self.parts, self.used = [], {k: [] for k in FACES}

    def text(self, x, y, s, face='body', size=20, fill='text', anchor='start', spacing=0):
        self.used[face].append(s)
        color = self.t.get(fill, fill)
        ls = f' letter-spacing="{spacing}"' if spacing else ''
        self.parts.append(f'<text x="{x}" y="{y}" font-family="ob-{face}" font-size="{size}" fill="{color}" '
                          f'text-anchor="{anchor}"{ls}>{escape(s)}</text>')

    def rect(self, x, y, w, h, r=14, fill='surface', stroke='border'):
        f, s = self.t.get(fill, fill), self.t.get(stroke, stroke)
        st = f' stroke="{s}" stroke-width="1.5"' if stroke else ''
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{f}"{st}/>')

    def raw(self, s):
        self.parts.append(s)

    def render(self):
        css = ''.join(font_face(f, ''.join(v)) for f, v in self.used.items() if v)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" '
                f'height="{self.h}" role="img" aria-label="{escape(self.label)}">'
                f'<title>{escape(self.label)}</title><style>{css}</style>'
                f'<rect width="{self.w}" height="{self.h}" rx="16" fill="{self.t["bg"]}"/>'
                + ''.join(self.parts) + '</svg>\n')


def how_it_works(theme):
    steps = [
        ('Discover', ['Finds the devices around you:', 'Wi-Fi, Bluetooth, USB, your', 'router, even other PCs.'],
         '24 devices found on my LAN'),
        ('Understand', ['Learns what each device can', 'really do, and proves it', 'before trusting it.'],
         'Vacuum: start, pause, dock'),
        ('Create', ['You ask in plain words. It', 'builds the control you need,', 'on the screen you pick.'],
         'Put vacuum buttons on my TV'),
        ('Check', ['You approve. It acts, then', 'reads the device back to be', 'sure it really happened.'],
         'Done, verified on the device'),
    ]
    s = Svg(1280, 300, 'How it works: discover, understand, create, check', theme)
    w, gap, x0 = 287, 23, 20
    for i, (title, lines, quote) in enumerate(steps):
        x = x0 + i * (w + gap)
        s.rect(x, 20, w, 260)
        s.text(x + 28, 66, f'0{i + 1}', 'display', 22, 'accent')
        s.text(x + 28, 112, title, 'display', 34)
        for j, line in enumerate(lines):
            s.text(x + 28, 150 + j * 26, line, 'body', 17.5, 'muted')
        s.raw(f'<line x1="{x + 28}" y1="{238 - 22}" x2="{x + w - 28}" y2="{238 - 22}" stroke="{s.t["border"]}" stroke-width="1.5"/>')
        s.text(x + 28, 252, f'“{quote}”', 'strong', 16, 'accent')
    return s.render()


def numbers(theme):
    stats = [('2,600+', 'automated tests'), ('37', 'verified device runs'), ('28', 'on real hardware'),
             ('6', 'platforms, one codebase'), ('0', 'runtime dependencies')]
    s = Svg(1280, 150, 'OpenBridge in numbers: ' + ', '.join(f'{v} {l}' for v, l in stats), theme)
    s.rect(1, 1, 1278, 148, 16, 'surface', 'border')
    cw = 1280 / len(stats)
    for i, (v, l) in enumerate(stats):
        cx = cw * i + cw / 2
        s.text(cx, 82, v, 'display', 50, 'text', 'middle')
        s.text(cx, 115, l, 'body', 19, 'muted', 'middle')
        if i:
            s.raw(f'<line x1="{cw * i:.0f}" y1="36" x2="{cw * i:.0f}" y2="114" stroke="{s.t["border"]}" stroke-width="1.5"/>')
    return s.render()


def partner_process(theme):
    steps = [
        ('You send a device', ['A unit to keep (donated or', 'permanent loan), your API or', 'SDK docs, a technical contact.']),
        ('I integrate and test it', ['A native adapter, an emulator,', 'and a test suite run on the', 'real hardware at every release.']),
        ('You get an ecosystem', ['Your device works with TVs,', 'watches, phones and PCs, with', 'a public compatibility report.']),
    ]
    s = Svg(1280, 270, 'How a hardware partnership works: you send a device, I integrate and test it, '
                       'you get an ecosystem', theme)
    w, gap = 386, 41
    for i, (title, lines) in enumerate(steps):
        x = 20 + i * (w + gap)
        s.rect(x, 20, w, 230)
        s.raw(f'<circle cx="{x + 46}" cy="68" r="22" fill="{s.t["accent"]}"/>')
        s.text(x + 46, 76, str(i + 1), 'display', 22, s.t['accent_ink'], 'middle')
        s.text(x + 28, 140, title, 'display', 32)
        for j, line in enumerate(lines):
            s.text(x + 28, 178 + j * 26, line, 'body', 19, 'muted')
        if i < 2:
            ax = x + w + 6
            s.raw(f'<path d="M{ax} 135 h{gap - 14} m-8 -7 l8 7 l-8 7" fill="none" stroke="{s.t["muted"]}" '
                  f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
    return s.render()


def logo_mark(color, size=64):
    """Bridge mark: two device nodes joined by an arch and a deck."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{size}" height="{size}">'
            f'<path d="M11 50 Q32 -12 53 50" fill="none" stroke="{color}" stroke-width="6.5" stroke-linecap="round"/>'
            f'<path d="M4 50 H60" stroke="{color}" stroke-width="6.5" stroke-linecap="round"/>'
            f'<circle cx="32" cy="19" r="7" fill="{color}"/></svg>\n')


def logo_lockup(theme):
    t = THEMES[theme]
    s = Svg(420, 96, 'OpenBridge', theme)
    s.parts.append(logo_mark(t['accent'], 64).replace('<svg ', '<svg x="16" y="14" ', 1))
    s.text(96, 64, 'OpenBridge', 'display', 46)
    out = s.render()
    return out.replace(f'<rect width="420" height="96" rx="16" fill="{t["bg"]}"/>', '')


def main():
    built = []
    for theme in THEMES:
        for name, fn in [('how-it-works', how_it_works), ('numbers', numbers),
                         ('partner-process', partner_process), ('logo', logo_lockup)]:
            path = OUT / f'{name}-{theme}.svg'
            path.write_text(fn(theme), encoding='utf-8')
            built.append(path)
    (OUT / 'logo-mark.svg').write_text(logo_mark('#2dd4bf'), encoding='utf-8')
    built.append(OUT / 'logo-mark.svg')
    for p in built:
        print(f'{p.relative_to(ROOT)}  {p.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
