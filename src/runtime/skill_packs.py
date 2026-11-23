"""Skill packs: ready-made features that show a device working with other brands, installable in one command.

A pack is a portable set of skill-library recipes. It never names someone's devices: it names *roles* ("a light",
"a TV or speaker", "a robot vacuum"), each accepting device categories. Installing a pack maps every role to one of
the owner's devices, resolves each step for that device's category (a robot vacuum through Home Assistant and a
Tuya vacuum take different commands), and saves the recipes in the skill library, **unapproved**: the owner still
approves each one, exactly as for anything else.

Packs shipped with OpenBridge live in src/runtime/packs/*.json; INDEX.json pins the SHA-256 of each file, so a pack
that was changed after review is refused. A partner pack (format below) showcases the partner's device next to
other brands; it goes through the same review and pinning before it is listed.

  {"format": "openbridge-skillpack/1", "id": "cinema", "version": "1.0.0",
   "title": {"en": "...", "fr": "..."}, "description": {"en": "...", "fr": "..."},
   "publisher": {"name": "OpenBridge", "kind": "openbridge" | "partner", "url": "https://..."},
   "roles": {"tv": {"categories": ["media_player", "tv"], "label": {"en": "TV or speaker", "fr": "TV ou enceinte"}}},
   "skills": [{"name": "...", "description": "...", "trigger": {"kind": "state", "device": "@tv", "state": "playing"},
               "steps": [{"device": "@light", "by_category": {"light": {"primitive": "ha_set",
                                                                        "params": {"action": "set_brightness", "value": 20}}}}]}]}
"""
import hashlib
import json
import re
from pathlib import Path

from src.runtime import skill_library as SL

FORMAT = 'openbridge-skillpack/1'
PACK_DIR = Path(__file__).resolve().parent / 'packs'
ID = re.compile(r'^[a-z0-9][a-z0-9-]{1,40}$')
ROLE = re.compile(r'^[a-z][a-z0-9_]{1,30}$')


class PackError(ValueError):
    pass


def _text(value, lang='en'):
    if isinstance(value, dict):
        return value.get(lang) or value.get('en') or next(iter(value.values()), '')
    return value or ''


def validate(pack):
    """Shape of a pack. Every step must be a valid skill-library step once resolved."""
    if not isinstance(pack, dict) or pack.get('format') != FORMAT:
        raise PackError('not an OpenBridge skill pack')
    if not ID.match(str(pack.get('id', ''))):
        raise PackError('pack id: lowercase letters, digits and dashes')
    pub = pack.get('publisher')
    if not isinstance(pub, dict) or not pub.get('name') or pub.get('kind') not in ('openbridge', 'partner'):
        raise PackError('pack publisher: {name, kind: openbridge | partner}')
    roles = pack.get('roles')
    if not isinstance(roles, dict) or not 0 < len(roles) <= 8:
        raise PackError('a pack declares 1 to 8 roles')
    for r, spec in roles.items():
        if not ROLE.match(r) or not isinstance(spec, dict) or not isinstance(spec.get('categories'), list) \
                or not spec['categories']:
            raise PackError('role %r: {categories: [...], label}' % r)
    skills = pack.get('skills')
    if not isinstance(skills, list) or not 0 < len(skills) <= 12:
        raise PackError('a pack holds 1 to 12 skills')
    for s in skills:
        refs = [st.get('device') for st in s.get('steps', [])]
        if isinstance(s.get('trigger'), dict) and s['trigger'].get('kind') == 'state':
            refs.append(s['trigger'].get('device'))
        for ref in refs:
            if not isinstance(ref, str) or not ref.startswith('@') or ref[1:] not in roles:
                raise PackError('skill %r refers to an unknown role %r' % (s.get('name'), ref))
        for st in s.get('steps', []):
            options = st.get('by_category')
            if not isinstance(options, dict) or not options:
                raise PackError('each step lists what to do per device category (by_category)')
            for cat, how in options.items():
                if cat not in roles[st['device'][1:]]['categories']:
                    raise PackError('step for %s: category %s is not accepted by that role' % (st['device'], cat))
                if not isinstance(how, dict) or how.get('primitive') not in SL.ALLOWED_PRIMITIVES \
                        or not isinstance(how.get('params'), dict):
                    raise PackError('step for %s/%s: primitive not allowed in a skill' % (st['device'], cat))
    return pack


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def available(pack_dir=None):
    """Packs shipped with OpenBridge whose file matches the pinned digest in INDEX.json."""
    d = Path(pack_dir or PACK_DIR)
    try:
        index = json.loads((d / 'INDEX.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    out = []
    for entry in index.get('packs', []):
        p = d / entry['file']
        try:
            ok = digest(p) == entry['sha256']
            pack = validate(json.loads(p.read_text(encoding='utf-8')))
        except (OSError, ValueError, KeyError):
            continue
        if ok and pack['id'] == entry['id']:
            out.append(pack)
    return out


def get(pack_id, pack_dir=None):
    for p in available(pack_dir):
        if p['id'] == pack_id:
            return p
    raise PackError('unknown pack %r (or its file changed since review)' % pack_id)


def candidates(pack, devices):
    """{role: [device keys whose category the role accepts]}. devices: {key: {'category', 'label'}}."""
    return {r: sorted(k for k, d in devices.items() if d.get('category') in spec['categories'])
            for r, spec in pack['roles'].items()}


def auto_map(pack, devices, role_map=None):
    """Complete an owner's role map with roles that have exactly one candidate. Returns (map, missing, ambiguous)."""
    mapping = dict(role_map or {})
    cands = candidates(pack, devices)
    missing, ambiguous = [], {}
    for r in pack['roles']:
        if r in mapping:
            continue
        if len(cands[r]) == 1:
            mapping[r] = cands[r][0]
        elif not cands[r]:
            missing.append(r)
        else:
            ambiguous[r] = cands[r]
    return mapping, missing, ambiguous


def resolve(pack, devices, role_map, lang='en'):
    """Concrete skill-library recipes for these devices. Raises PackError with what is missing."""
    validate(pack)
    for r in pack['roles']:
        key = role_map.get(r)
        if key is None:
            raise PackError('role %r is not mapped to a device' % r)
        cat = (devices.get(key) or {}).get('category')
        if cat not in pack['roles'][r]['categories']:
            raise PackError('device %s (%s) cannot play the role %r' % (key, cat, r))
    recipes = []
    for s in pack['skills']:
        trig = json.loads(json.dumps(s['trigger']))
        if trig['kind'] == 'state':
            trig['device'] = role_map[trig['device'][1:]]
        steps = []
        for st in s['steps']:
            key = role_map[st['device'][1:]]
            how = st['by_category'].get(devices[key]['category'])
            if how is None:
                raise PackError('the pack has no step for a %s in skill %r' % (devices[key]['category'], s['name']))
            steps.append({'device': key, 'primitive': how['primitive'], 'params': json.loads(json.dumps(how['params']))})
        recipe = {'name': _text(s['name'], lang)[:60], 'description': _text(s.get('description', ''), lang)[:300],
                  'trigger': trig, 'steps': steps}
        try:
            SL.validate(recipe)
        except SL.SkillError as e:
            raise PackError('%s: %s' % (recipe['name'], e)) from None
        recipes.append(recipe)
    return recipes


def install(library, pack, devices, role_map, lang='en'):
    """Save the pack's recipes in the library (unapproved). Returns the new skill ids.

    All recipes are resolved first: a pack is installed whole or not at all."""
    ids = []
    for recipe in resolve(pack, devices, role_map, lang):
        r = library.add(recipe, 'pack', request='pack:%s@%s' % (pack['id'], pack.get('version', '1')),
                        model=None)
        r['origin']['pack'] = {'id': pack['id'], 'version': pack.get('version', '1'),
                               'publisher': pack['publisher']['name']}
        ids.append(r['id'])
    library._save()
    return ids


def build_index(pack_dir=None):
    """INDEX.json content for the packs in a folder (run by a reviewer after reviewing them)."""
    d = Path(pack_dir or PACK_DIR)
    packs = []
    for p in sorted(d.glob('*.json')):
        if p.name == 'INDEX.json':
            continue
        pack = validate(json.loads(p.read_text(encoding='utf-8')))
        packs.append({'id': pack['id'], 'version': pack.get('version'), 'publisher': pack['publisher']['name'],
                      'file': p.name, 'sha256': digest(p)})
    return {'format': 'openbridge-skillpack-index/1', 'packs': packs}


def check_file(path):
    """What a partner runs on a pack before sending it: shape errors, or its id and SHA-256 for review."""
    pack = validate(json.loads(Path(path).read_text(encoding='utf-8')))
    return {'id': pack['id'], 'version': pack.get('version'), 'publisher': pack['publisher'],
            'roles': sorted(pack['roles']), 'skills': len(pack['skills']), 'sha256': digest(path)}


def summary(pack, lang='en'):
    return {'id': pack['id'], 'version': pack.get('version'), 'title': _text(pack['title'], lang),
            'description': _text(pack.get('description', ''), lang), 'publisher': pack['publisher']['name'],
            'roles': {r: {'categories': spec['categories'], 'label': _text(spec.get('label', r), lang)}
                      for r, spec in pack['roles'].items()},
            'skills': [_text(s['name'], lang) for s in pack['skills']]}
