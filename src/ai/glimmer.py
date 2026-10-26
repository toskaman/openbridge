"""Pinned Meta Muse Glimmer (open weights) on a private local Ollama service with GPU/CPU offload. No cloud fallback."""
from src.ai.local_meta import LocalMetaBroker

GLIMMER_ID='muse-glimmer:30b-q4_K_M'
GLIMMER_DIGEST='de878ce33ad81d060001db1469a02eebe4d86f0ad58cfe52dc062fdcbe4464c1'  # Verified 2026-10-26: equals sha256 of the official registry manifest for 30b-q4_K_M.
GLIMMER_ENDPOINT='http://127.0.0.1:11438'


class GlimmerBroker(LocalMetaBroker):
    model_id=GLIMMER_ID
    model_digest=GLIMMER_DIGEST
    endpoint=GLIMMER_ENDPOINT
    provider='Ollama local GPU/CPU offload'
    options={'temperature':0,'num_ctx':4096,'num_predict':512}
    extra={'think':False}
    timeout=300
