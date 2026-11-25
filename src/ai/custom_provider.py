"""Manually connected AI providers: bring your own model or API.

OpenBridge ships no paid model. An owner can connect, by hand, any model endpoint they run or
subscribe to:

* ``openai`` – any OpenAI-compatible ``/chat/completions`` server: LM Studio, llama.cpp server,
  vLLM, LocalAI, Jan, OpenRouter, or a hosted provider of the owner's choice.
* ``ollama`` – an Ollama server (``/api/chat``), on this PC or on the LAN.

Rules
* The provider list lives outside the repository, in the per-user data folder
  (``ai_providers.json``), and only the owner edits it (``openbridge ai …`` or the local UI).
* API keys are never written to that file. They come from the OS vault (Windows DPAPI entry
  ``ai-key-<name>``) or from the environment variable named in ``api_key_env``, and are never
  returned by the API or shown in logs.
* Plain ``http://`` is accepted only for loopback / private-LAN hosts; anything else must be HTTPS.
* A provider that is not on this PC (``execution == "remote"``) stays behind the explicit
  consent gate: OpenBridge never sends text to it on its own.
* No proxies from the environment, no redirects, bounded responses and timeouts.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from src.ai.broker import NoRedirect

SCHEMA_VERSION = 1
KINDS = ('openai', 'ollama')
NAME_RX = re.compile(r'^[a-z0-9][a-z0-9-]{0,31}$')
MODEL_RX = re.compile(r'^[A-Za-z0-9._:/@+\-]{1,128}$')
ENV_RX = re.compile(r'^[A-Z_][A-Z0-9_]{0,63}$')
MAX_RESPONSE = 512 * 1024
DEFAULT_TIMEOUT_S = 60
DEFAULT_MAX_TOKENS = 1024


class ProviderError(ValueError):
    """Invalid provider definition, missing provider, or a refused/failed call."""


# ---------------------------------------------------------------- storage

def private_root() -> Path:
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share'))) / 'OpenBridge'


def default_path() -> Path:
    override = os.environ.get('OPENBRIDGE_AI_PROVIDERS')
    return Path(override) if override else private_root() / 'ai_providers.json'


def _empty() -> dict:
    return {'schema_version': SCHEMA_VERSION, 'active': None, 'providers': []}


def load(path=None) -> dict:
    p = Path(path) if path else default_path()
    try:
        doc = json.loads(p.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return _empty()
    except (OSError, ValueError):
        raise ProviderError('AI provider file unreadable: %s' % p) from None
    if not isinstance(doc, dict) or doc.get('schema_version') != SCHEMA_VERSION \
            or not isinstance(doc.get('providers'), list):
        raise ProviderError('AI provider file malformed: %s' % p)
    providers = [validate(e) for e in doc['providers']]
    names = [e['name'] for e in providers]
    if len(set(names)) != len(names):
        raise ProviderError('duplicate provider names')
    active = doc.get('active')
    if active is not None and active not in names:
        active = None
    return {'schema_version': SCHEMA_VERSION, 'active': active, 'providers': providers}


def save(doc: dict, path=None) -> Path:
    p = Path(path) if path else default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, p)
    return p


# ---------------------------------------------------------------- validation

def _host_is_private(host: str) -> bool:
    from src.fabric import netguard
    return netguard.local_host(host)


def _host_is_loopback(host: str) -> bool:
    if host == 'localhost' or host.endswith('.localhost'):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate(entry) -> dict:
    """Return a normalised provider entry or raise ProviderError. Never contains a secret."""
    if not isinstance(entry, dict):
        raise ProviderError('provider must be an object')
    if 'api_key' in entry:
        raise ProviderError('API keys are never stored in the provider file: use the vault or api_key_env')
    name = str(entry.get('name', '')).strip().lower()
    if not NAME_RX.match(name):
        raise ProviderError('name: 1-32 chars, lowercase letters, digits and "-"')
    kind = entry.get('kind')
    if kind not in KINDS:
        raise ProviderError('kind must be one of %s' % ', '.join(KINDS))
    base = str(entry.get('base_url', '')).strip().rstrip('/')
    u = urlsplit(base)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password \
            or u.query or u.fragment:
        raise ProviderError('base_url must be http(s)://host[:port][/path] without credentials or query')
    if u.scheme == 'http' and not _host_is_private(u.hostname):
        raise ProviderError('plain http is only allowed for this PC or the local network; use https')
    model = str(entry.get('model', '')).strip()
    if not MODEL_RX.match(model):
        raise ProviderError('model: 1-128 chars [A-Za-z0-9._:/@+-]')
    env = entry.get('api_key_env')
    if env not in (None, ''):
        if not isinstance(env, str) or not ENV_RX.match(env):
            raise ProviderError('api_key_env must be an environment variable name (A-Z, 0-9, _)')
    else:
        env = None
    timeout = entry.get('timeout_s', DEFAULT_TIMEOUT_S)
    max_tokens = entry.get('max_tokens', DEFAULT_MAX_TOKENS)
    for label, value, lo, hi in (('timeout_s', timeout, 5, 300), ('max_tokens', max_tokens, 64, 8192)):
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            raise ProviderError('%s must be an integer in %d..%d' % (label, lo, hi))
    json_mode = entry.get('json_mode', False)
    if not isinstance(json_mode, bool):
        raise ProviderError('json_mode must be true or false')
    return {'name': name, 'kind': kind, 'base_url': base, 'model': model, 'api_key_env': env,
            'timeout_s': timeout, 'max_tokens': max_tokens, 'json_mode': json_mode}


def execution(entry: dict) -> str:
    """'local' when the provider runs on this PC (loopback), else 'remote' (LAN or internet)."""
    return 'local' if _host_is_loopback(urlsplit(entry['base_url']).hostname) else 'remote'


def endpoint(entry: dict) -> str:
    return entry['base_url'] + ('/api/chat' if entry['kind'] == 'ollama' else '/chat/completions')


# ---------------------------------------------------------------- secrets

def vault_name(name: str) -> str:
    return 'ai-key-' + name


def _vault():
    from src.fabric.credential_vault import Vault
    return Vault()


def api_key(entry: dict, vault=None):
    """The owner's key for this provider, or None (keyless local servers). Never logged."""
    try:
        v = vault if vault is not None else _vault()
        secret = v.get(vault_name(entry['name']))
    except Exception:
        secret = None
    if not secret and entry.get('api_key_env'):
        secret = os.environ.get(entry['api_key_env']) or None
    return secret


def store_key(name: str, secret: str, vault=None) -> None:
    v = vault if vault is not None else _vault()
    if not getattr(v, 'available', False):
        raise ProviderError('No OS secret store on this platform: set the key in an environment '
                            'variable and declare it with api_key_env')
    if not isinstance(secret, str) or not secret.strip() or len(secret) > 4096:
        raise ProviderError('invalid API key')
    v.put(vault_name(name), secret.strip())


def forget_key(name: str, vault=None) -> None:
    try:
        (vault if vault is not None else _vault()).delete(vault_name(name))
    except Exception:
        pass


def public_view(entry: dict, vault=None) -> dict:
    """Safe description for UI / API / CLI: never the key itself."""
    if entry is None:
        return None
    out = dict(entry)
    out['endpoint'] = endpoint(entry)
    out['execution'] = execution(entry)
    out['has_key'] = api_key(entry, vault) is not None
    return out


# ---------------------------------------------------------------- registry of the owner's choices

def add(entry: dict, activate: bool = True, path=None) -> dict:
    clean = validate(entry)
    doc = load(path)
    doc['providers'] = [e for e in doc['providers'] if e['name'] != clean['name']] + [clean]
    if activate or doc['active'] is None:
        doc['active'] = clean['name']
    save(doc, path)
    return clean


def remove(name: str, path=None, vault=None) -> bool:
    doc = load(path)
    before = len(doc['providers'])
    doc['providers'] = [e for e in doc['providers'] if e['name'] != name]
    if doc['active'] == name:
        doc['active'] = None
    save(doc, path)
    forget_key(name, vault)
    return len(doc['providers']) != before


def set_active(name, path=None) -> None:
    doc = load(path)
    if name is not None and name not in [e['name'] for e in doc['providers']]:
        raise ProviderError('unknown provider %r' % name)
    doc['active'] = name
    save(doc, path)


def get(name: str, path=None):
    return next((e for e in load(path)['providers'] if e['name'] == name), None)


def active(path=None):
    """The active provider entry, or None. A broken file is treated as 'no provider'."""
    try:
        doc = load(path)
    except ProviderError:
        return None
    return next((e for e in doc['providers'] if e['name'] == doc['active']), None)


def declared(model_id: str, url: str, path=None) -> bool:
    """True when (model, endpoint) was explicitly connected by the owner."""
    try:
        doc = load(path)
    except ProviderError:
        return False
    return any(e['model'] == model_id and endpoint(e) == url for e in doc['providers'])


# ---------------------------------------------------------------- transport

class ProviderTransport:
    """Chat with one connected provider. ``send`` is injectable for tests."""

    def __init__(self, entry: dict, send=None, vault=None):
        self.entry = validate(entry)
        self.model_id = self.entry['model']
        self.endpoint = endpoint(self.entry)
        self._send = send or self._http
        self._vault = vault

    def _http(self, url, payload, headers, timeout):
        req = Request(url, data=json.dumps(payload).encode(), method='POST', headers=headers)
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=timeout) as resp:
            data = resp.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise ProviderError('provider response too large')
        return json.loads(data)

    def _payload(self, messages, json_mode, max_tokens):
        e = self.entry
        if e['kind'] == 'ollama':
            body = {'model': e['model'], 'messages': messages, 'stream': False,
                    'options': {'temperature': 0, 'num_predict': max_tokens}}
            if json_mode:
                body['format'] = 'json'
            return body
        body = {'model': e['model'], 'messages': messages, 'temperature': 0, 'max_tokens': max_tokens}
        if json_mode and e['json_mode']:
            body['response_format'] = {'type': 'json_object'}
        return body

    def chat(self, messages, json_mode=False, max_tokens=None):
        """Return (text, raw_response). Raises ProviderError on any failure."""
        e = self.entry
        headers = {'Content-Type': 'application/json'}
        key = api_key(e, self._vault)
        if key:
            headers['Authorization'] = 'Bearer ' + key
        payload = self._payload(messages, json_mode, max_tokens or e['max_tokens'])
        try:
            raw = self._send(self.endpoint, payload, headers, e['timeout_s'])
        except ProviderError:
            raise
        except Exception as exc:
            # The message never echoes the key or the request body.
            raise ProviderError('provider call failed (%s)' % type(exc).__name__) from None
        try:
            if e['kind'] == 'ollama':
                text = raw['message']['content']
            else:
                text = raw['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError):
            raise ProviderError('provider returned an unexpected response shape') from None
        if not isinstance(text, str) or not text.strip():
            raise ProviderError('provider returned no content')
        return text, raw

    def chat_json(self, prompt, system='Reply with ONLY a JSON object matching the requested schema.'):
        text, raw = self.chat([{'role': 'system', 'content': system},
                               {'role': 'user', 'content': prompt}], json_mode=True)
        return extract_json_object(text), raw


def extract_json_object(text: str) -> dict:
    """Parse a JSON object, tolerating ```json fences or leading prose."""
    if len(text) > 65536:
        raise ProviderError('reply too long')
    s = text.strip()
    if s.startswith('```'):
        s = s.strip('`')
        s = s[4:] if s.lower().startswith('json') else s
    try:
        out = json.loads(s)
    except ValueError:
        start, end = s.find('{'), s.rfind('}')
        if start < 0 or end <= start:
            raise ProviderError('reply is not JSON') from None
        try:
            out = json.loads(s[start:end + 1])
        except ValueError:
            raise ProviderError('reply is not JSON') from None
    if not isinstance(out, dict):
        raise ProviderError('reply is not a JSON object')
    return out


def test(entry: dict, send=None, vault=None) -> dict:
    """Tiny round-trip so the owner can check URL, model and key. Sends one fixed sentence only."""
    t = ProviderTransport(entry, send=send, vault=vault)
    started = time.monotonic()
    text, raw = t.chat([{'role': 'user', 'content': 'Reply with exactly: OK'}], max_tokens=64)
    return {'ok': 'ok' in text.strip().lower()[:20], 'reply': text.strip()[:80],
            'seconds': round(time.monotonic() - started, 2), 'model': t.model_id,
            'endpoint': t.endpoint, 'execution': execution(t.entry),
            'reported_model': raw.get('model') if isinstance(raw, dict) else None}
