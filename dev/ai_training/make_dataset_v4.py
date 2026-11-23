"""v4 dataset: v3 + household chores that OpenBridge cannot do, said with the same verbs as real commands.

v3 understood « sors les poubelles » (take the bins out) as "empty the robot vacuum's dust bin": "vider / sortir /
bac / poubelle" sound like vacuum commands, and the only chores in v3 were two held-out lines. v4 adds about 70
chore phrasings in French, US and UK English (bins, dishes, laundry, pets, plants, windows...), all "no registered
skill does this", next to every vacuum command that names the robot. Same held-out rules as v3 (20 % of the
templates are test-only), plus hand-written requests never trained on (chores_novel.jsonl).

    python dev/ai_training/make_dataset_v4.py --out E:/OpenBridgeAI/data_v4
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import home_families as H  # noqa: E402
import make_dataset as V2  # noqa: E402
import make_dataset_v3 as V3  # noqa: E402

CHORES = [
    ('fr', 'Sors les poubelles'), ('fr', 'Sors la poubelle'), ('fr', 'Tu peux sortir les poubelles ?'),
    ('fr', 'Descends les poubelles'), ('fr', 'Vide la poubelle'), ('fr', 'Vide la poubelle de la cuisine'),
    ('fr', 'Vide les poubelles'), ('fr', 'Rentre les poubelles'), ('fr', 'Sors le recyclage'),
    ('fr', 'Mets les poubelles sur le trottoir'), ('fr', 'Sors le chien'), ('fr', 'Promène le chien'),
    ('fr', 'Fais la vaisselle'), ('fr', 'Vide le lave-vaisselle'), ('fr', 'Étends le linge'), ('fr', 'Plie le linge'),
    ('fr', 'Vide le sèche-linge'), ('fr', 'Sors le linge de la machine'), ('fr', 'Vide le bac à linge'),
    ('fr', 'Range la cuisine'), ('fr', 'Range ta chambre'), ('fr', 'Fais le lit'), ('fr', 'Arrose les plantes'),
    ('fr', 'Nourris le chat'), ('fr', 'Change la litière du chat'), ('fr', 'Vide le cendrier'), ('fr', 'Vide le frigo'),
    ('fr', 'Fais les courses'), ('fr', 'Repasse ma chemise'), ('fr', 'Nettoie les vitres'), ('fr', 'Lave la voiture'),
    ('fr', 'Tonds la pelouse'), ('fr', 'Vide la boîte aux lettres'), ('fr', 'Vide le lave-linge'),
    ('en-US', 'Take out the trash'), ('en-US', 'Take the trash out'), ('en-US', 'Empty the trash'),
    ('en-US', 'Empty the trash can'), ('en-US', 'Take the garbage out'), ('en-US', 'Take the recycling out'),
    ('en-US', 'Walk the dog'), ('en-US', 'Do the dishes'), ('en-US', 'Unload the dishwasher'),
    ('en-US', 'Empty the dishwasher'), ('en-US', 'Fold the laundry'), ('en-US', 'Empty the dryer'),
    ('en-US', 'Clean the windows'), ('en-US', 'Make the bed'), ('en-US', 'Water the plants'), ('en-US', 'Feed the cat'),
    ('en-US', 'Change the litter box'), ('en-US', 'Mow the lawn'), ('en-US', 'Wash the car'), ('en-US', 'Iron my shirt'),
    ('en-US', 'Get the mail'),
    ('en-GB', 'Put the bins out'), ('en-GB', 'Take the bins out'), ('en-GB', 'Empty the bin'), ('en-GB', 'Bring the bins in'),
    ('en-GB', 'Empty the kitchen bin'), ('en-GB', 'Do the washing up'), ('en-GB', 'Empty the dishwasher'),
    ('en-GB', 'Hang the washing out'), ('en-GB', 'Walk the dog'), ('en-GB', 'Feed the cat'), ('en-GB', 'Water the garden'),
    ('en-GB', 'Empty the recycling'), ('en-GB', 'Tidy the kitchen'),
]
_ED = lambda: V2.reply('empty the robot dust bin', 'vacuum.empty_dust', V2.DEV('vacuum'))
_ST = lambda: V2.reply('start cleaning', 'vacuum.start', V2.DEV('vacuum'))
_U = lambda: H.U('no registered skill does this')
# Written by hand, never generated, never trained on.
CHORES_NOVEL = [
    ('fr', 'sors les poubelles stp', _U), ('fr', 'tu peux vider la poubelle ?', _U), ('fr', 'vide la poubelle de la salle de bain', _U),
    ('fr', 'faut sortir le chien', _U), ('fr', 'fais la vaisselle steuplé', _U), ('fr', 'vide le lave vaisselle', _U),
    ('fr', "vide le bac de l'aspirateur", _ED), ('fr', 'le robot peut vider son bac ?', _ED), ("fr", "passe l'aspirateur dans le salon", _ST),
    ('en-US', 'take the trash out please', _U), ('en-US', 'empty the garbage can in the kitchen', _U), ('en-US', 'can you unload the dishwasher', _U),
    ('en-US', 'have the robot empty its dustbin', _ED), ('en-US', 'vacuum the kitchen', _ST),
    ('en-GB', 'put the bins out, ta', _U), ('en-GB', 'empty the bin in the bathroom', _U), ('en-GB', 'get the hoover going', _ST),
]


def chore_rows(seed):
    saved = dict(H.FAMILIES)
    try:
        H.FAMILIES.clear()
        H.FAMILIES['home.unsupported'] = (None, (), list(CHORES))     # gold: "no registered skill does this"
        train, test = [], []
        for s in (seed, seed + 1):
            a, b = H.build(V2.vary, seed=s, k_train=3, k_test=1)
            train += a
            test += b
    finally:
        H.FAMILIES.clear()
        H.FAMILIES.update(saved)
    relabel = lambda rows: [dict(r, family='home.chores') for r in rows]
    return relabel(train), relabel(test)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='E:/OpenBridgeAI/data_v4')
    ap.add_argument('--v3', default=None, help='existing v3 data folder to reuse (default: rebuild it)')
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    v3dir = Path(a.v3) if a.v3 else out / 'v3'
    if not a.v3:
        V3.main(['--out', str(v3dir)])
    load = lambda name: [json.loads(line) for line in open(v3dir / ('%s.jsonl' % name), encoding='utf-8') if line.strip()]
    c_train, c_test = chore_rows(41)
    held = {r['text'].lower() for r in c_test} | {t.lower() for _, t, _ in CHORES_NOVEL}
    seen, chores = set(), []
    for r in c_train:
        k = r['text'].lower()
        if k not in held and k not in seen:
            seen.add(k)
            chores.append(V3.ex(r))
    # Contrast: every v2 robot-vacuum training line that names the robot ("vide le bac de l'aspirateur").
    v2_train = V2.build(7)[0]
    have = {r['text'] for r in load('train')}
    contrast = [dict(r, dialect=r['lang']) for r in v2_train
                if r['family'] in ('vacuum.empty_dust', 'vacuum.start') and r['text'] not in have]
    rng = random.Random(4)
    train = load('train') + chores + contrast
    rng.shuffle(train)
    novel_rows = []
    for dialect, text, gold in CHORES_NOVEL:
        lang = 'fr' if dialect == 'fr' else 'en'
        fam = 'novel-chores/' + (gold()['skill_id'] or 'unsupported')
        novel_rows.append(V3.ex({'family': fam, 'lang': lang, 'dialect': dialect, 'text': text, 'reply': gold()}))
    sets = {'train': train, 'test': load('test') + [V3.ex(r) for r in c_test], 'novel': load('novel') + novel_rows,
            'home_test': load('home_test'), 'home_novel': load('home_novel'),
            'chores_test': [V3.ex(r) for r in c_test], 'chores_novel': novel_rows}
    for name, rows in sets.items():
        with open(out / ('%s.jsonl' % name), 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(json.dumps(dict({k: len(v) for k, v in sets.items()}, chores_train=len(chores), contrast=len(contrast))))


if __name__ == '__main__':
    main()
