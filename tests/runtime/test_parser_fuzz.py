"""Adversarial parser fuzz for the file-driven surfaces (TESTS ONLY).

Covers the skill recipe validator, the skills-bundle importer, the skill-pack
validator, the partner voice-profile validator and the quality observer.
Seeds are fixed and every family is capped: a failure reproduces by name.

Contract for every case: fail-closed and fail-typed. A mutated document must
either still validate (and then behave: import, resolve, repair) or raise the
documented error (SkillError, PackError, ProfileError, QualityError). A bare
KeyError/TypeError/AttributeError/UnicodeError from wire-shaped input is a
failure. Nothing here executes a device action.
"""
import copy
import json
import random
import unittest
from pathlib import Path

from src.ai import partner_voice as PV
from src.runtime import skill_library as SL
from src.runtime import skill_packs as SP
from src.runtime.quality_reports import Quality

ROOT = Path(__file__).resolve().parent.parent.parent

SEED_RECIPE = 0x5EC1
SEED_BUNDLE = 0x5EC2
SEED_PACK = 0x5EC3
SEED_VOICE = 0x5EC4
SEED_QUALITY = 0x5EC5
MAX_CASES = 128

NASTY_STRINGS = ['', 'x' * 5000, 'é\x00\x01\x02\t\n', '🔥' * 200, '{{', '%s', '../..', '@tv',
                 'skill-1', 'OPENBRIDGE-SKILLPACK/1', 'None', 'null', '  ', 'A' * 61]
NASTY_SCALARS = [None, True, False, 0, -1, 2 ** 62, 1.5, float('inf'), [], {}, ['x'], {'a': 1}]


def _mutate_value(rng, value, depth=0):
    roll = rng.random()
    if roll < 0.15:
        return rng.choice(NASTY_STRINGS)
    if roll < 0.25:
        return copy.deepcopy(rng.choice(NASTY_SCALARS))
    if isinstance(value, dict) and value and roll < 0.55:
        return _mutate_dict(rng, value, depth)
    if isinstance(value, list) and value and roll < 0.75:
        return _mutate_list(rng, value, depth)
    if isinstance(value, str) and roll < 0.85:
        i = rng.randrange(len(value) + 1)
        return value[:i] + rng.choice(NASTY_STRINGS) + value[i:]
    return value


def _mutate_dict(rng, doc, depth=0):
    doc = copy.deepcopy(doc)
    if not doc or depth > 4:
        return rng.choice([{}, {'zzz': 1}, doc])
    for _ in range(rng.randint(1, 3)):
        op = rng.random()
        if op < 0.3 and doc:
            doc.pop(rng.choice(sorted(doc)), None)
        elif op < 0.6 and doc:
            k = rng.choice(sorted(doc))
            doc[k] = _mutate_value(rng, doc[k], depth + 1)
        elif op < 0.8:
            doc[rng.choice(['zzz', '', 'x' * 100, 'trigger', 'steps'])] = _mutate_value(rng, 'v', depth + 1)
        else:
            return copy.deepcopy(rng.choice(NASTY_SCALARS))
    return doc


def _mutate_list(rng, items, depth=0):
    items = copy.deepcopy(items)
    if not items or depth > 4:
        return rng.choice([[], [None], items])
    for _ in range(rng.randint(1, 3)):
        op = rng.random()
        if op < 0.35 and items:
            items.pop(rng.randrange(len(items)))
        elif op < 0.7 and items:
            i = rng.randrange(len(items))
            items[i] = _mutate_value(rng, items[i], depth + 1)
        else:
            items.append(_mutate_value(rng, 'v', depth + 1))
    return items


def _valid_recipe():
    return {'name': 'Fuzz skill', 'description': 'd',
            'trigger': {'kind': 'state', 'device': 'dev_tv', 'state': 'playing'},
            'steps': [{'device': 'dev_lamp', 'primitive': 'ha_set',
                       'params': {'action': 'set_brightness', 'value': 20}}]}


class RecipeFuzz(unittest.TestCase):
    def test_mutated_recipes_validate_or_raise_skill_error(self):
        rng = random.Random(SEED_RECIPE)
        seen_ok = seen_err = 0
        for _ in range(MAX_CASES):
            doc = _mutate_dict(rng, _valid_recipe())
            try:
                SL.validate(doc)
            except SL.SkillError:
                seen_err += 1
            else:
                seen_ok += 1
                SL.fingerprint({'trigger': doc['trigger'], 'steps': doc['steps']})
        self.assertGreater(seen_err, 0)   # mutations must sometimes break validity

    def test_mutated_bundles_import_or_raise_skill_error(self):
        lib = SL.Library(None, persist=False)
        lib.add(_valid_recipe(), 'owner')
        bundle = lib.export()
        rng = random.Random(SEED_BUNDLE)
        seen_err = 0
        for _ in range(MAX_CASES):
            doc = _mutate_dict(rng, bundle)
            fresh = SL.Library(None, persist=False)
            try:
                fresh.import_bundle(doc)
            except SL.SkillError:
                seen_err += 1
        self.assertGreater(seen_err, 0)


class PackFuzz(unittest.TestCase):
    def test_mutated_packs_validate_or_raise_pack_error(self):
        pack = json.loads((ROOT / 'src' / 'runtime' / 'packs' / 'quiet-cleaning.json').read_text(encoding='utf-8'))
        rng = random.Random(SEED_PACK)
        seen_ok = seen_err = 0
        devices = {'tv1': {'category': 'media_player', 'label': 'TV'},
                   'rb1': {'category': 'robot', 'label': 'Robot'}}
        for _ in range(MAX_CASES):
            doc = _mutate_dict(rng, pack)
            try:
                SP.validate(doc)
            except SP.PackError:
                seen_err += 1
            else:
                seen_ok += 1
                try:
                    SP.resolve(doc, devices, {'media': 'tv1', 'robot': 'rb1'})
                except SP.PackError:
                    pass
        self.assertGreater(seen_err, 0)
        self.assertGreater(seen_ok, 0)


class VoiceProfileFuzz(unittest.TestCase):
    def test_mutated_profiles_validate_or_raise_profile_error(self):
        profile = json.loads((ROOT / 'docs' / 'partners' / 'examples' / 'voice-profile.acme.json').read_text(encoding='utf-8'))
        rng = random.Random(SEED_VOICE)
        seen_err = 0
        for _ in range(MAX_CASES):
            doc = _mutate_dict(rng, profile)
            try:
                PV.validate(doc)
            except PV.ProfileError:
                seen_err += 1
            else:
                PV.repairs(doc)          # accepted profiles must produce repairs without crashing
                PV.coverage(doc)
        self.assertGreater(seen_err, 0)


class QualityFuzz(unittest.TestCase):
    def test_observe_never_raises_on_wild_types(self):
        rng = random.Random(SEED_QUALITY)
        q = Quality(persist=False)
        q.enable()
        wild = NASTY_STRINGS + NASTY_SCALARS + [{'manufacturer': ['x']}, {'model': {'m': 1}}, {'firmware': 'f' * 500}]
        for _ in range(MAX_CASES):
            info = copy.deepcopy(rng.choice(wild))
            cat = copy.deepcopy(rng.choice(wild))
            act = copy.deepcopy(rng.choice(wild))
            receipt = {'state': rng.choice(['VERIFIED', 'FAILED', 'BLOCKED', 'EXECUTED_UNVERIFIED', None, 42]),
                       'verified': rng.choice([True, False, None, 1, 'yes']),
                       'started_at': rng.choice([None, 'not-a-date', '2026-11-23T10:00:00', 12345]),
                       'finished_at': rng.choice([None, '2026-11-23T10:00:01', 'xx', -7])}
            self.assertTrue(q.observe(info, cat, act, receipt))
        rows = q.months.get(q.month(), {})
        self.assertEqual(sum(r['runs'] for r in rows.values()), MAX_CASES)


if __name__ == '__main__':
    unittest.main()
