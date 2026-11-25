"""Training lines for a partner adapter of OpenBridge's own model, from a partner voice profile.

    python dev/ai_training/make_partner_dataset.py --profile acme.json --base-data E:/OpenBridgeAI/data_v3 \
        --out E:/OpenBridgeAI/data_acme

Every request family that fits a product's kind is rendered with the partner's product names (and the partner's own
phrasings), in the profile's dialects that the model already speaks (fr, en-US, en-GB). Gold replies name the
product by its canonical ref. A replay slice of the base training set is mixed in so the adapter does not forget the
rest of the home. Writes train.jsonl, test.jsonl (partner templates held out) and partner_test.jsonl.

Then, on the training PC (about 1 to 3 hours on one GPU, depending on size):
    python dev/ai_training/train_lora.py --base <llama-3.2-3b-instruct> --init-adapter E:/OpenBridgeAI/runs/llama3b_v3/adapter \
        --data E:/OpenBridgeAI/data_acme --out E:/OpenBridgeAI/adapter_acme --epochs 1
    python dev/ai_training/evaluate.py --backend hf --model <llama-3.2-3b-instruct> --adapter E:/OpenBridgeAI/adapter_acme \
        --data E:/OpenBridgeAI/data_acme --split partner_test --out E:/OpenBridgeAI/eval_acme.json
"""
import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import home_families as H  # noqa: E402
import make_dataset as V2  # noqa: E402

from src.ai import partner_voice as PV  # noqa: E402

HOME_KIND = {'light': 'light', 'appliance': 'appliance', 'thermostat': 'thermostat', 'speaker': 'speaker',
             'cover': 'cover', 'lock': 'lock'}


def _names(product, dialect):
    lang = 'fr' if dialect == 'fr' else 'en'
    exact = product['names'].get(dialect)
    if exact:
        return exact
    return [n for d, ns in product['names'].items() if ('fr' if d == 'fr' else 'en') == lang for n in ns]


def _example(row):
    if row['lang'] == 'fr':
        row = dict(row, text=H.fr_fix(row['text']))      # "de le robot Acme" -> "du robot Acme"
    e = V2.example(row)
    e['dialect'] = row.get('dialect', row['lang'])
    e['partner'] = row.get('partner')
    return e


def home_rows(profile, rng_seed=17, k_train=6, k_test=2):
    """Home families rendered with the partner's products only (H.OBJECTS swapped for the run)."""
    dialects = [d for d in profile['languages'] if d in PV.INTENT_DIALECTS]
    saved_objects, saved_families = dict(H.OBJECTS), dict(H.FAMILIES)
    try:
        objects = {}
        for p in profile['products']:
            kind = HOME_KIND.get(p['kind'])
            if kind is None:
                continue
            us, gb, fr = _names(p, 'en-US'), _names(p, 'en-GB'), _names(p, 'fr')
            # pick_device adds "the" before English names itself, so strip it here.
            strip = lambda ns: [n[4:] if n.lower().startswith('the ') else n for n in ns]
            objects.setdefault(kind, []).append((p['ref'], strip(us) or strip(gb), strip(gb) or strip(us), fr or us))
        if not objects:
            return [], []
        H.OBJECTS.clear()
        H.OBJECTS.update(objects)
        fams = {}
        for fam, (sid, kinds, templates) in saved_families.items():
            kinds_here = tuple(k for k in kinds if k in objects)
            if not kinds_here or fam == 'links.create':
                continue
            extra = [(ph['dialect'], ph['template']) for ph in profile.get('phrases', []) if ph['family'] == fam]
            norm = [(it[0], it[1], it[2] if len(it) > 2 else None) for it in templates + extra]
            ts = [(d, t, fx) for d, t, fx in norm if d in dialects and '{d}' in t]
            if ts:
                fams[fam] = (sid, kinds_here, ts)
        H.FAMILIES.clear()
        H.FAMILIES.update(fams)
        train, test = H.build(V2.vary, seed=rng_seed, k_train=k_train, k_test=k_test)
    finally:
        H.OBJECTS.clear()
        H.OBJECTS.update(saved_objects)
        H.FAMILIES.clear()
        H.FAMILIES.update(saved_families)
    for r in train + test:
        r['partner'] = profile['id']
    return train, test


def vacuum_rows(profile, seed=19):
    """Robot-vacuum families (v2 generator) with the partner's vacuum names; the gold target stays 'vacuum'."""
    vacs = [p for p in profile['products'] if p['kind'] == 'vacuum']
    if not vacs:
        return [], []
    saved = {k: list(v) for k, v in V2.VAC.items()}
    saved_extra = {k: list(v) for k, v in V2.EXTRA.items()}
    try:
        for ph in profile.get('phrases', []):
            if ph['family'].startswith('vacuum.') and ph['family'] in V2.FAMILIES:
                V2.EXTRA.setdefault(ph['family'], []).append(
                    ('fr' if ph['dialect'] == 'fr' else 'en', ph['template'].replace('{d}', '{vac}'), None))
        V2.VAC['en'] = [n for p in vacs for d in ('en-US', 'en-GB') for n in _names(p, d)] or saved['en']
        V2.VAC['fr'] = [n for p in vacs for n in _names(p, 'fr')] or saved['fr']
        train, test, _, _, _ = V2.build(seed, per_template=4, test_per_template=2)
    finally:
        V2.VAC.update(saved)
        V2.EXTRA.clear()
        V2.EXTRA.update(saved_extra)
    langs = {('fr' if d == 'fr' else 'en') for d in profile['languages'] if d in PV.INTENT_DIALECTS}
    allnames = [n.lower() for p in vacs for ns in p['names'].values() for n in ns]
    keep = lambda r: r['family'].startswith('vacuum.') and r['lang'] in langs and any(n in r['text'].lower() for n in allnames)
    return ([dict(r, partner=profile['id']) for r in train if keep(r)],
            [dict(r, partner=profile['id']) for r in test if keep(r)])


def build(profile, base_train=None, replay=800, seed=5):
    PV.validate(profile)
    h_train, h_test = home_rows(profile)
    v_train, v_test = vacuum_rows(profile)
    held = {r['text'].lower() for r in h_test + v_test}
    seen, partner_train = set(), []
    for r in h_train + v_train:
        k = r['text'].lower()
        if k not in held and k not in seen:
            seen.add(k)
            partner_train.append(_example(r))
    partner_test = [_example(r) for r in h_test + v_test]
    rng = random.Random(seed)
    old = list(base_train or [])
    rng.shuffle(old)
    train = partner_train + old[:replay]
    rng.shuffle(train)
    return {'train': train, 'test': partner_test, 'partner_test': partner_test,
            'report': {'partner_train': len(partner_train), 'partner_test': len(partner_test),
                       'replay': min(replay, len(old)), 'coverage': PV.coverage(profile)}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', required=True)
    ap.add_argument('--base-data', default=None, help='folder with the base train.jsonl (replayed to avoid forgetting)')
    ap.add_argument('--replay', type=int, default=800)
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    profile = json.loads(Path(a.profile).read_text(encoding='utf-8'))
    base = []
    if a.base_data:
        with open(Path(a.base_data) / 'train.jsonl', encoding='utf-8') as f:
            base = [json.loads(line) for line in f if line.strip()]
    sets = build(profile, base, a.replay)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in ('train', 'test', 'partner_test'):
        with open(out / ('%s.jsonl' % name), 'w', encoding='utf-8') as f:
            for r in sets[name]:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    (out / 'REPORT.json').write_text(json.dumps(sets['report'], indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(sets['report'], ensure_ascii=False))


if __name__ == '__main__':
    main()
