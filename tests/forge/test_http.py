import json
import threading
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from src.forge.demo_host import create_forge_server
from src.forge.service import MemoryProvider
from src.forge.fixtures import manifest

class ForgeHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server=create_forge_server(0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.token=self.fetch('/api/session')[1]['token']
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def fetch(self,path,method='GET',data=None,token=True,origin=True,headers=None):
        h={'Authorization':'Bearer '+self.token} if token and hasattr(self,'token') else {}
        if origin:h['Origin']=self.base
        if data is not None:h['Content-Type']='application/json'
        h.update(headers or {})
        req=Request(self.base+path,data=None if data is None else json.dumps(data).encode(),headers=h,method=method)
        try:r=urlopen(req,timeout=3)
        except HTTPError as e:r=e
        with r:return r.status,json.loads(r.read())
    def test_lifecycle_and_generated_route(self):
        self.assertEqual(self.fetch('/api/publish','POST',{'consent':True})[0],200)
        path='/v1/services/ble-observations/observations'
        self.assertEqual(self.fetch(path)[1]['observations'][0]['rssi_dbm'],-62)
        self.assertEqual(self.fetch('/api/documents')[1]['openapi']['openapi'],'3.1.0')
        self.assertEqual(self.fetch('/api/remove','POST',{})[0],200)
        self.assertEqual(self.fetch(path)[0],404)
    def test_auth_origin_host_and_no_arbitrary_dispatch(self):
        self.assertEqual(self.fetch('/api/catalog',token=False)[0],401)
        self.assertEqual(self.fetch('/api/publish','POST',{'consent':True},origin=False)[0],403)
        self.assertEqual(self.fetch('/api/publish','POST',{'consent':True},headers={'Origin':'http://evil.invalid'})[0],403)
        self.assertEqual(self.fetch('/api/catalog',headers={'Host':'evil.invalid'})[0],403)
        self.assertEqual(self.fetch('/api/publish','POST',{'consent':True,'command':'adb'})[0],400)
        self.assertEqual(self.fetch('/api/shell','POST',{})[0],404)
    def test_unavailable_meta_is_explicit(self):
        code,result=self.fetch('/api/plan','POST',{'planner':'glimmer'})
        self.assertEqual(code,409);self.assertIn('META_UNAVAILABLE',result['error'])
    def test_fixture_refresh_is_explicit_and_simulated(self):
        self.server.provider.current['observed_at']=0
        self.assertEqual(self.fetch('/api/publish','POST',{'consent':True})[0],409)
        self.assertEqual(self.fetch('/api/reset-fixture','POST',{})[0],200)
        self.assertEqual(self.fetch('/api/publish','POST',{'consent':True})[0],200)
    def test_wrong_content_type_is_rejected(self):
        self.assertEqual(self.fetch('/api/publish','POST',{'consent':True},headers={'Content-Type':'text/plain'})[0],415)
    def test_body_and_query_bounds(self):
        self.assertEqual(self.fetch('/api/publish','POST',{'consent':True,'padding':'x'*9000})[0],413)
        self.assertEqual(self.fetch('/api/catalog?url=http://evil.invalid')[0],404)

class RuntimeHostTests(ForgeHTTPTests):
    def setUp(self):
        m=manifest();m.update(service_id='relay-signals',capability_id='cap-runtime',simulation=False,status='REAL_HARDWARE_VERIFIED')
        self.provider=MemoryProvider(m)
        self.server=create_forge_server(0,provider=self.provider,capability_id='cap-runtime')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.token=self.fetch('/api/session')[1]['token']
    # Inherited fixture-specific lifecycle tests are replaced below; shared request guards remain useful.
    def test_lifecycle_and_generated_route(self):
        catalog=self.fetch('/api/catalog')[1]
        self.assertEqual(catalog['mode'],'PHYSICAL_READ_ONLY')
        self.assertFalse(catalog['fixture_reset_enabled'])
        self.assertEqual(self.fetch('/api/publish','POST',{'consent':True})[0],200)
        path=catalog['observation_path'];self.assertIn('relay-signals',path)
        self.assertFalse(self.fetch(path)[1]['simulation'])
        self.assertEqual(self.fetch('/api/documents')[1]['openapi']['servers'][0]['url'],self.base)
        self.provider.current['available']=False
        self.assertEqual(self.fetch(path)[0],409)
        blocked=self.fetch('/api/catalog')[1]
        self.assertFalse(blocked['available']);self.assertIsNone(blocked['manifest'])
        self.assertEqual(len(blocked['services']),1)
        self.assertEqual(self.fetch('/api/remove','POST',{})[0],200)
        self.assertEqual(self.fetch(path)[0],404)
    def test_fixture_refresh_is_explicit_and_simulated(self):
        self.assertEqual(self.fetch('/api/reset-fixture','POST',{})[0],409)
        self.assertFalse(self.provider.current['simulation'])
    def test_runtime_binding_cannot_silently_switch_source(self):
        self.provider.current['device_id']='different-device'
        self.assertEqual(self.fetch('/api/publish','POST',{'consent':True})[0],409)
        self.assertFalse(self.fetch('/api/catalog')[1]['available'])
