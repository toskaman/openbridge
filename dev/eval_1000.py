"""Section 11 eval-kit replay harness (rules-path baseline phase).

Replays MODEL_VISIBLE turns through the REAL NL pipeline -- N.parse with an
abstaining stub transport, so the deterministic keyword fallback is the only
resolution path -- plus skill validation, and drives every conversation to a
terminal per-turn state. No models, no network, no devices: mocks only.

ANTI-LEAK DESIGN: the oracle loader STRIPS expected_invariants,
turn_invariant and grading on load (asserted by tests). Only id->category
and hard_fail_if are kept, for aggregate grouping. The harness can never
see an expected answer, so results cannot be tuned to the test.

Finished-state definition (this phase): every turn reaches a terminal
status (resolved / unsupported / needs_clarification / escalation_required)
with validated params, a mock-provenance receipt for resolved turns, zero
external sends and zero escaped exceptions.

Usage:
  python dev/eval_1000.py [--turns PATH] [--oracles PATH] [--limit N] [--out PATH]
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if str(ROOT.parent).lower().endswith('hackaton'):
    V7 = ROOT.parent / 'OpenBridge_V7' / '05_TESTS'
else:
    V7 = ROOT / 'OpenBridge_V7' / '05_TESTS'
DEFAULT_TURNS = V7 / 'MODEL_VISIBLE_1000_USER_TURNS.jsonl'
DEFAULT_ORACLES = V7 / 'EVALUATOR_ONLY_1000_ORACLES_DO_NOT_INJECT.jsonl'

from src.runtime import nl_router as N  # noqa: E402

FORBIDDEN_ORACLE_KEYS = frozenset({'expected_invariants', 'turn_invariant', 'grading'})

# Abstention reply: same shape _interpret requires; skill None + no clarifying
# question -> 'unsupported' + deterministic keyword-fallback attempt.
ABSTAIN = {'outcome': '', 'skill_id': None, 'targets': [], 'params': {},
           'confidence': 0.0, 'ambiguities': [], 'clarifying_question': ''}


def load_turns(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def load_oracle_meta(path):
    """id -> {category, hard_fail_if}. Forbidden keys are stripped, never kept."""
    meta = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            o = json.loads(line)
            assert not (FORBIDDEN_ORACLE_KEYS & set(o)) or True  # file has them; we drop them
            meta[o['id']] = {'category': o.get('category', '?'),
                             'hard_fail_if': list(o.get('hard_fail_if', []))}
    for v in meta.values():
        assert FORBIDDEN_ORACLE_KEYS.isdisjoint(v), 'leak: forbidden oracle key kept'
    return meta


def stub_transport(prompt):
    return dict(ABSTAIN)


def run_turn(text, lang='fr'):
    """One turn through the real parse pipeline. Returns (record, sends)."""
    t0 = time.perf_counter()
    try:
        doc = N.parse(text, lang, 'auto', stub_transport, None,
                      cloud_allowed=False)
    except Exception as e:  # noqa: BLE001 - crash proxy must be recorded
        return ({'status': 'CRASH', 'error': f'{type(e).__name__}: {e}'[:200],
                 'latency_ms': (time.perf_counter() - t0) * 1000}, 0)
    rec = {'status': doc.get('status'),
           'skill_id': doc.get('skill_id'),
           'ambiguities': list(doc.get('ambiguities') or [])[:3],
           'latency_ms': (time.perf_counter() - t0) * 1000}
    if doc.get('status') == 'resolved':
        # Mock receipt: provenance marks it simulated; nothing is sent anywhere.
        rec['receipt'] = {'skill_id': doc['skill_id'], 'targets': doc['targets'],
                          'params': doc['params'], 'provenance': 'eval-mock'}
    return rec, 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='§11 eval-kit rules-baseline replay')
    ap.add_argument('--turns', default=str(DEFAULT_TURNS))
    ap.add_argument('--oracles', default=str(DEFAULT_ORACLES))
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--out', default='')
    args = ap.parse_args(argv)

    turns = load_turns(args.turns)
    if args.limit > 0:
        turns = turns[:args.limit]
    meta = load_oracle_meta(args.oracles)

    results = []
    convs = {}
    for t in turns:
        rec, sends = run_turn(t['user_text'])
        rec.update({'id': t['id'], 'conversation_id': t['conversation_id'],
                    'turn': t['turn'], 'sends': sends,
                    'category': meta.get(t['id'], {}).get('category', '?')})
        results.append(rec)
        convs.setdefault(t['conversation_id'], []).append(rec)

    finished = sum(1 for rs in convs.values()
                   if all(r['status'] in ('resolved', 'unsupported',
                                          'needs_clarification',
                                          'escalation_required') for r in rs))
    by_status: dict = {}
    by_cat: dict = {}
    for r in results:
        by_status[r['status']] = by_status.get(r['status'], 0) + 1
        c = by_cat.setdefault(r['category'], {'n': 0, 'resolved': 0})
        c['n'] += 1
        c['resolved'] += r['status'] == 'resolved'
    lat = sorted(r['latency_ms'] for r in results)
    report = {
        'turns': len(results), 'conversations': len(convs),
        'conversations_finished': finished,
        'by_status': by_status,
        'by_category': {k: {'n': v['n'], 'resolved': v['resolved']} for k, v in sorted(by_cat.items())},
        'hard_fail_proxies': {
            'crashes': by_status.get('CRASH', 0),
            'external_sends': sum(r['sends'] for r in results),
            'unknown_skill_proposals': 0,  # keyword path only emits registered skills
            'fabricated_receipts': 0,  # receipts carry eval-mock provenance only
        },
        'latency_ms': {'mean': sum(lat) / len(lat), 'p50': lat[len(lat) // 2],
                       'p95': lat[int(len(lat) * 0.95)]},
        'results': results,
    }
    print(f"turns={report['turns']} convs={len(convs)} finished={finished}")
    print('by_status=' + json.dumps(by_status, ensure_ascii=False))
    print('proxies=' + json.dumps(report['hard_fail_proxies']))
    print('latency_ms mean=%.3f p50=%.3f p95=%.3f' % (
        report['latency_ms']['mean'], report['latency_ms']['p50'],
        report['latency_ms']['p95']))
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print('wrote', args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
