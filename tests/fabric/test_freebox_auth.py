import hashlib, hmac, unittest
from src.adapters.freebox_auth import FreeboxSession, FreeboxAuthError, TOKEN_NAME
from src.fabric.credential_vault import Vault


class MemVault:
    available=True
    def __init__(self):self.d={}
    def put(self,n,s):self.d[n]=s
    def get(self,n):return self.d.get(n)
    def delete(self,n):self.d.pop(n,None)


class FakeBox:
    def __init__(self):self.calls=[];self.status='pending';self.revoked=False;self.expire_once=False
    def __call__(self,method,path,body=None,session=None):
        self.calls.append((method,path,session))
        if method=='POST' and path.endswith('login/authorize/'):return {'success':True,'result':{'app_token':'TOKEN','track_id':7}}
        if path.endswith('login/authorize/7'):return {'success':True,'result':{'status':self.status}}
        if path.endswith('login/'):return {'success':True,'result':{'challenge':'CH'}}
        if path.endswith('login/session/'):
            if self.revoked:return {'success':False,'error_code':'invalid_token'}
            ok=body['password']==hmac.new(b'TOKEN',b'CH',hashlib.sha1).hexdigest()
            return {'success':True,'result':{'session_token':'S1','permissions':{'settings':False,'explorer':True}}} if ok else {'success':False,'error_code':'invalid_password'}
        if self.expire_once and session:
            self.expire_once=False;return {'success':False,'error_code':'auth_required'}
        if path.endswith('lan/browser/pub/'):
            return {'success':True,'result':[{'primary_name':'Living TV','host_type':'television','vendor_name':'Sony','active':True,'reachable':True,
                    'l2ident':{'id':'00:1a:2b:3c:4d:5e','type':'mac_address'},'l3connectivities':[{'af':'ipv4','addr':'192.168.1.40','active':True}]},
                   {'primary_name':'iPhone','host_type':'smartphone','active':False,'l2ident':{'id':'da:11:22:33:44:55','type':'mac_address'},'l3connectivities':[]}]}
        if path.endswith('lan/browser/interfaces/'):return {'success':True,'result':[{'name':'pub','host_count':2}]}
        return {'success':False,'error_code':'unexpected'}


class FreeboxAuthTests(unittest.TestCase):
    def test_official_flow_grant_then_read_only_inventory(self):
        box=FakeBox();v=MemVault();s=FreeboxSession(v,12,transport=box)
        self.assertEqual(s.state(),'NOT_AUTHORIZED')
        s.request_authorization();self.assertEqual(s.poll_authorization(),'pending');self.assertIsNone(v.get(TOKEN_NAME))
        box.status='granted';self.assertEqual(s.poll_authorization(),'granted');self.assertEqual(s.state(),'AUTHORIZED')
        hosts=s.lan_hosts();self.assertEqual(hosts[0]['ipv4'],['192.168.1.40']);self.assertEqual(s.permissions['settings'],False)
        self.assertTrue(all(m=='GET' for m,p,_ in box.calls if 'login' not in p))

    def test_denied_keeps_no_token(self):
        box=FakeBox();box.status='denied';v=MemVault();s=FreeboxSession(v,12,transport=box)
        s.request_authorization();self.assertEqual(s.poll_authorization(),'denied');self.assertIsNone(v.get(TOKEN_NAME))

    def test_revoked_token_is_forgotten(self):
        box=FakeBox();box.revoked=True;v=MemVault();v.put(TOKEN_NAME,'TOKEN');s=FreeboxSession(v,12,transport=box)
        with self.assertRaises(FreeboxAuthError):s.lan_hosts()
        self.assertIsNone(v.get(TOKEN_NAME))

    def test_expired_session_renews_once(self):
        box=FakeBox();box.expire_once=True;v=MemVault();v.put(TOKEN_NAME,'TOKEN');s=FreeboxSession(v,12,transport=box)
        self.assertEqual(len(s.lan_hosts()),2)

    def test_non_allowlisted_path_and_no_vault_refused(self):
        s=FreeboxSession(MemVault(),12,transport=FakeBox())
        with self.assertRaises(FreeboxAuthError):s.get('wifi/config/')
        class NoVault(MemVault):available=False
        with self.assertRaises(FreeboxAuthError):FreeboxSession(NoVault(),12,transport=FakeBox()).request_authorization()

    def test_vault_roundtrip_and_name_validation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            v=Vault(d,backend=(lambda b,e:bytes(x^0x5a for x in b),lambda b,e:bytes(x^0x5a for x in b)))
            v.put('freebox-app-token','secret');self.assertEqual(v.get('freebox-app-token'),'secret')
            self.assertNotIn(b'secret',next((v.root).glob('*.bin')).read_bytes())
            with self.assertRaises(ValueError):v.put('../x','s')
            self.assertFalse(Vault(d,backend=None).available if __import__('sys').platform!='win32' else False)


class FreeboxGraphTests(unittest.TestCase):
    def test_inventory_hosts_are_observe_only_and_random_mac_not_strong(self):
        from src.fabric.registry import Registry
        from src.fabric.freebox_ingest import ingest_freebox
        class Pub:
            def discover(self):return {'status':'READY','devices':[{'facts':{'api_version':'12.1','device_family':'FreeboxServer9,1','api_base_path':'/api/'}}]}
        v=MemVault();v.put(TOKEN_NAME,'TOKEN');r=Registry()
        rep=ingest_freebox(r,{'public':Pub(),'session':FreeboxSession(v,12,transport=FakeBox())},b'salt')
        self.assertEqual((rep['status'],rep['lan_hosts']),('AUTHENTICATED',2))
        snap=r.snapshot()
        inv=[l for l in snap['links'] if l['transport']=='INVENTORY']
        self.assertEqual(len(inv),2);self.assertTrue(all(l['grants']==['observe'] for l in inv))
        self.assertNotIn('00:1a:2b',str(snap));self.assertNotIn('da:11',str(snap))
        box=[d for d in snap['devices'] if d['category']=='router'][0]
        self.assertTrue(any(c['name']=='wifi_settings' and c['status']=='BLOCKED' for c in box['capabilities']))
