import http.client
import json
import threading
import unittest
from unittest.mock import patch, Mock
from tempfile import TemporaryDirectory
from pathlib import Path
from contextlib import contextmanager
import queue
from src.adapters.simulated_setting import SimulatedSetting
from src.core.transactions import TransactionEngine
from src.server import create_server


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(0, fabric_salt=b'test-salt')
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port
        cls.origin = f'http://127.0.0.1:{cls.port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        conn.close()
        return result

    def test_home_and_security_headers(self):
        code, body, headers = self.request('GET', '/')
        self.assertEqual(code, 200)
        self.assertIn(b'SIMULATED', body)
        self.assertIn("default-src 'self'", headers['Content-Security-Policy'])

    def test_discovery(self):
        code, body, _ = self.request('GET', '/api/devices')
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)['devices'][0]['simulated'])

    def test_android_inventory_is_opt_in(self):
        with patch.object(self.server.android, 'discover', return_value={'devices': [], 'status': 'WAITING_FOR_DEVICE'}) as discover:
            self.request('GET', '/api/devices')
            discover.assert_not_called()
            code, body, _ = self.request('GET', '/api/devices?source=android')
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(body)['status'], 'WAITING_FOR_DEVICE')

    def test_android_event_stream_is_explicit_and_redacted(self):
        class Monitor:
            @contextmanager
            def subscribe(self):
                events=queue.Queue()
                events.put({'type':'inventory','status':'READY','devices':[]})
                events.put({'type':'closed'})
                yield events
        with patch.object(self.server,'android_events',Monitor()):
            code,body,headers=self.request('GET','/api/device-events?source=android')
            self.assertEqual(code,200)
            self.assertEqual(headers['Content-Type'],'text/event-stream')
            self.assertIn(b'data:',body)
            self.assertIn(b'"type": "inventory"',body)
        self.assertEqual(self.request('GET','/api/device-events?source=demo')[0],400)

    def test_freebox_discovery_is_opt_in(self):
        with patch.object(self.server.freebox, 'discover', return_value={'devices': [], 'status': 'GATEWAY_UNAVAILABLE'}) as discover:
            self.request('GET', '/api/devices')
            discover.assert_not_called()
            code, body, _ = self.request('GET', '/api/devices?source=freebox')
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(body)['status'], 'GATEWAY_UNAVAILABLE')

    def test_freebox_data_never_reaches_model(self):
        code, _, _ = self.request('POST', '/api/recommend', '{"source":"freebox","device_id":"freebox-local"}', self.session_headers())
        self.assertEqual(code, 400)

    def test_android_inspection_never_falls_back_to_fixture(self):
        with patch.object(self.server.android, 'inspect', side_effect=ValueError('Device unavailable')):
            code, _, _ = self.request('POST', '/api/inspect', '{"source":"android","device_id":"demo-android"}', self.session_headers())
            self.assertEqual(code, 400)

    def test_runtime_cloud_is_explicitly_blocked(self):
        code, body, _ = self.request('GET', '/api/model-status')
        self.assertEqual(code, 200)
        self.assertFalse(json.loads(body)['cloud_inference_enabled'])

    def test_recorded_model_proof_is_explicitly_historical(self):
        code, body, _ = self.request('GET','/api/model-proof')
        self.assertEqual(code,200)
        proof=json.loads(body)
        self.assertEqual(proof['evidence_kind'],'RECORDED_RUNTIME_CORE_CALL')
        self.assertFalse(proof['live_request'])
        self.assertEqual(proof['receipt']['model_id'],'muse-spark-1.3')

    def test_reasoning_requires_credit_permit(self):
        code, body, _ = self.request('POST', '/api/recommend', '{"source":"demo","device_id":"demo-android"}', self.session_headers())
        self.assertEqual(code, 409)
        self.assertIn('error', json.loads(body))

    def test_simulated_transaction_requires_consent_and_restores_exact_value(self):
        with TemporaryDirectory() as directory:
            setting=SimulatedSetting(Path(directory)/'setting.sqlite')
            engine=TransactionEngine(Path(directory)/'journal.sqlite',setting)
            with patch.object(self.server,'demo_engine',engine):
                payload={'source':'demo','device_id':'demo-android','operation':'apply','transaction_id':'http-demo','target':60,'consent':False}
                code,_,_=self.request('POST','/api/demo-transaction',json.dumps(payload),self.session_headers())
                self.assertEqual(code,409)
                self.assertEqual(setting.read_setting(),30)
                payload['consent']=True
                code,body,_=self.request('POST','/api/demo-transaction',json.dumps(payload),self.session_headers())
                self.assertEqual(code,200)
                self.assertEqual(json.loads(body)['state'],'VERIFIED')
                self.assertEqual(setting.read_setting(),60)
                payload['operation']='undo'
                code,body,_=self.request('POST','/api/demo-transaction',json.dumps(payload),self.session_headers())
                self.assertEqual(code,200)
                self.assertEqual(json.loads(body)['state'],'REVERTED')
                self.assertEqual(setting.read_setting(),30)

    def test_physical_source_cannot_use_simulated_transaction_route(self):
        payload='{"source":"android","device_id":"some-phone","operation":"apply"}'
        self.assertEqual(self.request('POST','/api/demo-transaction',payload,self.session_headers())[0],400)

    def test_misconfigured_physical_engine_cannot_be_called_from_demo_route(self):
        engine=Mock()
        engine.adapter.source='ADB'
        with patch.object(self.server,'demo_engine',engine):
            payload='{"source":"demo","device_id":"demo-android","operation":"apply","transaction_id":"test","consent":true,"target":60}'
            self.assertEqual(self.request('POST','/api/demo-transaction',payload,self.session_headers())[0],409)
            engine.prepare.assert_not_called()

    def test_real_device_data_cannot_be_sent_to_model(self):
        code, _, _ = self.request('POST', '/api/recommend', '{"source":"android","device_id":"some-device"}', self.session_headers())
        self.assertEqual(code, 400)

    def test_local_meta_receives_only_current_allowlisted_device_facts(self):
        broker=Mock();broker.local_only=True;broker.ready.return_value=True
        broker.recommend.return_value={'source':'ADB','model_id':'llama3.2:3b-instruct-q4_K_M'}
        report={'evidence':[{'key':'battery_percent','value':72},{'key':'storage_free_gb','value':38},
                            {'key':'model','value':'PRIVATE_MODEL'},{'key':'serial','value':'PRIVATE_SERIAL'}]}
        with patch.object(self.server,'model_broker',broker),patch.object(self.server.android,'inspect',return_value=report) as inspect:
            body=json.dumps({'source':'android','device_id':'opaque-phone','facts':{'serial':'DO_NOT_SEND'}})
            code,_,_=self.request('POST','/api/recommend',body,self.session_headers())
            self.assertEqual(code,200)
            inspect.assert_called_once_with('opaque-phone')
            broker.recommend.assert_called_once_with({'battery_percent':72,'storage_free_gb':38},source='ADB')

    def test_cloud_broker_cannot_receive_physical_device_data(self):
        broker=Mock();broker.local_only=False
        with patch.object(self.server,'model_broker',broker):
            code,_,_=self.request('POST','/api/recommend','{"source":"android","device_id":"opaque"}',self.session_headers())
            self.assertEqual(code,400)
            broker.recommend.assert_not_called()

    def test_agent_disabled_by_default_and_requires_android_and_csrf(self):
        code,_,_=self.request('POST','/api/agent-plan','{"source":"android","device_id":"x"}',self.session_headers())
        self.assertEqual(code,409)
        code,_,_=self.request('POST','/api/agent-plan','{"source":"android","device_id":"x"}',{'Content-Type':'application/json'})
        self.assertEqual(code,403)

    def test_agent_routes_delegate_and_reject_non_android(self):
        agent=Mock();agent.broker.ready.return_value=True
        agent.plan.return_value={'plan_id':'plan-1','gate':{'decision':'REVIEW_REQUIRED'}}
        agent.execute.return_value={'verified':True};agent.undo.return_value={'exact':True}
        with patch.object(self.server,'agent',agent):
            self.assertEqual(self.request('POST','/api/agent-plan','{"source":"demo","device_id":"demo-android"}',self.session_headers())[0],400)
            self.assertEqual(self.request('POST','/api/agent-plan','{"source":"android","device_id":"h"}',self.session_headers())[0],200)
            body='{"source":"android","device_id":"h","plan_id":"plan-1","consent":true}'
            self.assertEqual(self.request('POST','/api/agent-execute',body,self.session_headers())[0],200)
            agent.execute.assert_called_once_with('plan-1',True)
            self.assertEqual(self.request('POST','/api/agent-undo',body,self.session_headers())[0],200)
            agent.recover.return_value=[]
            self.assertEqual(self.request('POST','/api/agent-recover','{"source":"android","device_id":"h"}',self.session_headers())[0],200)

    def test_fabric_routes_csrf_validation_and_single_flight(self):
        self.assertEqual(json.loads(self.request('GET','/api/fabric')[1])['status'],'NOT_RUN')
        self.assertEqual(self.request('POST','/api/fabric-discover','{"device_id":"fabric"}',{'Content-Type':'application/json'})[0],403)
        self.assertEqual(self.request('POST','/api/fabric-discover','{"device_id":"fabric","providers":["portscan"]}',self.session_headers())[0],400)
        snap={'schema_version':1,'devices':[{'key':'dev-1'}],'links':[],'possible_duplicates':[],'providers':{}}
        with patch('src.server.fabric_discovery.run',return_value=(snap,None)) as run:
            code,body,_=self.request('POST','/api/fabric-discover','{"device_id":"fabric","providers":["mdns"]}',self.session_headers())
            self.assertEqual(code,200);self.assertEqual(run.call_args.kwargs['providers'],('mdns',))
        self.assertEqual(json.loads(self.request('GET','/api/fabric')[1])['devices'][0]['key'],'dev-1')
        self.server.fabric_lock.acquire()
        try:self.assertEqual(self.request('POST','/api/fabric-discover','{"device_id":"fabric"}',self.session_headers())[0],409)
        finally:self.server.fabric_lock.release()

    def test_freebox_authorization_flow_states(self):
        class S:
            def __init__(s):s.n=0
            def state(s):return 'NOT_AUTHORIZED'
            def request_authorization(s):return 1
            def poll_authorization(s):
                s.n+=1;return 'granted' if s.n>1 else 'pending'
        sess=S()
        code,body=self.server.start_freebox_authorization(lambda:sess)
        self.assertEqual((code,body['state']),(202,'PENDING'))
        self.assertEqual(self.server.start_freebox_authorization(lambda:sess)[0],409)
        import time;deadline=time.time()+6
        while self.server.freebox_auth['state']=='PENDING' and time.time()<deadline:time.sleep(0.2)
        self.assertEqual(json.loads(self.request('GET','/api/freebox-authorization')[1])['state'],'GRANTED')
        self.server.freebox_auth={'state':'IDLE'}
        self.assertEqual(self.request('POST','/api/freebox-authorize','{"device_id":"other"}',self.session_headers())[0],400)

    def test_dns_rebinding_host_denied(self):
        self.assertEqual(self.request('GET', '/api/session', headers={'Host': 'attacker.example'})[0], 403)

    def test_cross_origin_and_missing_token_denied(self):
        for headers in ({}, {'Origin': self.origin}, {'Origin': 'https://attacker.example'}):
            self.assertEqual(self.request('POST', '/api/inspect', '{}', headers)[0], 403)

    def session_headers(self):
        token = json.loads(self.request('GET', '/api/session')[1])['csrf_token']
        return {'Origin': self.origin, 'X-CSRF-Token': token, 'Content-Type': 'application/json'}

    def test_inspection_with_token(self):
        code, body, _ = self.request('POST', '/api/inspect', '{"device_id":"demo-android"}', self.session_headers())
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)['model_status'], 'NOT_CONNECTED')

    def test_invalid_json_and_unknown_device(self):
        for body in ('invalid', '[]', '{"device_id":"other"}'):
            self.assertEqual(self.request('POST', '/api/inspect', body, self.session_headers())[0], 400)

    def test_no_write_route_or_file_traversal(self):
        self.assertEqual(self.request('POST', '/api/write', '{}', self.session_headers())[0], 404)
        self.assertEqual(self.request('GET', '/../README.md')[0], 404)

    def test_oversized_body_denied(self):
        self.assertEqual(self.request('POST', '/api/inspect', 'x' * 9000, self.session_headers())[0], 413)
