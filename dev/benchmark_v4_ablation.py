"""V4-04 registered ablation: who ranks cross-transport hypotheses best on held-out cases?
Arms: rules (deterministic), Llama 3.2 3B local, Muse Glimmer 30B local, Muse Spark 1.3 hosted (synthetic cases only,
supervised credits). Models only RE-RANK the hypotheses produced by the rules from the same minimised payload
used by the cloud escalation; they cannot add a hypothesis. Registration: docs/benchmark/v4/REGISTRATION.md.
    python -m dev.benchmark_v4_ablation --arms rules,llama,glimmer[,spark] --repeats 3
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from src.ai.cloud_escalation import SYSTEM, CloudEscalation, projection
from src.runtime import hypotheses, redact
from src.runtime.timeline import Timeline

CASES = Path('docs/benchmark/v4/heldout_cases.json')
NO_OBSERVED = {'unobserved_cause', 'device_local_link'}       # registered equivalence class


def correct(pred, label):
    return pred == label or (label in NO_OBSERVED and pred in NO_OBSERVED)


def analysis(rows):
    tl = Timeline(clock=lambda: 0)
    for dev, cat, n, v, t in rows:
        tl.observe(dev, cat, n, v, 'heldout', t=t)
    r = tl.rows(limit=10_000)
    return hypotheses.analyze(r, 'tv'), r


def local_rank(broker):
    def rank(a, rows):
        local, _ = projection(a, rows)
        body = redact.prepare(local)['payload'].decode()
        ids = [h['id'] for h in a['hypotheses']]
        schema = {'type': 'object', 'additionalProperties': False, 'required': ['ranking', 'summary', 'uncertainty', 'next_read_only_check'],
                  'properties': {'ranking': {'type': 'array', 'minItems': 1, 'items': {'type': 'string', 'enum': ids}},
                                 'summary': {'type': 'string'}, 'uncertainty': {'type': 'string'}, 'next_read_only_check': {'type': 'string'}}}
        out, _ = broker._call({'model': broker.model_id, 'stream': False, 'format': schema, 'keep_alive': '120s', **broker.extra,
                               'options': {**broker.options, 'num_predict': 400},
                               'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': body}]})
        resp = {'model': 'muse-spark-1.3', 'choices': [{'message': {'content': json.dumps(out)}}]}   # reuse the same validator
        return CloudEscalation.validate(resp, ids)['ranking'][0]
    return rank


def spark_rank(esc):
    def rank(a, rows):
        pv = esc.preview(a, rows)
        return esc.confirm(pv['preview_id'], pv['sha256'], True)['answer']['ranking'][0]
    return rank


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--arms', default='rules'); ap.add_argument('--repeats', type=int, default=3)
    a = ap.parse_args()
    raw = CASES.read_text(); data = json.loads(raw)
    arms = {'rules': lambda an, rows: an['hypotheses'][0]['id']}
    if 'llama' in a.arms:
        from src.ai.local_meta import LocalMetaBroker; arms['llama'] = local_rank(LocalMetaBroker())
    if 'glimmer' in a.arms:
        from src.ai.glimmer import GlimmerBroker; arms['glimmer'] = local_rank(GlimmerBroker())
    if 'spark' in a.arms:
        import os
        from src.ai.broker import RuntimeModelBroker, CreditPermit, MetaTransport
        from src.runtime.api_v2 import _meta_key
        permit = CreditPermit(os.environ['OPENBRIDGE_CREDIT_OBSERVATION_ID'], datetime.fromisoformat(os.environ['OPENBRIDGE_CREDIT_VERIFIED_AT']),
                              float(os.environ['OPENBRIDGE_FREE_CREDITS_USD']), 0.20)
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
        arms['spark'] = spark_rank(CloudEscalation(RuntimeModelBroker(root / 'runtime-budget.sqlite', permit, MetaTransport(_meta_key()))))
    results = {}
    for arm, fn in arms.items():
        if arm not in ['rules'] + a.arms.split(','):
            continue
        rows_out, reps = [], (1 if arm == 'rules' else a.repeats)
        for cid, case in sorted(data['cases'].items()):
            an, rows = analysis(case)
            for rep in range(reps):
                t = time.monotonic()
                try:
                    pred, err = fn(an, rows), None
                except Exception as e:
                    pred, err = None, type(e).__name__
                rows_out.append({'case': cid, 'rep': rep, 'pred': pred, 'label': data['labels'][cid]['label'],
                                 'ok': bool(pred) and correct(pred, data['labels'][cid]['label']), 'error': err,
                                 'ms': round((time.monotonic() - t) * 1000)})
        n = len(rows_out)
        results[arm] = {'n': n, 'top1_accuracy': round(sum(r['ok'] for r in rows_out) / n, 3), 'errors': sum(bool(r['error']) for r in rows_out),
                        'median_ms': sorted(r['ms'] for r in rows_out)[n // 2], 'rows': rows_out}
    out = {'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'cases_sha256': hashlib.sha256(raw.encode()).hexdigest(),
           'summary': {k: {x: v[x] for x in ('n', 'top1_accuracy', 'errors', 'median_ms')} for k, v in results.items()}, 'arms': results}
    p = Path('docs/benchmark/v4'); f = p / f"ablation-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    f.write_text(json.dumps(out, indent=1)); print(json.dumps(out['summary'], indent=1)); print('saved', f)


if __name__ == '__main__':
    main()
