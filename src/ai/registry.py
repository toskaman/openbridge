"""Fail-closed runtime model registry.

Built-in models are pinned, free and local, served by Ollama on this PC: OpenBridge's own command model
(openbridge-intent, Llama 3.2 3B + an OpenBridge LoRA adapter) and Meta open-weight models.
Anything else must have been connected explicitly by the owner (src/ai/custom_provider.py);
no paid model is built in and no unknown endpoint is ever called.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit

META_MODELS={'llama3.2:3b-instruct-q4_K_M','muse-glimmer:30b-q4_K_M'}
OWN_MODELS={'openbridge-intent:latest'}
BUILT_IN_MODELS=META_MODELS|OWN_MODELS
ALLOWED_HOSTS={'127.0.0.1'}
MANIFEST=Path(__file__).resolve().parents[2]/'config'/'runtime_models.json'


class RegistryInvalid(ValueError):
    pass


def load(path=MANIFEST):
    try:data=json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):raise RegistryInvalid('Runtime model manifest unreadable') from None
    calls=data.get('model_calls') if isinstance(data,dict) else None
    if data.get('environment')!='runtime' or not isinstance(calls,list) or not calls:
        raise RegistryInvalid('Runtime model manifest malformed')
    for entry in calls:
        model=entry.get('model_id');host=urlsplit(entry.get('endpoint','')).hostname
        if model not in BUILT_IN_MODELS:raise RegistryInvalid(f'Unknown built-in runtime model rejected: {model!r}')
        if host not in ALLOWED_HOSTS:raise RegistryInvalid(f'Unapproved runtime model endpoint rejected: {host!r}')
        if entry.get('execution')!='local':raise RegistryInvalid('Built-in models must run locally')
    return {(e['model_id'],e['endpoint']) for e in calls}


def require(model_id,endpoint,path=MANIFEST,providers_path=None):
    """Accept a pinned built-in local model, or a provider the owner connected by hand."""
    if (model_id,endpoint) in load(path):
        return
    from src.ai import custom_provider
    if custom_provider.declared(model_id,endpoint,providers_path):
        return
    raise RegistryInvalid(f'Model {model_id!r} at {endpoint!r} is not declared (neither built in nor connected by the owner)')
