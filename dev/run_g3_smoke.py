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


def resolve_scope(links, tv_key):
    """Live grant scope from the SAME discover response (snapshot-level links,
    filtered by child key). (None, reason) when unverifiable: the runner must
    KILL, never invent a default scope (Sol HOLD). Device keys rotate between
    discovers, so links and key must come from one response."""
    grants = sorted({g for l in (links or []) if isinstance(l, dict) and l.get('child') == tv_key
                     for g in (l.get('grants') or [])})
    if not grants or not all(isinstance(g, str) and g for g in grants):
        return None, 'grant scope unverifiable from live links (refusing invented scope)'
    return grants, None


def success_predicate(pre, mid, post, st1, r1, st2, after_revoke_http):
    """SUCCESS requires a muted=false->true TRANSITION plus full restore: an
    already-muted oracle scores no success (Sol HOLD: no-op false-success)."""
    reasons = []
    if not isinstance(pre, dict) or pre.get('muted') is not False:
        reasons.append('pre must show muted=false (already-muted scores no success)')
    if not isinstance(mid, dict) or mid.get('muted') is not True:
        reasons.append('post-act oracle must show muted=true')
    if post != pre:
        reasons.append('post-restore oracle must equal the pre-run oracle')
    if not (st1 == 200 and (r1 or {}).get('status') in ('VERIFIED', 'EXECUTED')):
        reasons.append('act invoke must be VERIFIED/EXECUTED')
    if st2 != 200:
        reasons.append('restore invoke must succeed')
    if after_revoke_http == 200:
        reasons.append('invoke after revoke must be refused')
    return (not reasons), reasons


def effect_binding(steps, catalog):
    """Owner consent covers ONE effect: a single input.key{key: mute}. Every other step must be a
    READ-class primitive. Anything else is KILLed before a grant (generic compiler validity is not
    consent for an arbitrary key chain)."""
    effects = [s for s in steps if (catalog.get(s.get('primitive_id')) or {}).get('side_effect_class') != 'READ']
    if len(effects) != 1:
        return 'plan must contain exactly one effect step (got %d)' % len(effects)
    e = effects[0]
    if e.get('primitive_id') != 'input.key' or e.get('args') != {'key': 'mute'}:
        return 'the only allowed effect is input.key {"key": "mute"}'
    return None


def act_restore_sequence(invoke, oracle, revoke, sleep=time.sleep):
    """Act -> oracle -> conditional restore -> oracle, revoke always attempted.

    Restore runs ONLY if act executed (no blind restore after an unknown act);
    revoke runs in a finally and its own crash is recorded, never raised
    (Sol HOLD). Returns (st1, r1, mid, st2, r2, post, revoke_record).
    """
    st1 = r1 = mid = st2 = r2 = post = None
    try:
        st1, r1 = invoke('act')
        sleep(1.5)
        mid = oracle()
        # Restore only after an OBSERVED transition: an executed act whose effect was not seen
        # is reconciled by the owner, never by a second blind toggle.
        if st1 == 200 and (r1 or {}).get('status') in ('VERIFIED', 'EXECUTED') and (mid or {}).get('muted') is True:
            st2, r2 = invoke('restore')
            sleep(1.5)
            post = oracle()
    finally:
        try:
            st, rv = revoke()
        except Exception as e:
            st, rv = -1, {'error': '%s: %s' % (type(e).__name__, str(e)[:200])}
        record = {'http': st, **(rv if isinstance(rv, dict) else {})}
    return st1, r1, mid, st2, r2, post, record


def main():
    ap = argparse.ArgumentParser()
    for a in ('--base', '--observation-id', '--observed-at', '--authz-file', '--out'):
        ap.add_argument(a, required=True)
    ap.add_argument('--free-balance-usd', type=float, required=True)
    ap.add_argument('--allowance-usd', type=float, default=0.80)
    ap.add_argument('--replay-from', default=None,
                    help='reuse the validated Meta candidate recorded in a prior transcript (no new model call); re-validated against live evidence')
    ap.add_argument('--max-completion-tokens', type=int, default=MAX_COMPLETION_TOKENS)
    ap.add_argument('--reasoning-effort', choices=['minimal', 'low', 'medium', 'high'], default=None,
                    help='Muse Spark reasoning_effort (cannot be disabled); recorded in the transcript')
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    from dev.run_explain_eval import parse_observed_at, read_authz_file
    from src.ai.broker import CreditPermit, MetaTransport, RuntimeModelBroker, ModelBlocked, MODEL_ID, resolve_ledger
    from src.fabric.credential_vault import Vault
    from src.forge import v4_evidence, v4_synthesize, v4_substrate
    from src.forge.v4_metaclient import MetaClient, RulesPlanner

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    T = {'kind': 'G3_INTEGRATION_SMOKE', 'started': datetime.now(timezone.utc).isoformat(), 'intent': INTENT,
         'model': MODEL_ID, 'reasoning_effort': args.reasoning_effort, 'max_completion_tokens': args.max_completion_tokens, 'calls': [], 'steps': []}

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
    scope, scope_err = resolve_scope(snap.get('links'), tv['key'])
    if scope_err:
        return stop('KILL', reason=scope_err)
    T['scope'] = {'grants': scope, 'source': 'live-snapshot-links'}
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
        payload = {'model': MODEL_ID, 'temperature': 0, 'max_completion_tokens': args.max_completion_tokens,
                   'messages': [{'role': 'user', 'content': prompt}]}
        if args.reasoning_effort:
            payload['reasoning_effort'] = args.reasoning_effort
        resp = transport(payload)
        usage = resp.get('usage') or {}
        rec.update(elapsed_ms=round((time.monotonic() - t0) * 1000), request_id=resp.get('id'), model=resp.get('model'),
                   finish_reason=((resp.get('choices') or [{}])[0].get('finish_reason')),
                   usage={k: usage.get(k) for k in ('prompt_tokens', 'completion_tokens')}, reserved_usd=0.10,
                   reasoning_tokens=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens'))
        if isinstance(usage.get('prompt_tokens'), int) and isinstance(usage.get('completion_tokens'), int):
            rec['estimated_cost_usd'] = (usage['prompt_tokens'] * 1.25 + usage['completion_tokens'] * 4.25) / 1_000_000
        if resp.get('model') != MODEL_ID:
            rec['status'] = 'MODEL_IDENTITY_MISMATCH'; raise RuntimeError('model identity mismatch')
        content = (((resp.get('choices') or [{}])[0].get('message') or {}).get('content')) or ''
        rec['reply'] = content[:4000]; rec['status'] = 'RECORDED'
        return True, {'text': strip_fences(content), 'usage': rec['usage']}

    client = MetaClient({'spark': hosted})
    cand, rejects = None, []
    if args.replay_from:
        prior = json.loads(Path(args.replay_from).read_text(encoding='utf-8'))
        pc = prior.get('candidate')
        if not isinstance(pc, dict):
            return stop('KILL', reason='replay transcript has no validated candidate')
        doc = {k: v for k, v in pc.items() if k != 'digest'}
        try:
            v4_synthesize.validate_candidate(dict(doc), offer, bundle=bundle, schemas=schemas)
        except v4_synthesize.SynthError as e:
            return stop('KILL', reason='replayed candidate no longer binds to live evidence: %s' % e)
        cand = {'candidate': pc, 'prompt_sha256': prior.get('prompt_sha256')}
        T['replayed_from'] = {'path': Path(args.replay_from).name, 'candidate_digest': pc.get('digest'),
                              'model_calls': prior.get('calls'), 'note': 'no new model call; candidate generated by Muse Spark in the prior run'}
    for attempt in range(0 if cand else MAX_CALLS):
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
    bad = effect_binding(manifest['steps'], desc)
    if bad:
        return stop('KILL', reason='effect binding refused before grant: ' + bad)
    pre = oracle()
    if not pre.get('readable'):
        return stop('KILL', reason='state.audio unreadable before the run (UNKNOWN, not success)')
    if pre.get('muted') is not False:
        return stop('KILL', reason='TV already muted before the run: nothing to prove, no toggle sent')
    st, g = http('/api/v2/manifests/grant', {'manifest': manifest, 'facts': kfacts, 'consent': True, 'max_uses': 2, 'ttl_s': 900})
    T['grant'] = {'http': st, **{k: v for k, v in g.items() if k != 'grant'}, 'grant_id': (g.get('grant') or {}).get('grant_id')}
    if st != 200:
        return stop('KILL', reason='grant refused', code=g.get('code'))
    grant = g['grant']

    def invoke(tag):
        req = {'operation_id': 'op-' + secrets.token_hex(16), 'principal': 'owner', 'manifest_hash': comp['manifest_hash'],
               'grant_id': grant['grant_id'], 'inputs': {}, 'trace_id': ('g3-' + tag)[:40] + '-' + secrets.token_hex(3)}
        st, rc = http('/api/v2/manifests/invoke', {'manifest': manifest, 'grant': grant, 'facts': kfacts, 'request': req})
        T['steps'].append({'invoke': tag, 'http': st, 'receipt': rc}); save()
        return st, rc
    def revoke():
        # Stash the attempt in the transcript: if act/oracle crashes, the finally
        # still revokes but its record would otherwise be lost with the exception.
        try:
            st, rv = http('/api/v2/manifests/revoke', {'grant_id': grant['grant_id']})
        except Exception as e:
            T['revoke_attempt'] = {'http': -1,
                                   'error': '%s: %s' % (type(e).__name__, str(e)[:200])}
            save()
            raise
        T['revoke_attempt'] = {'http': st, **rv}
        save()
        return st, rv
    try:
        st1, r1, mid, st2, r2, post, record = act_restore_sequence(
            invoke, oracle, revoke, sleep=time.sleep)
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
    ok, predicate = success_predicate(pre, mid, post, st1, r1, st2, T['steps'][-1]['http'])
    return stop('SUCCESS' if ok else 'FAILED_ORACLE', pre=pre, after_act=mid, after_restore=post,
                act_status=r1.get('status'), restore_status=(r2 or {}).get('status'),
                predicate=predicate,
                after_revoke=T['steps'][-1].get('receipt', {}).get('code'))


if __name__ == '__main__':
    sys.exit(main())
