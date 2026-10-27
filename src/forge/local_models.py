"""Explicit optional isolated CPU Meta route; no automatic fallback or download."""
from src.ai.glimmer import GlimmerBroker

class IsolatedGlimmerCPU(GlimmerBroker):
    endpoint='http://127.0.0.1:11439'
    provider='Ollama isolated local CPU'
    options={'temperature':0,'num_gpu':0,'num_ctx':1024,'num_batch':32,'num_thread':4,'num_predict':384}
    timeout=180
