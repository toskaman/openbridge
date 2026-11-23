"""Manually connected AI (src/ai/custom_provider.py) + its local HTTP API. Hermetic: temp provider
file, fake vault, and a throw-away loopback HTTP server standing in for an OpenAI-compatible API."""
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from src.ai import custom_provider as CP


class FakeVault:
    available = True

    def __init__(self):
        self.items = {}

    def put(self, name, secret):
        self.items[name] = secret

    def get(self, name):
        return self.items.get(name)

    def delete(self, name):
        self.items.pop(name, None)


def entry(**kw):
    e = {'name': 'lab', 'kind': 'openai', 'base_url': 'http://127.0.0.1:1234/v1', 'model': 'my-model'}
    e.update(kw)
    return e


class Isolated(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'ai_providers.json')
        self.vault = FakeVault()
        self._env = mock.patch.dict(os.environ, {'OPENBRIDGE_AI_PROVIDERS': self.path})
        self._vault = mock.patch.object(CP, '_vault', lambda: self.vault)
        self._env.start()
        self._vault.start()

    def tearDown(self):
        self._vault.stop()
        self._env.stop()


class Validation(unittest.TestCase):
    def test_normalises_and_fills_defaults(self):
        e = CP.validate(entry(name='Lab', base_url='http://127.0.0.1:1234/v1/'))
        self.assertEqual(e, {'name': 'lab', 'kind': 'openai', 'base_url': 'http://127.0.0.1:1234/v1',
                             'model': 'my-model', 'api_key_env': None, 'timeout_s': 60,
                             'max_tokens': 1024, 'json_mode': False})

    def test_key_is_never_accepted_in_the_file(self):
        with self.assertRaisesRegex(CP.ProviderError, 'never stored'):
            CP.validate(entry(api_key='sk-secret'))

    def test_plain_http_only_for_this_pc_or_lan(self):
        for ok in ('http://127.0.0.1:8080/v1', 'http://localhost:1234/v1', 'http://192.168.1.20:11434',
                   'http://10.0.0.5/v1', 'http://nas.local:11434', 'https://openrouter.ai/api/v1'):
            CP.validate(entry(base_url=ok))
        for bad in ('http://openrouter.ai/api/v1', 'http://8.8.8.8/v1'):
            with self.assertRaisesRegex(CP.ProviderError, 'https'):
                CP.validate(entry(base_url=bad))

    def test_rejects_credentials_query_and_bad_fields(self):
        for bad in (entry(base_url='https://user:pw@example.com/v1'), entry(base_url='https://example.com/v1?k=1'),
                    entry(base_url='ftp://example.com'), entry(kind='anthropic'), entry(name='Bad Name!'),
                    entry(model='a b'), entry(api_key_env='lower-case'), entry(timeout_s=1),
                    entry(max_tokens=True), entry(json_mode='yes'), 'not a dict'):
            with self.assertRaises(CP.ProviderError, msg=repr(bad)):
                CP.validate(bad)

    def test_execution_is_local_only_for_loopback(self):
        self.assertEqual(CP.execution(CP.validate(entry())), 'local')
        self.assertEqual(CP.execution(CP.validate(entry(base_url='http://192.168.1.20:11434'))), 'remote')
        self.assertEqual(CP.execution(CP.validate(entry(base_url='https://openrouter.ai/api/v1'))), 'remote')

    def test_endpoint_per_kind(self):
        self.assertEqual(CP.endpoint(CP.validate(entry())), 'http://127.0.0.1:1234/v1/chat/completions')
        self.assertEqual(CP.endpoint(CP.validate(entry(kind='ollama', base_url='http://127.0.0.1:11434'))),
                         'http://127.0.0.1:11434/api/chat')

    def test_extract_json_object_tolerates_fences_and_prose(self):
        self.assertEqual(CP.extract_json_object('```json\n{"a": 1}\n```'), {'a': 1})
        self.assertEqual(CP.extract_json_object('Sure! {"a": 2} hope it helps'), {'a': 2})
        for bad in ('no json here', '[1, 2]'):
            with self.assertRaises(CP.ProviderError):
                CP.extract_json_object(bad)


class Store(Isolated):
    def test_add_activate_list_remove(self):
        CP.add(entry())
        CP.add(entry(name='other', model='m2'), activate=False)
        self.assertEqual(CP.active()['name'], 'lab')
        CP.set_active('other')
        self.assertEqual(CP.active()['name'], 'other')
        with self.assertRaises(CP.ProviderError):
            CP.set_active('ghost')
        self.assertTrue(CP.declared('my-model', 'http://127.0.0.1:1234/v1/chat/completions'))
        self.assertFalse(CP.declared('my-model', 'http://127.0.0.1:9999/v1/chat/completions'))
        CP.store_key('other', 'sk-123')
        self.assertTrue(CP.remove('other'))
        self.assertIsNone(CP.active())
        self.assertEqual(self.vault.items, {})                # its key went with it
        self.assertEqual([e['name'] for e in CP.load()['providers']], ['lab'])

    def test_file_never_contains_a_key_and_view_never_returns_it(self):
        CP.add(entry())
        CP.store_key('lab', 'sk-very-secret')
        with open(self.path, encoding='utf-8') as f:
            self.assertNotIn('sk-very-secret', f.read())
        view = CP.public_view(CP.get('lab'))
        self.assertTrue(view['has_key'])
        self.assertNotIn('sk-very-secret', json.dumps(view))

    def test_broken_file_means_no_provider(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('{not json')
        self.assertIsNone(CP.active())
        self.assertFalse(CP.declared('my-model', 'x'))

    def test_key_from_env_when_vault_empty(self):
        e = CP.validate(entry(api_key_env='OB_TEST_KEY'))
        with mock.patch.dict(os.environ, {'OB_TEST_KEY': 'env-secret'}):
            self.assertEqual(CP.api_key(e), 'env-secret')
        self.assertIsNone(CP.api_key(CP.validate(entry())))


class _Fake(BaseHTTPRequestHandler):
    calls = []
    reply = {'model': 'served-model', 'choices': [{'message': {'content': 'OK'}}]}
    redirect_to = None

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).calls.append({'path': self.path, 'auth': self.headers.get('Authorization'), 'body': body})
        if type(self).redirect_to:
            self.send_response(307)
            self.send_header('Location', type(self).redirect_to)
            self.end_headers()
            return
        data = json.dumps(type(self).reply).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class LiveLoopback(Isolated):
    """Real HTTP round-trips against a loopback fake: headers, payload, redirect refusal."""

    def setUp(self):
        super().setUp()
        _Fake.calls, _Fake.redirect_to = [], None
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), _Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:%d/v1' % self.srv.server_port

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def test_round_trip_sends_bearer_from_env_and_model(self):
        e = CP.validate(entry(base_url=self.base, api_key_env='OB_TEST_KEY'))
        with mock.patch.dict(os.environ, {'OB_TEST_KEY': 'env-secret'}):
            out = CP.test(e)
        self.assertTrue(out['ok'])
        self.assertEqual(out['reported_model'], 'served-model')
        self.assertEqual(out['execution'], 'local')
        call = _Fake.calls[0]
        self.assertEqual(call['path'], '/v1/chat/completions')
        self.assertEqual(call['auth'], 'Bearer env-secret')
        self.assertEqual(call['body']['model'], 'my-model')
        self.assertEqual(call['body']['messages'][-1]['content'], 'Reply with exactly: OK')

    def test_redirect_is_refused_and_key_not_forwarded(self):
        _Fake.redirect_to = self.base + '/elsewhere'
        e = CP.validate(entry(base_url=self.base, api_key_env='OB_TEST_KEY'))
        with mock.patch.dict(os.environ, {'OB_TEST_KEY': 'env-secret'}):
            with self.assertRaises(CP.ProviderError) as cm:
                CP.ProviderTransport(e).chat([{'role': 'user', 'content': 'hi'}])
        self.assertNotIn('env-secret', str(cm.exception))
        self.assertEqual(len(_Fake.calls), 1)                 # the redirect target was never called

    def test_unexpected_shape_is_a_provider_error(self):
        _Fake.reply = {'oops': True}
        try:
            with self.assertRaisesRegex(CP.ProviderError, 'unexpected response shape'):
                CP.test(CP.validate(entry(base_url=self.base)))
        finally:
            _Fake.reply = {'model': 'served-model', 'choices': [{'message': {'content': 'OK'}}]}


class HttpApi(Isolated):
    """/api/v2/ai/providers: list, connect (key to vault), test consent gate, activate, remove."""

    def call(self, path, body=None):
        from src.runtime.api_v2 import ai_providers
        return ai_providers(path, body)

    def test_full_lifecycle(self):
        status, body = self.call('/api/v2/ai/providers')
        self.assertEqual((status, body['providers'], body['paid_models_built_in']), (200, [], False))
        status, body = self.call('/api/v2/ai/providers', dict(entry(base_url='https://llm.example.test/v1'),
                                                              api_key='sk-api-secret'))
        self.assertEqual(status, 200)
        self.assertEqual(body['active'], 'lab')
        self.assertTrue(body['provider']['has_key'])
        self.assertEqual(self.vault.items, {'ai-key-lab': 'sk-api-secret'})
        status, listing = self.call('/api/v2/ai/providers')
        self.assertNotIn('sk-api-secret', json.dumps(listing))
        # A remote provider is never contacted without explicit consent.
        with mock.patch.object(CP, 'test', side_effect=AssertionError('must not send')):
            status, body = self.call('/api/v2/ai/providers/test', {'name': 'lab'})
        self.assertEqual(status, 409)
        with mock.patch.object(CP, 'test', return_value={'ok': True}) as t:
            status, body = self.call('/api/v2/ai/providers/test', {'name': 'lab', 'consent': True})
        self.assertEqual((status, body), (200, {'ok': True}))
        t.assert_called_once()
        self.assertEqual(self.call('/api/v2/ai/providers/activate', {'name': None}), (200, {'active': None}))
        self.assertEqual(self.call('/api/v2/ai/providers/remove', {'name': 'lab'}), (200, {'removed': True}))
        self.assertEqual(self.vault.items, {})
        self.assertEqual(self.call('/api/v2/ai/providers/remove', {'name': 'lab'})[0], 404)

    def test_bad_input_is_400(self):
        self.assertEqual(self.call('/api/v2/ai/providers', dict(entry(), extra=1))[0], 400)
        self.assertEqual(self.call('/api/v2/ai/providers', entry(base_url='http://example.com/v1'))[0], 400)
        self.assertEqual(self.call('/api/v2/ai/providers', ['not', 'an', 'object'])[0], 400)
        self.assertEqual(self.call('/api/v2/ai/providers/activate', {'name': 'ghost'})[0], 400)


if __name__ == '__main__':
    unittest.main()
