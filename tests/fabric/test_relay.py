import time
import unittest
from src.fabric import relay as R
from src.fabric.registry import Registry
from src.fabric.discovery import ingest_ble

KEY=R.derive_key('123456','rn','pn')


class FakeRelay:
    """Reference relay behaviour: verifies commands, returns signed bounded observations."""
    def __init__(s,observations=None,fail=None,malformed=False):s.seen={};s.obs=observations or [];s.fail=fail;s.ops=[];s.malformed=malformed
    def __call__(s,relay,message):
        msg=R.verify(KEY,message,s.seen);s.ops.append(msg['op'])
        if s.fail:raise s.fail
        params={'observations':'oops'} if s.malformed else {'observations':s.obs}
        now=int(time.time());reply={'protocol':R.PROTOCOL,'relay_id':msg['relay_id'],'op':'reply','params':params,'nonce':'r'+msg['nonce'],'issued_at':now,'expires_at':now+30}
        return {**reply,'mac':R.sign(KEY,reply)}


def manager(transport,perm=True,owner=True,caps=('ble_scan',),battery=False,rid='tv'):
    m=R.RelayManager(transport);m.enroll(rid,KEY,'dev-tv',{'capabilities':list(caps),'permissions':{'BLUETOOTH_SCAN':perm,'owner_enabled':owner},'battery_powered':battery});return m


class RelayTests(unittest.TestCase):
    def test_pairing_code_and_signed_bounded_commands(self):
        with self.assertRaises(R.RelayError):R.derive_key('12ab56','a','b')
        with self.assertRaises(R.RelayError):R.command(KEY,'tv','start_discovery',{'radio':'wifi'})
        with self.assertRaises(R.RelayError):R.command(KEY,'tv','start_discovery',{'radio':'ble','seconds':120})
        with self.assertRaises(R.RelayError):R.command(KEY,'tv','shell',{})

    def test_replay_expiry_and_tamper_rejected(self):
        c=R.command(KEY,'tv','get_status');seen={};R.verify(KEY,c,seen)
        with self.assertRaises(R.RelayError):R.verify(KEY,c,seen)
        with self.assertRaises(R.RelayError):R.verify(KEY,R.command(KEY,'tv','get_status',now=time.time()-100),None)
        t=dict(R.command(KEY,'tv','get_status'));t['op']='revoke_access'
        with self.assertRaises(R.RelayError):R.verify(KEY,t,None)
        with self.assertRaises(R.RelayError):R.verify(R.derive_key('000000','rn','pn'),R.command(KEY,'tv','get_status'),None)

    def test_scan_through_relay_adds_indirect_observe_only_device(self):
        obs=[{'address':'C1:22:33:44:55:66','name':'Thermo','rssi':-71,'company_ids':[76],'address_kind':'static_random'}]
        fake=FakeRelay(obs);rid,found=manager(fake).scan(5)
        self.assertEqual(fake.ops,['start_discovery','stop_discovery']);self.assertEqual(found[0]['name'],'Thermo')
        r=Registry();tv=r.upsert([],category='tv',label='TV')
        ingest_ble(r,{'devices':found},b's',observer=tv,source='RELAY:'+rid)
        link=[l for l in r.snapshot()['links'] if l['transport']=='BLE'][0]
        self.assertEqual((link['parent'],link['grants'],link['source']),(tv,['observe'],'RELAY:tv'))

    def test_relay_without_permission_or_owner_consent_is_never_chosen(self):
        for m in (manager(FakeRelay(),perm=False),manager(FakeRelay(),owner=False),manager(FakeRelay(),caps=())):
            with self.assertRaises(R.RelayError):m.scan()

    def test_relay_disappears_marks_offline_after_three_failures(self):
        m=manager(FakeRelay(fail=TimeoutError()))
        for _ in range(3):
            with self.assertRaises(R.RelayError):m.scan()
        self.assertFalse(m.relays['tv']['online']);self.assertEqual(m.eligible('ble_scan'),[])

    def test_malformed_reply_and_busy_relay(self):
        with self.assertRaises(R.RelayError):manager(FakeRelay(malformed=True)).scan()
        m=manager(FakeRelay());m.relays['tv']['busy']=True
        with self.assertRaises(R.RelayError):m.scan()

    def test_mains_powered_relay_preferred_and_revoke_forgets_key(self):
        m=manager(FakeRelay(),battery=True,rid='phone');m.enroll('tv',KEY,'dev-tv',{'capabilities':['ble_scan'],'permissions':{'BLUETOOTH_SCAN':True,'owner_enabled':True}})
        self.assertEqual(m.eligible('ble_scan'),['tv','phone'])
        m.revoke('tv');self.assertNotIn('tv',m.relays)

    def test_bounds_on_observations(self):
        with self.assertRaises(R.RelayError):R.validate_report({'observations':[{'address':'x'}]*201})
        clean=R.validate_report({'observations':[{'address':'A','rssi':999,'company_ids':[-1,70000,6],'name':'n'*500}]})
        self.assertEqual((clean[0]['rssi'],clean[0]['company_ids'],len(clean[0]['name'])),(None,[6],60))


class CapabilityAwareEligibilityTests(unittest.TestCase):
    """E1-A2: eligibility is per-capability; ble_scan behavior is unchanged."""

    def test_non_ble_capabilities_route_with_owner_consent(self):
        m=manager(FakeRelay(),caps=('remote_controls',),rid='phone')
        self.assertEqual(m.eligible('remote_controls'),['phone'])
        self.assertEqual(m.eligible('ble_scan'),[])
        m2=manager(FakeRelay(),caps=('command_submit',),rid='phone')
        self.assertEqual(m2.eligible('command_submit'),['phone'])

    def test_owner_consent_gates_every_capability(self):
        m=manager(FakeRelay(),owner=False,caps=('remote_controls','command_submit'))
        self.assertEqual(m.eligible('remote_controls'),[])
        self.assertEqual(m.eligible('command_submit'),[])

    def test_unknown_capability_yields_no_route(self):
        m=manager(FakeRelay())
        self.assertEqual(m.eligible('shell_exec'),[])
        self.assertEqual(m.eligible(''),[])

    def test_ble_scan_still_requires_bluetooth_permission(self):
        self.assertEqual(manager(FakeRelay(),perm=False).eligible('ble_scan'),[])
        self.assertEqual(manager(FakeRelay(),owner=False).eligible('ble_scan'),[])
        self.assertEqual(manager(FakeRelay()).eligible('ble_scan'),['tv'])


class TransportTests(unittest.TestCase):
    def test_http_transport_scope(self):
        R.http_transport('http://127.0.0.1:47800');R.http_transport('http://192.168.1.50:47800')
        for bad in ('http://8.8.8.8:47800','http://evil.example:47800','http://224.0.0.1:1'):
            with self.assertRaises(R.RelayError):R.http_transport(bad)

    def test_pairing_with_reference_relay(self):
        state={}
        def send(_r,msg):
            if msg.get('op')=='pair_request':
                state['pc']=msg['pc_nonce'];return {'protocol':R.PROTOCOL,'relay_id':'phone','relay_nonce':'ab'*8}
            k=R.derive_key('424242','ab'*8,state['pc']);R.verify(k,msg,None)
            now=int(time.time());rep={'protocol':R.PROTOCOL,'relay_id':'phone','op':'reply','params':{'capabilities':['ble_scan']},'nonce':'n1','issued_at':now,'expires_at':now+30}
            return {**rep,'mac':R.sign(k,rep)}
        rid,key,declared=R.pair(send,lambda:'424242');self.assertEqual((rid,declared['capabilities']),('phone',['ble_scan']))
        with self.assertRaises(R.RelayError):R.pair(send,lambda:'000000')


class ServerRelayFlowTests(unittest.TestCase):
    def test_pair_and_scan_through_server_adds_relayed_device(self):
        from unittest.mock import patch
        from src.server import create_server
        from src.fabric.registry import Registry
        server=create_server(0,fabric_salt=b's',session_journal=__import__('src.fabric.session',fromlist=['x']).SessionJournal(__import__('tempfile').mkdtemp()+'/s.json'))
        try:
            state={'code':None,'key':None,'seen':{},'owner':True}
            def send(_r,msg):
                if msg.get('op')=='pair_request':
                    state['pc']=msg['pc_nonce'];state['code']='314159'
                    return {'protocol':R.PROTOCOL,'relay_id':'phone','relay_nonce':'cd'*8,'declared':{}}
                k=R.derive_key(state['code'],'cd'*8,state['pc']);m=R.verify(k,msg,state['seen'])
                params={'capabilities':['ble_scan'],'permissions':{'BLUETOOTH_SCAN':True,'owner_enabled':state['owner']}}
                if m['op']=='start_discovery':params={'observations':[{'address':'C1:00:00:00:00:01','name':'Sensor','rssi':-80}]}
                now=int(time.time());rep={'protocol':R.PROTOCOL,'relay_id':'phone','op':'reply','params':params,'nonce':R.secrets.token_hex(6),'issued_at':now,'expires_at':now+30}
                return {**rep,'mac':R.sign(k,rep)}
            reg=Registry();phone=reg.upsert([],category='phone',label='Phone');reg.devices[phone]['handles']={'USB':'android-h'}
            server.fabric_registry=reg;server.fabric_snapshot=reg.snapshot()
            with patch.object(server.android,'relay_urls',return_value=['http://127.0.0.1:47800']):
                start=server.relay_action('/api/relay-pair-start',{'device_id':'android-h'},transport_factory=lambda u:send)
            self.assertEqual(start['state'],'CODE_SHOWN_ON_DEVICE')
            with self.assertRaises(R.RelayError):server.relay_action('/api/relay-pair-confirm',{'code':'000000'},transport_factory=None)
            server.relay_pending={'android-h':{'send':send,'url':'http://127.0.0.1:47800','urls':['http://127.0.0.1:47800'],'hello':{'protocol':R.PROTOCOL,'relay_id':'phone','relay_nonce':'cd'*8},'pc_nonce':state['pc'],'handle':'android-h','started_at':time.monotonic()}}
            conf=server.relay_action('/api/relay-pair-confirm',{'device_id':'android-h','code':'314159'})
            self.assertEqual((conf['state'],conf['eligible_for_ble']),('PAIRED',True))
            snap=server.relay_action('/api/relay-scan',{'relay_id':'phone','seconds':5})
            child=[d for d in snap['devices'] if d['label']=='Sensor'][0]
            link=[l for l in snap['links'] if l['child']==child['key']][0]
            self.assertEqual((link['parent'],link['grants']),(phone,['observe']))
            state['owner']=False
            with self.assertRaises(R.RelayError):server.relay_action('/api/relay-scan',{'relay_id':'phone'})
        finally:
            server.server_close()


class PairingIsolationTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        from src.server import create_server
        from src.fabric.session import SessionJournal
        import tempfile
        self.server = create_server(0, fabric_salt=b's', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        reg = Registry()
        reg.devices[reg.upsert([], category='phone', label='Phone')]['handles'] = {'USB': 'android-h1'}
        reg.devices[reg.upsert([], category='tv', label='TV')]['handles'] = {'WIFI': 'android-h2'}
        self.server.fabric_registry = reg; self.server.fabric_snapshot = reg.snapshot()
        self._patch = patch.object(self.server.android, 'relay_urls', return_value=['http://127.0.0.1:47800'])
        self._patch.start(); self.addCleanup(self._patch.stop); self.addCleanup(self.server.server_close)

    def companion(self, relay_id, code, relay_nonce):
        state = {}
        def send(_r, msg):
            if msg.get('op') == 'pair_request':
                state['pc'] = msg['pc_nonce']
                return {'protocol': R.PROTOCOL, 'relay_id': relay_id, 'relay_nonce': relay_nonce, 'declared': {}}
            key = R.derive_key(code, relay_nonce, state['pc']); R.verify(key, msg, None)
            now = int(time.time())
            rep = {'protocol': R.PROTOCOL, 'relay_id': relay_id, 'op': 'reply',
                   'params': {'capabilities': ['ble_scan'], 'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}},
                   'nonce': R.secrets.token_hex(6), 'issued_at': now, 'expires_at': now + 30}
            return {**rep, 'mac': R.sign(key, rep)}
        return send

    def start(self, handle, relay_id, code, nonce):
        return self.server.relay_action('/api/relay-pair-start', {'device_id': handle},
                                        transport_factory=lambda u: self.companion(relay_id, code, nonce))

    def test_pair_confirm_stores_relay_url(self):
        self.start('android-h1', 'phone', '111111', 'aa' * 8)
        self.server.relay_action('/api/relay-pair-confirm', {'device_id': 'android-h1', 'code': '111111'})
        self.assertEqual(self.server.relays.relays['phone']['url'], 'http://127.0.0.1:47800')

    def test_two_pairings_in_progress_do_not_clobber_each_other(self):
        self.start('android-h1', 'phone', '111111', 'aa' * 8)
        self.start('android-h2', 'tv', '222222', 'bb' * 8)
        pending = self.server.relay_pending
        self.assertIn('android-h1', pending); self.assertIn('android-h2', pending)
        c1 = self.server.relay_action('/api/relay-pair-confirm', {'device_id': 'android-h1', 'code': '111111'})
        c2 = self.server.relay_action('/api/relay-pair-confirm', {'device_id': 'android-h2', 'code': '222222'})
        self.assertEqual((c1['state'], c1['relay_id'], c2['state'], c2['relay_id']), ('PAIRED', 'phone', 'PAIRED', 'tv'))
        self.assertEqual(self.server.relays.relays['phone']['device_key'], 'android-h1')
        self.assertEqual(self.server.relays.relays['tv']['device_key'], 'android-h2')
        self.assertEqual(self.server.relay_pending, {})

    def test_confirm_requires_the_pairing_device_handle(self):
        self.start('android-h1', 'phone', '111111', 'aa' * 8)
        with self.assertRaises(R.RelayError):
            self.server.relay_action('/api/relay-pair-confirm', {'code': '111111'})
        with self.assertRaises(R.RelayError):
            self.server.relay_action('/api/relay-pair-confirm', {'device_id': 'android-h2', 'code': '111111'})
        conf = self.server.relay_action('/api/relay-pair-confirm', {'device_id': 'android-h1', 'code': '111111'})
        self.assertEqual(conf['state'], 'PAIRED')

    def test_stale_pairing_code_is_rejected_and_cleared(self):
        self.start('android-h1', 'phone', '111111', 'aa' * 8)
        pending = self.server.relay_pending
        self.assertIn('android-h1', pending)
        pending['android-h1']['started_at'] -= 600
        with self.assertRaises(R.RelayError):
            self.server.relay_action('/api/relay-pair-confirm', {'device_id': 'android-h1', 'code': '111111'})
        self.assertNotIn('android-h1', self.server.relay_pending)

    def test_wrong_codes_are_limited_then_pairing_invalidated(self):
        # §3.3: online guessing must not be unlimited. After 5 failed confirms the
        # pending pairing is invalidated (even the right code is then refused) and a
        # fresh pair-start is required.
        self.start('android-h1', 'phone', '111111', 'aa' * 8)
        for _ in range(5):
            with self.assertRaises(R.RelayError):
                self.server.relay_action('/api/relay-pair-confirm', {'device_id': 'android-h1', 'code': '000000'})
        self.assertNotIn('android-h1', self.server.relay_pending)
        with self.assertRaisesRegex(R.RelayError, 'No pairing in progress'):
            self.server.relay_action('/api/relay-pair-confirm', {'device_id': 'android-h1', 'code': '111111'})
        self.start('android-h1', 'phone', '111111', 'aa' * 8)
        conf = self.server.relay_action('/api/relay-pair-confirm', {'device_id': 'android-h1', 'code': '111111'})
        self.assertEqual(conf['state'], 'PAIRED')

    def test_attempts_on_one_handle_do_not_affect_other_handle(self):
        # §3.3: the attempt counter is per pending pairing, not global.
        self.start('android-h1', 'phone', '111111', 'aa' * 8)
        self.start('android-h2', 'tv', '222222', 'bb' * 8)
        for _ in range(5):
            with self.assertRaises(R.RelayError):
                self.server.relay_action('/api/relay-pair-confirm', {'device_id': 'android-h1', 'code': '000000'})
        self.assertNotIn('android-h1', self.server.relay_pending)
        conf = self.server.relay_action('/api/relay-pair-confirm', {'device_id': 'android-h2', 'code': '222222'})
        self.assertEqual((conf['state'], conf['relay_id']), ('PAIRED', 'tv'))


class NonceBoundTests(unittest.TestCase):
    def test_seen_nonces_bounded_without_reopening_replay(self):
        m = manager(FakeRelay()); seen = m.relays['tv']['seen']
        t0 = int(time.time())                           # one issue time: the test must not depend on runner speed
        cmds = [R.command(KEY, 'tv', 'get_status', now=t0) for _ in range(600)]
        accepted = 0
        for c in cmds:
            try:
                R.verify(KEY, c, seen, now=c['issued_at']); accepted += 1
            except R.RelayError as e:
                self.assertIn('Too many live', str(e))
        self.assertEqual(accepted, 512); self.assertLessEqual(len(seen), 512)
        with self.assertRaises(R.RelayError):          # a live, already-seen nonce is never forgotten
            R.verify(KEY, cmds[0], seen, now=cmds[0]['issued_at'])
        later = cmds[0]['expires_at'] + 1               # once those commands expired, the cache drains
        fresh = R.command(KEY, 'tv', 'get_status', now=later)
        R.verify(KEY, fresh, seen, now=later)
        self.assertEqual(len(seen), 1)
        with self.assertRaises(R.RelayError):           # and an old command is still refused (expired)
            R.verify(KEY, cmds[0], seen, now=later)


class NonceCacheApiTests(unittest.TestCase):
    def test_only_expiring_dict_or_one_shot(self):
        c = R.command(KEY, 'tv', 'get_status')
        with self.assertRaises(TypeError):            # a count-evicting set is no longer a supported cache
            R.verify(KEY, c, set())
        R.verify(KEY, c, None); R.verify(KEY, c, None)  # one-shot check: valid twice, nothing remembered (pairing replies)
        seen = {}
        R.verify(KEY, c, seen)
        with self.assertRaises(R.RelayError):
            R.verify(KEY, c, seen)


def _executor():
    from types import SimpleNamespace
    from src.runtime.primitives import Executor
    return Executor(SimpleNamespace(fabric_registry=None, session_journal=SimpleNamespace(open_changes=lambda: [])))


def _unresolved(ex, n, prefix='u'):
    from src.runtime.contract import TransactionReceipt
    for i in range(n):
        tx = f'{prefix}{i}'
        ex.receipts[tx] = TransactionReceipt(tx, 'pc_job', 'k', 'UNKNOWN_TIMEOUT', None, None, False, '', '', ())
        ex._receipt_order.append(tx)


class ReceiptBoundTests(unittest.TestCase):
    def test_unresolved_changes_are_never_evicted_and_admission_is_bounded(self):
        ex = _executor()
        _unresolved(ex, ex.MAX_UNRESOLVED)
        for _ in range(ex.MAX_RECEIPTS + 100):          # flood with resolved (BLOCKED) receipts
            ex.execute('no-such-primitive', 'k', {})
        self.assertLessEqual(len(ex.receipts), ex.MAX_RECEIPTS)
        self.assertEqual(sum(1 for r in ex.receipts.values() if r.state == 'UNKNOWN_TIMEOUT'), ex.MAX_UNRESOLVED)
        r = ex.execute('relay_revoke', 'k2', {'relay_id': 'r'}, consent=True)   # a changing operation is refused, not admitted
        self.assertEqual(r['state'], 'BLOCKED'); self.assertIn('RECOVERY_BACKLOG', r['errors'][0])
        self.assertEqual(len(ex.recovery().pending_transactions), ex.MAX_UNRESOLVED)
        self.assertTrue(ex.acknowledge('u0'))            # owner checked one: it leaves recovery and frees one slot
        self.assertFalse(ex.acknowledge('u0'))
        self.assertNotIn('u0', ex.recovery().pending_transactions)
        self.assertEqual(ex.receipts['u0'].state, 'UNKNOWN_TIMEOUT')   # acknowledging is not verification

    def test_concurrent_failures_never_exceed_capacity_or_lose_an_outcome(self):
        import threading
        from src.runtime.primitives import Executor
        ex = _executor()
        gate = threading.Event()
        def failing(self_, key, params):
            gate.wait(5)
            raise RuntimeError('adapter lost mid-operation')
        ex.RUNNERS = dict(Executor.RUNNERS, relay_revoke=failing)
        out, threads = [], []
        for i in range(ex.MAX_UNRESOLVED * 3):
            th = threading.Thread(target=lambda i=i: out.append(ex.execute('relay_revoke', f'dev{i}', {'relay_id': 'r'}, consent=True)))
            threads.append(th); th.start()
        for _ in range(200):                              # all admissions decided while every admitted job is still running
            if sum(1 for o in out if o['state'] == 'BLOCKED') + ex._admitted >= len(threads):
                break
            threading.Event().wait(0.01)
        gate.set()
        for th in threads:
            th.join(10)
        failed = [o for o in out if o['state'] == 'FAILED']
        blocked = [o for o in out if o['state'] == 'BLOCKED']
        self.assertEqual(len(failed), ex.MAX_UNRESOLVED)
        self.assertEqual(len(failed) + len(blocked), len(threads))
        self.assertTrue(all('RECOVERY_BACKLOG' in o['errors'][0] for o in blocked))
        self.assertEqual(set(ex.recovery().pending_transactions), {o['transaction_id'] for o in failed})   # none forgotten
        self.assertEqual(ex._admitted, 0)


class RelayLivenessTests(unittest.TestCase):
    """A Companion that stops answering goes offline at once; a signed status reply brings it back (physical run 28 Oct)."""
    def test_unreachable_relay_goes_offline_and_recovers_on_status(self):
        import tempfile
        from src.server import create_server
        from src.fabric.session import SessionJournal
        s = create_server(0, fabric_salt=b's', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        self.addCleanup(s.server_close)
        fake = FakeRelay()
        s.relays.enroll('tv', KEY, 'dev-tv', {'capabilities': ['ble_scan'], 'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
        def dead(relay, msg):
            raise ConnectionResetError('Remote end closed connection without response')
        s.relays.relays['tv']['send'] = dead
        with self.assertRaises(R.RelayError):
            s.relay_action('/api/relay-scan', {'relay_id': 'tv'})
        self.assertFalse(s.relays.relays['tv']['online'])
        self.assertEqual(s.relay_ledger.routes['tv']['failures'], 1)
        s.relays.relays['tv']['send'] = fake
        try:
            s.relay_action('/api/relay-scan', {'relay_id': 'tv'})
        except R.RelayError:
            pass                                          # no graph in this test; the status read-back already ran
        self.assertTrue(s.relays.relays['tv']['online'])


class RelayScanHttp(unittest.TestCase):
    """§3.7 (issue #68): the relay-scan HTTP endpoint propagates truthful errors (never a masked
    generic 400 for a well-formed body), recovers OFFLINE relays via the signed status read-back,
    and preserves the pairing across failures."""

    def setUp(self):
        import threading
        import tempfile
        from src.fabric.session import SessionJournal
        from src.server import create_server
        self.server = create_server(0, fabric_salt=b's', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        reg = Registry()
        phone = reg.upsert([], category='phone', label='Phone')
        reg.devices[phone]['handles'] = {'USB': 'android-h1'}
        self.server.fabric_registry = reg
        self.server.fabric_snapshot = reg.snapshot()
        self.key = R.derive_key('314159', 'cd' * 8, 'pc' * 8)
        self.alive = {'up': True}
        self.server.relays.enroll('phone', self.key, 'android-h1',
                                  {'capabilities': ['ble_scan'],
                                   'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
        self.server.relays.relays['phone']['send'] = self.fake_send
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)   # LIFO: shutdown stops serve_forever before the socket closes
        import json as _json
        import urllib.request as _url
        with _url.urlopen(self.base + '/api/session') as r:
            self.csrf = _json.loads(r.read())['csrf_token']

    def fake_send(self, relay, message):
        msg = R.verify(self.key, message, {})
        if not self.alive['up']:
            raise ConnectionRefusedError('companion closed')
        if msg['op'] == 'get_status':
            params = {'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}}
        elif msg['op'] == 'start_discovery':
            params = {'observations': [{'address': 'C1:00:00:00:00:01', 'name': 'Sensor', 'rssi': -80}]}
        elif msg['op'] == 'stop_discovery':
            params = {}
        else:
            raise AssertionError('unexpected op ' + msg['op'])
        now = int(time.time())
        reply = {'protocol': R.PROTOCOL, 'relay_id': 'phone', 'op': 'reply', 'params': params,
                 'nonce': 'r' + msg['nonce'], 'issued_at': now, 'expires_at': now + 30}
        return {**reply, 'mac': R.sign(self.key, reply)}

    def post(self, path, body):
        import json
        import urllib.request
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(),
                                     {'Content-Type': 'application/json', 'Origin': self.base,
                                      'X-CSRF-Token': self.csrf})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_scan_discovers_advertisers_through_http(self):
        code, snap = self.post('/api/relay-scan', {'device_id': 'android-h1', 'relay_id': 'phone', 'seconds': 5})
        self.assertEqual(code, 200)
        self.assertEqual(snap['providers']['relay']['status'], 'OK')
        child = [d for d in snap['devices'] if d['label'] == 'Sensor'][0]
        link = [l for l in snap['links'] if l['child'] == child['key']][0]
        self.assertEqual(link['grants'], ['observe'])

    def test_relay_id_only_body_is_rejected_as_malformed_shape(self):
        # Uniform POST contract: every body carries device_id (the UI always sends it); relay_id alone is a 400.
        code, doc = self.post('/api/relay-scan', {'relay_id': 'phone'})
        self.assertEqual(code, 400)
        self.assertIn('Invalid request', doc['error'])

    def test_unreachable_relay_gives_truthful_409_and_recovers(self):
        self.alive['up'] = False
        code, doc = self.post('/api/relay-scan', {'device_id': 'android-h1', 'relay_id': 'phone'})
        self.assertEqual(code, 409)                       # truthful relay error, never a masked generic 400
        self.assertIn('unreachable', doc['error'].lower())
        self.assertIn('guide', doc)
        relay = self.server.relays.relays['phone']
        self.assertFalse(relay['online'])
        self.assertEqual((relay['key'], relay['device_key']), (self.key, 'android-h1'))  # pairing continuity
        self.alive['up'] = True
        code, _ = self.post('/api/relay-scan', {'device_id': 'android-h1', 'relay_id': 'phone'})
        self.assertEqual(code, 200)                       # the signed status read-back brings it back
        self.assertTrue(self.server.relays.relays['phone']['online'])

    def test_unknown_relay_gives_truthful_409(self):
        code, doc = self.post('/api/relay-scan', {'device_id': 'android-h1', 'relay_id': 'nope'})
        self.assertEqual(code, 409)
        self.assertIn('Unknown relay', doc['error'])
