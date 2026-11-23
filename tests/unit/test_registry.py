import json
import re
import tempfile
import unittest
from pathlib import Path
from src.ai import custom_provider, registry
from src.ai.local_meta import LocalMetaBroker
from src.ai.glimmer import GlimmerBroker

ROOT=Path(__file__).resolve().parents[2]


def manifest(calls):
    f=tempfile.NamedTemporaryFile('w',suffix='.json',delete=False)
    json.dump({'schema_version':1,'environment':'runtime','model_calls':calls},f);f.close();return f.name


class RegistryTests(unittest.TestCase):
    def test_shipped_manifest_is_local_only_and_covers_every_broker(self):
        declared=registry.load()
        for broker in (LocalMetaBroker,GlimmerBroker):
            self.assertIn((broker.model_id,broker.endpoint),declared)
        self.assertTrue(all(endpoint.startswith('http://127.0.0.1:') for _,endpoint in declared))

    def test_no_paid_model_is_built_in(self):
        self.assertNotIn('muse-spark-1.3',registry.META_MODELS)
        self.assertEqual(registry.ALLOWED_HOSTS,{'127.0.0.1'})
        raw=(ROOT/'config'/'runtime_models.json').read_text(encoding='utf-8')
        self.assertNotIn('api.meta.ai',raw)
        self.assertNotIn('hosted',raw)

    def test_unknown_built_in_models_rejected_R04_R05(self):
        for bad in ('gpt-6.1','claude-opus','gemini-pro','qwen2.5','deepseek-r1','muse-spark-1.3','unknown'):
            path=manifest([{'model_id':bad,'execution':'local','endpoint':'http://127.0.0.1:11437'}])
            with self.assertRaises(registry.RegistryInvalid):registry.load(path)

    def test_hosted_or_non_loopback_endpoints_rejected_R06(self):
        for host in ('https://api.openai.com/v1','https://api.anthropic.com','https://api.meta.ai/v1/chat/completions',
                     'http://10.0.0.5:11434'):
            path=manifest([{'model_id':'llama3.2:3b-instruct-q4_K_M','execution':'local','endpoint':host}])
            with self.assertRaises(registry.RegistryInvalid):registry.load(path)
        path=manifest([{'model_id':'llama3.2:3b-instruct-q4_K_M','execution':'hosted','endpoint':'http://127.0.0.1:11437'}])
        with self.assertRaises(registry.RegistryInvalid):registry.load(path)

    def test_undeclared_pair_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(registry.RegistryInvalid):
                registry.require('llama3.2:3b-instruct-q4_K_M','http://127.0.0.1:11434',providers_path=Path(d)/'p.json')

    def test_owner_connected_provider_is_accepted_only_as_declared(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'providers.json'
            entry=custom_provider.add({'name':'mine','kind':'openai','base_url':'https://example.invalid/v1',
                                       'model':'some-model'},path=path)
            registry.require('some-model',custom_provider.endpoint(entry),providers_path=path)
            with self.assertRaises(registry.RegistryInvalid):
                registry.require('other-model',custom_provider.endpoint(entry),providers_path=path)
            with self.assertRaises(registry.RegistryInvalid):
                registry.require('some-model','https://elsewhere.invalid/v1/chat/completions',providers_path=path)

    def test_runtime_source_has_no_built_in_third_party_inference_clients_R12(self):
        pattern=re.compile(r'openai\.com|anthropic|generativelanguage|googleapis\.com/v1beta|deepseek|dashscope|mistral\.ai|api\.meta\.ai|import openai|from openai',re.I)
        hits=[str(p) for p in (ROOT/'src').rglob('*.py') if pattern.search(p.read_text(encoding='utf-8'))]
        hits+=[str(p) for p in (ROOT/'src'/'ui').glob('*') if p.is_file() and pattern.search(p.read_text(encoding='utf-8'))]
        self.assertEqual(hits,[])
