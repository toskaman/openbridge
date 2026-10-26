"""Pinned Meta Muse Glimmer (open weights) on a private local Ollama service with GPU/CPU offload. No cloud fallback."""
from src.ai.local_meta import LocalMetaBroker

GLIMMER_ID='muse-glimmer:30b-q4_K_M'
GLIMMER_DIGEST='PENDING_VERIFIED_PULL'  # Set only from the digest observed after the official registry pull.
GLIMMER_ENDPOINT='http://127.0.0.1:11438'


class GlimmerBroker(LocalMetaBroker):
    model_id=GLIMMER_ID
    model_digest=GLIMMER_DIGEST
    endpoint=GLIMMER_ENDPOINT
    provider='Ollama local GPU/CPU offload'
    options={'temperature':0,'num_ctx':4096,'num_predict':512}
    extra={'think':False}
    timeout=300
