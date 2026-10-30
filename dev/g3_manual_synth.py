"""G3 sealed-137 extended-budget synthesis (disclosed deviation from the freeze).

The frozen 120s/call budget cannot run Muse Glimmer 30B on the lab GPU
(3 attempts, 3 TimeoutErrors, transcripts kept). This script performs ONLY the
synthesis step with an extended model-call budget (600s) and otherwise reuses
the frozen pieces byte-for-byte:

- live evidence + bundle: same calls as dev/run_g3_local.py lines 1-199
  (fabric-discover -> signed facts -> catalog -> offer filter -> resolve)
- prompt: v4_synthesize.build_prompt (frozen, v4-synth-4), same args
- transport: transport_from_broker(GlimmerBroker()) (digest-provisioned, echo-checked)
- validation: v4_synthesize.validate_candidate with the same (schemas, required)

It writes a synthesis record consumable by run_g3_local.py --replay-from, which
re-validates the candidate against FRESH live evidence and then runs the frozen
bind -> compile -> grant -> invoke -> oracle -> restore -> revoke pipeline.

The sealed task (sha committed in PR139 before any synthesis) is unchanged; no
result existed when this deviation was recorded (freeze addendum committed
before this script ran). No cherry-picking: every attempt's record is kept.

Usage: python -m dev.g3_manual_synth --base URL --out DIR --task-spec PATH --task-sha256 HEX [--tier glimmer|llama] [--max-s N]
"""
import argparse
import hashlib
import json
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    for a in ('--base', '--out', '--task-spec', '--task-sha256'):
        ap.add_argument(a, required=True)
    ap.add_argument('--tier', choices=['glimmer', 'llama'], default='glimmer')
    ap.add_argument('--max-s', type=int, default=600)
    ap.add_argument('--attempts', type=int, default=3)
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    from dev.run_g3_smoke import Http, resolve_scope, strip_fences
    from src.forge import v4_evidence, v4_synthesize, v4_schemas as S
    from src.forge.v4_metaclient import transport_from_broker

    from dev import g3_task
    try:
        spec = g3_task.load(args.task_spec, args.task_sha256)
    except (g3_task.SpecError, OSError, ValueError) as e:
        print('TASK_SPEC: %s' % e); return 2
    INTENT_T, OFFER_T, CAT = spec['intent'], tuple(spec['offer']), spec['target_category']
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    R = {'kind': 'G3_EXTENDED_SYNTHESIS', 'task_id': spec['task_id'], 'task_sha256': g3_task.spec_sha256(spec),
         'started': datetime.now(timezone.utc).isoformat(), 'tier': args.tier, 'max_s': args.max_s,
         'deviation': ('model-call budget %ds instead of the frozen 120s; everything else identical '
                       '(prompt v4-synth-4, transport, validator). Recorded in the freeze addendum '
                       'before this script ran.') % args.max_s,
         'calls': []}

    def save(name='G3_SYNTH_RECORD.json'):
        (out / name).write_text(json.dumps(R, indent=1, ensure_ascii=False), encoding='utf-8')

    http = Http(args.base)
    st, snap = http('/api/fabric-discover', {'device_id': 'fabric', 'providers': ['android']})
    tv = next((d for d in snap.get('devices', []) if d['category'] == CAT), None)
    if tv is None:
        print('KILL no %s in the live graph' % CAT); return 2
    st, sf = http('/api/v2/facts/signed?device=' + tv['key'])
    if st != 200:
        print('KILL signed facts unavailable'); return 2
    fp, kfacts = sf['device_fingerprint'], sf['facts']
    scope, scope_err = resolve_scope(snap.get('links'), tv['key'])
    if scope_err:
        print('KILL %s' % scope_err); return 2
    st, cat = http('/api/v2/primitives/catalog')
    desc = {d['id']: d for d in cat['primitives']}
    offer = [p for p in OFFER_T if desc.get(p, {}).get('manifest_allowed')]
    schemas = {p: {k: v.get('type', 'string') for k, v in desc[p]['input_schema'].get('properties', {}).items()} for p in offer}
    required = {p: list(desc[p]['input_schema'].get('required', [])) for p in offer}
    bundle = v4_evidence.resolve([{'device_id': fp, 'category': CAT, 'permission_scope': scope,
                                   'facts': [{'kind': f['name'], 'value': f.get('value'), 'source': f.get('source', 'unknown'),
                                              'observed_at': time.time()} for f in kfacts]}], [], offer, time.time())
    prompt = v4_synthesize.build_prompt(bundle, INTENT_T, offer, CAT)
    R['prompt_sha256'] = S.digest(prompt)
    R['prompt_version'] = v4_synthesize.PROMPT_VERSION
    R['target'] = {'device_fingerprint': fp, 'fact_count': len(kfacts), 'scope': scope}
    (out / 'prompt.txt').write_text(prompt, encoding='utf-8')

    if args.tier == 'glimmer':
        from src.ai.glimmer import GlimmerBroker
        broker = GlimmerBroker()
    else:
        from src.ai.local_meta import LocalMetaBroker
        broker = LocalMetaBroker()
    try:
        transport = transport_from_broker(broker)
    except ValueError as e:
        print('KILL local model not provisioned: %s' % e); return 2
    R['model'] = {'model_id': broker.model_id, 'endpoint': broker.endpoint, 'provisioning': 'broker-pinned'}
    save()

    for i in range(args.attempts):
        rec = {'attempt': i, 'prompt_sha256': R['prompt_sha256']}
        R['calls'].append(rec)
        t0 = time.monotonic()
        try:
            ok, body = transport(prompt, {'max_s': args.max_s})
        except Exception as e:
            rec.update(status='TRANSPORT_FAILED', failure_class=type(e).__name__,
                       elapsed_ms=round((time.monotonic() - t0) * 1000)); save(); continue
        rec.update(elapsed_ms=round((time.monotonic() - t0) * 1000), usage=body.get('usage'),
                   provisioning=body.get('provisioning'))
        if not ok:
            rec.update(status=body.get('status'), failure_class=body.get('failure_class')); save(); continue
        text = strip_fences(body['text'])
        rec['reply'] = text[:4000]; rec['status'] = 'RECORDED'; save()
        try:
            doc = json.loads(text)
        except (TypeError, ValueError):
            rec['validation'] = 'not JSON'; save(); continue
        if not isinstance(doc, dict):
            rec['validation'] = 'not an object'; save(); continue
        doc = dict(doc)
        doc['model_run_id'] = 'mr-' + secrets.token_hex(8)
        try:
            cand = v4_synthesize.validate_candidate(dict(doc), offer, bundle=bundle, schemas=schemas, required=required)
        except v4_synthesize.SynthError as e:
            rec['validation'] = 'SCHEMA_REJECTED: %s' % e; save(); continue
        cand['digest'] = S.digest({k: v for k, v in cand.items()})
        R['candidate'] = cand
        R['synthesis'] = {'attempt': i, 'max_s': args.max_s, 'prompt_version': v4_synthesize.PROMPT_VERSION}
        R['finished'] = datetime.now(timezone.utc).isoformat()
        R['status'] = 'CANDIDATE'
        save()
        print('CANDIDATE attempt=%d digest=%s prompt=%s...' % (i, cand['digest'][:16], R['prompt_sha256'][:16]))
        print('CHAIN', json.dumps(cand['primitive_chain']))
        return 0
    R['finished'] = datetime.now(timezone.utc).isoformat()
    R['status'] = 'NO_CANDIDATE'
    save()
    print('NO_CANDIDATE after %d attempts' % args.attempts)
    return 2


if __name__ == '__main__':
    sys.exit(main())
