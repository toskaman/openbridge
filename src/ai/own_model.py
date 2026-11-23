"""OpenBridge's own command model: the official model for understanding requests.

openbridge-intent v3 = Llama 3.2 3B Instruct + a LoRA adapter trained for OpenBridge (dev/ai_training, docs/AI_TRAINING.md),
served by the owner's local Ollama. It turns a sentence into ONE registered skill, in French, US English or UK English.
Every request path that understands text (`openbridge ask`, the app, the Companions' voice, `openbridge ha say`) tries it
first; when it is not installed, the pinned general Llama 3.2 3B (LOCAL-FAST) takes over, and the receipt says which
model answered. It is digest-pinned like the other built-in models, and it never plans or writes code: planning and
advice stay on the general models.
"""
MODEL_ID = 'openbridge-intent:latest'
MODEL_DIGEST = '5198596071c9e6664ca1dc056a9d9724d0cbb14be982da138d2c8a8c897a48f2'
ENDPOINT = 'http://127.0.0.1:11434'
VERSION = 'v3'
BASE = 'Llama 3.2 3B Instruct + LoRA'
LANGUAGES = ('fr', 'en-US', 'en-GB')


def names():
    """Ways an owner may name it on the command line (Ollama adds ':latest' itself)."""
    return {MODEL_ID, MODEL_ID.split(':')[0]}
