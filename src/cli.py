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


def cloud_key():
    key = os.environ.get('OPENBRIDGE_META_KEY')
    return key or None


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
    """Minimal pinned chat client implementing the forge generate() contract."""

    def __init__(self, temperature=0):
        self.temperature = temperature

    def generate(self, tier, prompt, opts):
        from src.ai.local_meta import MODEL_ID as LLAMA_ID
        from src.ai.glimmer import GLIMMER_ID
        avail = local_availability()
        model = {'LOCAL-FAST': LLAMA_ID, 'LOCAL-QUALITY': GLIMMER_ID}.get(tier)
        if model is None:
            return False, {'status': 'TIER_REJECTED', 'reason': 'cloud tiers need consent flow'}
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
    from src.runtime.readiness import collect
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
    probes['cloud'] = 'AUTH_REQUIRED' if cloud_key() else 'MISSING'
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
    report['detail'] = {'endpoints': avail['endpoints'], 'os': platform.system(),
                        'evidence_dir': str(evidence_dir(args))}
    return report


# ---------------- models ----------------

def default_budget():
    from src.ai.cloud_budget import Budget
    total = os.environ.get('OPENBRIDGE_CLI_BUDGET_USD')
    try:
        total = float(total) if total else 0.0
    except ValueError:
        total = 0.0
    return Budget({'enabled': bool(total and cloud_key()), 'per_request_usd': 0.20,
                   'per_session_usd': 1.00, 'per_day_usd': 3.00, 'total_usd': total,
                   'allowed_models': ['muse-spark-1.3'], 'retries': 1})


def cmd_models_list(args):
    from src.ai import registry
    avail = local_availability()
    try:
        manifest = [{'model_id': m, 'endpoint': e} for m, e in sorted(registry.load())]
    except registry.RegistryInvalid:
        manifest = []
    return {'pinned': sorted(registry.META_MODELS), 'manifest': manifest,
            'availability': {'local_fast': avail['local_fast'],
                             'local_quality': avail['local_quality'],
                             'cloud_key': bool(cloud_key())}}


def cmd_models_status(args):
    from src.ai.router import TIERS
    avail = local_availability()
    return {'tiers': list(TIERS),
            'availability': {'local_fast': avail['local_fast'],
                             'local_quality': avail['local_quality'],
                             'cloud_key': bool(cloud_key())},
            'budget': default_budget().state()}


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
    from src.ai.cloud_budget import BudgetBlocked
    provider = getattr(args, 'provider', 'local')
    if provider == 'meta-cloud':
        return _cloud_preflight(args)
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


def _cloud_preflight(args):
    from src.ai.cloud_budget import CODES
    from src.ai.broker import MODEL_ID as SPARK_ID, ENDPOINT
    key = cloud_key()
    budget = default_budget()
    data = {'provider': 'meta-cloud', 'model': SPARK_ID, 'endpoint': ENDPOINT,
            'spent': False, 'key': bool(key), 'budget': budget.state()}
    if not key:
        raise CliError('auth', 'CLOUD_API_KEY_MISSING',
                       'No cloud key. Set OPENBRIDGE_META_KEY via your OS secret store; '
                       'never pass it as a CLI argument.', data=data)
    if getattr(args, 'spend', False):
        return _cloud_spend(args, budget, SPARK_ID, data)
    try:
        auth = budget.authorize(SPARK_ID, 0.02)
    except Exception as e:
        code = getattr(e, 'code', 'CLOUD_BUDGET_BLOCKED')
        raise CliError('permission', code, 'Spend pre-authorization refused: %s' % e)
    data['preauth_estimate_usd'] = auth['estimate_usd']
    data['next'] = 're-run with --spend --consent SPEND-APPROVED to execute one tiny completion'
    return data


def _cloud_spend(args, budget, model, data):
    from src.ai.broker import ENDPOINT, MetaTransport
    if getattr(args, 'consent', None) != 'SPEND-APPROVED':
        raise CliError('permission', 'CONSENT_REQUIRED',
                       'Paid inference needs explicit consent: re-run with --consent SPEND-APPROVED.')
    try:
        budget.authorize(model, 0.02)
    except Exception as e:
        raise CliError('permission', getattr(e, 'code', 'CLOUD_BUDGET_BLOCKED'), str(e))
    try:
        transport = MetaTransport(cloud_key())
        t0 = time.monotonic()
        raw = transport({'model': model, 'max_tokens': 16,
                         'messages': [{'role': 'user', 'content': 'Reply with exactly: OK'}]})
        elapsed = time.monotonic() - t0
    except Exception as e:
        raise CliError('inference', 'CLOUD_AUTH_FAILED', 'Cloud call failed: %s' % e)
    choices = raw.get('choices', [{}]) if isinstance(raw, dict) else [{}]
    text = ((choices[0].get('message') or {}).get('content', ''))
    data.update({'spent': True, 'seconds': round(elapsed, 2), 'reply': str(text)[:200],
                 'usage': raw.get('usage', {}) if isinstance(raw, dict) else {},
                 'reconciled': budget.record_spend(model, 0.02)})
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
    rows.append({'tier': 'CLOUD-HIGH', 'status': 'SKIPPED',
                 'reason': 'no spend without explicit --spend consent'})
    return {'rows': rows, 'note': 'n=3 tiny generations; not statistically meaningful'}


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
    raw = getattr(args, 'providers', None) or 'mdns,ssdp,android'
    providers = [p.strip() for p in raw.split(',') if p.strip()]
    allowed = {'mdns', 'ssdp', 'android', 'freebox', 'ble'}
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
    with Core() as server:
        ensure_discovery(server, default_providers(args))
        try:
            parsed = cmdmod.parse_request(server, {'text': text, 'lang': 'en'})
        except cmdmod.CommandError as e:
            raise CliError('args', 'PARSE_FAILED', str(e))
        intent = parsed.get('intent', parsed) if isinstance(parsed, dict) else parsed
        if not isinstance(intent, dict) or intent.get('status') != 'resolved':
            status = intent.get('status', 'unknown') if isinstance(intent, dict) else 'unknown'
            ambiguities = intent.get('ambiguities', []) if isinstance(intent, dict) else []
            return {'approval_required': False, 'resolved': False, 'status': status,
                    'ambiguities': ambiguities,
                    'need': 'a Meta model (LOCAL-FAST/QUALITY) or explicit cloud consent to resolve'}
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
        return {'approval_required': True, 'request_id': rid,
                'consent': preview_hash(preview), 'preview': preview,
                'next': 'approvals approve %s --consent %s' % (rid, preview_hash(preview))}
    with Core() as server:
        ensure_discovery(server, default_providers(args))
        try:
            result = cmdmod.execute(server, intent, True, preview)
        except cmdmod.CommandError as e:
            raise CliError('permission', 'EXECUTE_BLOCKED', str(e))
    return {'approval_required': False, 'preview': preview, 'result': result}


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
    if tier not in ('AUTO', 'LOCAL-FAST', 'LOCAL-QUALITY', 'CLOUD-HIGH', 'CLOUD-MAX'):
        tier = 'AUTO'
    avail = local_availability()
    availability = {'local_fast': avail['local_fast'], 'local_quality': avail['local_quality'],
                    'cloud': bool(cloud_key())}
    privacy = 'allow-cloud' if getattr(args, 'consent', None) == 'ALLOW-CLOUD' else 'local-only'
    try:
        decision = route(tier, 'synthesis', availability, privacy=privacy, user_text=intent_text)
    except RoutingError as e:
        raise CliError('inference', 'ROUTING_BLOCKED', str(e))
    if decision['needs_cloud_consent']:
        raise CliError('permission', 'CONSENT_REQUIRED',
                       'Cloud synthesis needs --consent ALLOW-CLOUD plus a configured budget.')
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
    if spec_file:
        try:
            spec = json.loads(Path(spec_file).read_text(encoding='utf-8'))
        except (OSError, ValueError) as e:
            raise CliError('args', 'SPEC_UNREADABLE', 'Cannot read spec: %s' % e)
    elif text.strip():
        spec = {'workflow_id': 'wf-%s' % hashlib.sha256(text.encode()).hexdigest()[:12],
                'steps': [{'step_id': 'note', 'note': text[:200]}]}
    else:
        raise CliError('args', 'MISSING_INPUT', 'plan needs request text or --file spec.json.')
    try:
        validate_workflow(spec)
    except WorkflowError as e:
        raise CliError('args', 'SPEC_INVALID', str(e)[:200])
    return {'workflow_id': spec.get('workflow_id'), 'steps': len(spec.get('steps', [])),
            'valid': True, 'spec': spec}


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
    """Rewrite label targets to live device keys (keys rotate per boot)."""
    import copy
    devices = snap.get('devices', []) if isinstance(snap, dict) else []
    by_key = {d.get('key'): d for d in devices}
    by_label = {}
    for device in devices:
        by_label.setdefault((device.get('label') or '').strip().lower(), []).append(device.get('key'))
    spec = copy.deepcopy(spec)
    for step in spec.get('steps', []):
        target = step.get('target', '')
        if target in by_key or target == 'fabric':
            continue
        hits = by_label.get(target.strip().lower(), [])
        if len(hits) != 1:
            raise CliError('device', 'TARGET_UNRESOLVED',
                           'Target %r matches %d live devices; use the exact label from '
                           '`devices discover`.' % (target, len(hits)))
        step['target'] = hits[0]
    return spec


def cmd_workflows_status(args):
    wid = getattr(args, 'workflow_id', '') or ''
    record = workflow_store().get(wid)
    if record is None:
        raise CliError('args', 'NOT_FOUND', 'Unknown workflow %r.' % wid)
    return {'workflow': record}


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


def cmd_sessions_list(args):
    return {'sessions': session_journal().open_changes()}


def cmd_sessions_inspect(args):
    sid = getattr(args, 'session_id', '') or ''
    for row in session_journal().open_changes():
        if str(row.get('id', '')) == sid:
            return {'session': row}
    raise CliError('args', 'NOT_FOUND', 'Unknown session %r.' % sid)


def cmd_sessions_undo(args):
    from src.fabric.session import restore
    sid = getattr(args, 'session_id', '') or ''
    journal = session_journal()
    target = None
    for row in journal.open_changes():
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
    journal.close(sid, 'reverted')
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
               'open_changes': journal.open_changes(), 'snapshot': snapshot_load()}
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
    rows.append(_row('cloud_key', bool(cloud_key()), 'present' if cloud_key() else 'CLOUD_API_KEY_MISSING'))
    if not (avail['local_fast'] or avail['local_quality'] or cloud_key()):
        raise CliError('inference', 'NO_MODELS', 'No local model and no cloud key.')
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
    args.session_id = getattr(args, 'session_id', None) or 'judge-demo'
    steps = []
    report = cmd_doctor(args)
    steps.append({'step': 'doctor', 'global': report['global']})
    found = cmd_devices_discover(args)
    steps.append({'step': 'discover', 'count': found['count']})
    caps = cmd_capabilities_list(args)
    steps.append({'step': 'capabilities', 'primitives': len(caps['primitives'])})
    exported = cmd_evidence_export(args)
    steps.append({'step': 'evidence_export', 'sha256': exported['sha256'][:16]})
    verified = cmd_evidence_verify(args)
    steps.append({'step': 'evidence_verify', 'verified': verified['verified']})
    return {'steps': steps, 'verdict': 'DEMO_COMPLETE'}


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
    test_parser.add_argument('--spend', action='store_true')
    leaf(model_subs, 'benchmark', cmd_models_benchmark, 'models benchmark')

    devices = subs.add_parser('devices')
    device_subs = devices.add_subparsers(dest='devices_command')
    discover_parser = leaf(device_subs, 'discover', cmd_devices_discover, 'devices discover')
    leaf(device_subs, 'list', cmd_devices_list, 'devices list')
    inspect_parser = leaf(device_subs, 'inspect', cmd_devices_inspect, 'devices inspect')
    inspect_parser.add_argument('device_id')
    pair_parser = leaf(device_subs, 'pair', cmd_devices_pair, 'devices pair')
    pair_parser.add_argument('device_id')
    leaf(device_subs, 'status', cmd_devices_status, 'devices status')

    ask_parser = leaf(subs, 'ask', cmd_ask, 'ask')
    ask_parser.add_argument('text')

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
