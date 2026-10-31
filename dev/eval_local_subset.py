"""§10 local eval subset: identical frozen inputs + identical rubric across arms.

Arms: rules (abstaining stub, keyword fallback only), llama (LOCAL-FAST via the
production OllamaIntentTransport), glimmer (LOCAL-QUALITY, same transport).
Sequential, one model loaded at a time (explicit unload between arms); $0.

Anti-leak: same oracle loader as dev/eval_1000.py (category + hard_fail_if
only; forbidden keys stripped). No cloud arm here: hosted Spark needs separate
authorization and is not run by this script.

Usage:
  python dev/eval_local_subset.py [--limit 50] [--arms rules,llama,glimmer] [--out PATH]
"""
import argparse
import importlib.util
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location('eval_1000', ROOT / 'dev' / 'eval_1000.py')
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

from src.runtime import nl_router as N  # noqa: E402
from src.ai.local_meta import local_request  # noqa: E402

TERMINAL = ('resolved', 'unsupported', 'needs_clarification', 'escalation_required')


def tags(endpoint):
    req = urllib.request.Request(endpoint + '/api/tags', method='GET')
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8')).get('models', [])


def unload(model_id, endpoint):
    try:
        local_request('/api/generate', {'model': model_id, 'keep_alive': 0}, endpoint=endpoint, timeout=30)
    except Exception:
        pass


def make_transport(model_id, endpoint, usage):
    def chat(payload):
        r = local_request('/api/chat', payload, endpoint=endpoint, timeout=180)
        usage['prompt'] += r.get('prompt_eval_count', 0) or 0
        usage['eval'] += r.get('eval_count', 0) or 0
        return r
    return N.OllamaIntentTransport(model_id, endpoint, chat=chat, timeout=180)


def run_turn(text, transport, quality):
    t0 = time.perf_counter()
    try:
        if quality == 'medium':
            doc = N.parse(text, 'fr', 'medium', E.stub_transport, None,
                          medium_transport=transport, cloud_allowed=False)
        else:
            doc = N.parse(text, 'fr', 'low', transport, None, cloud_allowed=False)
    except Exception as e:  # noqa: BLE001 - crash proxy must be recorded
        return {'status': 'CRASH', 'error': f'{type(e).__name__}: {e}'[:200],
                'latency_ms': (time.perf_counter() - t0) * 1000}, 0
    rec = {'status': doc.get('status'), 'skill_id': doc.get('skill_id'),
           'ambiguities': list(doc.get('ambiguities') or [])[:3],
           'latency_ms': (time.perf_counter() - t0) * 1000}
    if doc.get('status') == 'resolved':
        rec['receipt'] = {'skill_id': doc['skill_id'], 'targets': doc['targets'],
                          'params': doc['params'], 'provenance': 'eval-mock'}
    return rec, 0


def summarize(results, convs, usage):
    finished = sum(1 for rs in convs.values() if all(r['status'] in TERMINAL for r in rs))
    by_status = {}
    by_cat = {}
    for r in results:
        by_status[r['status']] = by_status.get(r['status'], 0) + 1
        c = by_cat.setdefault(r['category'], {'n': 0, 'resolved': 0})
        c['n'] += 1
        c['resolved'] += r['status'] == 'resolved'
    lat = sorted(r['latency_ms'] for r in results)
    return {
        'turns': len(results), 'conversations': len(convs), 'conversations_finished': finished,
        'by_status': by_status,
        'by_category': {k: {'n': v['n'], 'resolved': v['resolved']} for k, v in sorted(by_cat.items())},
        'hard_fail_proxies': {'crashes': by_status.get('CRASH', 0),
                              'external_sends': sum(r['sends'] for r in results)},
        'latency_ms': {'mean': round(sum(lat) / len(lat), 1), 'p50': round(lat[len(lat) // 2], 1),
                       'p95': round(lat[int(len(lat) * 0.95)], 1)},
        'tokens': dict(usage),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description='§10 frozen-subset local eval (rules/llama/glimmer)')
    ap.add_argument('--turns', default=str(E.DEFAULT_TURNS))
    ap.add_argument('--oracles', default=str(E.DEFAULT_ORACLES))
    ap.add_argument('--limit', type=int, default=50)
    ap.add_argument('--arms', default='rules,llama,glimmer')
    ap.add_argument('--out', default='')
    args = ap.parse_args(argv)

    turns = E.load_turns(args.turns)[:args.limit]          # frozen prefix: identical inputs per arm
    meta = E.load_oracle_meta(args.oracles)
    report = {'limit': args.limit, 'turns_file': str(args.turns),
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'arms': {}, 'manifest': {}}

    for arm in [a.strip() for a in args.arms.split(',') if a.strip()]:
        usage = {'prompt': 0, 'eval': 0}
        if arm == 'rules':
            transport, quality = E.stub_transport, 'low'
        elif arm in ('llama', 'glimmer'):
            tier = 'low' if arm == 'llama' else 'medium'
            model_id, endpoint = N.TIERS[tier]
            rows = tags(endpoint)
            m = next((r for r in rows if r.get('name') == model_id), None)
            if m is None:
                report['arms'][arm] = {'error': f'{model_id} not served on {endpoint}'}
                continue
            report['manifest'][arm] = {'model_id': model_id, 'endpoint': endpoint,
                                       'digest': m.get('digest'), 'size': m.get('size')}
            transport = make_transport(model_id, endpoint, usage)
            quality = 'low' if arm == 'llama' else 'medium'
        else:
            report['arms'][arm] = {'error': f'unknown arm {arm}'}
            continue
        results, convs = [], {}
        for t in turns:
            rec, sends = run_turn(t['user_text'], transport, quality)
            rec.update({'id': t['id'], 'conversation_id': t['conversation_id'],
                        'turn': t['turn'], 'sends': sends,
                        'category': meta.get(t['id'], {}).get('category', '?')})
            results.append(rec)
            convs.setdefault(t['conversation_id'], []).append(rec)
        report['arms'][arm] = summarize(results, convs, usage)
        report['arms'][arm]['results'] = results
        if arm in ('llama', 'glimmer'):                    # one model in VRAM at a time
            _mid, _ep = N.TIERS['low' if arm == 'llama' else 'medium']
            unload(_mid, _ep)

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1), encoding='utf-8')
    for arm, rep in report['arms'].items():
        if 'error' in rep:
            print(f'{arm}: ERROR {rep["error"]}')
            continue
        print(f"{arm}: n={rep['turns']} resolved={rep['by_status'].get('resolved', 0)} "
              f"by_status={rep['by_status']} p50={rep['latency_ms']['p50']}ms "
              f"tokens={rep['tokens']} crashes={rep['hard_fail_proxies']['crashes']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
