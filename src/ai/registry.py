"""Fail-closed runtime model registry: every model the app can call must be an explicitly pinned Meta model."""
import json
from pathlib import Path
from urllib.parse import urlsplit

META_MODELS={'muse-spark-1.3','llama3.2:3b-instruct-q4_K_M','muse-glimmer:30b-q4_K_M'}
ALLOWED_HOSTS={'api.meta.ai','127.0.0.1'}
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
        if model not in META_MODELS:raise RegistryInvalid(f'Non-Meta or unknown runtime model rejected: {model!r}')
        if host not in ALLOWED_HOSTS:raise RegistryInvalid(f'Unapproved runtime model endpoint rejected: {host!r}')
        if host=='127.0.0.1' and entry.get('execution')!='local':raise RegistryInvalid('Loopback endpoint must be local execution')
    return {(e['model_id'],e['endpoint']) for e in calls}


def require(model_id,endpoint,path=MANIFEST):
    if (model_id,endpoint) not in load(path):
        raise RegistryInvalid(f'Model {model_id!r} at {endpoint!r} is not declared in the runtime manifest')
