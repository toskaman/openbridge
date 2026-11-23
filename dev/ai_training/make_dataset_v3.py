"""v3 dataset: v2 commands + every kind of home device (US English, UK English, French) + creating new features.

    python dev/ai_training/make_dataset_v3.py --out E:/OpenBridgeAI/data_v3
Writes train / test / novel (all) plus home_test / home_novel (the new parts alone, for reporting).
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_dataset as V2  # noqa: E402
import home_families as H  # noqa: E402


def novel_home_rows():
    rows = []
    for dialect, text, exp in H.HOME_NOVEL:
        lang = 'fr' if dialect == 'fr' else 'en'
        if exp[0] == 'clarify':
            r, fam = H.Q('ambiguous request', 'Can you be more specific?', 'underspecified'), 'clarify'
        elif exp[0] == 'unsupported':
            r, fam = H.U('no registered skill does this'), 'unsupported'
        elif exp[0] == 'link':
            r, fam = H.R('novel link', 'links.create', [H.DEVT(x) for x in exp[1]], exp[2]), 'links.create'
        else:
            _, sid, params, ref = exp
            r, fam = H.R('novel request', sid, H.FABRIC if ref == 'fabric' else [H.DEVT(ref)], params), sid
        rows.append({'family': 'novel-home/' + fam, 'lang': lang, 'dialect': dialect, 'text': text, 'reply': r})
    return rows


def ex(row):
    e = V2.example(row)
    e['dialect'] = row.get('dialect', row['lang'])
    return e


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='E:/OpenBridgeAI/data_v3')
    ap.add_argument('--old-train', type=int, default=1400, help='v2 training lines kept (the v1 adapter already knows them)')
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    v2_train, v2_test, v2_novel, _, _ = V2.build(7)
    h_train, h_test = H.build(V2.vary)
    h_novel = novel_home_rows()
    held = {r['text'].lower() for r in h_test} | {r['text'].lower() for r in h_novel} | {r['text'].lower() for r in v2_test} | \
           {r['text'].lower() for r in v2_novel}
    seen, h_uniq = set(), []
    for r in h_train:
        k = r['text'].lower()
        if k not in held and k not in seen:
            seen.add(k)
            h_uniq.append(r)
    rng = random.Random(3)
    old = v2_train[:]
    rng.shuffle(old)
    train = [dict(r, dialect=r['lang']) for r in old[:a.old_train]] + [ex(r) for r in h_uniq]
    rng.shuffle(train)
    sets = {'train': train, 'test': v2_test + [ex(r) for r in h_test], 'novel': v2_novel + [ex(r) for r in h_novel],
            'home_test': [ex(r) for r in h_test], 'home_novel': [ex(r) for r in h_novel]}
    # The registry grew: every prompt is rebuilt with today's catalog (v2 rows were built with it too).
    for name, rows in sets.items():
        with open(out / ('%s.jsonl' % name), 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(json.dumps({k: len(v) for k, v in sets.items()}))


if __name__ == '__main__':
    main()
