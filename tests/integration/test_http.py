import http.client
import json
import threading
import unittest
from unittest.mock import patch
from src.server import create_server


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(0)
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

    def test_real_device_data_cannot_be_sent_to_model(self):
        code, _, _ = self.request('POST', '/api/recommend', '{"source":"android","device_id":"some-device"}', self.session_headers())
        self.assertEqual(code, 400)

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
