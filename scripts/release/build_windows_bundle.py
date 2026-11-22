"""Build the ready-to-run Windows download: OpenBridge + an embedded Python, nothing to install.

    python scripts/release/build_windows_bundle.py --out dist/OpenBridge-Windows-x64.zip [--smoke]

Contents: the tracked application files (code, configuration, tests, text docs; no media), the official Python
"embeddable package" for Windows x64 from python.org, and double-click launchers. The Python archive's SHA-256 is
recorded in BUILD.json; pass --python-sha256 to require a known value. --smoke runs the offline demo with the
embedded Python before zipping (Windows only). Standard library only.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
PY_URL = 'https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip'
MAX_PY_BYTES = 64 * 1024 * 1024

LAUNCHERS = {
    'openbridge.cmd': '@echo off\r\n"%~dp0python\\python.exe" -m src.cli %*\r\n',
    'Start OpenBridge.cmd': ('@echo off\r\ncd /d "%~dp0"\r\necho Starting OpenBridge on http://127.0.0.1:18765 (close this window to stop it)\r\n'
                             'start "" /b cmd /c "timeout /t 4 /nobreak >nul && start http://127.0.0.1:18765"\r\n'
                             '"%~dp0python\\python.exe" -m src.server\r\n'),
    'Run the offline demo.cmd': '@echo off\r\ncd /d "%~dp0"\r\n"%~dp0python\\python.exe" -m src.cli demo\r\necho.\r\npause\r\n',
}
README = """OpenBridge for Windows (x64)
============================

Nothing to install: Python is included in the "python" folder.

  Start OpenBridge.cmd       opens the OpenBridge app in your browser (http://127.0.0.1:18765)
  Run the offline demo.cmd   checks everything works, no devices needed
  openbridge.cmd             the command line (openbridge.cmd --help)

Windows may warn that the files come from the internet: right-click the zip, Properties, "Unblock", before extracting.
The local AI models are optional and downloaded separately: see docs/QUICKSTART.md.
Project, documentation and source: https://github.com/toskaman/openbridge

----

OpenBridge pour Windows (x64)

Rien a installer : Python est inclus dans le dossier "python".

  Start OpenBridge.cmd       ouvre l'appli OpenBridge dans votre navigateur (http://127.0.0.1:18765)
  Run the offline demo.cmd   verifie que tout fonctionne, sans appareil
  openbridge.cmd             la ligne de commande (openbridge.cmd --help)

Si Windows signale que les fichiers viennent d'Internet : clic droit sur le zip, Proprietes, "Debloquer", avant d'extraire.
Les modeles d'IA locaux sont facultatifs et se telechargent a part : voir docs/QUICKSTART.md.
"""


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


# What the app needs: code, configuration, scripts, tests, the companion sources and the text documentation.
APP_DIRS = ('src', 'config', 'scripts', 'tests', 'dev', 'companion', 'docs')
MEDIA = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.webm', '.mov', '.pdf', '.zip', '.apk', '.wav', '.mp3')


def git_rev():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=15).stdout.strip()
    except OSError:
        return 'unknown'


def app_files():
    """Tracked files only (never local work files), minus media; the root launchers are replaced below."""
    out = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout.decode('utf-8')
    keep = []
    for rel in filter(None, out.split('\0')):
        top = rel.split('/', 1)[0]
        low = rel.lower()
        if low.endswith(MEDIA) or '/__pycache__/' in rel:
            continue
        if top in APP_DIRS or ('/' not in rel and (low.endswith(('.md', '.txt')) or rel in ('LICENSE', 'openbridge'))):
            keep.append(rel)
    return keep


def fetch_python(version, dest, local=None):
    if local:
        shutil.copy2(local, dest)
        return
    with urlopen(PY_URL.format(v=version), timeout=60) as r, open(dest, 'wb') as out:
        total = 0
        for chunk in iter(lambda: r.read(65536), b''):
            total += len(chunk)
            if total > MAX_PY_BYTES:
                raise SystemExit('Python download larger than expected; refused')
            out.write(chunk)


def build(out, version, python_zip=None, python_sha256=None, smoke=False):
    out = Path(out).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stage = tmp / 'OpenBridge'
        for rel in app_files():
            dst = stage / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
        (stage / 'BUILD.json').write_text(json.dumps({'git_rev': git_rev()}), encoding='utf-8')

        py_zip = tmp / 'python.zip'
        fetch_python(version, py_zip, python_zip)
        digest = sha256_file(py_zip)
        if python_sha256 and digest != python_sha256.lower():
            raise SystemExit('Python archive SHA-256 mismatch: %s' % digest)
        with zipfile.ZipFile(py_zip) as z:
            z.extractall(stage / 'python')
        pth = next((stage / 'python').glob('python*._pth'))
        lines = pth.read_text(encoding='utf-8').splitlines()
        if '..' not in lines:
            lines.insert(lines.index('.') + 1 if '.' in lines else 0, '..')   # the app root, so `-m src.cli` works anywhere
        pth.write_text('\n'.join(lines) + '\n', encoding='utf-8')

        for name, text in LAUNCHERS.items():
            (stage / name).write_text(text, encoding='ascii', newline='')
        (stage / 'README-WINDOWS.txt').write_text(README.replace('\n', '\r\n'), encoding='utf-8', newline='')
        build_info = json.loads((stage / 'BUILD.json').read_text(encoding='utf-8')) if (stage / 'BUILD.json').exists() else {}
        build_info.update({'bundle': 'windows-x64', 'python_version': version, 'python_embed_sha256': digest,
                           'python_source': PY_URL.format(v=version), 'bundled_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        (stage / 'BUILD.json').write_text(json.dumps(build_info, indent=1), encoding='utf-8')

        if smoke:
            if sys.platform != 'win32':
                raise SystemExit('--smoke needs Windows (it runs the embedded python.exe)')
            env = dict(os.environ, LOCALAPPDATA=str(tmp / 'localappdata'), PYTHONIOENCODING='utf-8')
            env.pop('PYTHONPATH', None)
            r = subprocess.run([str(stage / 'python' / 'python.exe'), '-m', 'src.cli', 'demo'], cwd=tmp, capture_output=True,
                               text=True, timeout=600, env=env)
            if 'DEMO_COMPLETE' not in r.stdout:
                raise SystemExit('smoke test failed:\n' + r.stdout[-2000:] + r.stderr[-2000:])

        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():
                    z.write(p, Path('OpenBridge') / p.relative_to(stage))
    digest = sha256_file(out)
    Path(str(out) + '.sha256').write_text('%s  %s\n' % (digest, out.name), encoding='ascii')
    return {'zip': str(out), 'bytes': out.stat().st_size, 'sha256': digest, 'python_embed_sha256': build_info['python_embed_sha256']}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', default='dist/OpenBridge-Windows-x64.zip')
    ap.add_argument('--python', default='3.14.4', help='Python version of the embeddable package')
    ap.add_argument('--python-zip', default=None, help='use a local copy of the embeddable package')
    ap.add_argument('--python-sha256', default=None, help='require this SHA-256 for the embeddable package')
    ap.add_argument('--smoke', action='store_true', help='run the offline demo with the embedded Python first')
    args = ap.parse_args(argv)
    print(json.dumps(build(args.out, args.python, args.python_zip, args.python_sha256, args.smoke), indent=1))


if __name__ == '__main__':
    main()
