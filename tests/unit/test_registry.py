import json
import re
import tempfile
import unittest
from pathlib import Path
from src.ai import registry
from src.ai.local_meta import LocalMetaBroker
from src.ai.glimmer import GlimmerBroker

ROOT=Path(__file__).resolve().parents[2]


def manifest(calls):
    f=tempfile.NamedTemporaryFile('w',suffix='.json',delete=False)
    json.dump({'schema_version':1,'environment':'runtime','model_calls':calls},f);f.close();return f.name


class RegistryTests(unittest.TestCase):
    def test_shipped_manifest_is_meta_only_and_covers_every_broker(self):
        declared=registry.load()
        for broker in (LocalMetaBroker,GlimmerBroker):
            self.assertIn((broker.model_id,broker.endpoint),declared)
        from src.ai import broker as cloud
        self.assertIn((cloud.MODEL_ID,cloud.ENDPOINT),declared)

    def test_non_meta_models_rejected_R04_R05(self):
        for bad in ('gpt-6.1','claude-opus','gemini-pro','qwen2.5','deepseek-r1','unknown'):
            path=manifest([{'model_id':bad,'execution':'hosted','endpoint':'https://api.meta.ai/v1/chat/completions'}])
            with self.assertRaises(registry.RegistryInvalid):registry.load(path)

    def test_non_meta_endpoint_rejected_R06(self):
        for host in ('https://api.openai.com/v1','https://api.anthropic.com','http://10.0.0.5:11434'):
            path=manifest([{'model_id':'muse-spark-1.3','execution':'hosted','endpoint':host}])
            with self.assertRaises(registry.RegistryInvalid):registry.load(path)

    def test_undeclared_pair_rejected(self):
        with self.assertRaises(registry.RegistryInvalid):registry.require('llama3.2:3b-instruct-q4_K_M','http://127.0.0.1:11434')

    def test_runtime_source_has_no_non_meta_inference_clients_R12(self):
        pattern=re.compile(r'openai\.com|anthropic|generativelanguage|googleapis\.com/v1beta|deepseek|dashscope|mistral\.ai|import openai|from openai',re.I)
        hits=[str(p) for p in (ROOT/'src').rglob('*.py') if pattern.search(p.read_text(encoding='utf-8'))]
        hits+=[str(p) for p in (ROOT/'src'/'ui').glob('*') if p.is_file() and pattern.search(p.read_text(encoding='utf-8'))]
        self.assertEqual(hits,[])
