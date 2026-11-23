"""Français / English for everything the glasses (and the glasses CLI) say.

Stable keys (``hud.navigation.next_turn``) travel through the engines; text is produced only when a screen is drawn.
Language choice (owner setting, ``openbridge glasses set --lang`` / ``--hud-lang``):
  language      auto | fr | en      app language; auto follows the system, English when the system language is neither
  hud_language  follow | fr | en    the glasses follow the app by default; a bilingual owner can set them apart
Units are a separate setting (metric | imperial). Device names, ids and values are never translated.
"""
from __future__ import annotations

import json
import locale
import os
from pathlib import Path

LANGS = ('fr', 'en')
NATIVE_NAMES = {'fr': 'Français', 'en': 'English'}       # shown in their own language, never as flags
_DIR = Path(__file__).resolve().parent / 'locales'
_CACHE: dict[str, dict] = {}


def table(lang):
    if lang not in _CACHE:
        _CACHE[lang] = json.loads((_DIR / ('%s.json' % lang)).read_text(encoding='utf-8'))
    return _CACHE[lang]


def system_language():
    for raw in (os.environ.get('LC_ALL'), os.environ.get('LANG'), (locale.getlocale()[0] or '')):
        code = (raw or '').replace('-', '_').split('_')[0].lower()
        if code in LANGS:
            return code
        if code.startswith('french'):
            return 'fr'
    return 'en'


def resolve(settings):
    """(app language, glasses language) from the owner settings."""
    app = (settings or {}).get('language', 'auto')
    app = system_language() if app not in LANGS else app
    hud = (settings or {}).get('hud_language', 'follow')
    return app, (app if hud not in LANGS else hud)


def t(key, _lang='en', **params):
    """Text for key in the language; falls back to English, then to the key itself (never crashes a screen)."""
    s = table(_lang if _lang in LANGS else 'en').get(key) or table('en').get(key) or key
    try:
        return s.format(**params) if params else s
    except (KeyError, IndexError, ValueError):
        return s


def missing():
    """Keys present in one language and not the other (the test suite requires none)."""
    a, b = set(table('en')), set(table('fr'))
    return {'fr': sorted(a - b), 'en': sorted(b - a)}


def fmt_distance(meters, units='metric', lang='en'):
    if meters is None:
        return '—'
    if units == 'imperial':
        miles = meters / 1609.344
        return ('%.1f mi' % miles) if miles >= 0.1 else ('%d ft' % (round(meters * 3.28084 / 10) * 10))
    if meters >= 1000:
        s = '%.1f km' % (meters / 1000)
        return s.replace('.', ',') if lang == 'fr' else s
    return '%d m' % (round(meters / 10) * 10 if meters >= 100 else round(meters))


def fmt_duration(seconds):
    if seconds is None:
        return '—'
    s = int(round(seconds))
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return '%d:%02d:%02d' % (h, m, sec) if h else '%d:%02d' % (m, sec)


def fmt_pace(sec_per_km, units='metric'):
    """Pace as m:ss per km (or per mile)."""
    if not sec_per_km or sec_per_km <= 0 or sec_per_km > 3600:
        return '—'
    v = sec_per_km * (1.609344 if units == 'imperial' else 1)
    return '%d:%02d' % (int(v) // 60, int(round(v)) % 60)


def fmt_speed(mps, units='metric', lang='en'):
    if mps is None:
        return '—'
    v = mps * (2.236936 if units == 'imperial' else 3.6)
    s = '%.1f' % v
    return s.replace('.', ',') if lang == 'fr' else s
