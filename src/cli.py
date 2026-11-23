"""OpenBridge CLI: the same core as the GUI, from a terminal.

In-process mode builds the real server core (adapters, router, executor,
journal) without serving HTTP; every handler calls the same functions as
the GUI's /api/v2 routes, so parity holds by construction. Client mode
(--server URL) talks HTTP to a running server for cross-process state.

Headless-safe: only stdlib + src.* imports. No GUI dependency is loaded.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import URLError, HTTPError

CLI_VERSION = 1
NAME = 'OpenBridge'
EXIT = {'ok': 0, 'internal': 1, 'args': 2, 'dep': 3, 'auth': 4, 'permission': 5,
        'device': 6, 'timeout': 7, 'inference': 8, 'verify': 9, 'uncertain': 10,
        'cancelled': 11}
PRIVILEGED = {'approvals approve', 'workflows run', 'capabilities publish',
              'capabilities revoke', 'sessions undo', 'devices pair'}


class CliError(Exception):
    def __init__(self, exit_name, code, message, data=None):
        super().__init__(message)
        self.exit_name = exit_name
        self.code = code
        self.data = data or {}


def private_root():
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / '.local' / 'share')
    return Path(base) / 'OpenBridge'


def evidence_dir(args):
    if getattr(args, 'evidence_dir', None):
        return Path(args.evidence_dir)
    return Path(os.environ.get('OPENBRIDGE_EVIDENCE_DIR') or (private_root() / 'evidence'))


# ---------------- output ----------------

def _human(data, indent=0):
    pad = '  ' * indent
    if isinstance(data, dict):
        lines = []
        for key in sorted(data):
            value = data[key]
            if isinstance(value, (dict, list)) and value:
                lines.append('%s%s:' % (pad, key))
                lines.extend(_human(value, indent + 1))
            else:
                lines.append('%s%s: %s' % (pad, key, value))
        return lines
    if isinstance(data, list):
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append('%s-' % pad)
                lines.extend(_human(item, indent + 1))
            else:
                lines.append('%s- %s' % (pad, item))
        return lines
    return ['%s%s' % (pad, data)]


def emit(args, command, ok, data, error=None):
    if getattr(args, 'quiet', False) and ok:
        return
    if getattr(args, 'json', False):
        doc = {'cli_version': CLI_VERSION, 'command': command, 'ok': ok, 'data': data,
               'error': error}
        sys.stdout.write(json.dumps(doc, default=str) + '\n')
    elif ok:
        for line in _human(data):
            sys.stdout.write(line + '\n')
    else:
        sys.stderr.write('error [%s]: %s\n' % (error['code'], error['message']))


def fail(args, command, exc):
    emit(args, command, False, exc.data, {'code': exc.code, 'message': str(exc)})
    return EXIT[exc.exit_name]


# ---------------- core access ----------------

class Core:
    """One in-process server core per CLI invocation (never served)."""

    def __init__(self):
        self.server = None

    def __enter__(self):
        from src.server import create_server
        self.server = create_server(0)
        return self.server

    def __exit__(self, *exc):
        try:
            if self.server is not None:
                self.server.server_close()
        except (OSError, ValueError):
            pass
        return False


def api_get(args, server, path, query=None):
    if getattr(args, 'server_url', None):
        return http_call(args, 'GET', path, query or {})
    from src.runtime import api_v2
    return api_v2.get(server, path, query or {})


def api_post(args, server, path, body):
    if getattr(args, 'server_url', None):
        return http_call(args, 'POST', path, body)
    from src.runtime import api_v2
    return api_v2.post(server, path, body)


def http_call(args, method, path, body):
    url = getattr(args, 'server_url').rstrip('/') + path
    data = None
    if method == 'POST':
        data = json.dumps(body).encode()
    req = Request(url, data=data, headers={'Content-Type': 'application/json'}, method=method)
    timeout = getattr(args, 'timeout', None) or 30
    try:
        with build_opener(ProxyHandler({})).open(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except ValueError:
            return e.code, {'error': 'HTTP %s' % e.code}
    except (URLError, socket.timeout, TimeoutError) as e:
        raise CliError('device', 'SERVER_UNREACHABLE', 'Server %s unreachable: %s'
                       % (getattr(args, 'server_url'), e))


def check_status(status, body):
    if status == 200:
        return body
    if status in (400, 404):
        raise CliError('args', 'BAD_REQUEST', body.get('error', 'bad request'))
    if status in (401, 403):
        raise CliError('auth', 'FORBIDDEN', body.get('error', 'forbidden'))
    if status == 409:
        raise CliError('permission', 'BLOCKED', body.get('error', 'blocked'))
    raise CliError('internal', 'CORE_ERROR', body.get('error', 'status %s' % status))


# ---------------- model probes ----------------

def manifest_endpoints():
    from urllib.parse import urlsplit
    from src.ai import registry
    try:
        pairs = sorted(registry.load())
    except registry.RegistryInvalid:
        return {}
    out = {}
    for model, endpoint in pairs:
        bare = urlsplit(endpoint).path in ('', '/')
        # Prefer the bare-host entry when a model has several endpoints.
        if model not in out or bare:
            out[model] = endpoint
    return out


def registry_allows(model, endpoint):
    from src.ai import registry
    try:
        return (model, endpoint) in registry.load()
    except registry.RegistryInvalid:
        return False


def tags_probe(endpoint, timeout=3):
    """Real /api/tags probe. Returns (reachable, [model ids]). Never raises."""
    try:
        req = Request(endpoint + '/api/tags', method='GET')
        with build_opener(ProxyHandler({})).open(req, timeout=timeout) as resp:
            doc = json.loads(resp.read().decode('utf-8'))
        models = [m.get('name', '') for m in doc.get('models', [])]
        return True, models
    except Exception:
        return False, []


def connected_ai():
    """The owner's active manually connected AI (public view, no secret), or None."""
    from src.ai import custom_provider
    try:
        return custom_provider.public_view(custom_provider.active())
    except Exception:
        return None


def custom_availability(avail=None):
    entry = connected_ai()
    out = dict(avail or {})
    out.update({'custom': entry is not None, 'custom_model': entry['model'] if entry else None,
                'custom_execution': entry['execution'] if entry else None})
    return out


def local_availability():
    from src.ai.local_meta import MODEL_ID as LLAMA_ID, LOCAL_ENDPOINT as LLAMA_EP
    from src.ai.glimmer import GLIMMER_ID, GLIMMER_ENDPOINT
    endpoints = manifest_endpoints()
    fast_ep = endpoints.get(LLAMA_ID, LLAMA_EP)
    qual_ep = endpoints.get(GLIMMER_ID, GLIMMER_ENDPOINT)
    fast_up, fast_models = tags_probe(fast_ep)
    qual_up, qual_models = tags_probe(qual_ep)
    return {'local_fast': fast_up and any(LLAMA_ID.split(':')[0] in m for m in fast_models),
            'local_quality': qual_up and any('glimmer' in m.lower() for m in qual_models),
            'endpoints': {'LOCAL-FAST': fast_ep, 'LOCAL-QUALITY': qual_ep},
            'reachable': {'LOCAL-FAST': fast_up, 'LOCAL-QUALITY': qual_up}}


class OllamaClient:
    """Minimal pinned chat client implementing the forge generate() contract.

    LOCAL-* tiers use the pinned local models; CUSTOM uses the owner's connected AI."""

    def __init__(self, temperature=0):
        self.temperature = temperature

    def _generate_custom(self, prompt, opts):
        from src.ai import custom_provider
        entry = custom_provider.active()
        if entry is None:
            return False, {'status': 'CUSTOM_PROVIDER_MISSING', 'reason': 'connect an AI with `openbridge ai add`'}
        try:
            text, raw = custom_provider.ProviderTransport(entry).chat(
                [{'role': 'user', 'content': prompt}], json_mode=False)
        except custom_provider.ProviderError as e:
            return False, {'status': 'INFERENCE_FAILED', 'reason': str(e)[:160]}
        usage = raw.get('usage', {}) if isinstance(raw, dict) else {}
        return True, {'text': text, 'model': entry['model'], 'usage': usage if isinstance(usage, dict) else {}}

    def generate(self, tier, prompt, opts):
        from src.ai.local_meta import MODEL_ID as LLAMA_ID
        from src.ai.glimmer import GLIMMER_ID
        avail = local_availability()
        if tier == 'CUSTOM':
            return self._generate_custom(prompt, opts)
        model = {'LOCAL-FAST': LLAMA_ID, 'LOCAL-QUALITY': GLIMMER_ID}.get(tier)
        if model is None:
            return False, {'status': 'TIER_REJECTED', 'reason': 'unknown tier'}
        endpoint = avail['endpoints'][tier]
        if not avail['reachable'][tier]:
            return False, {'status': 'MODEL_NOT_FOUND', 'reason': endpoint + ' unreachable'}
        if not registry_allows(model, endpoint):
            return False, {'status': 'MODEL_BLOCKED',
                           'reason': 'endpoint not in runtime manifest'}
        payload = {'model': model, 'stream': False, 'think': False,
                   'messages': [{'role': 'user', 'content': prompt}],
                   'options': {'temperature': self.temperature, 'num_predict': 2048}}
        try:
            req = Request(endpoint + '/api/chat', data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
            max_s = (opts or {}).get('max_s', 120)
            with build_opener(ProxyHandler({})).open(req, timeout=max_s) as resp:
                doc = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return False, {'status': 'INFERENCE_FAILED', 'reason': str(e)[:120]}
        text = (doc.get('message') or {}).get('content', '')
        return True, {'text': text, 'usage': {'eval_count': doc.get('eval_count'),
                                             'total_duration_ns': doc.get('total_duration_ns')}}


# ---------------- pending approvals ----------------

def pending_path():
    return private_root() / 'cli_pending.json'


class _FileLock:
    """Cross-process exclusive lock (concurrent GUI/CLI clients)."""

    def __init__(self, path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, 'a+b')
        try:
            import msvcrt
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
        except (ImportError, OSError):
            try:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (ImportError, OSError):
                pass
        return self.handle

    def __exit__(self, *exc):
        try:
            try:
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            except (ImportError, OSError):
                try:
                    import fcntl
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                except (ImportError, OSError):
                    pass
        finally:
            try:
                self.handle.close()
            except OSError:
                pass
        return False


_PENDING_THREAD_LOCK = threading.Lock()


def pending_load():
    try:
        return json.loads(pending_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def pending_save(rows):
    path = pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=1), encoding='utf-8')


def pending_mutate(func):
    """Atomic read-modify-write of the pending store (threads + processes)."""
    with _PENDING_THREAD_LOCK:
        with _FileLock(pending_path().with_suffix('.lock')):
            rows = pending_load()
            result = func(rows)
            pending_save(rows)
            return result


def preview_hash(preview):
    return hashlib.sha256(json.dumps(preview, sort_keys=True, default=str).encode()).hexdigest()[:16]


def require_consent(args, expected_hash, label):
    if getattr(args, 'yes', False):
        raise CliError('permission', 'CONSENT_REQUIRED',
                       '--yes cannot bypass mandatory consent for %s; pass --consent %s'
                       % (label, expected_hash))
    if getattr(args, 'consent', None) != expected_hash:
        raise CliError('permission', 'CONSENT_REQUIRED',
                       '%s needs explicit preview-bound consent: re-run with --consent %s'
                       % (label, expected_hash))


# ---------------- version / doctor / init ----------------

def cmd_version(args):
    return {'name': NAME, 'cli_version': CLI_VERSION, 'python': platform.python_version(),
            'platform': '%s %s' % (platform.system(), platform.machine()), 'core': 'ok'}


def cmd_init(args):
    root = private_root()
    created = []
    for path in (root, evidence_dir(args), root / 'capabilities'):
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path))
    return {'private_root': str(root), 'evidence_dir': str(evidence_dir(args)), 'created': created}


def cmd_doctor(args):
    from src.runtime.readiness import REQUIRED, collect
    avail = local_availability()
    probes = {}
    try:
        with Core():
            probes['core'] = 'READY'
    except Exception:
        probes['core'] = 'INVALID'
    probes['os'] = 'READY' if platform.system() in ('Windows', 'Linux', 'Darwin') else 'INCOMPATIBLE'
    probes['local_fast'] = 'READY' if avail['local_fast'] else 'MODEL_NOT_FOUND'
    probes['local_quality'] = 'READY' if avail['local_quality'] else 'MODEL_NOT_FOUND'
    probes['custom_ai'] = 'READY' if connected_ai() else 'MISSING'
    probes['devices'] = 'READY' if shutil.which('adb') else 'MISSING'
    try:
        dest = evidence_dir(args)
        dest.mkdir(parents=True, exist_ok=True)
        probe = dest / '.writetest'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
        probes['evidence'] = 'READY'
        free_gb = shutil.disk_usage(str(dest)).free / 1e9
        probes['storage'] = 'READY' if free_gb >= 1.0 else 'INSUFFICIENT_RESOURCES'
    except OSError:
        probes['evidence'] = 'INVALID'
        probes['storage'] = 'NOT_TESTED'
    report = collect(probes)
    split = collect(probes, required=REQUIRED)
    report['required_global'] = split['global']
    report['required'] = split['required']
    report['optional'] = split['optional']
    report['detail'] = {'endpoints': avail['endpoints'], 'os': platform.system(),
                        'evidence_dir': str(evidence_dir(args))}
    return report


# ---------------- models ----------------

def official_model_status():
    """OpenBridge's own command model: installed, and the pinned version (digest)?"""
    from src.ai import own_model
    from src.runtime.nl_router import OllamaIntentTransport
    up, models = tags_probe(own_model.ENDPOINT)
    present = own_model.MODEL_ID in models
    pinned = present and OllamaIntentTransport(own_model.MODEL_ID, own_model.ENDPOINT, digest=own_model.MODEL_DIGEST).ready()
    return {'model': own_model.MODEL_ID, 'version': own_model.VERSION, 'base': own_model.BASE,
            'languages': list(own_model.LANGUAGES), 'endpoint': own_model.ENDPOINT, 'reachable': up,
            'installed': present, 'pinned_digest_match': bool(pinned),
            'role': 'understands requests (ask, the app, Companion voice, ha say); Llama 3.2 3B takes over when absent',
            'install': None if present else 'see docs/AI_TRAINING.md (build the adapter, then `ollama create openbridge-intent`)'}


def cmd_models_list(args):
    from src.ai import registry
    avail = local_availability()
    try:
        manifest = [{'model_id': m, 'endpoint': e} for m, e in sorted(registry.load())]
    except registry.RegistryInvalid:
        manifest = []
    return {'official_command_model': official_model_status(),
            'pinned': sorted(registry.BUILT_IN_MODELS), 'manifest': manifest,
            'paid_models_built_in': False, 'connected_ai': connected_ai(),
            'availability': {'local_fast': avail['local_fast'],
                             'local_quality': avail['local_quality'],
                             'custom': connected_ai() is not None}}


def cmd_models_status(args):
    from src.ai.router import TIERS
    avail = local_availability()
    return {'tiers': list(TIERS), 'official_command_model': official_model_status(),
            'availability': {'local_fast': avail['local_fast'],
                             'local_quality': avail['local_quality'],
                             'custom': connected_ai() is not None},
            'connected_ai': connected_ai()}


def _tiny_chat(endpoint, model, prompt, timeout):
    payload = {'model': model, 'stream': False, 'think': False,
               'messages': [{'role': 'user', 'content': prompt}],
               'options': {'temperature': 0, 'num_predict': 128}}
    req = Request(endpoint + '/api/chat', data=json.dumps(payload).encode(),
                  headers={'Content-Type': 'application/json'}, method='POST')
    start = time.monotonic()
    with build_opener(ProxyHandler({})).open(req, timeout=timeout) as resp:
        doc = json.loads(resp.read().decode('utf-8'))
    elapsed = time.monotonic() - start
    text = (doc.get('message') or {}).get('content', '')
    return {'text': text[:200], 'seconds': round(elapsed, 2),
            'eval_count': doc.get('eval_count'), 'model': doc.get('model')}


def cmd_models_test(args):
    from src.ai.local_meta import MODEL_ID as LLAMA_ID
    provider = getattr(args, 'provider', 'local') or 'local'
    if provider in ('custom', 'connected'):
        return cmd_ai_test(args)
    if provider != 'local':
        raise CliError('args', 'BAD_PROVIDER', 'provider must be local or custom (no paid model is built in)')
    avail = local_availability()
    ep = avail['endpoints']['LOCAL-FAST']
    up, models = tags_probe(ep)
    data = {'provider': 'local', 'endpoint': ep, 'reachable': up, 'tags': models,
            'pinned_present': avail['local_fast']}
    if getattr(args, 'deep', False):
        if not avail['local_fast']:
            raise CliError('inference', 'MODEL_NOT_FOUND', 'LOCAL-FAST pinned model not served.')
        try:
            data['generation'] = _tiny_chat(ep, LLAMA_ID, 'Reply with exactly: OK',
                                            getattr(args, 'timeout', None) or 120)
        except Exception as e:
            raise CliError('inference', 'INFERENCE_FAILED', 'Local generation failed: %s' % e)
    if not up:
        raise CliError('inference', 'MODEL_NOT_FOUND', 'Local endpoint %s unreachable.' % ep,
                       data=data)
    return data


def cmd_models_benchmark(args):
    from src.ai.local_meta import MODEL_ID as LLAMA_ID
    from src.ai.glimmer import GLIMMER_ID
    avail = local_availability()
    rows = []
    for tier, model in (('LOCAL-FAST', LLAMA_ID), ('LOCAL-QUALITY', GLIMMER_ID)):
        ep = avail['endpoints'][tier]
        key = 'local_fast' if tier == 'LOCAL-FAST' else 'local_quality'
        if not avail[key]:
            rows.append({'tier': tier, 'status': 'MODEL_NOT_FOUND', 'endpoint': ep})
            continue
        samples = []
        try:
            for _ in range(3):
                samples.append(_tiny_chat(ep, model, 'Reply with exactly: OK',
                                          getattr(args, 'timeout', None) or 180)['seconds'])
        except Exception as e:
            rows.append({'tier': tier, 'status': 'INFERENCE_FAILED', 'reason': str(e)[:120]})
            continue
        rows.append({'tier': tier, 'status': 'READY', 'endpoint': ep, 'n': 3,
                     'seconds': samples, 'mean_s': round(sum(samples) / len(samples), 2)})
    rows.append({'tier': 'CUSTOM', 'status': 'SKIPPED',
                 'reason': 'your connected AI is never benchmarked automatically: use `openbridge ai test`'})
    return {'rows': rows, 'note': 'n=3 tiny generations; not statistically meaningful'}


# ---------------- ai (manually connected providers) ----------------

def cmd_ai_list(args):
    from src.ai import custom_provider as CP
    try:
        doc = CP.load()
    except CP.ProviderError as e:
        raise CliError('args', 'PROVIDERS_INVALID', str(e))
    return {'active': doc['active'], 'paid_models_built_in': False, 'file': str(CP.default_path()),
            'providers': [CP.public_view(e) for e in doc['providers']]}


def cmd_ai_add(args):
    """Connect a model/API by hand. The key comes from a prompt (OS vault) or an env var, never from argv."""
    from src.ai import custom_provider as CP
    entry = {'name': getattr(args, 'name', None) or '', 'kind': getattr(args, 'kind', None) or 'openai',
             'base_url': getattr(args, 'base_url', None) or '', 'model': getattr(args, 'model', None) or '',
             'api_key_env': getattr(args, 'api_key_env', None),
             'timeout_s': getattr(args, 'timeout_s', None) or CP.DEFAULT_TIMEOUT_S,
             'max_tokens': getattr(args, 'max_tokens', None) or CP.DEFAULT_MAX_TOKENS,
             'json_mode': bool(getattr(args, 'json_mode', False))}
    try:
        clean = CP.validate(entry)
        if getattr(args, 'store_key', False):
            import getpass
            CP.store_key(clean['name'], getpass.getpass('API key for %s (kept in the OS vault): ' % clean['name']))
        CP.add(clean, activate=not getattr(args, 'no_activate', False))
    except CP.ProviderError as e:
        raise CliError('args', 'PROVIDER_INVALID', str(e))
    view = CP.public_view(clean)
    return {'provider': view, 'active': CP.load()['active'],
            'next': 'openbridge ai test %s%s' % (clean['name'], '' if view['execution'] == 'local'
                                                 else ' --consent ALLOW-REMOTE')}


def cmd_ai_remove(args):
    from src.ai import custom_provider as CP
    name = getattr(args, 'name', '')
    if CP.get(name) is None:
        raise CliError('args', 'UNKNOWN_PROVIDER', 'No connected AI named %r.' % name)
    return {'removed': CP.remove(name), 'active': CP.load()['active']}


def cmd_ai_use(args):
    from src.ai import custom_provider as CP
    name = getattr(args, 'name', None)
    try:
        CP.set_active(None if name in (None, '', 'none') else name)
    except CP.ProviderError as e:
        raise CliError('args', 'UNKNOWN_PROVIDER', str(e))
    return {'active': CP.load()['active']}


def cmd_ai_test(args):
    from src.ai import custom_provider as CP
    name = getattr(args, 'name', None)
    entry = CP.get(name) if name else CP.active()
    if entry is None:
        raise CliError('args', 'CUSTOM_PROVIDER_MISSING', 'No connected AI: add one with `openbridge ai add`.')
    if CP.execution(entry) != 'local' and getattr(args, 'consent', None) not in ('ALLOW-REMOTE', 'ALLOW-CLOUD'):
        raise CliError('permission', 'CONSENT_REQUIRED',
                       '%s is outside this PC; the test sends one fixed sentence. Re-run with --consent ALLOW-REMOTE.'
                       % entry['name'])
    try:
        return CP.test(entry)
    except CP.ProviderError as e:
        raise CliError('inference', 'INFERENCE_FAILED', str(e))


# ---------------- learning, creation and device links (through Home Assistant devices) ----------------

def _ha_fabric(args):
    """(ha, registry, executor, learner, entity->key) with every receipt fed to the device learner."""
    from types import SimpleNamespace
    from src.fabric.discovery import install_salt
    from src.fabric.home_assistant_ingest import ingest_home_assistant
    from src.fabric.registry import Registry
    from src.runtime.device_learning import Learner
    from src.runtime.primitives import Executor
    ha = _ha_client(args)
    reg = Registry()
    rep_ = ingest_home_assistant(reg, ha, install_salt())
    if rep_.get('status') != 'OK':
        raise CliError('device', 'HA_UNAVAILABLE', 'Home Assistant unavailable (%s)' % rep_.get('detail', ''))
    learner = Learner()
    ex = Executor(SimpleNamespace(fabric_registry=reg, fabric_snapshot=reg.snapshot(),
                                  fabric_adapters=lambda p=None: {'home_assistant': ha}))
    keys = {d['ha_entity']: k for k, d in reg.devices.items() if d.get('ha_entity')}
    set_actions = ('turn_on', 'turn_off', 'set_brightness', 'set_volume', 'set_temperature')

    def latency_hint(entity_id, action):
        # Learned p95 latency of this action on this device stretches its read-back window (slow devices).
        prof = learner.action_profile(keys.get(entity_id), ('ha_set:' if action in set_actions else 'ha_command:') + action)
        return (prof or {}).get('latency_p95_s')
    ha.latency_hint = latency_hint
    _quality_listener(ha, learner, keys)
    return ha, reg, ex, learner, keys


def _quality_listener(ha, learner, keys):
    """If the owner turned quality reports on, count each receipt by device model and firmware (no names, no ids)."""
    from src.runtime.quality_reports import Quality
    q = Quality()
    if not q.enabled:
        return None
    info = ha.device_info(list(keys))
    entity_of = {k: e for e, k in keys.items()}
    learner.listeners.append(lambda receipt, category, action:
                             q.observe(info.get(entity_of.get(receipt.get('device_key'))), category, action, receipt))
    return q


def _learned(learner, reg, receipt, key, action):
    learner.observe_receipt(dict(receipt, device_key=key), category=reg.devices[key]['category'], action=action)


def cmd_ha_soak(args):
    """Long real test: every controllable device, every allowed action, many cycles; changes are undone."""
    import random
    import time as _t
    from src.adapters import home_assistant as HA
    if getattr(args, 'consent', None) != 'ALLOW':
        raise CliError('permission', 'CONSENT_REQUIRED', 'The soak test changes devices (and undoes them). Re-run with --consent ALLOW.')
    ha, reg, ex, learner, keys = _ha_fabric(args)
    rng = random.Random(getattr(args, 'seed', 7))
    values = {'set_brightness': (5, 100), 'set_volume': (0, 100), 'set_temperature': (16, 26)}
    SET = ('turn_on', 'turn_off', 'set_brightness', 'set_volume', 'set_temperature')
    stats, t0, reasons, acked = {}, _t.time(), {}, 0
    plan = []
    only = set(getattr(args, 'entity', None) or ())
    for s in ha.states():
        if only and s['entity_id'] not in only:
            continue                      # real homes: test only the devices the owner listed
        for a in HA.actions_for(s):
            if a in ('open', 'close', 'stop') and not getattr(args, 'include_covers', False):
                continue
            plan.append((s['entity_id'], a))
    for cycle in range(int(getattr(args, 'cycles', 3))):
        rng.shuffle(plan)
        for eid, a in plan:
            key = keys.get(eid)
            if key is None:
                continue
            params = {'action': a}
            if a in values:
                lo, hi = values[a]
                params['value'] = rng.randint(lo, hi)
            prim = 'ha_set' if a in SET else 'ha_command'
            r = ex.execute(prim, key, params, consent=True)
            _learned(learner, reg, r, key, '%s:%s' % (prim, a))
            row = stats.setdefault(prim + ':' + a, {'runs': 0, 'verified': 0, 'blocked': 0, 'other': 0, 'undo_exact': 0, 'undo_runs': 0})
            row['runs'] += 1
            row['verified' if r['verified'] else 'blocked' if r['state'] == 'BLOCKED' else 'other'] += 1
            if not r['verified']:
                why = ((r['errors'][0] if r['errors'] else r['state'])[:60] + ' | ' + eid.split('.')[0])
                reasons[why] = reasons.get(why, 0) + 1
            if not r['verified'] and r['state'] != 'BLOCKED' and r.get('transaction_id'):
                # The soak is the owner here: it reads the device back and acknowledges the outcome,
                # so one demo quirk cannot fill the recovery backlog for the rest of the run.
                try:
                    if ha.confirm(eid, a, params.get('value'))['verified']:
                        row['verified_late'] = row.get('verified_late', 0) + 1
                    if ex.acknowledge(r['transaction_id']):
                        acked += 1
                except Exception:
                    pass
            if prim == 'ha_set' and r['verified']:
                u = ex.execute('ha_undo', key, {}, consent=True)
                _learned(learner, reg, u, key, 'ha_undo')
                row['undo_runs'] += 1
                row['undo_exact'] += 1 if u['state'] == 'REVERTED' else 0
    total = sum(r['runs'] for r in stats.values())
    ok = sum(r['verified'] for r in stats.values())
    undo = sum(r['undo_runs'] for r in stats.values())
    return {'cycles': int(getattr(args, 'cycles', 3)), 'actions': total, 'verified': ok,
            'verified_pct': round(100 * ok / max(1, total), 1),
            'undo_exact_pct': round(100 * sum(r['undo_exact'] for r in stats.values()) / max(1, undo), 1),
            'duration_s': round(_t.time() - t0, 1), 'by_action': stats,
            'learned': learner.report()['proven_actions'], 'acknowledged_after_readback': acked,
            'verified_late': sum(r.get('verified_late', 0) for r in stats.values()),
            'not_verified_reasons': dict(sorted(reasons.items(), key=lambda kv: -kv[1])[:15])}


def cmd_learn_reset(args):
    from src.runtime.device_learning import Learner
    if getattr(args, 'consent', None) != 'ALLOW':
        raise CliError('permission', 'CONSENT_REQUIRED', 'This forgets everything OpenBridge learned. Re-run with --consent ALLOW.')
    l = Learner()
    n = len(l.devices)
    l.devices = {}
    l._save()
    return {'forgotten_devices': n}


def cmd_learn_report(args):
    from src.runtime.device_learning import Learner
    rep_ = Learner().report()
    if getattr(args, 'summary', False):
        rep_['devices'] = [{'device': d['device'], 'category': d['category'], 'reliability': d['reliability'],
                            'proven': sorted(a for a, p in d['actions'].items() if p['proven'])} for d in rep_['devices']]
    return rep_


def cmd_create_suggest(args):
    from src.runtime.device_learning import suggest_recipes
    ha, reg, ex, learner, keys = _ha_fabric(args)
    ideas = suggest_recipes(reg, learner, limit=int(getattr(args, 'limit', 12)))
    inv = {v: k for k, v in keys.items()}
    for i in ideas:
        i['when']['entity'] = inv.get(i['when']['device'])
        i['then']['entity'] = inv.get(i['then']['device'])
    return {'ideas': ideas, 'count': len(ideas),
            'next': 'openbridge links add --when ENTITY --state STATE --then ENTITY --action ACTION [--value N]'}


def _links(args, need_fabric=True):
    from src.runtime.device_links import Links
    if need_fabric:
        ha, reg, ex, learner, keys = _ha_fabric(args)
        return Links(ex, learner=learner), ha, reg, keys
    return Links(None), None, None, None


def cmd_links_add(args):
    from src.runtime.device_links import LinkError
    links, ha, reg, keys = _links(args)
    for e in (args.when, args.then):
        if e not in keys:
            raise CliError('args', 'HA_UNKNOWN_ENTITY', 'No listed Home Assistant device %r.' % e)
    SET = ('turn_on', 'turn_off', 'set_brightness', 'set_volume', 'set_temperature')
    params = {'action': args.action}
    if getattr(args, 'value', None) is not None:
        params['value'] = args.value
    try:
        link = links.add(keys[args.when], args.state, keys[args.then], 'ha_set' if args.action in SET else 'ha_command', params,
                         title=getattr(args, 'title', '') or '%s %s -> %s %s' % (args.when, args.state, args.then, args.action),
                         cooldown_s=getattr(args, 'cooldown', 30))
    except LinkError as e:
        raise CliError('args', 'LINK_INVALID', str(e))
    return {'link': link, 'next': 'openbridge links approve %s --consent ALLOW' % link['id']}


def cmd_links_approve(args):
    from src.runtime.device_links import LinkError
    if getattr(args, 'consent', None) != 'ALLOW':
        raise CliError('permission', 'CONSENT_REQUIRED', 'Approving a link lets it act on its own. Re-run with --consent ALLOW.')
    links = _links(args, need_fabric=False)[0]
    try:
        return {'link': links.approve(args.id)}
    except LinkError as e:
        raise CliError('args', 'LINK_UNKNOWN', str(e))


def cmd_links_list(args):
    links = _links(args, need_fabric=False)[0]
    return {'links': list(links.links.values())}


def cmd_links_remove(args):
    from src.runtime.device_links import LinkError
    links = _links(args, need_fabric=False)[0]
    try:
        links.remove(args.id)
    except LinkError as e:
        raise CliError('args', 'LINK_UNKNOWN', str(e))
    return {'removed': args.id}


def cmd_links_watch(args):
    """Run the link engine on live Home Assistant states for a while; every firing goes through the gate."""
    import time as _t
    links, ha, reg, keys = _links(args)
    end = _t.time() + float(getattr(args, 'seconds', 60))
    events, ticks = [], 0
    while _t.time() < end:
        states = {keys[s['entity_id']]: s.get('state') for s in ha.states() if s['entity_id'] in keys}
        events += links.tick(states)
        ticks += 1
        _t.sleep(float(getattr(args, 'interval', 2)))
    by = {}
    for e in events:
        by[e['result']] = by.get(e['result'], 0) + 1
    return {'ticks': ticks, 'events': events[-50:], 'by_result': by}


# ---------------- skill library and skill packs (no AI model needed to run) ----------------

def _skill_library(args, need_fabric=False):
    from src.runtime.skill_library import Library
    if need_fabric:
        ha, reg, ex, learner, keys = _ha_fabric(args)
        return Library(ex, learner=learner), reg, keys
    return Library(None), None, None


def _skill_call(fn, *a):
    from src.runtime.skill_library import SkillError
    from src.runtime.skill_packs import PackError
    try:
        return fn(*a)
    except (SkillError, PackError) as e:
        raise CliError('args', 'SKILL_INVALID', str(e))


def cmd_skills_list(args):
    return {'skills': _skill_library(args)[0].summary()}


def cmd_skills_show(args):
    lib = _skill_library(args)[0]
    r = _skill_call(lib._get, args.id)
    return {'skill': dict(r, approved=lib.is_approved(r))}


def cmd_skills_approve(args):
    if getattr(args, 'consent', None) != 'ALLOW':
        raise CliError('permission', 'CONSENT_REQUIRED',
                       'Approving a skill lets it act (on a button, a schedule or a device change). Re-run with --consent ALLOW.')
    return {'skill': _skill_call(_skill_library(args)[0].approve, args.id)}


def cmd_skills_run(args):
    lib = _skill_library(args, need_fabric=True)[0]
    return {'run': _skill_call(lib.run, args.id)}


def cmd_skills_remove(args):
    _skill_call(_skill_library(args)[0].remove, args.id)
    return {'removed': args.id}


def cmd_skills_export(args):
    import json as _json
    lib = _skill_library(args)[0]
    lib._save()                       # keeps this install's signing key, so its own files import as trusted
    bundle = _skill_call(lib.export, args.ids or None)
    Path(args.out).write_text(_json.dumps(bundle, indent=1), encoding='utf-8')
    return {'file': args.out, 'skills': len(bundle['skills']), 'note': 'approvals are never exported'}


def cmd_skills_import(args):
    import json as _json
    try:
        bundle = _json.loads(Path(args.file).read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise CliError('args', 'SKILL_INVALID', 'cannot read %s: %s' % (args.file, e))
    return _skill_call(_skill_library(args)[0].import_bundle, bundle)


def cmd_skills_packs(args):
    from src.runtime import skill_packs as P
    return {'packs': [P.summary(p, args.lang) for p in P.available()]}


def cmd_skills_pack_show(args):
    from src.runtime import skill_packs as P
    return {'pack': P.summary(_skill_call(P.get, args.id), args.lang)}


def cmd_skills_pack_check(args):
    from src.runtime import skill_packs as P
    try:
        return {'pack': P.check_file(args.file)}
    except (OSError, ValueError) as e:
        raise CliError('args', 'PACK_INVALID', str(e))


def cmd_skills_install_pack(args):
    """Install a pack on this home's devices: roles -> Home Assistant entities. The skills arrive unapproved."""
    from src.runtime import skill_packs as P
    pack = _skill_call(P.get, args.id)
    lib, reg, keys = _skill_library(args, need_fabric=True)
    devices = {k: {'category': d.get('category'), 'label': d.get('label')} for k, d in reg.devices.items()}
    given = {}
    for item in args.map or []:
        role, _, entity = item.partition('=')
        if role not in pack['roles'] or entity not in keys:
            raise CliError('args', 'PACK_MAP', 'Use --map ROLE=ENTITY with a role of this pack (%s) and a listed entity.'
                           % ', '.join(pack['roles']))
        given[role] = keys[entity]
    mapping, missing, ambiguous = P.auto_map(pack, devices, given)
    if missing or ambiguous:
        by_key = {v: k for k, v in keys.items()}
        raise CliError('args', 'PACK_ROLES', 'Choose a device for each role with --map ROLE=ENTITY. Missing: %s. To choose: %s'
                       % (', '.join(missing) or 'none',
                          '; '.join('%s = %s' % (r, ' | '.join(by_key.get(k, k) for k in c)) for r, c in ambiguous.items()) or 'none'))
    ids = _skill_call(P.install, lib, pack, devices, mapping, args.lang)
    return {'installed': ids, 'pack': pack['id'],
            'next': 'review each skill with `openbridge skills show ID`, then `openbridge skills approve ID --consent ALLOW`'}


# ---------------- quality reports (off unless the owner turns them on; never sent) ----------------

def cmd_quality_status(args):
    from src.runtime.quality_reports import Quality
    q = Quality()
    return {'enabled': q.enabled, 'consent': q.consent, 'months': sorted(q.months),
            'kept': 'counts per manufacturer, model, firmware, category and action, on this PC only'}


def cmd_quality_enable(args):
    from src.runtime.quality_reports import Quality
    if getattr(args, 'consent', None) != 'ALLOW':
        raise CliError('permission', 'CONSENT_REQUIRED',
                       'Quality reports count, per device model and firmware, how often actions succeed. Nothing is sent; '
                       'you choose whether to export and share a month. Re-run with --consent ALLOW.')
    return {'consent': Quality().enable()}


def cmd_quality_disable(args):
    from src.runtime.quality_reports import Quality
    return {'consent': Quality().disable(forget=args.forget), 'forgotten': bool(args.forget)}


def _quality_out(report, args):
    from src.runtime import quality_reports as QR
    if getattr(args, 'markdown', None):
        Path(args.markdown).write_text(QR.markdown(report), encoding='utf-8')
    return {'report': report, 'markdown': getattr(args, 'markdown', None)}


def cmd_quality_report(args):
    from src.runtime.quality_reports import Quality, QualityError
    try:
        return _quality_out(Quality().report(args.month), args)
    except QualityError as e:
        raise CliError('args', 'QUALITY_INVALID', str(e))


def cmd_quality_export(args):
    import json as _json
    from src.runtime.quality_reports import Quality, QualityError
    try:
        doc = Quality().export(args.month)
    except QualityError as e:
        raise CliError('args', 'QUALITY_INVALID', str(e))
    Path(args.out).write_text(_json.dumps(doc, indent=1), encoding='utf-8')
    return {'file': args.out, 'month': doc['month'], 'rows': len(doc['rows']), 'contains': doc['contains']}


def cmd_quality_merge(args):
    """For a device maker: merge the exports owners chose to send into one report with firmware regressions."""
    import json as _json
    from src.runtime import quality_reports as QR
    try:
        docs = [_json.loads(Path(f).read_text(encoding='utf-8')) for f in args.files]
        return _quality_out(QR.build_report(docs), args)
    except (OSError, ValueError) as e:
        raise CliError('args', 'QUALITY_INVALID', str(e))


# ---------------- partner integration kit ----------------

def cmd_partner_new(args):
    """Scaffold a device integration: adapter, emulator, graph entry, passing tests, checklist."""
    from src import partner_kit, partner_kit_api
    spec = None
    if getattr(args, 'from_openapi', None):
        try:
            spec = partner_kit_api.api_spec(json.loads(Path(args.from_openapi).read_text(encoding='utf-8')))
        except (OSError, ValueError) as e:      # SpecError is a ValueError, like a JSON error
            raise CliError('args', 'PARTNER_KIT', 'cannot use %s: %s' % (args.from_openapi, e))
    try:
        out = partner_kit.generate(args.name, title=getattr(args, 'title', None) or (spec or {}).get('title'),
                                   category=getattr(args, 'category', None) or 'device',
                                   dry_run=bool(getattr(args, 'dry_run', False)), spec=spec)
    except partner_kit.KitError as e:
        raise CliError('args', 'PARTNER_KIT', str(e))
    if spec is not None:
        out['mapped'] = {'read': sorted(spec['read']['fields']), 'settings': sorted(spec['writable']),
                         'commands': sorted(spec['commands']), 'refused': sorted(spec['policy']), 'skipped': spec['skipped']}
    return out


# ---------------- home assistant bridge ----------------

def _ha_client(args):
    from src.adapters import home_assistant as HA
    try:
        return HA.HomeAssistant.from_config()
    except HA.HABlocked as e:
        raise CliError('auth', 'HA_NOT_CONNECTED', str(e))


def cmd_ha_connect(args):
    """Link a Home Assistant instance. The token comes from a prompt (OS vault) or an env var, never from argv."""
    from src.adapters import home_assistant as HA
    try:
        cfg = HA.save_config(getattr(args, 'url', ''), getattr(args, 'token_env', None))
    except HA.HABlocked as e:
        raise CliError('args', 'HA_URL_INVALID', str(e))
    if getattr(args, 'store_token', False):
        import getpass
        from src.fabric.credential_vault import Vault, VaultUnavailable
        try:
            Vault().put(HA.SECRET_NAME, getpass.getpass('Home Assistant long-lived access token (kept in the OS vault): ').strip())
        except VaultUnavailable as e:
            raise CliError('dep', 'VAULT_UNAVAILABLE', '%s; use --token-env instead' % e)
    out = {'url': cfg['url'], 'token_env': cfg['token_env'], 'file': str(HA.config_path())}
    try:
        out['check'] = HA.HomeAssistant.from_config(cfg).ping()
    except (HA.HABlocked, HA.HAError) as e:
        out['check'] = {'ok': False, 'reason': str(e)}
    out['next'] = 'openbridge ha devices'
    return out


def cmd_ha_status(args):
    from src.adapters import home_assistant as HA
    cfg = HA.load_config()
    if not cfg:
        return {'connected': False, 'next': 'openbridge ha connect --url http://homeassistant.local:8123 --store-token'}
    try:
        ha = HA.HomeAssistant.from_config(cfg)
        ping = ha.ping()
        states = ha.states()
    except (HA.HABlocked, HA.HAError) as e:
        raise CliError('device', 'HA_UNAVAILABLE', str(e))
    by = {}
    for s in states:
        d = HA.domain_of(s['entity_id'])
        row = by.setdefault(d, {'devices': 0, 'controllable': 0})
        row['devices'] += 1
        row['controllable'] += 1 if HA.actions_for(s) else 0
    return {'connected': True, 'url': cfg['url'], 'home_assistant': ping['message'], 'domains': by,
            'status': 'verified on a real Home Assistant with demo devices; physical devices not yet tested'}


# ---------------- natural language on the home: `openbridge ha say "..."` ----------------

SAY_DOMAINS = {'home.turn_on': ('light', 'switch', 'fan', 'media_player'), 'home.turn_off': ('light', 'switch', 'fan', 'media_player'),
               'home.set_brightness': ('light',), 'home.set_temperature': ('climate',),
               'home.media_play': ('media_player',), 'home.media_pause': ('media_player',), 'home.media_volume': ('media_player',),
               'home.cover_open': ('cover',), 'home.cover_close': ('cover',), 'home.lock': ('lock',),
               'home.undo': ('light', 'switch', 'fan', 'media_player', 'climate')}
GENERIC = {'light', 'lights', 'lamp', 'the', 'smart', 'device', 'speaker', 'thermostat', 'heating', 'plug', 'blinds',
           'shutters', 'curtains', 'door', 'player', 'media'}
REF_DOMAIN = {'tv': ('media_player',), 'speaker': ('media_player',), 'sonos': ('media_player',), 'vacuum': ('vacuum',),
              'front door': ('lock',), 'back door': ('lock',), 'heating': ('climate',), 'thermostat': ('climate',),
              'blinds': ('cover',), 'shutters': ('cover',), 'curtains': ('cover',)}


def _words_of(text):
    return set(''.join(c if c.isalnum() else ' ' for c in (text or '').lower()).split())


def _match_entities(states, target, domains):
    """HA entities for one router target: a category ("all the lights") or the best name match within the allowed domains."""
    pool = [s for s in states if s['entity_id'].split('.', 1)[0] in domains]
    if target.get('kind') == 'category':
        cat = {'light': 'light', 'plug': 'switch', 'fan': 'fan'}.get(target.get('ref'))
        return [s['entity_id'] for s in pool if s['entity_id'].startswith((cat or '-') + '.')][:16]
    want = _words_of(target.get('ref'))
    best, score = [], 0
    for s in pool:
        name = _words_of((s.get('attributes') or {}).get('friendly_name')) | _words_of(s['entity_id'].split('.', 1)[1].replace('_', ' '))
        near = lambda w: any(w == n or (min(len(w), len(n)) >= 3 and (w.startswith(n) or n.startswith(w))) for n in name)
        hit = sum(2 for w in want - GENERIC if near(w)) + sum(1 for w in want & GENERIC if near(w))
        if hit > score:
            best, score = [s['entity_id']], hit
        elif hit == score and hit:
            best.append(s['entity_id'])
    if score == 0 and pool and (not want or want <= GENERIC | {'tv', 'vacuum', 'air', 'conditioning', 'smart', 'front', 'back'}):
        # "the TV", "the heating": the household's default device of that kind (first by id), never a random one.
        return sorted((s['entity_id'] for s in pool), key=lambda e: ('living' not in e and 'tv' not in e, e))[:1]
    return best[:1] if score else []


def _ollama_intent(model, prompt, endpoint, timeout=120):
    from urllib.request import Request, urlopen
    from src.runtime import nl_router as NR
    body = {'model': model, 'stream': False, 'format': NR.INTENT_SCHEMA, 'keep_alive': '15m',
            'options': {'temperature': 0, 'num_ctx': 4096},
            'messages': [{'role': 'system', 'content': 'Reply in English only as compact JSON matching the schema.'},
                         {'role': 'user', 'content': prompt}]}
    req = Request(endpoint.rstrip('/') + '/api/chat', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(json.loads(r.read())['message']['content'])


def cmd_ha_say(args):
    """Say it in plain English or French: OpenBridge's own model understands, the gate checks, Home Assistant acts."""
    import time as _t
    from src.runtime import intent as I
    from src.runtime import nl_router as NR
    from src.runtime import skills as S
    text, lang = args.text, getattr(args, 'lang', None) or 'auto'
    if lang == 'auto':
        fr = _words_of(text) & {'le', 'la', 'les', 'de', 'du', 'des', 'allume', 'eteins', 'mets', 'ferme', 'ouvre', 'quand', 'stp',
                                'baisse', 'monte', 'coupe', 'propose', 'appareils', 'lumiere', 'porte', 'chauffage', 'verrouille'}
        lang = 'fr' if fr else 'en'
    t0 = _t.perf_counter()
    try:
        reply = _ollama_intent(args.intent_model, NR.build_prompt(text, lang), args.endpoint)
    except Exception as e:
        raise CliError('inference', 'MODEL_UNAVAILABLE', '%s: %s' % (type(e).__name__, str(e)[:160]))
    doc = NR._interpret(I.new_intent(text, lang), reply, 'local', args.intent_model)
    out = {'text': text, 'lang': lang, 'understood_in_s': round(_t.perf_counter() - t0, 2),
           'intent': {k: doc.get(k) for k in ('status', 'skill_id', 'targets', 'params', 'clarifying_question', 'ambiguities')}}
    if doc['status'] != 'resolved':
        out['done'] = False
        return out
    sid = doc['skill_id']
    if sid == 'learn.report':
        from src.runtime.device_learning import Learner
        rep_ = Learner().report()
        out.update(done=True, result={'devices': len(rep_['devices']), 'proven_actions': rep_['proven_actions']})
        return out
    if not sid.startswith(('home.', 'links.', 'create.')):
        out.update(done=False, note='understood; this skill runs through `openbridge ask` / the app, not the home bridge')
        return out
    ha, reg, ex, learner, keys = _ha_fabric(args)
    if sid == 'create.suggest':
        from src.runtime.device_learning import suggest_recipes
        inv = {v: k for k, v in keys.items()}
        ideas = suggest_recipes(reg, learner, limit=5)
        out.update(done=True, result=[{'title': i['title'], 'when': inv.get(i['when']['device']), 'then': inv.get(i['then']['device'])}
                                      for i in ideas])
        return out
    states = ha.states()
    if sid == 'links.create':
        tg = doc['targets']
        p = doc['params']
        if len(tg) != 2 or not p.get('when_state') or not p.get('then_action'):
            out.update(done=False, note='a link needs a trigger device, a state, a target device and an action')
            return out
        trig = _match_entities(states, tg[0], REF_DOMAIN.get(tg[0]['ref'], ('media_player', 'light', 'switch', 'lock', 'vacuum', 'cover', 'climate', 'fan')))
        action = p['then_action']
        tdom = {'set_brightness': ('light',), 'pause': ('media_player',), 'play': ('media_player',),
                'open': ('cover',), 'close': ('cover',)}.get(action, ('light', 'switch', 'fan', 'media_player'))
        tgt = _match_entities(states, tg[1], tdom)
        if not trig or not tgt:
            out.update(done=False, note='no Home Assistant device matches %r / %r' % (tg[0]['ref'], tg[1]['ref']))
            return out
        from src.runtime.device_links import Links, LinkError
        params = {'action': action}
        if p.get('value') is not None:
            params['value'] = p['value']
        SET = ('turn_on', 'turn_off', 'set_brightness', 'set_volume', 'set_temperature')
        try:
            link = Links(ex, learner=learner).add(keys[trig[0]], p['when_state'], keys[tgt[0]], 'ha_set' if action in SET else 'ha_command',
                                                 params, title=text[:80])
        except LinkError as e:
            out.update(done=False, note=str(e))
            return out
        out.update(done=True, result={'link': link['id'], 'when': trig[0], 'state': p['when_state'], 'then': tgt[0], 'params': params,
                                      'approved': False, 'next': 'openbridge links approve %s --consent ALLOW' % link['id']})
        return out
    from src.adapters import home_assistant as HA
    action = S.get(sid)['params'].get('action')
    if action:   # only devices that really support this action (e.g. a single target temperature, not a range)
        states = [s for s in states if action in HA.actions_for(s)]
    ents = []
    for t in doc['targets'] or [{'kind': 'device', 'ref': ''}]:
        ents += [e for e in _match_entities(states, t, SAY_DOMAINS[sid]) if e not in ents]
    if not ents:
        out.update(done=False, note='no Home Assistant device matches %s' % [t.get('ref') for t in doc['targets']])
        return out
    plan = S.resolve(sid, doc['params'])
    out['plan'] = {'primitive': plan['primitive_id'], 'params': plan['params'], 'entities': ents}
    if getattr(args, 'consent', None) != 'ALLOW':
        out.update(done=False, note='understood; add --consent ALLOW to act')
        return out
    receipts = []
    for e in ents:
        r = ex.execute(plan['primitive_id'], keys[e], dict(plan['params']), consent=True)
        _learned(learner, reg, r, keys[e], '%s:%s' % (plan['primitive_id'], plan['params'].get('action', 'undo')))
        receipts.append({'entity': e, 'state': r['state'], 'verified': r['verified'], 'before': r['before'], 'after': r['after'],
                         'errors': r['errors'][:1]})
    out.update(done=all(r['verified'] or r['state'] == 'REVERTED' for r in receipts), receipts=receipts)
    return out


def cmd_ha_devices(args):
    from src.adapters import home_assistant as HA
    ha = _ha_client(args)
    try:
        states = ha.states()
    except HA.HAError as e:
        raise CliError('device', 'HA_UNAVAILABLE', str(e))
    rows = []
    for s in states:
        d = HA.domain_of(s['entity_id'])
        acts = sorted(HA.actions_for(s))
        rows.append({'entity': s['entity_id'], 'name': (s.get('attributes') or {}).get('friendly_name', ''),
                     'category': HA.CATEGORY[d], 'state': s.get('state'), 'actions': acts,
                     'policy': HA.policy_refusal(d, '*' if d == 'alarm_control_panel' else 'unlock' if d == 'lock' else 'open', s) or ''})
    return {'devices': rows, 'count': len(rows)}


def cmd_ha_do(args):
    """One action through the same gate as the app: typed primitive, consent, read-back, receipt."""
    from types import SimpleNamespace
    from src.adapters import home_assistant as HA
    from src.fabric.discovery import install_salt
    from src.fabric.home_assistant_ingest import ingest_home_assistant
    from src.fabric.registry import Registry
    from src.runtime.primitives import Executor
    ha = _ha_client(args)
    reg = Registry()
    report = ingest_home_assistant(reg, ha, install_salt())
    if report.get('status') != 'OK':
        raise CliError('device', 'HA_UNAVAILABLE', 'Home Assistant unavailable (%s)' % report.get('detail', ''))
    key = next((k for k, d in reg.devices.items() if d.get('ha_entity') == args.entity), None)
    if key is None:
        raise CliError('args', 'HA_UNKNOWN_ENTITY', 'No listed Home Assistant device %r (see `openbridge ha devices`).' % args.entity)
    prim = 'ha_set' if args.action in ('turn_on', 'turn_off', 'set_brightness', 'set_volume', 'set_temperature') else 'ha_command'
    params = {'action': args.action}
    if getattr(args, 'value', None) is not None:
        params['value'] = args.value
    ctx = SimpleNamespace(fabric_registry=reg, fabric_snapshot=reg.snapshot(), fabric_adapters=lambda p=None: {'home_assistant': ha})
    receipt = Executor(ctx).execute(prim, key, params, consent=getattr(args, 'consent', None) == 'ALLOW')
    if receipt['state'] == 'BLOCKED' and any(e.startswith('CONSENT_REQUIRED') for e in receipt['errors']):
        raise CliError('permission', 'CONSENT_REQUIRED', 'Re-run with --consent ALLOW to approve this one action.', receipt)
    return receipt


def cmd_ha_disconnect(args):
    from src.adapters import home_assistant as HA
    from src.fabric.credential_vault import Vault
    try:
        HA.config_path().unlink()
    except FileNotFoundError:
        pass
    Vault().delete(HA.SECRET_NAME)
    return {'connected': False}


# ---------------- devices ----------------

def snapshot_path():
    return private_root() / 'cli_snapshot.json'


def snapshot_load():
    try:
        return json.loads(snapshot_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'devices': []}


def snapshot_save(doc):
    path = snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1), encoding='utf-8')


def default_providers(args):
    raw = getattr(args, 'providers', None) or 'mdns,ssdp,android,tuya,home_assistant'
    providers = [p.strip() for p in raw.split(',') if p.strip()]
    allowed = {'mdns', 'ssdp', 'android', 'freebox', 'ble', 'tuya', 'home_assistant'}
    unknown = [p for p in providers if p not in allowed]
    if unknown:
        raise CliError('args', 'BAD_PROVIDERS', 'Unknown providers: %s' % ', '.join(unknown))
    return providers


def ensure_discovery(server, providers):
    """Same discovery the GUI server runs: fills snapshot + registry in-process."""
    from src.fabric import discovery as D
    snap, reg = D.run(server.fabric_adapters(tuple(providers)), server.fabric_salt,
                      providers=tuple(providers))
    server.fabric_snapshot = snap
    server.fabric_registry = reg
    if 'android' in providers and hasattr(server, 'restore_relays'):
        try:
            server.restore_relays()
        except Exception:
            pass
    return snap


def cmd_devices_discover(args):
    providers = default_providers(args)
    with Core() as server:
        snap = ensure_discovery(server, providers)
    devices = snap.get('devices', []) if isinstance(snap, dict) else []
    doc = {'devices': devices, 'providers': providers, 'at': time.time()}
    snapshot_save(doc)
    return {'devices': devices, 'count': len(devices), 'providers': providers}


def cmd_devices_list(args):
    with Core() as server:
        status, body = api_get(args, server, '/api/v2/relays', {})
    known = snapshot_load().get('devices', [])
    return {'devices': known, 'count': len(known),
            'relays': body if status == 200 else {'error': 'unavailable'},
            'hint': 'run `devices discover` to refresh' if not known else ''}


def cmd_devices_inspect(args):
    device_id = getattr(args, 'device_id', '')
    for row in snapshot_load().get('devices', []):
        if str(row.get('id', '')) == device_id or str(row.get('label', '')) == device_id:
            return {'device': row}
    raise CliError('device', 'DEVICE_NOT_FOUND', 'Unknown device %r; run `devices discover`.' % device_id)


def cmd_devices_pair(args):
    device_id = getattr(args, 'device_id', '')
    with Core() as server:
        status, body = api_post(args, server, '/api/v2/onboarding/apk-portal', {})
    info = check_status(status, body) if isinstance(body, dict) else {}
    return {'device_id': device_id, 'paired': False, 'state': 'PENDING_ON_DEVICE_ACTION',
            'steps': ['connect the device to this PC (USB) or join it to this LAN',
                      'open the portal on the device and approve the pairing',
                      're-run `devices discover` to verify'],
            'portal': info}


def cmd_devices_status(args):
    with Core() as server:
        status, body = api_get(args, server, '/api/v2/relays/samples', {})
    if status != 200:
        status, body = api_get(args, server, '/api/v2/relays', {})
    return {'status': check_status(status, body)}


# ---------------- ask ----------------

def cmd_ask(args):
    from src.runtime import command as cmdmod
    text = getattr(args, 'text', '')
    if not text.strip():
        raise CliError('args', 'EMPTY_REQUEST', 'ask needs a natural-language request.')
    prior = None
    prior_file = getattr(args, 'prior', None)
    if prior_file:
        prior = _read_json_file(prior_file, 'prior intent')
    with Core() as server:
        ensure_discovery(server, default_providers(args))
        try:
            parsed = cmdmod.parse_request(server, {'text': text, 'lang': 'en', 'prior': prior})
        except cmdmod.CommandError as e:
            raise CliError('args', 'PARSE_FAILED', str(e))
        intent = parsed.get('intent', parsed) if isinstance(parsed, dict) else parsed
        understood_by = ((intent.get('provenance') or {}).get('model_id')) if isinstance(intent, dict) else None
        if not isinstance(intent, dict) or intent.get('status') != 'resolved':
            status = intent.get('status', 'unknown') if isinstance(intent, dict) else 'unknown'
            ambiguities = intent.get('ambiguities', []) if isinstance(intent, dict) else []
            return {'approval_required': False, 'resolved': False, 'status': status,
                    'ambiguities': ambiguities, 'understood_by': understood_by,
                    'need': 'a local model (LOCAL-FAST/QUALITY) or your connected AI (`openbridge ai add`) to resolve'}
        try:
            preview = cmdmod.approve(server, intent)
        except cmdmod.CommandError as e:
            raise CliError('permission', 'PREVIEW_BLOCKED', str(e))
    read_only = bool(isinstance(preview, dict) and preview.get('read_only'))
    if getattr(args, 'dry_run', False) or not read_only:
        rid = 'req-%s' % hashlib.sha256(text.encode()).hexdigest()[:12]
        entry = {'text': text, 'intent': intent, 'preview': preview,
                 'hash': preview_hash(preview), 'created': time.time()}

        def _add(rows):
            rows[rid] = entry
            return rid

        pending_mutate(_add)
        return {'approval_required': True, 'request_id': rid, 'understood_by': understood_by,
                'consent': preview_hash(preview), 'preview': preview,
                'next': 'approvals approve %s --consent %s' % (rid, preview_hash(preview))}
    with Core() as server:
        ensure_discovery(server, default_providers(args))
        try:
            result = cmdmod.execute(server, intent, True, preview)
        except cmdmod.CommandError as e:
            raise CliError('permission', 'EXECUTE_BLOCKED', str(e))
    return {'approval_required': False, 'preview': preview, 'result': result, 'understood_by': understood_by}


# ---------------- capabilities ----------------

def capabilities_dir():
    path = private_root() / 'capabilities'
    path.mkdir(parents=True, exist_ok=True)
    return path


def cmd_capabilities_list(args):
    from src.runtime.primitives import PRIMITIVES
    stored = []
    for child in sorted(capabilities_dir().glob('*.json')):
        try:
            doc = json.loads(child.read_text(encoding='utf-8'))
        except ValueError:
            continue
        stored.append({'id': child.stem, 'state': doc.get('state', 'candidate'),
                       'target': doc.get('target_category')})
    return {'capabilities': stored, 'primitives': sorted(PRIMITIVES)}


def cmd_capabilities_generate(args):
    from src.ai.router import route, RoutingError
    from src.forge import v4_synthesize as synth
    from src.runtime.primitives import PRIMITIVES
    intent_text = getattr(args, 'intent', '') or ''
    target = getattr(args, 'target', '') or ''
    if not intent_text.strip() or not target.strip():
        raise CliError('args', 'MISSING_INPUT', 'generate needs --intent and --target.')
    tier = (getattr(args, 'model', None) or 'AUTO').upper().replace('_', '-')
    if tier in ('CLOUD-HIGH', 'CLOUD-MAX'):
        tier = 'CUSTOM'
    if tier not in ('AUTO', 'LOCAL-FAST', 'LOCAL-QUALITY', 'CUSTOM'):
        tier = 'AUTO'
    avail = local_availability()
    availability = custom_availability({'local_fast': avail['local_fast'],
                                        'local_quality': avail['local_quality']})
    privacy = 'allow-cloud' if getattr(args, 'consent', None) in ('ALLOW-REMOTE', 'ALLOW-CLOUD') else 'local-only'
    try:
        decision = route(tier, 'synthesis', availability, privacy=privacy, user_text=intent_text)
    except RoutingError as e:
        raise CliError('inference', 'ROUTING_BLOCKED', str(e))
    if decision['needs_cloud_consent']:
        raise CliError('permission', 'CONSENT_REQUIRED',
                       'Your connected AI is outside this PC: re-run with --consent ALLOW-REMOTE.')
    from src.forge.v4_synthesize import validate_candidate, SynthError
    bundle = build_bundle(snapshot_load().get('devices', []), sorted(PRIMITIVES))
    prompt = synth.build_prompt(bundle, intent_text, sorted(PRIMITIVES), target)
    retries = max(0, int(getattr(args, 'retries', 0) or 0))
    temperature = float(getattr(args, 'temperature', 0) or 0)
    attempts = []
    candidate, usage = None, {}
    for attempt in range(retries + 1):
        temp = 0 if attempt == 0 else (temperature or 0.7)
        ok, body = OllamaClient(temperature=temp).generate(
            decision['tier'], prompt, {'max_s': getattr(args, 'timeout', None) or 180})
        if not ok:
            attempts.append({'attempt': attempt, 'temperature': temp, 'ok': False,
                             'reason': body.get('reason', body.get('status'))})
            continue
        try:
            doc, extracted = extract_json(body.get('text', ''))
        except (TypeError, ValueError):
            full = str(body.get('text', ''))
            attempts.append({'attempt': attempt, 'temperature': temp, 'ok': False,
                             'reason': 'not JSON', 'text_len': len(full),
                             'excerpt': full[:200], 'tail': full[-200:]})
            continue
        if isinstance(doc, dict):
            import secrets as _secrets
            doc = dict(doc)
            doc.setdefault('model_run_id', 'mr-' + _secrets.token_hex(8))
        try:
            candidate = validate_candidate(doc, sorted(PRIMITIVES), bundle=bundle)
        except SynthError as e:
            attempts.append({'attempt': attempt, 'temperature': temp, 'ok': False,
                             'reason': str(e)[:160],
                             'excerpt': json.dumps(doc)[:300] if isinstance(doc, dict) else ''})
            continue
        usage = body.get('usage', {})
        attempts.append({'attempt': attempt, 'temperature': temp, 'ok': True,
                         'extracted': extracted})
        break
    if candidate is None:
        raise CliError('verify', 'SCHEMA_REJECTED',
                       'All %d attempt(s) rejected: %s' % (len(attempts), attempts[-1].get('reason')),
                       data={'attempts': attempts})
    cid = 'cap-%s' % hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()[:12]
    stored = {'id': cid, 'state': 'candidate', 'candidate': candidate,
              'target_category': target, 'model_id': decision['model_id'],
              'routing': decision['reasons'], 'usage': usage, 'attempts': attempts}
    (capabilities_dir() / (cid + '.json')).write_text(json.dumps(stored, indent=1), encoding='utf-8')
    return {'id': cid, 'state': 'candidate', 'model_id': decision['model_id'],
            'routing': decision['reasons'], 'digest': preview_hash(candidate),
            'attempts': len(attempts)}


def _capability_path(cid):
    path = capabilities_dir() / (cid + '.json')
    if not path.exists():
        raise CliError('args', 'NOT_FOUND', 'Unknown capability %r.' % cid)
    return path


def extract_json(text):
    """Parse the first JSON object in model output (fences tolerated).

    This only locates the object; the forge validator still decides.
    Returns (doc, extracted) where extracted=True if fences/prefix were stripped.
    """
    cleaned = re.sub(r'^```(?:json)?\s*', '', (text or '').strip())
    cleaned = re.sub(r'\s*```\s*$', '', cleaned)
    start = cleaned.find('{')
    if start < 0:
        raise ValueError('no JSON object')
    depth, in_str, esc = 0, False, False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start:i + 1]), (start > 0 or cleaned != (text or '').strip())
    raise ValueError('unbalanced JSON object')


def build_bundle(snapshot_devices, primitive_ids, salt='cli'):
    """Value-free evidence bundle for synthesis: opaque ids + fact descriptors.

    Raw fact values never enter the bundle, so they never reach the model.
    """
    import secrets
    from src.forge import v4_schemas as schemas
    level_scope = {'read': 'read', 'observe': 'observe', 'restore': 'control',
                   'control': 'control', 'write': 'control'}
    devices = []
    for row in snapshot_devices or []:
        key = str(row.get('key', row.get('label', '?')))
        opaque = 'opaque:' + hashlib.sha256((salt + key).encode()).hexdigest()[:16]
        scope = sorted({level_scope.get(c.get('level', ''), 'read')
                        for c in row.get('capabilities', [])} or {'read'})
        facts = []
        for name, fact in sorted((row.get('facts') or {}).items()):
            value = (fact or {}).get('value')
            sources = (fact or {}).get('sources') or ['unknown']
            facts.append({'fact_id': str(name)[:64], 'kind': str(name)[:64],
                          'value_class': type(value).__name__, 'source': str(sources[0])[:32],
                          'observed_at': time.time(),
                          'evidence_ref': 'opaque:' + hashlib.sha256(
                              (salt + key + str(name)).encode()).hexdigest()[:16]})
        devices.append({'opaque_id': opaque, 'category': str(row.get('category', 'unknown'))[:32],
                        'permission_scope': scope, 'facts': facts})
    bundle = {'schema_version': schemas.SCHEMA_VERSION,
              'bundle_id': 'bnd-' + secrets.token_hex(8),
              'observed_at': time.time(), 'devices': devices, 'relays': [],
              'primitives': sorted(primitive_ids),
              'registry_digest': hashlib.sha256(
                  json.dumps(devices, sort_keys=True, default=str).encode()).hexdigest()}
    return schemas.validate_bundle(bundle)


def cmd_capabilities_inspect(args):
    path = _capability_path(getattr(args, 'capability_id', ''))
    return {'capability': json.loads(path.read_text(encoding='utf-8'))}


def cmd_capabilities_publish(args):
    from src.forge import v4_substrate as kernel
    path = _capability_path(getattr(args, 'capability_id', ''))
    doc = json.loads(path.read_text(encoding='utf-8'))
    if doc.get('state') == 'revoked':
        raise CliError('permission', 'REVOKED', 'Capability %r was revoked; it cannot publish.'
                       % path.stem)
    require_consent(args, preview_hash(doc.get('candidate', {})), 'capabilities publish')
    candidate = doc.get('candidate', {})
    manifest = kernel.to_manifest(
        candidate,
        {'category': doc.get('target_category', 'unknown'),
         'device_fingerprint': candidate.get('target_opaque_id', '')},
        {'model': doc.get('model_id', 'unknown'),
         'run_id': candidate.get('model_run_id', 'mr-unknown')},
        title='cli: %s' % candidate.get('candidate_id', path.stem),
        permissions=candidate.get('required_grants', []),
        facts_required=candidate.get('evidence_refs', []),
        expires_at=time.time() + 86400)
    mirrored = [s['primitive_id'] for s in manifest.get('steps', [])]
    chained = [s['primitive_id'] for s in candidate.get('primitive_chain', [])]
    if mirrored != chained or not mirrored:
        raise CliError('verify', 'MANIFEST_MISMATCH', 'Manifest steps do not mirror the chain.')
    # No substrate kernel is merged (see v4_substrate docstring): the obv4.1
    # document is staged durably and honestly labeled pending-kernel.
    doc.update({'state': 'published-pending-kernel', 'manifest': manifest,
                'manifest_digest': preview_hash(manifest), 'published_at': time.time()})
    path.write_text(json.dumps(doc, indent=1), encoding='utf-8')
    return {'id': path.stem, 'state': 'published-pending-kernel',
            'manifest_digest': doc['manifest_digest']}


def cmd_capabilities_revoke(args):
    path = _capability_path(getattr(args, 'capability_id', ''))
    doc = json.loads(path.read_text(encoding='utf-8'))
    doc.update({'state': 'revoked', 'revoked_at': time.time()})
    path.write_text(json.dumps(doc, indent=1), encoding='utf-8')
    return {'id': path.stem, 'state': 'revoked'}


# ---------------- dashboards (model-generated panels) ----------------

def _ui_bindable():
    from src.runtime.dashboards import BINDABLE_PATCH_SKILLS
    return BINDABLE_PATCH_SKILLS


def cmd_dashboards_propose(args):
    """Ask a pinned local Meta model to draft a control-panel patch.

    Read-only: discovery + inference + strict validation. Nothing is
    installed; install takes the saved patch file with explicit consent."""
    from src.forge import v4_uidraft, v4_ui
    from src.runtime import nl_plan, nl_router
    text = getattr(args, 'text', '') or ''
    if not text.strip():
        raise CliError('args', 'MISSING_INPUT', 'propose needs intent text.')
    model_id = getattr(args, 'model', None) or nl_router.TIERS['low'][0]
    endpoint = next((ep for mid, ep in nl_router.TIERS.values() if mid == model_id), None)
    if endpoint is None or endpoint.startswith('https://'):
        raise CliError('args', 'MODEL_NOT_PINNED',
                       'propose needs a pinned local Meta model (low/medium tier)')
    bindable = _ui_bindable()
    with Core() as server:
        snap = ensure_discovery(server, default_providers(args))
    devices = snap.get('devices', []) if isinstance(snap, dict) else []
    bundle = build_bundle(devices, list(bindable))
    prompt_devices = [{'label': row.get('label', '?'), 'category': bdev['category'],
                       'opaque_id': bdev['opaque_id']}
                      for row, bdev in zip(devices, bundle['devices'])]
    from src.runtime.routing import SKILLS
    hints = {sid: nl_plan.param_hint(SKILLS[sid].get('input'))
             for sid in bindable if sid in SKILLS}
    prompt = v4_uidraft.build_ui_prompt(text, prompt_devices, bindable, hints=hints)
    ui_options = {'num_ctx': 4096, 'num_predict': 1024}
    if model_id == nl_router.TIERS['medium'][0]:
        # Pinned partial offload: full offload dies allocating a 3.7GB
        # pinned CUDA_Host buffer (01:34 + 01:40 500s); num_gpu=28 loads in
        # 21s on this host (14.9GB VRAM free, no lock-memory privilege).
        ui_options['num_gpu'] = 28
    transport = nl_plan.local_chat(model_id, endpoint,
                                   timeout=getattr(args, 'timeout', None) or 600,
                                   format=v4_ui.UI_RESPONSE_SCHEMA,
                                   options=ui_options)
    try:
        res = transport(prompt)
    except nl_plan.TransportError as e:
        raise CliError('inference', 'MODEL_UNAVAILABLE', str(e)[:200]) from None
    reply = res.get('content', '') if isinstance(res, dict) else res
    run = {'model_id': model_id, 'endpoint': endpoint,
           'reply_sha256': hashlib.sha256(reply.encode()).hexdigest()}
    try:
        doc, _ = extract_json(reply)
    except ValueError as e:
        if str(e) != 'no JSON object':
            raise CliError('inference', 'PATCH_REJECTED',
                           'Model reply is not a valid panel: %s' % (e,)) from None
        # No JSON at all reads as a refusal (§12): explicit, unrendered, uninstalled.
        return {'outcome': 'refusal', 'reason': 'model returned no JSON response',
                'offered_opaque_ids': [d['opaque_id'] for d in bundle['devices']],
                'devices': prompt_devices, 'primitives': sorted(bindable),
                'model_run': run, 'prompt_chars': len(prompt)}
    try:
        outcome, patch, detail, code = v4_ui.parse_response_full(doc, bindable)
    except v4_ui.UIError as e:
        raise CliError('inference', 'PATCH_REJECTED', 'Model reply is not a valid panel: %s' % (e,)) from None
    offered = [d['opaque_id'] for d in bundle['devices']]
    # Prompt-time label map: opaque ids salt rotating discovery keys, so the
    # patch-target label is unrecoverable later without this record.
    if outcome != 'proposal':
        key = 'clarifying_question' if outcome == 'clarification' else 'reason'
        out = {'outcome': outcome, key: detail, 'offered_opaque_ids': offered,
               'devices': prompt_devices, 'primitives': sorted(bindable),
               'model_run': run, 'prompt_chars': len(prompt)}
        if code:
            out['code'] = code
        return out
    return {'outcome': 'proposal', 'patch': patch, 'offered_opaque_ids': offered,
            'devices': prompt_devices,
            'primitives': sorted(bindable),
            'model_run': run,
            'prompt_chars': len(prompt)}


def _load_ui_patch_file(spec_file):
    if not spec_file:
        raise CliError('args', 'MISSING_INPUT', 'install needs --patch panel.json.')
    try:
        doc = json.loads(Path(spec_file).read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise CliError('args', 'SPEC_UNREADABLE', 'Cannot read patch: %s' % e)
    if not isinstance(doc, dict) or not isinstance(doc.get('patch'), dict):
        raise CliError('args', 'SPEC_INVALID', 'Patch file must hold a {patch, offered_opaque_ids} object.')
    return doc


def cmd_dashboards_install(args):
    """Install a proposed panel on a Companion relay (consent-bound).

    Re-validates the patch, checks the patch target was an id actually
    offered at propose time (anti-hallucination), then installs through
    the trusted set_controls path with the owner-supplied target label
    resolved to the live device key at dispatch time."""
    from src.forge import v4_ui
    from src.runtime import api_v2
    from src.runtime import dashboards as D
    from src.runtime.remote_controls import RemoteControlError
    doc = _load_ui_patch_file(getattr(args, 'patch', None))
    bindable = _ui_bindable()
    try:
        patch = v4_ui.validate_patch(doc['patch'], bindable)
    except v4_ui.UIError as e:
        raise CliError('inference', 'PATCH_REJECTED', 'Panel failed validation: %s' % (e,)) from None
    offered = doc.get('offered_opaque_ids') or []
    if patch.get('target_opaque_id') not in offered:
        raise CliError('verify', 'PATCH_TARGET_UNKNOWN',
                       'Patch target %r was not an id offered at propose time.' % (patch.get('target_opaque_id'),))
    rid = getattr(args, 'relay', '') or ''
    target = getattr(args, 'target', '') or ''
    if not rid or not target:
        raise CliError('args', 'MISSING_INPUT', 'install needs --relay RID and --target label.')
    preview_controls = [{'label': w['label'], 'skill_id': w['binding_primitive'],
                         'params': w['params']} for w in patch['widgets']]
    preview = {'relay_id': rid, 'target': target, 'controls': preview_controls}
    require_consent(args, preview_hash(preview), 'dashboards install on %s' % rid)
    with Core() as server:
        ensure_discovery(server, default_providers(args))
        controls = api_v2.remote_controls(server)
        router = api_v2.router(server)
        try:
            state = D.install_patch(controls, rid, patch, target, bindable,
                                    consent=True, resolve_target=router.resolve_target)
        except D.DashboardError as e:
            raise CliError('inference', 'PATCH_REJECTED', str(e)[:200]) from None
        except RemoteControlError as e:
            raise CliError('device', 'INSTALL_FAILED', str(e)[:200]) from None
    return {'relay_id': rid, 'target': target, 'controls': preview_controls, 'state': state}


def cmd_dashboards_revoke(args):
    """Revoke every control on a relay (consent-bound); later presses are denied."""
    from src.runtime import api_v2
    from src.runtime.remote_controls import RemoteControlError
    rid = getattr(args, 'relay', '') or ''
    if not rid:
        raise CliError('args', 'MISSING_INPUT', 'revoke needs --relay RID.')
    preview = {'relay_id': rid, 'action': 'revoke-all'}
    require_consent(args, preview_hash(preview), 'dashboards revoke %s' % rid)
    with Core() as server:
        if hasattr(server, 'restore_relays'):
            try:
                server.restore_relays()
            except Exception:
                pass
        controls = api_v2.remote_controls(server)
        try:
            state = controls.set_controls({'relay_id': rid, 'controls': [], 'consent': True})
        except RemoteControlError as e:
            raise CliError('device', 'REVOKE_FAILED', str(e)[:200]) from None
    return {'relay_id': rid, 'revoked': True, 'state': state}


def cmd_dashboards_export(args):
    """Export a saved dashboard (or a relay's live panel) as a sealed bundle.

    Read-only: verifies the source, seals it with a sha256 digest, and writes
    (or prints) the bundle JSON. Targets travel as opaque hints only."""
    from src.runtime import dashboards as D
    from src.runtime import dashboard_port as P
    from src.runtime.state_store import StateStore
    name = getattr(args, 'name', '') or ''
    rid = getattr(args, 'relay', '') or ''
    if not name:
        raise CliError('args', 'MISSING_INPUT', 'export needs --name BUNDLE_NAME.')
    if bool(getattr(args, 'saved', None)) == bool(rid):
        raise CliError('args', 'MISSING_INPUT',
                       'export needs exactly one of --saved NAME (stored dashboard) or --relay RID (live panel).')
    with Core() as server:
        ensure_discovery(server, default_providers(args))
        if rid:
            from src.runtime import api_v2
            controls = api_v2.remote_controls(server)
            try:
                bundle = P.export_bundle(name=name, controls=D.defs(controls, rid))
            except P.PortError as e:
                raise CliError('args', 'EXPORT_FAILED', str(e)[:200]) from None
        else:
            store = D.DashStore(StateStore.for_server(server))
            try:
                bundle = P.export_bundle(store=store, name=getattr(args, 'saved'))
            except P.PortError as e:
                raise CliError('args', 'EXPORT_FAILED', str(e)[:200]) from None
            if bundle['name'] != name:
                # Re-seal under the requested bundle name (export, not edit).
                bundle = P.export_bundle(
                    name=name,
                    controls=[dict(c, target=c.get('target_hint'))
                              for c in bundle['controls']])
    text = json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False)
    out = getattr(args, 'out', None)
    if out:
        try:
            Path(out).write_text(text, encoding='utf-8')
        except OSError as e:
            raise CliError('args', 'EXPORT_FAILED', 'Cannot write bundle: %s' % e)
        return {'bundle': bundle['name'], 'controls': len(bundle['controls']),
                'digest': bundle['integrity']['digest'], 'file': out}
    return {'bundle': bundle}


def cmd_dashboards_import(args):
    """Install a sealed dashboard bundle on a relay (consent-bound).

    Verifies the seal, resolves every target hint through the owner-supplied
    --target/--target-map, then installs through set_controls. --dry-run
    verifies + resolves and installs nothing."""
    from src.runtime import api_v2
    from src.runtime import dashboard_port as P
    from src.runtime.remote_controls import RemoteControlError
    spec = getattr(args, 'bundle', None)
    if not spec:
        raise CliError('args', 'MISSING_INPUT', 'import needs --bundle panel-bundle.json.')
    try:
        bundle = json.loads(Path(spec).read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise CliError('args', 'SPEC_UNREADABLE', 'Cannot read bundle: %s' % e)
    rid = getattr(args, 'relay', '') or ''
    if not rid:
        raise CliError('args', 'MISSING_INPUT', 'import needs --relay RID.')
    target = getattr(args, 'target', None) or None
    raw_map = getattr(args, 'target_map', None)
    try:
        target_map = json.loads(raw_map) if raw_map else None
    except ValueError as e:
        raise CliError('args', 'SPEC_INVALID', 'target-map is not JSON: %s' % e)
    if target_map is not None and not isinstance(target_map, dict):
        raise CliError('args', 'SPEC_INVALID', 'target-map must be a JSON object.')
    try:
        plan = P.dry_run(bundle, target=target, target_map=target_map)
    except P.PortError as e:
        raise CliError('verify', 'BUNDLE_REJECTED', str(e)[:200]) from None
    if getattr(args, 'dry_run', False):
        return {'relay_id': rid, 'dry_run': True, 'name': plan['name'],
                'controls': plan['controls'], 'targets': plan['targets'],
                'bundle_digest': plan['bundle_digest']}
    preview = {'relay_id': rid, 'bundle': plan['name'],
               'digest': plan['bundle_digest'], 'controls': plan['controls']}
    require_consent(args, preview_hash(preview), 'dashboards import on %s' % rid)
    save_as = getattr(args, 'save_as', None) or None
    with Core() as server:
        ensure_discovery(server, default_providers(args))
        controls = api_v2.remote_controls(server)
        router = api_v2.router(server)
        store = None
        if save_as:
            from src.runtime import dashboards as D
            from src.runtime.state_store import StateStore
            store = D.DashStore(StateStore.for_server(server))
        try:
            receipt = P.import_bundle(controls, rid, bundle, target=target,
                                      target_map=target_map, consent=True,
                                      resolve_target=router.resolve_target,
                                      store=store, save_as=save_as)
        except P.PortError as e:
            raise CliError('verify', 'BUNDLE_REJECTED', str(e)[:200]) from None
        except RemoteControlError as e:
            raise CliError('device', 'INSTALL_FAILED', str(e)[:200]) from None
    receipt.pop('state', None)
    return receipt


# ---------------- workflows ----------------

def workflow_store():
    from src.runtime.state_store import StateStore
    from src.runtime.workflows import StateStoreJournal
    path = private_root() / 'cli_workflows.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    return StateStoreJournal(StateStore(path))


def cmd_workflows_list(args):
    store = workflow_store()
    try:
        doc = store._s.load()
    except Exception:
        doc = {}
    rows = [{'workflow_id': k, 'status': v.get('status')}
            for k, v in sorted((doc.get('workflows') or {}).items())]
    return {'workflows': rows, 'dry_run': bool(getattr(args, 'dry_run', False))}


def cmd_workflows_plan(args):
    from src.runtime.workflows import validate_workflow, WorkflowError
    text = getattr(args, 'text', '') or ''
    spec_file = getattr(args, 'file', None)
    model_run = None
    if spec_file:
        try:
            spec = json.loads(Path(spec_file).read_text(encoding='utf-8'))
        except (OSError, ValueError) as e:
            raise CliError('args', 'SPEC_UNREADABLE', 'Cannot read spec: %s' % e)
    elif text.strip():
        spec, model_run = _plan_from_text(args, text)
    else:
        raise CliError('args', 'MISSING_INPUT', 'plan needs request text or --file spec.json.')
    try:
        validate_workflow(spec)
    except WorkflowError as e:
        raise CliError('args', 'SPEC_INVALID', str(e)[:200])
    out = {'workflow_id': spec.get('workflow_id'), 'steps': len(spec.get('steps', [])),
           'valid': True, 'spec': spec}
    if model_run is not None:
        out['model_run'] = model_run
        out['consent'] = preview_hash(spec)
    return out


def _plan_from_text(args, text):
    from src.runtime import nl_plan, nl_router
    model_id = getattr(args, 'model', None) or nl_router.TIERS['low'][0]
    endpoint = next((ep for mid, ep in nl_router.TIERS.values() if mid == model_id), None)
    if endpoint is None or endpoint.startswith('https://'):
        raise CliError('args', 'MODEL_NOT_PINNED',
                       'plan-text needs a pinned local Meta model (low/medium tier)')
    with Core() as server:
        snap = ensure_discovery(server, default_providers(args))
    devices = snap.get('devices', []) if isinstance(snap, dict) else []
    transport = nl_plan.local_chat(model_id, endpoint, timeout=getattr(args, 'timeout', None) or 180,
                                   format=nl_plan.PLAN_RESPONSE_SCHEMA)
    try:
        res = nl_plan.plan(text, devices, transport)
    except nl_plan.PlanError as e:
        raise CliError('inference', 'PLAN_REJECTED', str(e)[:300])
    res['spec']['workflow_id'] = 'wf-%s' % hashlib.sha256(text.encode()).hexdigest()[:12]
    return res['spec'], dict(res['model_run'], reply_sha256=res['reply_sha256'])


def cmd_workflows_run(args):
    from src.runtime.workflows import run, WorkflowError
    from src.runtime import api_v2
    if getattr(args, 'dry_run', False):
        try:
            planned = cmd_workflows_plan(args)
        except CliError:
            planned = {'workflow_id': getattr(args, 'workflow_id', '') or '', 'planned': False}
        planned['dry_run'] = True
        if planned.get('valid'):
            planned['consent'] = preview_hash(planned['spec'])
            planned['next'] = 'workflows run --file %s --consent %s' % (
                getattr(args, 'file', ''), planned['consent'])
        return planned
    spec_file = getattr(args, 'file', None)
    if spec_file:
        planned = cmd_workflows_plan(args)
        spec, wid = planned['spec'], planned['workflow_id']
    else:
        wid = getattr(args, 'workflow_id', '') or ''
        store = workflow_store()
        record = store.get(wid)
        if record is None or 'spec' not in record:
            raise CliError('args', 'NOT_FOUND',
                           'Unknown workflow %r; pass --file spec.json.' % wid)
        spec = record['spec']
    require_consent(args, preview_hash(spec), 'workflows run')
    prior = workflow_store().get(wid)
    if prior is not None:
        raise CliError('args', 'ALREADY_RECORDED',
                       'Workflow %r already ran (status %s); the engine never dispatches twice. '
                       'Use `workflows status %s` to inspect it, or a fresh workflow_id to re-run.'
                       % (wid, prior.get('status'), wid))
    with Core() as server:
        snap = ensure_discovery(server, default_providers(args))
        spec = _resolve_workflow_targets(spec, snap)
        try:
            result = run(spec, api_v2.router(server), workflow_store(), wid, actor='cli')
        except WorkflowError as e:
            raise CliError('permission', 'WORKFLOW_BLOCKED', str(e)[:200])
    return {'workflow_id': wid, 'result': result}


def _resolve_workflow_targets(spec, snap):
    """Validate targets against the live snapshot; labels stay labels.

    Keys rotate every discovery, so the spec keeps the stable label (and the
    consent hash stays valid across processes); dispatch resolves to the live
    key via Router.resolve_target. Stale keys are rejected, never guessed."""
    import copy
    from src.runtime import nl_plan
    devices = snap.get('devices', []) if isinstance(snap, dict) else []
    by_key = {d.get('key') for d in devices}
    spec = copy.deepcopy(spec)
    for step in spec.get('steps', []):
        target = step.get('target', '')
        if target in by_key or target == 'fabric':
            continue
        try:
            label, _, disambiguated = nl_plan.resolve_target(target, devices)
        except nl_plan.PlanError as e:
            raise CliError('device', 'TARGET_UNRESOLVED',
                           '%s; use the exact label from `devices discover`.' % e)
        step['target'] = label
        if disambiguated:
            step['disambiguated'] = True
    return spec


def cmd_workflows_status(args):
    wid = getattr(args, 'workflow_id', '') or ''
    record = workflow_store().get(wid)
    if record is None:
        raise CliError('args', 'NOT_FOUND', 'Unknown workflow %r.' % wid)
    return {'workflow': record}


def _workflow_step_preview(wid, sid, step):
    return {'workflow_id': wid, 'step_id': sid, 'skill_id': step['skill_id'],
            'target': step['target'], 'params': step['params']}


def cmd_workflows_compose(args):
    from src.runtime import api_v2, composer as comp, nl_plan, nl_router
    text = getattr(args, 'text', '') or ''
    if not text.strip():
        raise CliError('args', 'MISSING_INPUT', 'compose needs request text.')
    model_id = getattr(args, 'model', None) or nl_router.TIERS['low'][0]
    endpoint = next((ep for mid, ep in nl_router.TIERS.values() if mid == model_id), None)
    if endpoint is None or endpoint.startswith('https://'):
        raise CliError('args', 'MODEL_NOT_PINNED',
                       'compose-text needs a pinned local Meta model (low/medium tier)')
    with Core() as server:
        snap = ensure_discovery(server, default_providers(args))
        devices = snap.get('devices', []) if isinstance(snap, dict) else []
        transport = nl_plan.local_chat(model_id, endpoint,
                                       timeout=getattr(args, 'timeout', None) or 180,
                                       format=comp.COMPOSER_RESPONSE_SCHEMA)
        try:
            doc = comp.propose_and_compose(text, devices, api_v2.router(server), transport)
        except comp.ComposerError as e:
            raise CliError('inference', 'COMPOSE_REJECTED', str(e)[:300])
    out = {'composed': doc}
    if doc['refused'] == 0:
        try:
            spec = comp.to_workflow(doc)
        except comp.ComposerError as e:
            raise CliError('args', 'SPEC_INVALID', str(e)[:200])
        out['spec'] = spec
        out['consent'] = preview_hash(spec)
    return out


def cmd_workflows_summary(args):
    from src.runtime import composer as comp
    wid = getattr(args, 'workflow_id', '') or ''
    record = workflow_store().get(wid)
    if record is None:
        raise CliError('args', 'NOT_FOUND', 'Unknown workflow %r.' % wid)
    return {'summary': comp.summarize(record)}


def cmd_workflows_approve(args):
    from src.runtime.workflows import approve, WorkflowError
    from src.runtime import api_v2
    wid = getattr(args, 'workflow_id', '') or ''
    sid = getattr(args, 'step_id', '') or ''
    allow = not bool(getattr(args, 'deny', False))
    store = workflow_store()
    record = store.get(wid)
    if record is None:
        raise CliError('args', 'NOT_FOUND', 'Unknown workflow %r.' % wid)
    if record.get('status') != 'waiting_approval':
        raise CliError('args', 'NOT_WAITING',
                       'Workflow %r is %s, not waiting_approval.' % (wid, record.get('status')))
    states = {s['id']: s for s in record.get('steps', [])}
    if states.get(sid, {}).get('state') != 'WAITING':
        raise CliError('args', 'STEP_NOT_WAITING',
                       'Step %r of workflow %r is not waiting for approval.' % (sid, wid))
    step = ((record.get('spec') or {}).get('steps') or {}).get(sid)
    if step is None:
        raise CliError('args', 'STEP_NOT_WAITING',
                       'Step %r of workflow %r is not waiting for approval.' % (sid, wid))
    preview = _workflow_step_preview(wid, sid, step)
    require_consent(args, preview_hash(preview),
                    'workflows approve %s %s (%s %s %s)' % (
                        wid, sid, step['skill_id'], step['target'], step['params']))
    with Core() as server:
        ensure_discovery(server, default_providers(args))
        try:
            record = approve(wid, sid, allow, api_v2.router(server), store, actor='cli')
        except WorkflowError as e:
            raise CliError('permission', 'WORKFLOW_BLOCKED', str(e)[:200])
    return {'workflow_id': wid, 'step_id': sid, 'allowed': allow,
            'preview': preview, 'record': record}


# ---------------- routes / diagnose / transplant (F90 wiring) ----------------

def _read_json_file(spec_file, what):
    try:
        return json.loads(Path(spec_file).read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise CliError('args', 'SPEC_UNREADABLE', 'Cannot read %s: %s' % (what, e))


def cmd_routes_list(args):
    from urllib.parse import urlencode
    from src.runtime import api_v2
    target = getattr(args, 'target', '') or ''
    if not target.strip():
        raise CliError('args', 'MISSING_INPUT', 'routes list needs --target.')
    with Core() as server:
        status, body = api_v2.get(server, '/api/v2/route_intel', urlencode({'target': target}))
    return check_status(status, body)


def cmd_routes_dispatch(args):
    from src.fabric import route_intel as RI
    from src.runtime import api_v2
    target = getattr(args, 'target', '') or ''
    if not target.strip():
        raise CliError('args', 'MISSING_INPUT', 'routes dispatch needs --target.')
    params = getattr(args, 'params', None)
    if params:
        try:
            params = json.loads(params)
        except ValueError as e:
            raise CliError('args', 'PARAMS_INVALID', 'Cannot parse --params JSON: %s' % e)
        if not isinstance(params, dict):
            raise CliError('args', 'PARAMS_INVALID', '--params must be a JSON object.')
    op = getattr(args, 'op', None) or 'get_status'
    consent = True
    if op not in RI.READ_OPS:
        preview = {'op': op, 'target': target, 'relay_id': getattr(args, 'relay', None),
                   'params': params}
        require_consent(args, preview_hash(preview), 'routes dispatch')
    with Core() as server:
        status, body = api_v2.post(server, '/api/v2/route_intel/dispatch', {
            'target': target, 'op': op, 'consent': consent,
            'params': params,
            'capability': getattr(args, 'capability', None) or 'ble_scan',
            'relay_id': getattr(args, 'relay', None)})
    return check_status(status, body)


def cmd_routes_simulate_loss(args):
    from src.runtime import api_v2
    target = getattr(args, 'target', '') or ''
    lost = getattr(args, 'lost_relay', '') or ''
    if not target.strip() or not lost.strip():
        raise CliError('args', 'MISSING_INPUT',
                       'routes simulate-loss needs --target and --lost-relay.')
    with Core() as server:
        status, body = api_v2.post(server, '/api/v2/route_intel/simulate_loss',
                                   {'target': target, 'lost_relay': lost})
    return check_status(status, body)


def cmd_diagnose(args):
    from src.runtime import api_v2
    question = getattr(args, 'question', '') or ''
    bundle_file = getattr(args, 'bundle', None)
    if not question.strip():
        raise CliError('args', 'MISSING_INPUT', 'diagnose needs --question.')
    if not bundle_file:
        raise CliError('args', 'MISSING_INPUT', 'diagnose needs --bundle facts.json.')
    bundle = _read_json_file(bundle_file, 'bundle')
    with Core() as server:
        status, body = api_v2.post(server, '/api/v2/diagnose',
                                   {'question': question, 'bundle': bundle,
                                    'device': getattr(args, 'device', None)})
    return check_status(status, body)


def cmd_transplant_run(args):
    from src.runtime import api_v2
    request_file = getattr(args, 'request', None)
    if not request_file:
        raise CliError('args', 'MISSING_INPUT', 'transplant run needs --request plan.json.')
    req = _read_json_file(request_file, 'transplant request')
    if not isinstance(req, dict):
        raise CliError('args', 'SPEC_INVALID', 'Transplant request must be a JSON object.')
    require_consent(args, preview_hash(req), 'transplant run')
    with Core() as server:
        status, body = api_v2.post(server, '/api/v2/transplant/run', req)
    return check_status(status, body)


def cmd_migrate_propose(args):
    from src.runtime import api_v2
    body = {'text': getattr(args, 'text', None), 'source': getattr(args, 'source', None),
            'target': getattr(args, 'target', None), 'match': getattr(args, 'match', None)}
    if not body['text'] and not (body['source'] and body['target']):
        raise CliError('args', 'MISSING_INPUT',
                       'migrate propose needs --text or --source + --target.')
    with Core() as server:
        status, resp = api_v2.post(server, '/api/v2/migrate/propose', body)
    return check_status(status, resp)


def cmd_migrate_apply(args):
    from src.runtime import api_v2
    proposal_file = getattr(args, 'proposal', None)
    if not proposal_file:
        raise CliError('args', 'MISSING_INPUT', 'migrate apply needs --proposal proposal.json.')
    proposal = _read_json_file(proposal_file, 'migration proposal')
    if not isinstance(proposal, dict):
        raise CliError('args', 'SPEC_INVALID', 'Migration proposal must be a JSON object.')
    require_consent(args, preview_hash(proposal), 'migrate apply')
    with Core() as server:
        status, resp = api_v2.post(server, '/api/v2/migrate/apply',
                                   {'proposal': proposal, 'consent': True})
    return check_status(status, resp)


def cmd_migrate_rollback(args):
    from src.runtime import api_v2
    receipt_file = getattr(args, 'receipt', None)
    if not receipt_file:
        raise CliError('args', 'MISSING_INPUT', 'migrate rollback needs --receipt receipt.json.')
    receipt = _read_json_file(receipt_file, 'migration receipt')
    if not isinstance(receipt, dict):
        raise CliError('args', 'SPEC_INVALID', 'Migration receipt must be a JSON object.')
    require_consent(args, preview_hash(receipt), 'migrate rollback')
    with Core() as server:
        status, resp = api_v2.post(server, '/api/v2/migrate/rollback',
                                   {'receipt': receipt, 'consent': True})
    return check_status(status, resp)


# ---------------- approvals ----------------

def cmd_approvals_list(args):
    rows = [{'request_id': k, 'text': v.get('text'), 'hash': v.get('hash'),
             'created': v.get('created')} for k, v in sorted(pending_load().items())]
    return {'approvals': rows}


def cmd_approvals_approve(args):
    from src.runtime import command as cmdmod
    rid = getattr(args, 'request_id', '') or ''
    consent = getattr(args, 'consent', None)
    if getattr(args, 'yes', False):
        raise CliError('permission', 'CONSENT_REQUIRED',
                       '--yes cannot bypass mandatory consent for approvals approve.')

    def _claim(rows):
        if rid not in rows:
            return None
        return rows.pop(rid)

    pending = pending_mutate(_claim)
    if pending is None:
        raise CliError('permission', 'NOT_FOUND',
                       'Unknown request %r; consent is still required for any approval.' % rid)
    if consent != pending['hash']:
        def _restore(rows):
            rows[rid] = pending
            return rid

        pending_mutate(_restore)
        raise CliError('permission', 'CONSENT_REQUIRED',
                       'approvals approve needs explicit preview-bound consent: re-run with '
                       '--consent %s' % pending['hash'])
    with Core() as server:
        ensure_discovery(server, default_providers(args))
        try:
            result = cmdmod.execute(server, pending['intent'], True, pending['preview'])
        except cmdmod.CommandError as e:
            def _restore(rows):
                rows[rid] = pending
                return rid

            pending_mutate(_restore)
            raise CliError('permission', 'EXECUTE_BLOCKED', str(e))
    return {'request_id': rid, 'executed': True, 'result': result}


def cmd_approvals_deny(args):
    rid = getattr(args, 'request_id', '') or ''

    def _deny(rows):
        if rid not in rows:
            return False
        del rows[rid]
        return True

    if not pending_mutate(_deny):
        raise CliError('args', 'NOT_FOUND', 'Unknown request %r.' % rid)
    return {'request_id': rid, 'denied': True}


# ---------------- sessions ----------------

def session_journal():
    from src.fabric.session import SessionJournal
    path = private_root() / 'cli_sessions.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text('[]', encoding='utf-8')
    return SessionJournal(path)


def _journal_open_changes(journal):
    from src.fabric.session import SessionError
    try:
        return journal.open_changes()
    except SessionError as e:
        raise CliError('internal', 'SESSION_CORRUPT', 'Session journal is corrupt; preserve %s for review.' % journal.path)


def _journal_close(journal, sid, state, detail=''):
    from src.fabric.session import SessionError
    try:
        journal.close(sid, state, detail)
    except SessionError as e:
        raise CliError('internal', 'SESSION_CORRUPT', 'Session journal is corrupt; preserve %s for review.' % journal.path)


def cmd_sessions_list(args):
    return {'sessions': _journal_open_changes(session_journal())}


def cmd_sessions_inspect(args):
    sid = getattr(args, 'session_id', '') or ''
    for row in _journal_open_changes(session_journal()):
        if str(row.get('id', '')) == sid:
            return {'session': row}
    raise CliError('args', 'NOT_FOUND', 'Unknown session %r.' % sid)


def cmd_sessions_undo(args):
    from src.fabric.session import restore
    sid = getattr(args, 'session_id', '') or ''
    journal = session_journal()
    target = None
    for row in _journal_open_changes(journal):
        if str(row.get('id', '')) == sid:
            target = row
    if target is None:
        raise CliError('args', 'NOT_FOUND', 'Unknown session %r.' % sid)
    require_consent(args, sid, 'sessions undo')
    with Core() as server:
        try:
            outcome = restore(target, server.android)
        except Exception as e:
            raise CliError('uncertain', 'UNDO_UNCERTAIN', 'Restore outcome uncertain: %s' % e)
    _journal_close(journal, sid, 'reverted')
    return {'session_id': sid, 'outcome': outcome}


# ---------------- evidence ----------------

def cmd_evidence_list(args):
    dest = evidence_dir(args)
    rows = []
    if dest.exists():
        for child in sorted(dest.glob('*')):
            if child.name.startswith('.'):
                continue
            rows.append({'name': child.name, 'bytes': child.stat().st_size if child.is_file() else 0})
    return {'evidence_dir': str(dest), 'artifacts': rows}


def cmd_evidence_verify(args):
    sid = getattr(args, 'session_id', '') or ''
    dest = evidence_dir(args)
    manifest = dest / (sid + '.sha256')
    if not manifest.exists():
        raise CliError('verify', 'MANIFEST_MISSING', 'No manifest for session %r.' % sid)
    failures = []
    for line in manifest.read_text(encoding='utf-8').splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        digest, name = parts
        blob = dest / name
        if not blob.exists():
            failures.append(name + ': missing')
            continue
        actual = hashlib.sha256(blob.read_bytes()).hexdigest()
        if actual != digest:
            failures.append(name + ': hash mismatch')
    if failures:
        raise CliError('verify', 'VERIFY_FAILED', '; '.join(failures[:5]))
    return {'session_id': sid, 'verified': True}


def cmd_evidence_export(args):
    sid = getattr(args, 'session_id', '') or ''
    dest = evidence_dir(args)
    dest.mkdir(parents=True, exist_ok=True)
    journal = session_journal()
    payload = {'session_id': sid, 'exported_at': time.time(),
               'open_changes': _journal_open_changes(journal), 'snapshot': snapshot_load()}
    blob = dest / (sid + '.json')
    blob.write_text(json.dumps(payload, indent=1), encoding='utf-8')
    digest = hashlib.sha256(blob.read_bytes()).hexdigest()
    (dest / (sid + '.sha256')).write_text('%s  %s\n' % (digest, blob.name), encoding='utf-8')
    return {'session_id': sid, 'exported': str(blob), 'sha256': digest}


# ---------------- test suites ----------------

def _row(name, ok, detail=''):
    return {'check': name, 'ok': bool(ok), 'detail': str(detail)[:160]}


def cmd_test_smoke(args):
    rows = []
    try:
        with Core():
            rows.append(_row('core_init', True))
    except Exception as e:
        rows.append(_row('core_init', False, e))
    try:
        report = cmd_doctor(args)
        rows.append(_row('doctor', report['global'] in ('READY', 'BLOCKED', 'NOT_TESTED'),
                         report['global']))
    except Exception as e:
        rows.append(_row('doctor', False, e))
    avail = local_availability()
    rows.append(_row('local_probe_attempted', True, str(avail['reachable'])))
    failed = [r for r in rows if not r['ok']]
    if failed:
        raise CliError('verify', 'SMOKE_FAILED', '; '.join(r['check'] for r in failed))
    return {'rows': rows}


def cmd_test_integrations(args):
    rows = []
    with Core() as server:
        for path in ('/api/v2/primitives/catalog', '/api/v2/relays', '/api/v2/contract'):
            try:
                status, body = api_get(args, server, path, {})
                rows.append(_row('GET ' + path, status == 200, 'status %s' % status))
            except CliError as e:
                rows.append(_row('GET ' + path, False, e))
        try:
            status, body = api_post(args, server, '/api/v2/command/parse',
                                    {'text': 'list connected devices', 'lang': 'en'})
            rows.append(_row('POST command/parse', status in (200, 400), 'status %s' % status))
        except CliError as e:
            rows.append(_row('POST command/parse', False, e))
    failed = [r for r in rows if not r['ok']]
    if failed:
        raise CliError('verify', 'INTEGRATIONS_FAILED', '; '.join(r['check'] for r in failed))
    return {'rows': rows}


def cmd_test_hardware(args):
    rows = []
    adb = shutil.which('adb')
    rows.append(_row('adb_present', bool(adb), adb or 'install platform-tools'))
    if adb:
        try:
            proc = subprocess.run([adb, 'devices'], capture_output=True, text=True, timeout=15)
            lines = [ln for ln in proc.stdout.splitlines()[1:] if ln.strip()]
            attached = [ln for ln in lines if ln.endswith('device')]
            rows.append(_row('adb_devices', True, '%d attached' % len(attached)))
            for ln in attached[:8]:
                rows.append(_row('device ' + ln.split()[0], True, 'device'))
        except Exception as e:
            rows.append(_row('adb_devices', False, e))
    if not [r for r in rows if r['check'].startswith('device ')]:
        raise CliError('device', 'NO_DEVICES', 'No hardware attached; connect a device or boot the AVD.')
    return {'rows': rows}


def cmd_test_models(args):
    rows = []
    avail = local_availability()
    rows.append(_row('local_fast', avail['local_fast'], str(avail['endpoints']['LOCAL-FAST'])))
    rows.append(_row('local_quality', avail['local_quality'],
                     str(avail['endpoints']['LOCAL-QUALITY'])))
    ai = connected_ai()
    rows.append(_row('connected_ai', ai is not None,
                     ('%s (%s, %s)' % (ai['name'], ai['model'], ai['execution'])) if ai else 'CUSTOM_PROVIDER_MISSING'))
    if not (avail['local_fast'] or avail['local_quality'] or ai):
        raise CliError('inference', 'NO_MODELS', 'No local model and no connected AI.')
    return {'rows': rows}


def cmd_test_jury(args):
    rows = []
    for name, fn in (('smoke', cmd_test_smoke), ('integrations', cmd_test_integrations),
                     ('hardware', cmd_test_hardware), ('models', cmd_test_models)):
        try:
            fn(args)
            rows.append(_row(name, True))
        except CliError as e:
            rows.append(_row(name, False, '%s: %s' % (e.code, e)))
    failed = [r for r in rows if not r['ok']]
    verdict = 'GO' if not failed else 'CONDITIONAL (%s)' % ', '.join(r['check'] for r in failed)
    return {'rows': rows, 'verdict': verdict}


# ---------------- judge demo / serve / agent ----------------

def cmd_judge_demo(args):
    from src.runtime.readiness import REQUIRED, collect, plain_line
    args.session_id = getattr(args, 'session_id', None) or 'judge-demo'
    steps = []
    report = cmd_doctor(args)
    split = collect(report['features'], required=REQUIRED)
    need, extra = split['required'], split['optional']
    ready = sum(1 for v in need.values() if v == 'READY')
    if split['global'] == 'READY':
        missing = [n for n, v in sorted(extra.items()) if v != 'READY']
        say = 'Ready for the offline demo: %d/%d required checks passed.' % (ready, len(need))
        if missing:
            say += ' Optional extras missing (%s); the demo continues without them.' % (
                ', '.join(plain_line(n, extra[n]) for n in missing))
        else:
            say += ' All optional extras present too.'
    else:
        bad = [n for n, v in sorted(need.items()) if v != 'READY']
        say = 'Demo blocked: required checks failing (%s).' % (
            ', '.join(plain_line(n, need[n]) for n in bad))
    steps.append({'step': 'doctor', 'required': split['global'], 'overall': report['global'],
                  'say': say})
    found = cmd_devices_discover(args)
    noun = 'device' if found['count'] == 1 else 'devices'
    steps.append({'step': 'discover', 'count': found['count'],
                  'say': 'Found %d %s nearby (read-only scan, nothing was changed).'
                         % (found['count'], noun)})
    caps = cmd_capabilities_list(args)
    steps.append({'step': 'capabilities', 'primitives': len(caps['primitives']),
                  'say': '%d built-in device actions available.' % len(caps['primitives'])})
    exported = cmd_evidence_export(args)
    steps.append({'step': 'evidence_export', 'sha256': exported['sha256'][:16],
                  'say': 'Saved the demo evidence file (sha %s).' % exported['sha256'][:16]})
    verified = cmd_evidence_verify(args)
    steps.append({'step': 'evidence_verify', 'verified': verified['verified'],
                  'say': 'Evidence file verified: nothing was modified.'})
    verdict = 'DEMO_COMPLETE' if split['global'] == 'READY' else 'DEMO_BLOCKED'
    return {'steps': steps, 'verdict': verdict}


def cmd_demo(args):
    """Offline demo, no hardware needed (same flow as the older `judge demo`)."""
    args.session_id = getattr(args, 'session_id', None) or 'demo'
    return cmd_judge_demo(args)


def cmd_serve(args):
    import src.server as server_mod
    port = int(getattr(args, 'port', None) or 18765)
    stop = threading.Event()

    def _handler(signum, frame):
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (OSError, ValueError):
            pass
    with server_mod.create_server(port) as server:
        from src.runtime import command_drain
        command_drain.start(server)   # Companion typed/spoken orders -> parse -> report back
        sys.stderr.write('OpenBridge serving http://127.0.0.1:%s (headless=%s)\n'
                         % (server.server_port, bool(getattr(args, 'headless', False))))
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.2},
                                  daemon=True)
        thread.start()
        while not stop.wait(0.2):
            pass
        server.shutdown()
        thread.join(timeout=5)
    return {'served': True, 'port': port}


def cmd_agent_start(args):
    import src.server as server_mod
    port = int(getattr(args, 'port', None) or 9876)
    stop = threading.Event()

    def _handler(signum, frame):
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (OSError, ValueError):
            pass
    bridge = server_mod.start_windows_bridge(port)
    sys.stderr.write('Bridge agent listener on port %s (graceful shutdown armed)\n' % port)
    try:
        while not stop.wait(0.2):
            pass
    finally:
        try:
            bridge.close()
        except Exception:
            pass
    return {'agent': 'stopped', 'port': port}


# ---------------- argument parsing ----------------

def _globals(parser, leaf=False):
    # Leaf parsers use SUPPRESS so flags given before the subcommand survive.
    kw = {'default': argparse.SUPPRESS} if leaf else {}
    parser.add_argument('--json', action='store_true', **kw)
    parser.add_argument('--quiet', action='store_true', **kw)
    parser.add_argument('--verbose', action='store_true', **kw)
    parser.add_argument('--no-color', action='store_true', **kw)
    parser.add_argument('--timeout', type=float, **({} if leaf else {'default': None}), **kw)
    parser.add_argument('--model', **({} if leaf else {'default': None}), **kw)
    parser.add_argument('--provider', **({} if leaf else {'default': None}), **kw)
    parser.add_argument('--session', **({} if leaf else {'default': None}), **kw)
    parser.add_argument('--evidence-dir', **({} if leaf else {'default': None}), **kw)
    parser.add_argument('--dry-run', action='store_true', **kw)
    parser.add_argument('--yes', action='store_true', **kw)
    parser.add_argument('--consent', **({} if leaf else {'default': None}), **kw)
    parser.add_argument('--providers', **({} if leaf else {'default': None}), **kw)
    parser.add_argument('--server', dest='server_url', **({} if leaf else {'default': None}), **kw,
                        help='client mode: http://127.0.0.1:PORT of a running server')
    return parser


def build_parser():
    parser = _globals(argparse.ArgumentParser(prog='openbridge', description='OpenBridge CLI'))
    parser.add_argument('--version', action='store_true')
    subs = parser.add_subparsers(dest='command')

    def leaf(parent, name, func, command_name):
        leaf_parser = parent.add_parser(name)
        _globals(leaf_parser, leaf=True)
        leaf_parser.set_defaults(func=func, command_name=command_name)
        return leaf_parser

    leaf(subs, 'version', cmd_version, 'version')
    leaf(subs, 'doctor', cmd_doctor, 'doctor')
    leaf(subs, 'init', cmd_init, 'init')

    models = subs.add_parser('models')
    model_subs = models.add_subparsers(dest='models_command')
    leaf(model_subs, 'list', cmd_models_list, 'models list')
    leaf(model_subs, 'status', cmd_models_status, 'models status')
    test_parser = leaf(model_subs, 'test', cmd_models_test, 'models test')
    test_parser.add_argument('--deep', action='store_true')
    leaf(model_subs, 'benchmark', cmd_models_benchmark, 'models benchmark')

    ai = subs.add_parser('ai', help='connect your own model or API by hand (no paid model is built in)')
    ai_subs = ai.add_subparsers(dest='ai_command')
    leaf(ai_subs, 'list', cmd_ai_list, 'ai list')
    ai_add = leaf(ai_subs, 'add', cmd_ai_add, 'ai add')
    ai_add.add_argument('--name', required=True, help='short id, e.g. lmstudio, openrouter')
    ai_add.add_argument('--kind', choices=['openai', 'ollama'], default='openai',
                        help='openai = any OpenAI-compatible /chat/completions server; ollama = /api/chat')
    ai_add.add_argument('--base-url', required=True, help='e.g. http://127.0.0.1:1234/v1 or https://openrouter.ai/api/v1')
    ai_add.add_argument('--api-key-env', default=None, help='name of the environment variable holding the key')
    ai_add.add_argument('--store-key', action='store_true', help='prompt for the key and keep it in the OS vault')
    ai_add.add_argument('--timeout-s', type=int, default=None)
    ai_add.add_argument('--max-tokens', type=int, default=None)
    ai_add.add_argument('--json-mode', action='store_true', help='send response_format=json_object (if supported)')
    ai_add.add_argument('--no-activate', action='store_true')
    ai_rm = leaf(ai_subs, 'remove', cmd_ai_remove, 'ai remove')
    ai_rm.add_argument('name')
    ai_use = leaf(ai_subs, 'use', cmd_ai_use, 'ai use')
    ai_use.add_argument('name', help='provider name, or "none" to disconnect')
    ai_test = leaf(ai_subs, 'test', cmd_ai_test, 'ai test')
    ai_test.add_argument('name', nargs='?')

    learn = subs.add_parser('learn', help='what OpenBridge learned about each device')
    learn_subs = learn.add_subparsers(dest='learn_command')
    lr = leaf(learn_subs, 'report', cmd_learn_report, 'learn report')
    lr.add_argument('--summary', action='store_true')
    leaf(learn_subs, 'reset', cmd_learn_reset, 'learn reset')

    create = subs.add_parser('create', help='new cross-device features from proven capabilities')
    create_subs = create.add_subparsers(dest='create_command')
    cs = leaf(create_subs, 'suggest', cmd_create_suggest, 'create suggest')
    cs.add_argument('--limit', type=int, default=12)

    links = subs.add_parser('links', help='devices that talk to each other')
    links_subs = links.add_subparsers(dest='links_command')
    la = leaf(links_subs, 'add', cmd_links_add, 'links add')
    la.add_argument('--when', required=True, help='trigger entity, e.g. media_player.living_room')
    la.add_argument('--state', required=True, help='trigger state, e.g. playing')
    la.add_argument('--then', required=True, help='target entity')
    la.add_argument('--action', required=True)
    la.add_argument('--value', type=float, default=None)
    la.add_argument('--title', default='')
    la.add_argument('--cooldown', type=int, default=30)
    lap = leaf(links_subs, 'approve', cmd_links_approve, 'links approve')
    lap.add_argument('id')
    leaf(links_subs, 'list', cmd_links_list, 'links list')
    lrm = leaf(links_subs, 'remove', cmd_links_remove, 'links remove')
    lrm.add_argument('id')
    lw = leaf(links_subs, 'watch', cmd_links_watch, 'links watch')
    lw.add_argument('--seconds', type=float, default=60)
    lw.add_argument('--interval', type=float, default=2)

    skills = subs.add_parser('skills', help='saved features that run with no AI model, and ready-made skill packs')
    skills_subs = skills.add_subparsers(dest='skills_command')
    leaf(skills_subs, 'list', cmd_skills_list, 'skills list')
    for name, func in (('show', cmd_skills_show), ('approve', cmd_skills_approve), ('run', cmd_skills_run),
                       ('remove', cmd_skills_remove)):
        leaf(skills_subs, name, func, 'skills ' + name).add_argument('id')
    sex = leaf(skills_subs, 'export', cmd_skills_export, 'skills export')
    sex.add_argument('ids', nargs='*')
    sex.add_argument('--out', required=True)
    leaf(skills_subs, 'import', cmd_skills_import, 'skills import').add_argument('file')
    leaf(skills_subs, 'packs', cmd_skills_packs, 'skills packs').add_argument('--lang', default='en', choices=['en', 'fr'])
    sps = leaf(skills_subs, 'pack-show', cmd_skills_pack_show, 'skills pack-show')
    sps.add_argument('id')
    sps.add_argument('--lang', default='en', choices=['en', 'fr'])
    leaf(skills_subs, 'pack-check', cmd_skills_pack_check, 'skills pack-check').add_argument('file')
    sip = leaf(skills_subs, 'install-pack', cmd_skills_install_pack, 'skills install-pack')
    sip.add_argument('id')
    sip.add_argument('--map', action='append', help='ROLE=ENTITY, e.g. robot=vacuum.kitchen (repeat per role)')
    sip.add_argument('--lang', default='en', choices=['en', 'fr'])

    quality = subs.add_parser('quality', help='quality reports by device model and firmware (opt-in, never sent)')
    quality_subs = quality.add_subparsers(dest='quality_command')
    leaf(quality_subs, 'status', cmd_quality_status, 'quality status')
    leaf(quality_subs, 'enable', cmd_quality_enable, 'quality enable')
    leaf(quality_subs, 'disable', cmd_quality_disable, 'quality disable').add_argument('--forget', action='store_true')
    qrep = leaf(quality_subs, 'report', cmd_quality_report, 'quality report')
    qrep.add_argument('--month', default=None, help='YYYY-MM (default: this month)')
    qrep.add_argument('--markdown', default=None, help='also write the report as Markdown to this file')
    qex = leaf(quality_subs, 'export', cmd_quality_export, 'quality export')
    qex.add_argument('--month', default=None)
    qex.add_argument('--out', required=True)
    qm = leaf(quality_subs, 'merge', cmd_quality_merge, 'quality merge')
    qm.add_argument('files', nargs='+')
    qm.add_argument('--markdown', default=None)

    partner = subs.add_parser('partner', help='partner integration kit')
    partner_subs = partner.add_subparsers(dest='partner_command')
    partner_new = leaf(partner_subs, 'new', cmd_partner_new, 'partner new')
    partner_new.add_argument('name', help='device name, e.g. "Acme Lamp"')
    partner_new.add_argument('--title', default=None, help='display name (defaults to the name)')
    partner_new.add_argument('--category', default='device', help='short category: lamp, plug, glasses, robot...')
    partner_new.add_argument('--from-openapi', default=None, metavar='FILE',
                             help="generate from the device's OpenAPI 3 description (JSON): settings, commands, emulator, tests")

    ha = subs.add_parser('ha', help='Home Assistant bridge')
    ha_subs = ha.add_subparsers(dest='ha_command')
    ha_connect = leaf(ha_subs, 'connect', cmd_ha_connect, 'ha connect')
    ha_connect.add_argument('--url', required=True, help='e.g. http://homeassistant.local:8123')
    ha_connect.add_argument('--token-env', default=None, help='environment variable holding the long-lived access token')
    ha_connect.add_argument('--store-token', action='store_true', help='prompt for the token and keep it in the OS vault')
    leaf(ha_subs, 'status', cmd_ha_status, 'ha status')
    leaf(ha_subs, 'devices', cmd_ha_devices, 'ha devices')
    ha_do = leaf(ha_subs, 'do', cmd_ha_do, 'ha do')
    ha_do.add_argument('entity', help='entity id, e.g. light.living_room')
    ha_do.add_argument('action', help='turn_on, turn_off, set_brightness, set_volume, set_temperature, play, pause, open, close, stop, lock, start, return_to_base')
    ha_do.add_argument('--value', type=float, default=None)
    leaf(ha_subs, 'disconnect', cmd_ha_disconnect, 'ha disconnect')
    ha_say = leaf(ha_subs, 'say', cmd_ha_say, 'ha say')
    ha_say.add_argument('text', help='a request in English or French, e.g. "dim the kitchen lights to 30%%"')
    ha_say.add_argument('--lang', default='auto', choices=['auto', 'en', 'fr'])
    ha_say.add_argument('--intent-model', dest='intent_model', default='openbridge-intent:latest',
                        help="Ollama model that understands OpenBridge commands (default: OpenBridge's own model)")
    ha_say.add_argument('--endpoint', default='http://127.0.0.1:11434')
    ha_soak = leaf(ha_subs, 'soak', cmd_ha_soak, 'ha soak')
    ha_soak.add_argument('--cycles', type=int, default=3)
    ha_soak.add_argument('--seed', type=int, default=7)
    ha_soak.add_argument('--include-covers', action='store_true')
    ha_soak.add_argument('--entity', action='append', default=[],
                         help='only test this entity (repeat); recommended on a real home, e.g. --entity light.desk')

    devices = subs.add_parser('devices')
    device_subs = devices.add_subparsers(dest='devices_command')
    discover_parser = leaf(device_subs, 'discover', cmd_devices_discover, 'devices discover')
    leaf(device_subs, 'list', cmd_devices_list, 'devices list')
    inspect_parser = leaf(device_subs, 'inspect', cmd_devices_inspect, 'devices inspect')
    inspect_parser.add_argument('device_id')
    pair_parser = leaf(device_subs, 'pair', cmd_devices_pair, 'devices pair')
    pair_parser.add_argument('device_id')
    leaf(device_subs, 'status', cmd_devices_status, 'devices status')

    routes = subs.add_parser('routes')
    route_subs = routes.add_subparsers(dest='routes_command')
    routes_list = leaf(route_subs, 'list', cmd_routes_list, 'routes list')
    routes_list.add_argument('--target', default=None)
    routes_dispatch = leaf(route_subs, 'dispatch', cmd_routes_dispatch, 'routes dispatch')
    routes_dispatch.add_argument('--target', default=None)
    routes_dispatch.add_argument('--op', default='get_status')
    routes_dispatch.add_argument('--params', default=None)
    routes_dispatch.add_argument('--capability', default='ble_scan')
    routes_dispatch.add_argument('--relay', default=None)
    routes_sim = leaf(route_subs, 'simulate-loss', cmd_routes_simulate_loss,
                      'routes simulate-loss')
    routes_sim.add_argument('--target', default=None)
    routes_sim.add_argument('--lost-relay', default=None)

    diagnose_parser = leaf(subs, 'diagnose', cmd_diagnose, 'diagnose')
    diagnose_parser.add_argument('--question', default=None)
    diagnose_parser.add_argument('--bundle', default=None)
    diagnose_parser.add_argument('--device', default=None)

    transplant = subs.add_parser('transplant')
    transplant_subs = transplant.add_subparsers(dest='transplant_command')
    transplant_run = leaf(transplant_subs, 'run', cmd_transplant_run, 'transplant run')
    transplant_run.add_argument('--request', default=None)

    migrate = subs.add_parser('migrate')
    migrate_subs = migrate.add_subparsers(dest='migrate_command')
    migrate_propose = leaf(migrate_subs, 'propose', cmd_migrate_propose, 'migrate propose')
    migrate_propose.add_argument('--text', default=None)
    migrate_propose.add_argument('--source', default=None)
    migrate_propose.add_argument('--target', default=None)
    migrate_propose.add_argument('--match', default=None)
    migrate_apply = leaf(migrate_subs, 'apply', cmd_migrate_apply, 'migrate apply')
    migrate_apply.add_argument('--proposal', default=None)
    migrate_rollback = leaf(migrate_subs, 'rollback', cmd_migrate_rollback, 'migrate rollback')
    migrate_rollback.add_argument('--receipt', default=None)

    ask_parser = leaf(subs, 'ask', cmd_ask, 'ask')
    ask_parser.add_argument('text')
    ask_parser.add_argument('--prior', default=None,
                            help='follow-up turn: prior resolved intent JSON file')

    caps = subs.add_parser('capabilities')
    cap_subs = caps.add_subparsers(dest='capabilities_command')
    leaf(cap_subs, 'list', cmd_capabilities_list, 'capabilities list')
    gen_parser = leaf(cap_subs, 'generate', cmd_capabilities_generate, 'capabilities generate')
    gen_parser.add_argument('--intent', default=None)
    gen_parser.add_argument('--target', default=None)
    gen_parser.add_argument('--retries', type=int, default=0)
    gen_parser.add_argument('--temperature', type=float, default=0)
    cap_inspect = leaf(cap_subs, 'inspect', cmd_capabilities_inspect, 'capabilities inspect')
    cap_inspect.add_argument('capability_id')
    cap_publish = leaf(cap_subs, 'publish', cmd_capabilities_publish, 'capabilities publish')
    cap_publish.add_argument('capability_id')
    cap_revoke = leaf(cap_subs, 'revoke', cmd_capabilities_revoke, 'capabilities revoke')
    cap_revoke.add_argument('capability_id')

    dash = subs.add_parser('dashboards')
    dash_subs = dash.add_subparsers(dest='dashboards_command')
    dash_propose = leaf(dash_subs, 'propose', cmd_dashboards_propose, 'dashboards propose')
    dash_propose.add_argument('text', nargs='?')
    dash_install = leaf(dash_subs, 'install', cmd_dashboards_install, 'dashboards install')
    dash_install.add_argument('--patch', default=None)
    dash_install.add_argument('--relay', default=None)
    dash_install.add_argument('--target', default=None)
    dash_revoke = leaf(dash_subs, 'revoke', cmd_dashboards_revoke, 'dashboards revoke')
    dash_revoke.add_argument('--relay', default=None)
    dash_export = leaf(dash_subs, 'export', cmd_dashboards_export, 'dashboards export')
    dash_export.add_argument('--name', default=None)
    dash_export.add_argument('--saved', default=None)
    dash_export.add_argument('--relay', default=None)
    dash_export.add_argument('--out', default=None)
    dash_import = leaf(dash_subs, 'import', cmd_dashboards_import, 'dashboards import')
    dash_import.add_argument('--bundle', default=None)
    dash_import.add_argument('--relay', default=None)
    dash_import.add_argument('--target', default=None)
    dash_import.add_argument('--target-map', default=None)
    dash_import.add_argument('--save-as', default=None)

    flows = subs.add_parser('workflows')
    flow_subs = flows.add_subparsers(dest='workflows_command')
    leaf(flow_subs, 'list', cmd_workflows_list, 'workflows list')
    plan_parser = leaf(flow_subs, 'plan', cmd_workflows_plan, 'workflows plan')
    plan_parser.add_argument('text', nargs='?')
    plan_parser.add_argument('--file', default=None)
    run_parser = leaf(flow_subs, 'run', cmd_workflows_run, 'workflows run')
    run_parser.add_argument('workflow_id', nargs='?')
    run_parser.add_argument('--file', default=None)
    status_parser = leaf(flow_subs, 'status', cmd_workflows_status, 'workflows status')
    status_parser.add_argument('workflow_id')
    compose_parser = leaf(flow_subs, 'compose', cmd_workflows_compose, 'workflows compose')
    compose_parser.add_argument('text', nargs='?')
    summary_parser = leaf(flow_subs, 'summary', cmd_workflows_summary, 'workflows summary')
    summary_parser.add_argument('workflow_id')
    flow_approve = leaf(flow_subs, 'approve', cmd_workflows_approve, 'workflows approve')
    flow_approve.add_argument('workflow_id')
    flow_approve.add_argument('step_id')
    flow_approve.add_argument('--deny', action='store_true')

    approvals = subs.add_parser('approvals')
    approval_subs = approvals.add_subparsers(dest='approvals_command')
    leaf(approval_subs, 'list', cmd_approvals_list, 'approvals list')
    approve_parser = leaf(approval_subs, 'approve', cmd_approvals_approve, 'approvals approve')
    approve_parser.add_argument('request_id')
    deny_parser = leaf(approval_subs, 'deny', cmd_approvals_deny, 'approvals deny')
    deny_parser.add_argument('request_id')

    sessions = subs.add_parser('sessions')
    session_subs = sessions.add_subparsers(dest='sessions_command')
    leaf(session_subs, 'list', cmd_sessions_list, 'sessions list')
    session_inspect = leaf(session_subs, 'inspect', cmd_sessions_inspect, 'sessions inspect')
    session_inspect.add_argument('session_id')
    session_undo = leaf(session_subs, 'undo', cmd_sessions_undo, 'sessions undo')
    session_undo.add_argument('session_id')

    evidence = subs.add_parser('evidence')
    evidence_subs = evidence.add_subparsers(dest='evidence_command')
    leaf(evidence_subs, 'list', cmd_evidence_list, 'evidence list')
    verify_parser = leaf(evidence_subs, 'verify', cmd_evidence_verify, 'evidence verify')
    verify_parser.add_argument('session_id')
    export_parser = leaf(evidence_subs, 'export', cmd_evidence_export, 'evidence export')
    export_parser.add_argument('session_id')

    tests = subs.add_parser('test')
    test_subs = tests.add_subparsers(dest='test_command')
    leaf(test_subs, 'smoke', cmd_test_smoke, 'test smoke')
    leaf(test_subs, 'integrations', cmd_test_integrations, 'test integrations')
    leaf(test_subs, 'hardware', cmd_test_hardware, 'test hardware')
    leaf(test_subs, 'models', cmd_test_models, 'test models')
    leaf(test_subs, 'jury', cmd_test_jury, 'test jury')

    judge = subs.add_parser('judge')
    judge_subs = judge.add_subparsers(dest='judge_command')
    leaf(judge_subs, 'demo', cmd_judge_demo, 'judge demo')
    leaf(subs, 'demo', cmd_demo, 'demo')

    serve_parser = leaf(subs, 'serve', cmd_serve, 'serve')
    serve_parser.add_argument('--port', type=int, default=18765)
    serve_parser.add_argument('--headless', action='store_true')

    agent = subs.add_parser('agent')
    agent_subs = agent.add_subparsers(dest='agent_command')
    agent_start = leaf(agent_subs, 'start', cmd_agent_start, 'agent start')
    agent_start.add_argument('--port', type=int, default=9876)
    return parser


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    if getattr(args, 'version', False) and not getattr(args, 'command', None):
        emit(args, 'version', True, cmd_version(args))
        return 0
    func = getattr(args, 'func', None)
    if func is None:
        parser.print_help(sys.stderr)
        return EXIT['args']
    command = getattr(args, 'command_name', getattr(args, 'command', ''))
    try:
        data = func(args)
    except CliError as e:
        return fail(args, command, e)
    except BrokenPipeError:
        return EXIT['cancelled']
    except Exception as e:  # never a traceback on stdout; JSON stays pure
        if getattr(args, 'verbose', False):
            import traceback
            traceback.print_exc()
        emit(args, command, False, {}, {'code': 'INTERNAL', 'message': '%s: %s'
                                                        % (type(e).__name__, e)})
        return EXIT['internal']
    emit(args, command, True, data)
    return 0


if __name__ == '__main__':
    sys.exit(main())
