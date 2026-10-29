"""S1 offline synthesis benchmark: v4-synth-3 (local llama, $0) vs RulesPlanner.

Frozen DEV cases only: synthetic media/watch devices, read-only intents,
primitives ('read_facts',). Disjoint from the sealed pool by device, primitive
and effect (no TV, no audio/screen, no effects) — running this cannot tune
toward the sealed task. No ledger, no provider, no hardware, no network
beyond 127.0.0.1:11437.

Metrics per case: valid (schema+evidence), failure class, latency, evidence
precision (refs known?), grants minimal+in-scope. Baseline: RulesPlanner
always ABSTAINs (its correct behavior — it cannot generate); the benchmark
quantifies what only Meta synthesis does, plus its failure taxonomy.

Usage: python -m dev.synth_bench --out docs/evidence/v4/synth-bench
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIMS = ('read_facts',)
MODEL_ID = 'llama3.2:3b-instruct-q4_K_M'
ENDPOINT = 'http://127.0.0.1:11437'

CASES = [
    {'id': 'D1', 'category': 'media', 'intent': 'Read the media player facts for the owner.',
     'facts': [('model', 'ClipBox 2'), ('fw', '3.1.4')]},
    {'id': 'D2', 'category': 'media', 'intent': 'Summarize what the media renderer exposes.',
     'facts': [('model', 'ClipBox 2'), ('codecs', 'h264,opus'), ('net', 'wifi')]},
    {'id': 'D3', 'category': 'watch', 'intent': 'Read the watch facts without changing anything.',
     'facts': [('model', 'Pulse S'), ('os', 'wear-4')]},
    {'id': 'D4', 'category': 'watch', 'intent': 'List the watch sensors as read-only facts.',
     'facts': [('model', 'Pulse S'), ('sensors', 'hr,acc'), ('batt', '82')]},
    {'id': 'D5', 'category': 'media', 'intent': 'Give me a read-only view of the speaker state.',
     'facts': [('model', 'BoomMini'), ('state', 'idle')]},
    {'id': 'D6', 'category': 'watch', 'intent': 'What facts does the paired watch report?',
     'facts': [('model', 'Pulse S'), ('paired', 'yes')]},
    {'id': 'D7', 'category': 'media', 'intent': 'Read facts, then stop: no effects allowed.',
     'facts': [('model', 'ClipBox 2'), ('queue', 'empty')]},
    {'id': 'D8', 'category': 'watch', 'intent': 'Observe-only summary of the watch, minimal grants.',
     'facts': [('model', 'Pulse S'), ('os', 'wear-4'), ('apps', '5')]},
]


def build_bundle(case):
    sys.path.insert(0, str(ROOT))
    from src.forge import v4_evidence as E
    facts = [{'fact_id': 'f%d' % i, 'kind': k, 'value': v, 'source': 'SIMULATED', 'observed_at': 1000.0}
             for i, (k, v) in enumerate(case['facts'])]
    return E.resolve([{'category': case['category'], 'device_id': 'synth-dev-1',
                       'permission_scope': ['observe', 'read'], 'facts': facts}],
                     [], PRIMS, 1000.0)


def score(case, bundle, ok, body):
    """Pure scoring of one synthesize outcome. No I/O."""
    known = {f['evidence_ref'] for d in bundle['devices'] for f in d['facts']}
    scopes = set(bundle['devices'][0].get('permission_scope', []))
    rec = {'id': case['id'], 'baseline': 'ABSTAIN_UNSUPPORTED', 'valid': False,
           'reason': None, 'evidence_precision': None, 'grants_ok': None,
           'usage': (body.get('usage') or {}) if isinstance(body, dict) else {}}
    if not ok:
        rec['reason'] = (body.get('status'), (body.get('reason') or '')[:100])
        return rec
    cand = body['candidate']
    refs = cand.get('evidence_refs') or []
    rec['evidence_precision'] = sum(1 for r in refs if r in known) / max(len(refs), 1)
    grants = cand.get('required_grants') or []
    rec['grants_ok'] = bool(grants) and set(grants) <= scopes and len(set(grants)) == len(grants)
    rec['valid'] = rec['evidence_precision'] == 1.0 and rec['grants_ok'] \
        and all(s['primitive_id'] in PRIMS for s in cand.get('primitive_chain', []))
    if not rec['valid']:
        rec['reason'] = ('INVALID', 'evidence=%.2f grants_ok=%s' % (rec['evidence_precision'], rec['grants_ok']))
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    from src.forge import v4_metaclient as M
    from src.forge import v4_synthesize as Y
    send = M.ollama_transport(ENDPOINT, MODEL_ID, pinned_models={MODEL_ID})
    client = M.MetaClient({'low': send})
    base = M.RulesPlanner(PRIMS)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for case in CASES:
        bundle = build_bundle(case)
        base.propose(bundle, case['intent'])  # recorded abstention, $0
        t0 = time.monotonic()
        try:
            ok, body = Y.synthesize(client, 'low', bundle, case['intent'], PRIMS,
                                    case['category'])
        except Exception as e:
            ok, body = False, {'status': 'HARNESS_ERROR', 'reason': '%s: %s' % (type(e).__name__, str(e)[:100])}
        rec = score(case, bundle, ok, body)
        rec['latency_ms'] = round((time.monotonic() - t0) * 1000)
        records.append(rec)
        print('%s valid=%s reason=%s ms=%d' % (rec['id'], rec['valid'], rec['reason'], rec['latency_ms']), flush=True)
        (out / 'BENCH.json').write_text(json.dumps(
            {'model': MODEL_ID, 'prompt': Y.PROMPT_VERSION, 'cases': records}, indent=1), encoding='utf-8')
    n_valid = sum(1 for r in records if r['valid'])
    print('SYNTH_BENCH valid=%d/%d provider_cost_usd=0.0' % (n_valid, len(records)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
