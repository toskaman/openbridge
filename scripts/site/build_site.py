"""Build the OpenBridge website into an output folder.

Copies site/ plus the README images it reuses, and generates the data files
behind the Compatibility and Benchmarks pages from the evidence registry and
the benchmark results already committed in docs/.

    python scripts/site/build_site.py --out _site

Standard library only, like the rest of OpenBridge.
"""
import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GITHUB = 'https://github.com/toskaman/openbridge/blob/main/'

CATEGORY_BY_PREFIX = [
    ('tv-vacuum', 'cross'), ('watch-tv', 'cross'), ('phone-bv9300-01-avd', 'cross'),
    ('tv-', 'screens'), ('watch-', 'wearables'), ('phone-', 'phones'), ('avd-', 'phones'),
    ('vacuum-', 'robots'), ('freebox-', 'network'), ('pc', 'pcs'), ('vm-', 'vms'),
    ('esp32', 'micro'),
]
LEVEL = {'REAL_HARDWARE': 'real', 'FULL_GUEST_OS': 'vm', 'OFFICIAL_PLATFORM_EMULATOR': 'official'}


def category(device_id):
    for prefix, cat in CATEGORY_BY_PREFIX:
        if device_id.startswith(prefix):
            return cat
    return 'other'


def evidence_url(ref):
    if ref.startswith('http'):
        return ref
    if ' ' in ref.strip():
        return None  # a description, not a file (for example: held on the author's PC)
    return GITHUB + ref


def clean_name(alias, platform=''):
    name = alias.replace('Owner phone', 'Android phone').replace('Owner TV', 'Android TV')
    name = re.sub(r'\bOwner\s+', '', name).replace('(owner router)', 'router').replace(' (owner-linked)', '')
    name = name.replace(' (owner set)', '')
    if 'USB' in platform and 'USB' not in name:
        name += ', over USB'
    return name.strip()


def compatibility():
    records = json.loads((ROOT / 'docs' / 'DEVICE_EVIDENCE.json').read_text(encoding='utf-8'))
    devices = {}
    for r in records:
        dev = devices.setdefault(r['public_device_id'], {
            'id': r['public_device_id'], 'name': clean_name(r['device_alias'], r.get('platform', '')),
            'category': category(r['public_device_id']), 'level': LEVEL.get(r['environment'], 'other'),
            'integration': r.get('integration', ''), 'platform': r.get('platform', ''), 'runs': []})
        dev['runs'].append({
            'alias': clean_name(r['device_alias'], r.get('platform', '')),
            'test': r.get('test_id', ''), 'date': r.get('test_utc', '')[:10], 'status': r.get('status', ''),
            'environment': r.get('environment', ''), 'operations': r.get('operations', []),
            'oracle': r.get('independent_oracle', ''), 'limitations': r.get('limitations', []),
            'evidence': [{'label': e if ' ' in e.strip() else e.rstrip('/').rsplit('/', 1)[-1], 'url': evidence_url(e)}
                         for e in r.get('evidence', [])],
        })
    out = sorted(devices.values(), key=lambda d: (d['level'] != 'real', d['category'], d['name']))
    for d in out:
        d['runs'].sort(key=lambda x: x['date'], reverse=True)
        d['last'] = d['runs'][0]['date']
        d['name'] = d['runs'][0]['alias']  # the most recent description of the device
    # Not in the registry on purpose: emulator results never count as hardware proof.
    out.append({'id': 'engo-hud-emulated', 'name': 'ENGO smart glasses (ActiveLook)', 'category': 'glasses',
                'level': 'emulated', 'integration': 'HUD Studio emulator + official ActiveLook app',
                'platform': 'ActiveLook HUD', 'last': '', 'runs': [], 'note': 'pending-hardware',
                'link': GITHUB + 'docs/partners/ENGO.md'})
    return {'source': 'docs/DEVICE_EVIDENCE.json', 'verified_runs': len(records), 'devices': out}


def benchmarks():
    bdir = ROOT / 'docs' / 'benchmark'
    routes = []
    for name, label in (('rules', 'Rules only'), ('llama3b', 'Llama 3.2 3B'), ('glimmer', 'Glimmer 30B')):
        d = json.loads((bdir / ('agent-benchmark-%s.json' % name)).read_text(encoding='utf-8'))
        routes.append({'route': name, 'label': label, 'attempts': d['attempts'],
                       'correct_pct': d['decision_correct_pct'], 'schema_valid_pct': d['schema_valid_pct'],
                       'unsafe_proposed': d['unsafe_proposals'], 'unsafe_refused_pct': d['unsafe_refused_by_gate_pct'],
                       'median_s': round(d['median_ms'] / 1000.0, 1), 'cost_usd': d['cost_usd'],
                       'recorded_at': d['recorded_at'][:10]})
    ev = json.loads((bdir / 'eval_1000_rules_baseline.json').read_text(encoding='utf-8'))
    records = json.loads((ROOT / 'docs' / 'DEVICE_EVIDENCE.json').read_text(encoding='utf-8'))
    env = {}
    for r in records:
        env[LEVEL.get(r['environment'], 'other')] = env.get(LEVEL.get(r['environment'], 'other'), 0) + 1
    return {
        'agent_planning': {'source': 'docs/benchmark/STATUS.md', 'cases': 30, 'repeats': 3,
                           'synthetic_inputs': True, 'routes': routes},
        'eval_1000': {'source': 'docs/benchmark/EVAL_1000_RULES_BASELINE.md', 'turns': ev['turns'],
                      'conversations': ev['conversations'], 'hard_fail': ev['hard_fail_proxies']},
        # Figures from docs/benchmark/F90_ENDURANCE_BASELINE.md (2026-11-01, Windows, Python 3.14.4, seed 7).
        'endurance': {'source': 'docs/benchmark/F90_ENDURANCE_BASELINE.md', 'simulated': True,
                      'cycles': 360, 'duration_s': 92.7, 'dispatch_ms': {'p50': 30.4, 'p95': 45.5, 'max': 290},
                      'error_rate_pct': 0.53, 'errors_injected_only': True, 'leaked_threads': 0,
                      'leaked_sockets': 0, 'shutdown_s': 0.42},
        'evidence': {'source': 'docs/DEVICE_EVIDENCE.json', 'verified_runs': len(records), 'by_level': env},
    }


def build(out):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / 'site', out)
    for sub in ('readme', 'partners'):
        shutil.copytree(ROOT / 'docs' / 'assets' / sub, out / 'assets' / sub, dirs_exist_ok=True)
    shutil.copy2(ROOT / 'docs' / 'partners' / 'engo' / 'img' / 'hud_studio_overview.png', out / 'assets')
    (out / 'data').mkdir(exist_ok=True)
    for name, data in (('compatibility', compatibility()), ('benchmarks', benchmarks())):
        (out / 'data' / (name + '.json')).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding='utf-8')
    (out / '.nojekyll').write_text('', encoding='utf-8')
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', default='_site')
    args = ap.parse_args(argv)
    out = build(args.out)
    print('site built in %s' % out)


if __name__ == '__main__':
    main()
