"""Owner-attended: state.audio read-back + mute toggle (twice, restores) on the Android TV via the real Executor."""
import json, time, urllib.request, urllib.error
B = 'http://127.0.0.1:18780'
CSRF = json.loads(urllib.request.urlopen(B + '/api/session').read())['csrf_token']
def req(path, body=None):
    h = {'Content-Type': 'application/json'}
    if body is not None: h.update({'X-CSRF-Token': CSRF, 'Origin': B})
    r = urllib.request.Request(B + path, json.dumps(body).encode() if body is not None else None, h)
    try:
        with urllib.request.urlopen(r, timeout=90) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')
T = {'started': time.time(), 'steps': []}
st, snap = req('/api/fabric-discover', {'device_id': 'fabric', 'providers': ['android']})
tv = next(d for d in snap['devices'] if d['category'] == 'tv'); T['tv'] = tv['key']
def ex(action, args=None):
    p = {'action': action}
    if args: p['args'] = args
    st, r = req('/api/v2/execute', {'primitive_id': 'device_action', 'device_key': tv['key'], 'params': p, 'consent': True})
    rec = {'action': action, 'args': args, 'http': st, 'state': r.get('state'), 'tx': r.get('transaction_id'),
           'result': (r.get('result') or r.get('output') or {}), 'errors': r.get('errors')}
    T['steps'].append(rec); print(json.dumps(rec)[:400]); return r
ex('audio_state'); ex('key', {'key': 'mute'}); time.sleep(1.5); ex('audio_state')
ex('key', {'key': 'mute'}); time.sleep(1.5); ex('audio_state')
T['finished'] = time.time()
json.dump(T, open(r'C:\Users\TheBox\Desktop\Hackaton\.xbuild\HW_STATE_AUDIO_TRANSCRIPT.json', 'w'), indent=1)
