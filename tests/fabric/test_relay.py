import time
import unittest
from src.fabric import relay as R
from src.fabric.registry import Registry
from src.fabric.discovery import ingest_ble

KEY=R.derive_key('123456','rn','pn')


class FakeRelay:
    """Reference relay behaviour: verifies commands, returns signed bounded observations."""
    def __init__(s,observations=None,fail=None,malformed=False):s.seen=set();s.obs=observations or [];s.fail=fail;s.ops=[];s.malformed=malformed
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
        c=R.command(KEY,'tv','get_status');seen=set();R.verify(KEY,c,seen)
        with self.assertRaises(R.RelayError):R.verify(KEY,c,seen)
        with self.assertRaises(R.RelayError):R.verify(KEY,R.command(KEY,'tv','get_status',now=time.time()-100),set())
        t=dict(R.command(KEY,'tv','get_status'));t['op']='revoke_access'
        with self.assertRaises(R.RelayError):R.verify(KEY,t,set())
        with self.assertRaises(R.RelayError):R.verify(R.derive_key('000000','rn','pn'),R.command(KEY,'tv','get_status'),set())

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
            k=R.derive_key('424242','ab'*8,state['pc']);R.verify(k,msg,set())
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
            state={'code':None,'key':None,'seen':set(),'owner':True}
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
            with patch.object(server.android,'forward_companion',return_value='http://127.0.0.1:47800'):
                start=server.relay_action('/api/relay-pair-start',{'device_id':'android-h'},transport_factory=lambda u:send)
            self.assertEqual(start['state'],'CODE_SHOWN_ON_DEVICE')
            with self.assertRaises(R.RelayError):server.relay_action('/api/relay-pair-confirm',{'code':'000000'},transport_factory=None)
            server.relay_pending={'android-h':{'send':send,'hello':{'protocol':R.PROTOCOL,'relay_id':'phone','relay_nonce':'cd'*8},'pc_nonce':state['pc'],'handle':'android-h','started_at':time.monotonic()}}
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
        self._patch = patch.object(self.server.android, 'forward_companion', return_value='http://127.0.0.1:47800')
        self._patch.start(); self.addCleanup(self._patch.stop); self.addCleanup(self.server.server_close)

    def companion(self, relay_id, code, relay_nonce):
        state = {}
        def send(_r, msg):
            if msg.get('op') == 'pair_request':
                state['pc'] = msg['pc_nonce']
                return {'protocol': R.PROTOCOL, 'relay_id': relay_id, 'relay_nonce': relay_nonce, 'declared': {}}
            key = R.derive_key(code, relay_nonce, state['pc']); R.verify(key, msg, set())
            now = int(time.time())
            rep = {'protocol': R.PROTOCOL, 'relay_id': relay_id, 'op': 'reply',
                   'params': {'capabilities': ['ble_scan'], 'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}},
                   'nonce': R.secrets.token_hex(6), 'issued_at': now, 'expires_at': now + 30}
            return {**rep, 'mac': R.sign(key, rep)}
        return send

    def start(self, handle, relay_id, code, nonce):
        return self.server.relay_action('/api/relay-pair-start', {'device_id': handle},
                                        transport_factory=lambda u: self.companion(relay_id, code, nonce))

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


class NonceBoundTests(unittest.TestCase):
    def test_seen_nonces_are_bounded_fifo(self):
        m = manager(FakeRelay()); seen = m.relays['tv']['seen']
        cmds = [R.command(KEY, 'tv', 'get_status') for _ in range(600)]
        for c in cmds:
            R.verify(KEY, c, seen, now=c['issued_at'])
        self.assertLessEqual(len(seen), 512)
        with self.assertRaises(R.RelayError):
            R.verify(KEY, cmds[-1], seen, now=cmds[-1]['issued_at'])
        R.verify(KEY, cmds[0], seen, now=cmds[0]['issued_at'])
