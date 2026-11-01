"""Preflight: what this machine can do before OpenBridge touches any device. Read-only, loopback only.

Each check returns OK / MISSING / MISMATCH / OPTIONAL_ABSENT with the pinned expectation, licence and why it matters.
Run: python -m src.runtime.preflight [--json]"""
import importlib.metadata as md
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

PINS = {  # package: (version, licence, purpose, required)
    'bleak': ('3.0.2', 'MIT', 'PC Bluetooth LE observation (optional; a Companion relay can replace it)', False),
    'playwright': ('1.63.0', 'Apache-2.0', 'browser e2e tests only (dev)', False),
}
from src.ai.local_meta import MODEL_DIGEST as _LLAMA
from src.ai.glimmer import GLIMMER_DIGEST as _GLIMMER
MODELS = {  # endpoint port: (model, full pinned digest, purpose)
    11437: ('llama3.2:3b-instruct-q4_K_M', _LLAMA, 'local Meta planner/reviewer (CPU)'),
    11438: ('muse-glimmer:30b-q4_K_M', _GLIMMER, 'local Meta open-weight model (GPU/CPU)'),
}


def check(name, status, detail, required=False):
    return {'check': name, 'status': status, 'detail': detail, 'required': required}


def python_version():
    ok = sys.version_info >= (3, 12)
    return check('python', 'OK' if ok else 'MISMATCH', f'{sys.version.split()[0]} (needs ≥ 3.12; developed on 3.14.4, stdlib only)', True)


def packages():
    out = []
    for pkg, (ver, lic, why, req) in PINS.items():
        try:
            have = md.version(pkg)
            out.append(check(f'pkg:{pkg}', 'OK' if have == ver else 'MISMATCH', f'{have} installed, pinned {ver} ({lic}) — {why}', req))
        except md.PackageNotFoundError:
            out.append(check(f'pkg:{pkg}', 'OPTIONAL_ABSENT' if not req else 'MISSING', f'pinned {ver} ({lic}) — {why}', req))
    return out


def adb(run=subprocess.run):
    path = shutil.which('adb')
    if not path:
        return check('adb', 'OPTIONAL_ABSENT', 'Android Platform Tools not on PATH: Android/TV features disabled')
    try:
        v = run([path, 'version'], capture_output=True, text=True, timeout=8).stdout.splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return check('adb', 'MISMATCH', 'adb present but did not answer')
    return check('adb', 'OK', v.strip()[:80])


def models(fetch=None):
    fetch = fetch or (lambda url: json.loads(urllib.request.urlopen(url, timeout=2).read()))
    out = []
    for port, (model, digest, why) in MODELS.items():
        try:
            tags = fetch(f'http://127.0.0.1:{port}/api/tags')
        except Exception:
            out.append(check(f'model:{model}', 'OPTIONAL_ABSENT', f'no private Ollama on 127.0.0.1:{port} — {why}'))
            continue
        m = next((x for x in tags.get('models', []) if x.get('name') == model), None)
        if m is None:
            out.append(check(f'model:{model}', 'MISSING', f'service up on :{port} but model not pulled'))
        elif str(m.get('digest', '')).removeprefix('sha256:') != digest:
            out.append(check(f'model:{model}', 'MISMATCH', f'digest {str(m.get("digest"))[:8]} ≠ pinned {digest[:8]}: refusing to treat as the pinned model'))
        else:
            out.append(check(f'model:{model}', 'OK', f'digest {digest[:8]}… on :{port} — {why}'))
    return out


def storage():
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / '.preflight'; probe.write_text('ok', encoding='utf-8'); probe.unlink()
        return check('private_storage', 'OK', 'per-user state directory writable', True)
    except OSError as e:
        return check('private_storage', 'MISSING', f'cannot write private state: {type(e).__name__}', True)


def secret_store():
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.crypt32.CryptProtectData
            return check('secret_store', 'OK', 'Windows DPAPI available (Freebox token encrypted per user)')
        except (AttributeError, OSError):
            return check('secret_store', 'MISSING', 'DPAPI unavailable: Freebox authorization disabled')
    return check('secret_store', 'OPTIONAL_ABSENT', 'no OS secret store wired on this platform: Freebox authorization disabled')


def companion():
    apk = Path(os.environ.get('OPENBRIDGE_COMPANION_APK', 'artifacts/companion/openbridge-companion.apk'))
    return check('companion_apk', 'OK' if apk.exists() else 'OPTIONAL_ABSENT',
                 'built' if apk.exists() else 'not built (python -m dev.build_companion; needs Android SDK build-tools 34)')


def run_all(fetch=None):
    return [python_version(), storage(), secret_store(), adb(), companion(), *packages(), *models(fetch)]


def ready(results):
    return all(r['status'] == 'OK' for r in results if r['required'])


def main():
    res = run_all()
    if '--json' in sys.argv:
        print(json.dumps({'ready': ready(res), 'checks': res}, indent=2))
    else:
        for r in res:
            print(f"{r['status']:<16} {r['check']:<40} {r['detail']}")
        print('READY' if ready(res) else 'NOT READY (a required check failed)')
    return 0 if ready(res) else 1


if __name__ == '__main__':
    sys.exit(main())
