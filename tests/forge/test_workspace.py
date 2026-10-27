"""Controlled runtime selection; no discovery, hardware, or model calls."""
import copy
from datetime import datetime,timezone
import json,threading,time,unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from tests.forge import test_runtime_bridge
from src.forge.workspace import WorkspaceManager,create_workspace_server
from src.forge.compiler import ForgeError


def runtime_data():
    fixture=test_runtime_bridge.RuntimeBridgeTests();fixture.setUp();data=fixture.data
    for value in data.values():
        for fact in value.get('facts',[]):fact['observed_at']=datetime.now(timezone.utc).isoformat()
    return data

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.data=runtime_data();self.paths=[]
        def read(path):self.paths.append(path);return copy.deepcopy(self.data[path])
        self.manager=WorkspaceManager(read,allow_simulated=True)
    def tearDown(self):self.manager.close()
    def test_select_requires_server_issued_candidate_and_fresh_authority(self):
        rows=self.manager.candidates();self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['simulation']);self.assertNotIn('dev:beacon',json.dumps(rows))
        with self.assertRaises(ForgeError):self.manager.select('invented')
        self.data['/api/v2/routes']['routes'][0]['owner_enabled']=False
        with self.assertRaises(ForgeError):self.manager.select(rows[0]['id'])
        self.assertEqual(self.manager.sessions(),[])
        self.assertFalse(any('/execute' in path for path in self.paths))
    def test_default_refuses_simulated_runtime_and_expired_candidate(self):
        strict=WorkspaceManager(lambda p:copy.deepcopy(self.data[p]));self.addCleanup(strict.close)
        self.assertEqual(strict.candidates(),[])
        row=self.manager.candidates()[0];self.manager._candidate_deadline=0
        with self.assertRaisesRegex(ForgeError,'CANDIDATE_EXPIRED'):self.manager.select(row['id'])
    def test_session_identity_close_and_bounded_capacity(self):
        self.manager.max_sessions=1;row=self.manager.candidates()[0];session=self.manager.select(row['id'])
        self.assertTrue(session['url'].startswith('http://127.0.0.1:'))
        self.assertNotIn('token',session);self.assertEqual(len(self.manager.sessions()),1)
        with self.assertRaisesRegex(ForgeError,'SESSION_LIMIT'):self.manager.select(row['id'])
        self.manager.remove_session(session['id']);self.assertEqual(self.manager.sessions(),[])
        with self.assertRaises(OSError):urlopen(session['url'],timeout=1)
    def test_http_requires_auth_origin_exact_body_and_no_arbitrary_binding(self):
        server=create_workspace_server(0,self.manager);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        def post(body,origin=True):
            headers={'Content-Type':'application/json','Authorization':'Bearer '+server.token}
            if origin:headers['Origin']=base
            return urlopen(Request(base+'/api/select',json.dumps(body).encode(),headers=headers),timeout=3)
        with self.assertRaises(HTTPError) as error:urlopen(base+'/api/candidates')
        self.assertEqual(error.exception.code,401);error.exception.close()
        with self.assertRaises(HTTPError) as error:post({'candidate_id':'x'},False)
        self.assertEqual(error.exception.code,403);error.exception.close()
        with self.assertRaises(HTTPError) as error:post({'candidate_id':'x','provider':'http://evil.invalid'})
        self.assertEqual(error.exception.code,400);error.exception.close()
        candidate=self.manager.candidates()[0]
        with post({'candidate_id':candidate['id']}) as response:session=json.load(response)
        with urlopen(session['url']+'/api/session') as response:token=json.load(response)['token']
        req=Request(session['url']+'/api/catalog',headers={'Authorization':'Bearer '+token})
        with urlopen(req) as response:catalog=json.load(response)
        self.assertEqual(catalog['mode'],'SIMULATED');self.assertFalse(catalog['fixture_reset_enabled'])
    def test_slow_new_selection_does_not_block_existing_session_removal(self):
        blocked=threading.Event();release=threading.Event();stall=threading.Event();result=[]
        def read(path):
            if stall.is_set() and path=='/api/v2/contract':blocked.set();release.wait(4)
            return copy.deepcopy(self.data[path])
        manager=WorkspaceManager(read,allow_simulated=True);self.addCleanup(manager.close)
        candidate=manager.candidates()[0];first=manager.select(candidate['id'])
        stall.set()
        worker=threading.Thread(target=lambda:result.append(manager.select(candidate['id'])),daemon=True);worker.start()
        self.assertTrue(blocked.wait(1));removed=threading.Event()
        closer=threading.Thread(target=lambda:(manager.remove_session(first['id']),removed.set()),daemon=True);closer.start()
        try:self.assertTrue(removed.wait(1),'A pending source read blocked another workspace closure')
        finally:release.set();worker.join(5);closer.join(5)
    def test_accepted_publish_cannot_recreate_service_after_workspace_closure(self):
        candidate=self.manager.candidates()[0];session=self.manager.select(candidate['id'])
        child=self.manager._sessions[session['id']]['server'];blocked=threading.Event();release=threading.Event();results=[]
        original=child.snapshot
        def delayed():blocked.set();release.wait(4);return original()
        child.snapshot=delayed
        def publish():
            request=Request(session['url']+'/api/publish',b'{"consent":true}',headers={
                'Content-Type':'application/json','Origin':session['url'],'Authorization':'Bearer '+child.token})
            try:
                with urlopen(request,timeout=5) as response:results.append(response.status)
            except HTTPError as error:results.append(error.code);error.close()
        worker=threading.Thread(target=publish,daemon=True);worker.start();self.assertTrue(blocked.wait(1))
        try:self.manager.remove_session(session['id'])
        finally:release.set();worker.join(5)
        self.assertEqual(results,[409]);self.assertEqual(child.forge.list_services(),[])
    def test_stalled_existing_read_does_not_block_terminal_workspace_closure(self):
        candidate=self.manager.candidates()[0];session=self.manager.select(candidate['id'])
        child=self.manager._sessions[session['id']]['server'];manifest=child.snapshot()
        child.forge.publish_verified(manifest,consent=True)
        blocked=threading.Event();release=threading.Event();removed=threading.Event();errors=[]
        original=child.provider.snapshot
        def delayed(key):blocked.set();release.wait(4);return original(key)
        child.provider.snapshot=delayed
        def read():
            try:child.forge.read(child.service_id)
            except ForgeError as error:errors.append(str(error))
        worker=threading.Thread(target=read,daemon=True);worker.start();self.assertTrue(blocked.wait(1))
        closer=threading.Thread(target=lambda:(self.manager.remove_session(session['id']),removed.set()),daemon=True);closer.start()
        try:
            self.assertTrue(removed.wait(1),'Closure waited for an unavailable source')
            self.assertEqual(child.forge.list_services(),[])
        finally:release.set();worker.join(5);closer.join(5)
        self.assertEqual(errors,['WORKSPACE_CLOSED']);self.assertEqual(child.forge.list_services(),[])
    def test_stop_service_is_terminal_and_does_not_wait_for_provider_read(self):
        candidate=self.manager.candidates()[0];session=self.manager.select(candidate['id'])
        child=self.manager._sessions[session['id']]['server'];manifest=child.snapshot()
        child.forge.publish_verified(manifest,consent=True)
        blocked=threading.Event();release=threading.Event();removed=threading.Event()
        original=child.provider.snapshot
        def delayed(key):blocked.set();release.wait(4);return original(key)
        child.provider.snapshot=delayed
        def read():
            try:child.forge.read(child.service_id)
            except ForgeError:pass
        worker=threading.Thread(target=read,daemon=True);worker.start();self.assertTrue(blocked.wait(1))
        closer=threading.Thread(target=lambda:(child.forge.remove(child.service_id),removed.set()),daemon=True);closer.start()
        try:self.assertTrue(removed.wait(1),'Stop service waited for provider I/O')
        finally:release.set();worker.join(5);closer.join(5)
        self.assertEqual(child.forge.list_services(),[])
        with self.assertRaisesRegex(ForgeError,'WORKSPACE_CLOSED'):child.snapshot()
        with self.assertRaisesRegex(ForgeError,'SERVICE_REMOVED'):child.forge.read(child.service_id)

if __name__=='__main__':unittest.main()
