"""G3 sealed task on a LOCAL Meta model ($0): sealed spec -> Meta-generated manifest ->
trusted kernel -> owner grant -> physical invoke on the sealed target -> oracle
read-back -> restore -> revoke.

Same frozen procedure as dev/run_g3_smoke.py (evidence, bundle, RulesPlanner
baseline, effect binding, compile, grant, act/restore/revoke, predicate), except
the generator is a digest-provisioned LOCAL Meta model (Muse Glimmer 30B or
Llama 3.2 3B) bound through transport_from_broker: no hosted spend, no ledger,
no authz file. The task spec is REQUIRED and its sha256 must match the value
Sol committed in a PR before the run; the runner refuses anything else, so the
task cannot be chosen or edited after results.

Physical authorization: this reversible task (oracle pre-read, single effect,
deterministic restore to the pre-value, revoke) runs under the owner's standing
written autonomy orders for reversible lab tests. Recorded in the transcript;
no fresh per-run authz file exists for $0 local runs.

Usage: python -m dev.run_g3_local --base http://127.0.0.1:18780 --out DIR
       --task-spec PATH --task-sha256 HEX [--tier glimmer|llama]
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_CALLS = 3


def main():
    ap = argparse.ArgumentParser()
    for a in ('--base', '--out', '--task-spec', '--task-sha256'):
        ap.add_argument(a, required=True)
    ap.add_argument('--tier', choices=['glimmer', 'llama'], default='glimmer')
    ap.add_argument('--replay-from', default=None,
                    help='reuse the validated Meta candidate recorded in an extended-budget synthesis record (no new model call); re-validated against live evidence')
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    from dev.run_g3_smoke import Http, act_restore_sequence, resolve_scope, strip_fences
    from src.forge import v4_evidence, v4_synthesize, v4_substrate
    from src.forge.v4_metaclient import MetaClient, RulesPlanner, transport_from_broker

    from dev import g3_task
    try:
        spec = g3_task.load(args.task_spec, args.task_sha256)
    except (g3_task.SpecError, OSError, ValueError) as e:
        print('TASK_SPEC: %s' % e); return 2
    INTENT_T, OFFER_T, CAT = spec['intent'], tuple(spec['offer']), spec['target_category']
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    T = {'kind': 'G3_SEALED_TASK', 'task_id': spec['task_id'],
         'task_sha256': g3_task.spec_sha256(spec), 'started': datetime.now(timezone.utc).isoformat(),
         'intent': INTENT_T, 'tier': args.tier, 'spend_usd': 0,
         'authorization': ('standing owner autonomy orders for reversible lab tests '
                           '(chat); oracle pre-read + deterministic restore + revoke; '
                           'no fresh per-run authz file for $0 local runs'),
         'calls': [], 'steps': []}

    def save():
        (out / 'G3_SEALED_TRANSCRIPT.json').write_text(json.dumps(T, indent=1, ensure_ascii=False), encoding='utf-8')

    def stop(status, **kw):
        T.update(status=status, **kw); T['finished'] = datetime.now(timezone.utc).isoformat(); save()
        print('STOP', status, json.dumps(kw)[:400]); return 0 if status == 'SUCCESS' else 2

    http = Http(args.base)

    # 1. Live evidence: sealed target from discovery, signed kernel facts (never fixtures).
    st, snap = http('/api/fabric-discover', {'device_id': 'fabric', 'providers': ['android']})
    tv = next((d for d in snap.get('devices', []) if d['category'] == CAT), None)
    if tv is None:
        return stop('KILL', reason='no %s in the live graph' % CAT)
    st, sf = http('/api/v2/facts/signed?device=' + tv['key'])
    if st != 200:
        return stop('KILL', reason='signed facts unavailable', http=st)
    fp, kfacts = sf['device_fingerprint'], sf['facts']
    T['target'] = {'device_fingerprint': fp, 'fact_count': len(kfacts)}
    scope, scope_err = resolve_scope(snap.get('links'), tv['key'])
    if scope_err:
        return stop('KILL', reason=scope_err)
    T['scope'] = {'grants': scope, 'source': 'live-snapshot-links'}
    st, cat = http('/api/v2/primitives/catalog')
    desc = {d['id']: d for d in cat['primitives']}
    offer = [p for p in OFFER_T if desc.get(p, {}).get('manifest_allowed')]
    schemas = {p: {k: v.get('type', 'string') for k, v in desc[p]['input_schema'].get('properties', {}).items()} for p in offer}
    required = {p: list(desc[p]['input_schema'].get('required', [])) for p in offer}
    bundle = v4_evidence.resolve([{'device_id': fp, 'category': CAT, 'permission_scope': scope,
                                   'facts': [{'kind': f['name'], 'value': f.get('value'), 'source': f.get('source', 'unknown'),
                                              'observed_at': time.time()} for f in kfacts]}], [], offer, time.time())
    ref_to_fact = {bf['evidence_ref']: kf for bf, kf in zip(bundle['devices'][0]['facts'], kfacts)}
    T['bundle_id'] = bundle['bundle_id']

    # 2. Baselines (fair ablation recorded, not a strawman claim).
    T['baseline'] = {'rules_planner': RulesPlanner(offer).propose(bundle, INTENT_T),
                     'stocked_path': ('no prebuilt skill covers %s; the generic Executor primitive exists (the model must compose it)' % spec['task_id'])}

    # 3. Local Meta generation; validation is the unchanged Forge code.
    if args.tier == 'glimmer':
        from src.ai.glimmer import GlimmerBroker
        broker = GlimmerBroker()
    else:
        from src.ai.local_meta import LocalMetaBroker
        broker = LocalMetaBroker()
    try:
        transport = transport_from_broker(broker)
    except ValueError as e:
        return stop('KILL', reason='local model not provisioned: %s' % e)
    T['model'] = {'model_id': broker.model_id, 'endpoint': broker.endpoint, 'provisioning': 'broker-pinned'}
    save()

    def local(prompt, budget):
        rec = {'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}
        T['calls'].append(rec)
        ok, body = transport(prompt, budget)
        rec.update(provisioning=body.get('provisioning'), usage=body.get('usage'))
        if not ok:
            rec['status'] = body.get('status'); rec['failure_class'] = body.get('failure_class')
            raise RuntimeError('local transport failed: %s' % body.get('failure_class'))
        rec['reply'] = body['text'][:4000]; rec['status'] = 'RECORDED'; save()
        return True, {'text': strip_fences(body['text']), 'usage': body.get('usage')}

    client = MetaClient({args.tier: local})
    cand, rejects = None, []
    if args.replay_from:
        prior = json.loads(Path(args.replay_from).read_text(encoding='utf-8'))
        pc = prior.get('candidate')
        if not isinstance(pc, dict):
            return stop('KILL', reason='replay record has no validated candidate')
        doc = {k: v for k, v in pc.items() if k != 'digest'}
        try:
            v4_synthesize.validate_candidate(dict(doc), offer, bundle=bundle, schemas=schemas, required=required)
        except v4_synthesize.SynthError as e:
            return stop('KILL', reason='replayed candidate no longer binds to live evidence: %s' % e)
        cand = {'candidate': pc, 'prompt_sha256': prior.get('prompt_sha256')}
        T['replayed_from'] = {'path': Path(args.replay_from).name, 'candidate_digest': pc.get('digest'),
                              'model': prior.get('model'), 'synthesis': prior.get('synthesis'),
                              'note': 'no new model call; candidate from the extended-budget synthesis record'}
    for _ in range(0 if cand else MAX_CALLS):
        try:
            ok, body = v4_synthesize.synthesize(client, args.tier, bundle, INTENT_T, offer, CAT,
                                                schemas=schemas, required=required)
        except RuntimeError as e:
            return stop('KILL', reason='model call failed (no retry)', detail=str(e)[:200])
        save()
        if ok:
            cand = body; break
        rejects.append(body)
        if body.get('status') == 'MODEL_UNAVAILABLE' or (T['calls'] and T['calls'][-1].get('status') != 'RECORDED'):
            return stop('KILL', reason='model call failed or transport refused (no retry)', detail=body)
    T['synthesis_rejects'] = rejects
    if cand is None:
        return stop('KILL', reason='no valid candidate within the frozen call budget')
    c = cand['candidate']
    T['candidate'] = c; T['prompt_sha256'] = cand['prompt_sha256']
    T['prompt_version'] = v4_synthesize.PROMPT_VERSION

    # 4. Host binding (not model authority): opaque refs -> kernel fact ids; only verified facts are required.
    cited = [ref_to_fact[r] for r in c['evidence_refs'] if r in ref_to_fact]
    cat_fact = next(f for f in kfacts if f['name'] == 'category')
    required = sorted({f['fact_id'] for f in cited if f.get('verified')} | {cat_fact['fact_id']})
    extra_src = [r for r in c['evidence_refs'] if isinstance(r, str) and r.startswith('src:')]
    cand_k = dict(c, evidence_refs=sorted({f['fact_id'] for f in cited} | {cat_fact['fact_id']}))
    expires = datetime.fromtimestamp(time.time() + 3600, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    manifest = v4_substrate.to_manifest(cand_k, {'category': CAT, 'device_fingerprint': fp},
                                        {'model': broker.model_id, 'run_id': c['model_run_id'].replace('mr-', 'mr_')},
                                        ('G3 task ' + spec['task_id'])[:80], sorted(set(c['required_grants'])), required,
                                        expires, inputs={}, evidence_extra=extra_src)
    T['manifest'] = manifest
    st, comp = http('/api/v2/manifests/compile', {'manifest': manifest, 'facts': kfacts})
    T['compile'] = {'http': st, **comp}; save()
    if st != 200:
        return stop('KILL', reason='kernel rejected the generated manifest', code=comp.get('code'))
    print('COMPILED', comp['manifest_hash'], 'permissions', comp['permissions'], 'dispatches', comp['dispatches'])
    print('PLAN', json.dumps([(s['step_id'], s['primitive_id'], s['args']) for s in manifest['steps']]))

    # 5. Oracle pre-read, grant (two uses = act + restore), invoke, read-back.
    def oracle():
        st, r = http('/api/v2/execute', {'primitive_id': 'device_action', 'device_key': tv['key'],
                                         'params': dict({'action': spec['oracle']['action']}, **({'args': spec['oracle']['args']} if spec['oracle']['args'] else {})), 'consent': True})
        res = r.get('result') or {}
        T['steps'].append({'oracle': res, 'tx': r.get('transaction_id'), 'state': r.get('state')}); return res
    bad = g3_task.effect_binding(manifest['steps'], desc, spec)
    if bad:
        return stop('KILL', reason='effect binding refused before grant: ' + bad)
    pre = oracle()
    if not g3_task.readable(pre, spec):
        return stop('KILL', reason='oracle unreadable before the run (UNKNOWN, not success)')
    if g3_task.observed(pre, spec):
        return stop('KILL', reason='oracle already shows the expected value: nothing to prove, no effect sent')
    st, g = http('/api/v2/manifests/grant', {'manifest': manifest, 'facts': kfacts, 'consent': True, 'max_uses': 2 if spec['restore']['mode'] == 'reinvoke' else 1, 'ttl_s': 900})
    T['grant'] = {'http': st, **{k: v for k, v in g.items() if k != 'grant'}, 'grant_id': (g.get('grant') or {}).get('grant_id')}
    if st != 200:
        return stop('KILL', reason='grant refused', code=g.get('code'))
    grant = g['grant']

    def invoke(tag):
        import secrets as _s
        req = {'operation_id': 'op-' + _s.token_hex(16), 'principal': 'owner', 'manifest_hash': comp['manifest_hash'],
               'grant_id': grant['grant_id'], 'inputs': {}, 'trace_id': ('g3-' + tag)[:40] + '-' + _s.token_hex(3)}
        st, rc = http('/api/v2/manifests/invoke', {'manifest': manifest, 'grant': grant, 'facts': kfacts, 'request': req})
        T['steps'].append({'invoke': tag, 'http': st, 'receipt': rc}); save()
        return st, rc
    def revoke():
        try:
            st, rv = http('/api/v2/manifests/revoke', {'grant_id': grant['grant_id']})
        except Exception as e:
            T['revoke_attempt'] = {'http': -1, 'error': '%s: %s' % (type(e).__name__, str(e)[:200])}
            save()
            raise
        T['revoke_attempt'] = {'http': st, **rv}
        save()
        return st, rv
    def owner_restore():
        body = g3_task.restore_args(spec, pre)
        st, r = http('/api/v2/execute', {'primitive_id': 'device_action', 'device_key': tv['key'],
                                         'params': body, 'consent': True})
        T['steps'].append({'owner_restore': body, 'http': st, 'state': r.get('state'), 'tx': r.get('transaction_id')}); save()
        return st, r
    try:
        st1, r1, mid, st2, r2, post, record = act_restore_sequence(
            invoke, oracle, revoke, sleep=time.sleep, observed=lambda m: g3_task.observed(m, spec),
            restore=None if spec['restore']['mode'] == 'reinvoke' else owner_restore)
    except Exception as e:
        return stop('KILL', reason='act/restore sequence crashed (revoke was attempted)',
                    error='%s: %s' % (type(e).__name__, str(e)[:200]))
    T['revoke'] = record
    save()
    if not (st1 == 200 and (r1 or {}).get('status') in ('VERIFIED', 'EXECUTED')):
        return stop('KILL', reason='act did not execute; restore skipped (no blind restore)',
                    pre=pre, after_act=mid, act_status=(r1 or {}).get('status'))
    st, rv2 = invoke('after_revoke_must_refuse')
    st, recs = http('/api/v2/manifests/receipts')
    T['kernel_receipts'] = recs.get('receipts', [])[-3:]
    act_ok = st1 == 200 and (r1 or {}).get('status') in ('VERIFIED', 'EXECUTED')
    restore_ok = st2 == 200 and (r2 or {}).get('state', (r2 or {}).get('status')) not in ('BLOCKED', 'FAILED')
    ok, predicate = g3_task.predicate(spec, pre, mid, post, act_ok, restore_ok, T['steps'][-1]['http'])
    return stop('SUCCESS' if ok else 'FAILED_ORACLE', pre=pre, after_act=mid, after_restore=post,
                act_status=r1.get('status'), restore_status=(r2 or {}).get('status'),
                predicate=predicate,
                after_revoke=T['steps'][-1].get('receipt', {}).get('code'))


if __name__ == '__main__':
    sys.exit(main())
