"""G3 integration smoke (owner-supervised): Meta-generated manifest -> trusted kernel -> owner grant ->
physical invoke on the Android TV -> state.audio read-back -> restore -> revoke.

Labeled an INTEGRATION SMOKE (docs/forge/G3_RUN_PLAN.md rev 2): the TV-mute target is public, so this
proves the generation->grant->invoke->read-back machinery, not held-out novelty.

Spend: Muse Spark 1.3 via broker._reserve on the canonical ledger, explicit owner allowance + authz file,
at most 3 calls x $0.10 reservation. No retry after a transport failure. Model output is validated by the
unchanged Forge code (v4_synthesize.synthesize) and then compiled by the kernel; nothing the model says
is executed without the kernel and an owner grant.

Usage: python -m dev.run_g3_smoke --base http://127.0.0.1:18780 --observation-id ID --observed-at ISO
       --free-balance-usd N --authz-file PATH --out DIR
"""
import argparse
import hashlib
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTENT = 'Mute the TV audio, then confirm by reading the media stream state that it reports muted.'
MAX_CALLS = 3
MAX_COMPLETION_TOKENS = 4000
OFFER = ('input.key', 'state.audio', 'state.screen', 'state.read_setting', 'app.list', 'device.read_descriptor')


class Http:
    def __init__(self, base):
        self.base = base.rstrip('/')
        self.csrf = json.loads(urllib.request.urlopen(self.base + '/api/session').read())['csrf_token']

    def __call__(self, path, body=None):
        h = {'Content-Type': 'application/json'}
        if body is not None:
            h.update({'X-CSRF-Token': self.csrf, 'Origin': self.base})
        r = urllib.request.Request(self.base + path, json.dumps(body).encode() if body is not None else None, h)
        try:
            with urllib.request.urlopen(r, timeout=120) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')


def strip_fences(text):
    m = re.fullmatch(r'\s*```(?:json)?\s*(.*?)\s*```\s*', text or '', re.S)
    return m[1] if m else text


def main():
    ap = argparse.ArgumentParser()
    for a in ('--base', '--observation-id', '--observed-at', '--authz-file', '--out'):
        ap.add_argument(a, required=True)
    ap.add_argument('--free-balance-usd', type=float, required=True)
    ap.add_argument('--allowance-usd', type=float, default=0.80)
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    from dev.run_explain_eval import parse_observed_at, read_authz_file
    from src.ai.broker import CreditPermit, MetaTransport, RuntimeModelBroker, ModelBlocked, MODEL_ID, resolve_ledger
    from src.fabric.credential_vault import Vault
    from src.forge import v4_evidence, v4_synthesize, v4_substrate
    from src.forge.v4_metaclient import MetaClient, RulesPlanner

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    T = {'kind': 'G3_INTEGRATION_SMOKE', 'started': datetime.now(timezone.utc).isoformat(), 'intent': INTENT,
         'model': MODEL_ID, 'calls': [], 'steps': []}

    def save():
        (out / 'G3_SMOKE_TRANSCRIPT.json').write_text(json.dumps(T, indent=1, ensure_ascii=False), encoding='utf-8')

    def stop(status, **kw):
        T.update(status=status, **kw); T['finished'] = datetime.now(timezone.utc).isoformat(); save()
        print('STOP', status, json.dumps(kw)[:400]); return 0 if status == 'SUCCESS' else 2

    authz = read_authz_file(args.authz_file)
    observed = parse_observed_at(args.observed_at)
    T['budget'] = {'ledger': str(resolve_ledger(None)), 'allowance_usd': args.allowance_usd, 'authz': authz,
                   'observation_id': args.observation_id, 'observed_at': args.observed_at,
                   'free_balance_usd_lower_bound': args.free_balance_usd}
    http = Http(args.base)

    # 1. Live evidence: TV from discovery, signed kernel facts (never fixtures).
    st, snap = http('/api/fabric-discover', {'device_id': 'fabric', 'providers': ['android']})
    tv = next((d for d in snap.get('devices', []) if d['category'] == 'tv'), None)
    if tv is None:
        return stop('KILL', reason='no TV in the live graph')
    st, sf = http('/api/v2/facts/signed?device=' + tv['key'])
    if st != 200:
        return stop('KILL', reason='signed facts unavailable', http=st)
    fp, kfacts = sf['device_fingerprint'], sf['facts']
    T['target'] = {'device_fingerprint': fp, 'fact_count': len(kfacts)}
    scope = sorted({g for l in tv.get('links', []) for g in (l.get('grants') or [])} or {'observe', 'read', 'control'})
    st, cat = http('/api/v2/primitives/catalog')
    desc = {d['id']: d for d in cat['primitives']}
    offer = [p for p in OFFER if desc.get(p, {}).get('manifest_allowed')]
    schemas = {p: {k: v.get('type', 'string') for k, v in desc[p]['input_schema'].get('properties', {}).items()} for p in offer}
    bundle = v4_evidence.resolve([{'device_id': tv['key'], 'category': 'tv', 'permission_scope': scope,
                                   'facts': [{'kind': f['name'], 'value': f.get('value'), 'source': f.get('source', 'unknown'),
                                              'observed_at': time.time()} for f in kfacts]}], [], offer, time.time())
    ref_to_fact = {bf['evidence_ref']: kf for bf, kf in zip(bundle['devices'][0]['facts'], kfacts)}
    T['bundle_id'] = bundle['bundle_id']

    # 2. Baseline (fair ablation recorded, not a strawman claim): stocked deterministic path for the same task.
    T['baseline'] = {'rules_planner': RulesPlanner(offer).propose(bundle, INTENT),
                     'stocked_path': 'device_action key=mute exists in the prebuilt catalog (Executor); a stocked path CAN do this task'}

    # 3. Meta generation through the broker-guarded hosted call; validation is the unchanged Forge code.
    transport = MetaTransport(Vault().get('meta-api-key'))
    broker = RuntimeModelBroker(resolve_ledger(None), CreditPermit(args.observation_id, observed, args.free_balance_usd, 0.20),
                                transport, evaluation_allowance_usd=args.allowance_usd, evaluation_authz=authz)

    def hosted(prompt, budget):
        rec = {'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}
        T['calls'].append(rec)
        try:
            broker._reserve()
        except ModelBlocked as e:
            rec['status'] = 'BLOCKED'; rec['error'] = str(e); raise
        t0 = time.monotonic()
        resp = transport({'model': MODEL_ID, 'temperature': 0, 'max_completion_tokens': MAX_COMPLETION_TOKENS,
                          'messages': [{'role': 'user', 'content': prompt}]})
        usage = resp.get('usage') or {}
        rec.update(elapsed_ms=round((time.monotonic() - t0) * 1000), request_id=resp.get('id'), model=resp.get('model'),
                   finish_reason=((resp.get('choices') or [{}])[0].get('finish_reason')),
                   usage={k: usage.get(k) for k in ('prompt_tokens', 'completion_tokens')}, reserved_usd=0.10)
        if isinstance(usage.get('prompt_tokens'), int) and isinstance(usage.get('completion_tokens'), int):
            rec['estimated_cost_usd'] = (usage['prompt_tokens'] * 1.25 + usage['completion_tokens'] * 4.25) / 1_000_000
        if resp.get('model') != MODEL_ID:
            rec['status'] = 'MODEL_IDENTITY_MISMATCH'; raise RuntimeError('model identity mismatch')
        content = (((resp.get('choices') or [{}])[0].get('message') or {}).get('content')) or ''
        rec['reply'] = content[:4000]; rec['status'] = 'RECORDED'
        return True, {'text': strip_fences(content), 'usage': rec['usage']}

    client = MetaClient({'spark': hosted})
    cand, rejects = None, []
    for attempt in range(MAX_CALLS):
        ok, body = v4_synthesize.synthesize(client, 'spark', bundle, INTENT, offer, 'tv', schemas=schemas)
        save()
        if ok:
            cand = body; break
        rejects.append(body)
        if body.get('status') == 'MODEL_UNAVAILABLE' or (T['calls'] and T['calls'][-1].get('status') != 'RECORDED'):
            return stop('KILL', reason='model call failed or spend guard refused (no retry)', detail=body)
    T['synthesis_rejects'] = rejects
    if cand is None:
        return stop('KILL', reason='no valid candidate within the frozen call budget')
    c = cand['candidate']
    T['candidate'] = c; T['prompt_sha256'] = cand['prompt_sha256']

    # 4. Host binding (not model authority): opaque refs -> kernel fact ids; only verified facts are required.
    cited = [ref_to_fact[r] for r in c['evidence_refs'] if r in ref_to_fact]
    cat_fact = next(f for f in kfacts if f['name'] == 'category')
    required = sorted({f['fact_id'] for f in cited if f.get('verified')} | {cat_fact['fact_id']})
    extra_src = [r for r in c['evidence_refs'] if isinstance(r, str) and r.startswith('src:')]
    cand_k = dict(c, evidence_refs=sorted({f['fact_id'] for f in cited} | {cat_fact['fact_id']}))
    expires = datetime.fromtimestamp(time.time() + 3600, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    manifest = v4_substrate.to_manifest(cand_k, {'category': 'tv', 'device_fingerprint': fp},
                                        {'model': MODEL_ID, 'run_id': c['model_run_id'].replace('mr-', 'mr_')},
                                        'Mute the TV (Meta-generated)', sorted(set(c['required_grants'])), required,
                                        expires, inputs={}, evidence_extra=extra_src)
    T['manifest'] = manifest
    st, comp = http('/api/v2/manifests/compile', {'manifest': manifest, 'facts': kfacts})
    T['compile'] = {'http': st, **comp}; save()
    if st != 200:
        return stop('KILL', reason='kernel rejected the generated manifest', code=comp.get('code'))
    print('COMPILED', comp['manifest_hash'], 'permissions', comp['permissions'], 'dispatches', comp['dispatches'])
    print('PLAN', json.dumps([(s['step_id'], s['primitive_id'], s['args']) for s in manifest['steps']]))

    # 5. Oracle pre-read, owner grant (owner present, authorized in chat: two uses = act + restore), invoke, read-back.
    def oracle():
        st, r = http('/api/v2/execute', {'primitive_id': 'device_action', 'device_key': tv['key'],
                                         'params': {'action': 'audio_state'}, 'consent': True})
        res = r.get('result') or {}
        T['steps'].append({'oracle': res, 'tx': r.get('transaction_id'), 'state': r.get('state')}); return res
    pre = oracle()
    if not pre.get('readable'):
        return stop('KILL', reason='state.audio unreadable before the run (UNKNOWN, not success)')
    st, g = http('/api/v2/manifests/grant', {'manifest': manifest, 'facts': kfacts, 'consent': True, 'max_uses': 2, 'ttl_s': 900})
    T['grant'] = {'http': st, **{k: v for k, v in g.items() if k != 'grant'}, 'grant_id': (g.get('grant') or {}).get('grant_id')}
    if st != 200:
        return stop('KILL', reason='grant refused', code=g.get('code'))
    grant = g['grant']

    def invoke(tag):
        req = {'operation_id': 'op-' + secrets.token_hex(16), 'principal': 'owner', 'manifest_hash': comp['manifest_hash'],
               'grant_id': grant['grant_id'], 'inputs': {}, 'trace_id': 'g3' + tag}
        st, rc = http('/api/v2/manifests/invoke', {'manifest': manifest, 'grant': grant, 'facts': kfacts, 'request': req})
        T['steps'].append({'invoke': tag, 'http': st, 'receipt': rc}); save()
        return st, rc
    st1, r1 = invoke('act')
    time.sleep(1.5)
    mid = oracle()
    st2, r2 = invoke('restore')
    time.sleep(1.5)
    post = oracle()
    st, rv = http('/api/v2/manifests/revoke', {'grant_id': grant['grant_id']})
    T['revoke'] = {'http': st, **rv}
    st, rv2 = invoke('after_revoke_must_refuse')
    st, recs = http('/api/v2/manifests/receipts')
    T['kernel_receipts'] = recs.get('receipts', [])[-3:]
    ok = (st1 == 200 and r1.get('status') in ('VERIFIED', 'EXECUTED') and mid.get('muted') is True
          and st2 == 200 and post == pre and T['steps'][-1]['http'] != 200)
    return stop('SUCCESS' if ok else 'FAILED_ORACLE', pre=pre, after_act=mid, after_restore=post,
                act_status=r1.get('status'), restore_status=r2.get('status'),
                after_revoke=T['steps'][-1].get('receipt', {}).get('code'))


if __name__ == '__main__':
    sys.exit(main())
