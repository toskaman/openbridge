"""Partner voice profiles: a partner's product names and phrasings, understood offline by OpenBridge's voice flow.

A profile does two things, both local:
1. At run time, it repairs how speech-to-text mishears the partner's product names ("acmé x cinq" -> "acme x5").
   Repairs feed MATCHING only, as in voice_normalize: the original transcript is kept, and a request that matches
   only thanks to a repair is asked back ("did you mean the Acme X5?") instead of being run.
2. At training time, dev/ai_training/make_partner_dataset.py turns it into training lines for a partner adapter of
   OpenBridge's own model (openbridge-intent), in the profile's languages.

Profiles shipped with OpenBridge live in config/voice_profiles/; an owner can add one in
%LOCALAPPDATA%/OpenBridge/voice_profiles/. Nothing is sent anywhere.

  {"format": "openbridge-voiceprofile/1", "id": "acme", "partner": "Acme Robotics", "version": "1.0.0",
   "languages": ["fr", "en-US", "en-GB"],
   "products": [{"ref": "acme x5", "kind": "vacuum",
                 "names": {"fr": ["l'Acme X5", "le robot Acme"], "en-US": ["the Acme X5"], "en-GB": ["the Acme X5"]},
                 "misheard": {"fr": ["acne x5", "acmé x cinq"], "en": ["ack me x5"]}}],
   "phrases": [{"family": "vacuum.start", "dialect": "fr", "template": "Envoie {d} en mission"}]}
"""
import json
import os
import re
from pathlib import Path

from src.ai import voice_normalize as VN

FORMAT = 'openbridge-voiceprofile/1'
SHIPPED_DIR = Path(__file__).resolve().parents[2] / 'config' / 'voice_profiles'
KINDS = ('light', 'appliance', 'thermostat', 'speaker', 'cover', 'lock', 'vacuum')
DIALECTS = ('fr', 'en-US', 'en-GB')
# What OpenBridge can do today, per language, with no new training.
STT_LANGUAGES = ('fr', 'en')            # src/ai/stt_local.LANG_CODE
INTENT_DIALECTS = ('fr', 'en-US', 'en-GB')
ID = re.compile(r'^[a-z0-9][a-z0-9-]{1,40}$')


class ProfileError(ValueError):
    pass


def owner_dir():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'voice_profiles'


def _lang(dialect):
    return 'fr' if dialect == 'fr' else 'en' if dialect.startswith('en') else dialect.split('-')[0]


def validate(profile):
    if not isinstance(profile, dict) or profile.get('format') != FORMAT:
        raise ProfileError('not an OpenBridge voice profile')
    if not ID.match(str(profile.get('id', ''))) or not profile.get('partner'):
        raise ProfileError('a profile needs an id (lowercase, digits, dashes) and a partner name')
    langs = profile.get('languages')
    if not isinstance(langs, list) or not langs or not all(isinstance(x, str) and 1 < len(x) <= 10 for x in langs):
        raise ProfileError('languages: a list such as ["fr", "en-US", "en-GB"]')
    products = profile.get('products')
    if not isinstance(products, list) or not 0 < len(products) <= 50:
        raise ProfileError('a profile lists 1 to 50 products')
    refs = set()
    for p in products:
        if not isinstance(p, dict) or not isinstance(p.get('ref'), str) or not 0 < len(p['ref']) <= 40:
            raise ProfileError('each product has a short canonical ref, e.g. "acme x5"')
        if p['ref'] in refs:
            raise ProfileError('product ref %r appears twice' % p['ref'])
        refs.add(p['ref'])
        if p.get('kind') not in KINDS:
            raise ProfileError('product %r: kind must be one of %s' % (p['ref'], ', '.join(KINDS)))
        names = p.get('names')
        if not isinstance(names, dict) or not names or not all(
                isinstance(v, list) and v and all(isinstance(n, str) and 0 < len(n) <= 60 for n in v) for v in names.values()):
            raise ProfileError('product %r: names per dialect, e.g. {"fr": ["l\'Acme X5"]}' % p['ref'])
        mis = p.get('misheard', {})
        if not isinstance(mis, dict) or not all(isinstance(v, list) and all(isinstance(n, str) and 0 < len(n) <= 60 for n in v)
                                                for v in mis.values()):
            raise ProfileError('product %r: misheard is {lang: [variants]}' % p['ref'])
    for ph in profile.get('phrases', []):
        if not isinstance(ph, dict) or ph.get('dialect') not in DIALECTS or not isinstance(ph.get('family'), str) \
                or not isinstance(ph.get('template'), str) or not 0 < len(ph['template']) <= 120:
            raise ProfileError('each phrase is {family, dialect (fr | en-US | en-GB), template}')
    _check_repairs(profile)
    return profile


def _canonical_name(product, lang):
    """The folded name a repair writes: the product's first name in that language, without its article."""
    names = [n for d, ns in product['names'].items() if _lang(d) == lang for n in ns] or \
        [n for ns in product['names'].values() for n in ns]
    folded = VN.fold(names[0]).split()
    while folded and folded[0] in ('le', 'la', 'les', 'l', 'the', 'my', 'mon', 'ma'):
        folded = folded[1:]
    return ' '.join(folded) or VN.fold(product['ref'])


def repairs(profile):
    """[(lang, folded misheard variant, folded canonical name, label)], longest variant first."""
    out = []
    for p in profile['products']:
        for lang, variants in p.get('misheard', {}).items():
            to = _canonical_name(p, _lang(lang))
            for v in variants:
                fv = VN.fold(v)
                if fv and fv != to:
                    out.append((_lang(lang), fv, to, '%s->%s (%s)' % (fv, to, profile['id'])))
    return sorted(out, key=lambda r: -len(r[1]))


def _check_repairs(profile):
    # A variant that is an ordinary word would rewrite everyday speech: refuse one-word variants that are common words.
    common = VN._FR | VN._EN
    for _, fv, to, _ in repairs(profile):
        if fv in common or (len(fv.split()) == 1 and len(fv) < 4):
            raise ProfileError('misheard variant %r is too short or an everyday word' % fv)
        if re.search(r'\b%s\b' % re.escape(fv), to):
            raise ProfileError('misheard variant %r is part of the name itself (%r)' % (fv, to))


def load_dir(d):
    out = []
    for p in sorted(Path(d).glob('*.json')) if Path(d).is_dir() else []:
        try:
            out.append(validate(json.loads(p.read_text(encoding='utf-8'))))
        except (OSError, ValueError):
            continue
    return out


def installed():
    """Shipped profiles, then the owner's; the owner's wins on the same id."""
    by_id = {}
    for p in load_dir(SHIPPED_DIR) + load_dir(owner_dir()):
        by_id[p['id']] = p
    return list(by_id.values())


_CACHE = {}


def installed_vocab():
    """Repair table of every installed profile, read once per process."""
    if 'vocab' not in _CACHE:
        _CACHE['vocab'] = tuple(r for p in installed() for r in repairs(p))
    return _CACHE['vocab']


def apply(fixed, lang, vocab):
    """Apply profile repairs to folded text. Returns (text, [labels]). lang None = any language."""
    labels = []
    for vlang, fv, to, label in vocab:
        if lang not in (None, 'unknown') and vlang != lang:
            continue
        rx = re.compile(r'\b%s\b' % re.escape(fv))
        if rx.search(fixed):
            fixed = rx.sub(to, fixed)
            labels.append(label)
    return fixed, labels


def coverage(profile):
    """Which of the profile's languages work today, and what each missing one needs."""
    report = {}
    for d in profile['languages']:
        lang = _lang(d)
        stt = lang in STT_LANGUAGES
        intent = d in INTENT_DIALECTS or (lang == 'en' and d.startswith('en'))
        needs = []
        if not stt:
            needs.append('speech-to-text adapter for %r (the local model has one per language; add it to LANG_CODE and '
                         'measure it on recorded commands)' % lang)
        if not intent:
            needs.append('training lines in %r for the intent model (templates for every family, then a partner '
                         'adapter run)' % d)
        names = sum(len(v) for p in profile['products'] for k, v in p['names'].items() if k == d or _lang(k) == lang)
        if not names:
            needs.append('product names in %r' % d)
        report[d] = {'ready': not needs, 'needs': needs}
    return report
