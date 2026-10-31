"""§7 clean-install check: isolated venv, stdlib-only runtime, start → CLI →
UI → offline demo → diagnostics → clean shutdown with orphan check.

Usage:
  python scripts/verify/clean_install_check.py --venv E:/ob-clean/venv [--port 18799]

The venv intentionally contains NO third-party packages: the runtime imports
must all resolve from the standard library. A failure names the missing piece.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKS = []


def check(name, ok, detail=''):
    CHECKS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:300]})
    print(('PASS ' if ok else 'FAIL ') + name + (f' — {detail}'[:160] if detail else ''))
    return bool(ok)


def run(py, args, timeout=120):
    env = {**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONNOUSERSITE': '1'}
    p = subprocess.run([py, *args], capture_output=True, text=True, timeout=timeout, cwd=ROOT, env=env)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--venv', required=True)
    ap.add_argument('--port', type=int, default=18799)
    args = ap.parse_args()
    venv = Path(args.venv)
    py = str(venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))

    if not venv.exists():
        r = subprocess.run([sys.executable, '-m', 'venv', str(venv)], capture_output=True, text=True)
        check('venv-create', r.returncode == 0, r.stderr.strip()[:200] or 'created')
    else:
        check('venv-create', True, 'reused existing venv')
    if not Path(py).exists():
        check('venv-python', False, py)
        return 1
    check('venv-python', True, py)

    code, out = run(py, ['-m', 'pip', 'list', '--format=json'])
    try:
        pkgs = sorted(p['name'] for p in json.loads(out) if p['name'] not in ('pip', 'setuptools', 'wheel'))
    except Exception:
        # Fallback for venvs without working pip (Debian): stdlib metadata.
        code2, out2 = run(py, ['-c', 'import importlib.metadata as m, json; '
                                     'print(json.dumps(sorted({(d.metadata.get(\"Name\") or \"?\") for d in m.distributions()})))'])
        try:
            pkgs = sorted(n for n in json.loads(out2) if n not in ('pip', 'setuptools', 'wheel'))
            code = code2
        except Exception:
            pkgs = ['<unparseable:%s>' % out.strip().splitlines()[:1]]
    check('venv-isolated', pkgs == [], f'third-party: {pkgs}')

    code, out = run(py, ['-m', 'src.cli', 'doctor'])
    check('cli-doctor', 'BLOCKED' in out or code == 0, out.strip().splitlines()[:1])

    code, out = run(py, ['-m', 'src.cli', 'test', 'smoke'])
    check('cli-smoke', code == 0, out.strip().splitlines()[-1:] or out[:120])

    code, out = run(py, ['-m', 'src.cli', 'judge', 'demo'])
    check('offline-demo', 'DEMO_COMPLETE' in out, out.strip().splitlines()[-1:] or out[:120])

    env = {**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONNOUSERSITE': '1'}
    srv = subprocess.Popen([py, '-m', 'src.server', '--port', str(args.port)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ROOT, env=env)
    url = f'http://127.0.0.1:{args.port}/'
    up, body = False, ''
    for _ in range(60):
        time.sleep(1)
        if srv.poll() is not None:
            break
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                body = r.read().decode('utf-8', 'replace')
                up = r.status == 200 and 'OpenBridge' in body
                break
        except Exception:
            pass
    check('server-start-ui', up, f'serving {url}' if up else 'no UI in 60s')
    srv.terminate()
    try:
        srv.wait(timeout=15)
        orphans = False
    except subprocess.TimeoutExpired:
        srv.kill()
        orphans = True
    check('clean-shutdown', srv.returncode is not None and not orphans,
          f'exit={srv.returncode}' if not orphans else 'had to kill')

    failed = [c for c in CHECKS if not c['ok']]
    print(f'clean-install: {len(CHECKS) - len(failed)}/{len(CHECKS)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
