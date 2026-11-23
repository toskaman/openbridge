"""Write docs/partners/engo/21_FEATURE_TRACEABILITY_MATRIX.md from feature_registry.json (the single source).

    python dev/engo_feature_matrix.py            # regenerate
    python dev/engo_feature_matrix.py --check    # exit 1 if the Markdown is out of date (used by the tests)
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / 'docs' / 'partners' / 'engo' / 'feature_registry.json'
OUT = ROOT / 'docs' / 'partners' / 'engo' / '21_FEATURE_TRACEABILITY_MATRIX.md'
GROUPS = [('HUD', 'Core HUD'), ('CONN', 'Connection and maintenance'), ('NAV', 'GPS and navigation'), ('RUN', 'Running'),
          ('TRAIL', 'Trail and ultra'), ('BIKE', 'Cycling'), ('GHOST', 'Ghost Competition'), ('SENSOR', 'Sensors'),
          ('AI', 'AI coach'), ('RULE', 'Rules'), ('VOICE', 'Voice'), ('PHONE', 'Phone as sensor proxy'),
          ('SAFE', 'Safety and SOS'), ('ENV', 'Weather'), ('HEALTH', 'Recovery'), ('INT', 'Integrations'),
          ('PC', 'PC and simulators'), ('SPORT', 'Other sports'), ('GOLF', 'Golf'), ('PRO', 'Professional'),
          ('SOC', 'Community'), ('PRIV', 'Privacy'), ('EXT', 'Extensions'), ('OBH', 'OpenBridge home on the glasses'),
          ('I18N', 'Français / English'), ('F', 'HUD Studio feature catalogue F01-F38')]


def render(reg):
    feats = reg['features']
    c = Counter(f['status'] for f in feats)
    lines = ['# ENGO feature traceability matrix', '',
             '> Generated from [`feature_registry.json`](feature_registry.json) by `python dev/engo_feature_matrix.py`.',
             '> Do not edit by hand. Statuses: ' + ', '.join('`%s`' % s for s in reg['statuses']) + '.',
             '> Evidence categories never merge: ' + ', '.join('`%s`' % s for s in reg['evidence_categories']) + '.',
             '> **No feature is `VALIDATED_REAL` yet: the ENGO 3 Photochromic pair has not arrived.**', '',
             '| Status | Count |', '|---|---:|']
    lines += ['| %s | %d |' % (s, c.get(s, 0)) for s in reg['statuses']]
    lines += ['| **Total** | **%d** |' % len(feats), '']
    for prefix, title in GROUPS:
        rows = [f for f in feats if f['feature_id'].split('-')[0] == prefix or (prefix == 'F' and f['feature_id'][:1] == 'F' and '-' not in f['feature_id'])]
        if not rows:
            continue
        lines += ['## %s' % title, '', '| ID | Feature | Status | Code | Tests | Evidence | Limits |', '|---|---|---|---|---|---|---|']
        for f in rows:
            tests = '<br>'.join('`%s`' % Path(t).name for t in f['tests'])
            lines.append('| %s | %s | %s | %s | %s | %s | %s |' % (
                f['feature_id'], f['name'].replace('|', '/'), f['status'], ('`%s`' % f['owner_module']) if f['owner_module'] else '',
                tests, ', '.join(f['evidence_refs']), (f['limitations'] or '').replace('|', '/')))
        lines.append('')
    return '\n'.join(lines)


def main():
    reg = json.loads(REG.read_text(encoding='utf-8'))
    text = render(reg)
    if '--check' in sys.argv:
        sys.exit(0 if OUT.exists() and OUT.read_text(encoding='utf-8') == text else 1)
    OUT.write_text(text, encoding='utf-8', newline='\n')
    print('%d features -> %s' % (len(reg['features']), OUT))


if __name__ == '__main__':
    main()
