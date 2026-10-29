"""Owner-authorized hardware run: multi-device workflow (TV + phone) through the kernel, isolated server :18780."""
import json, secrets, sys, time, urllib.request, urllib.error
sys.path.insert(0, r'C:\Users\TheBox\Desktop\Hackaton\OpenBridge-v4')
from src.substrate.kernel import manifest_hash
B = 'http://127.0.0.1:18780'
OUT = r'C:\Users\TheBox\Desktop\Hackaton\.xbuild\HW_WORKFLOW_TRANSCRIPT.json'
CSRF = json.loads(urllib.request.urlopen(B + '/api/session').read())['csrf_token']
T = {'kind': 'HW_MULTI_DEVICE_WORKFLOW', 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'log': []}
t0 = time.time()
def log(k, v):
    T['log'].append({'t': round(time.time() - t0, 2), k: v}); print(k, json.dumps(v, ensure_ascii=False)[:500], flush=True)
    json.dump(T, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
def req(path, body=None):
    h = {'Content-Type': 'application/json'}
    if body is not None: h.update({'X-CSRF-Token': CSRF, 'Origin': B})
    r = urllib.request.Request(B + path, json.dumps(body).encode() if body is not None else None, h)
    try:
        with urllib.request.urlopen(r, timeout=120) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')
st, snap = req('/api/fabric-discover', {'device_id': 'fabric', 'providers': ['android']})
tv = next(d for d in snap['devices'] if d['category'] == 'tv'); ph = next(d for d in snap['devices'] if d['category'] == 'phone')
def facts(key):
    st, sf = req('/api/v2/facts/signed?device=' + key); return sf['device_fingerprint'], sf['facts']
tv_fp, tv_f = facts(tv['key']); ph_fp, ph_f = facts(ph['key'])
cat = lambda fs: next(f for f in fs if f['name'] == 'category')['fact_id']
exp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 3600))
g4 = json.load(open(r'C:\Users\TheBox\Desktop\Hackaton\OpenBridge-v4\docs\evidence\v4\g3-smoke\attempt4_SUCCESS.json', encoding='utf-8'))
tv_m = dict(g4['manifest'], target={'category': 'tv', 'device_fingerprint': tv_fp}, facts_required=[cat(tv_f)], evidence_refs=[cat(tv_f)], expires_at=exp)
ph_m = {'manifest_version': 'obv4.1', 'capability_id': 'phone.screen_read', 'title': 'Read the phone screen state', 'origin': 'meta_generated',
        'model_run': g4['manifest']['model_run'], 'target': {'category': 'phone', 'device_fingerprint': ph_fp}, 'inputs': {},
        'steps': [{'step_id': 's0', 'primitive_id': 'state.screen', 'args': {}, 'on_uncertain': 'INCONCLUSIVE'}],
        'facts_required': [cat(ph_f)], 'max_fact_age_s': 600, 'evidence_refs': [cat(ph_f)], 'permissions_requested': ['read'], 'expires_at': exp}
log('manifests', {'tv': {'model_run': tv_m['model_run'], 'steps': [(s['primitive_id'], s['args']) for s in tv_m['steps']], 'note': 'Meta G3 steps, host-rebound'},
                  'phone': {'steps': [(s['primitive_id'], s['args']) for s in ph_m['steps']], 'note': 'FIXTURE read-only manifest (labelled meta_generated only because obv4.1 requires that origin; authored by Claude for this infrastructure test)'}})
def grant(m, f, uses):
    st, g = req('/api/v2/manifests/grant', {'manifest': m, 'facts': f, 'consent': True, 'max_uses': uses, 'ttl_s': 1800})
    log('node_grant', {'http': st, 'capability': m['capability_id'], 'err': g.get('error')}); return g['grant']
b = {manifest_hash(tv_m): {'manifest': tv_m, 'grant': grant(tv_m, tv_f, 2), 'facts': tv_f},
     manifest_hash(ph_m): {'manifest': ph_m, 'grant': grant(ph_m, ph_f, 1), 'facts': ph_f}}
def oracle():
    st, r = req('/api/v2/execute', {'primitive_id': 'device_action', 'device_key': tv['key'], 'params': {'action': 'audio_state'}, 'consent': True})
    return (r.get('result') or {}).get('muted'), (r.get('result') or {}).get('volume_index')
def wf(wid, nodes):
    return {'workflow_version': 'obv4.1-wf', 'workflow_id': wid, 'title': wid.replace('.', ' '), 'origin': 'meta_generated',
            'model_run': g4['manifest']['model_run'], 'nodes': nodes, 'max_parallel': 2}
w1 = wf('wf.tv-mute-and-phone-read', [{'node_id': 'tv_mute', 'manifest_hash': manifest_hash(tv_m), 'depends_on': []},
                                       {'node_id': 'phone_read', 'manifest_hash': manifest_hash(ph_m), 'depends_on': []}])
log('oracle_pre', oracle())
st, wg = req('/api/v2/workflows/grant', {'workflow': w1, 'bindings': b, 'consent': True}); log('wgrant1', {'http': st, 'err': wg.get('error')})
op1 = 'op-' + secrets.token_hex(16)
st, rec = req('/api/v2/workflows/run', {'workflow': w1, 'wgrant': wg['wgrant'], 'bindings': b, 'operation_id': op1})
log('run1', {'http': st, 'status': rec.get('status'), 'nodes': [(n['node_id'], n['status']) for n in rec.get('nodes', [])], 'err': rec.get('error')})
time.sleep(1.5); log('oracle_after_wf1', oracle())
st, rp = req('/api/v2/workflows/run', {'workflow': w1, 'wgrant': wg['wgrant'], 'bindings': b, 'operation_id': op1}); log('replay_wf1', {'http': st, 'code': rp.get('code')})
w2 = wf('wf.tv-restore', [{'node_id': 'tv_unmute', 'manifest_hash': manifest_hash(tv_m), 'depends_on': []}])
st, wg2 = req('/api/v2/workflows/grant', {'workflow': w2, 'bindings': {manifest_hash(tv_m): b[manifest_hash(tv_m)]}, 'consent': True}); log('wgrant2', {'http': st, 'err': wg2.get('error')})
st, rec2 = req('/api/v2/workflows/run', {'workflow': w2, 'wgrant': wg2['wgrant'], 'bindings': {manifest_hash(tv_m): b[manifest_hash(tv_m)]}, 'operation_id': 'op-' + secrets.token_hex(16)})
log('run2', {'http': st, 'status': rec2.get('status'), 'nodes': [(n['node_id'], n['status']) for n in rec2.get('nodes', [])]})
time.sleep(1.5); log('oracle_after_wf2', oracle())
st, rs = req('/api/v2/workflows/receipts'); T['workflow_receipts'] = rs.get('receipts')
st, mr = req('/api/v2/manifests/receipts'); T['manifest_receipts'] = mr.get('receipts', [])[-4:]
T['finished'] = time.strftime('%Y-%m-%dT%H:%M:%S%z'); json.dump(T, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False); print('DONE')
