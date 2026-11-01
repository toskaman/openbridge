"""OpenBridge release packaging (§17): three verified artifacts.

ARTIFACT A — application distribution: complete runnable source tree
  (src/, dev/, tests/, scripts/, companion/, config/, requirements, docs,
  entry points). Installs from scratch; tested by clean_install_check.py.

ARTIFACT B — jury evidence package: claims, matrices, setup guides, test
  results, verifier tools. Docs only by design; never presented as runnable.

ARTIFACT C — curated media package: selected authentic shots/clips plus a
  manifest (test id, classification, commit, hashes). Content curated in PH9.

Usage:
  python scripts/release_pack.py app --out E:/OpenBridge-App.zip
  python scripts/release_pack.py evidence --out E:/OpenBridge-Evidence.zip [--evidence-dir D] [--test-results T]
  python scripts/release_pack.py media --out E:/OpenBridge-Media.zip --media-dir D --manifest M.json

Every artifact gets BUILD.json, RELEASE_MANIFEST.json, sha256sums.txt and a
secret-pattern refusal. No private keys, no model weights, no E: paths.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = (re.compile(rb'OPENBRIDGE_META_' + rb'KEY=\S+'),
                   re.compile(rb'sk-[' + rb'A-Za-z0-9]{16,}'),
                   re.compile(rb'api_' + rb'key["\']?\s*[:=]\s*["\']?[A-Za-z0-9_\-]{16,}'),
                   re.compile(rb'BEGIN PRI' + rb'VATE KEY'))

APP_EXCLUDE_DIRS = {'.git', '__pycache__', '.xbuild', '.pytest_cache', '.venv',
                    'node_modules', '.idea', '.vscode'}
APP_EXCLUDE_SUFFIXES = {'.pyc', '.pyo'}
APP_REQUIRED = ('src/server.py', 'src/cli.py', 'requirements.txt', 'docs/QUICKSTART.md',
                'README.md', 'LICENSE', 'CONTRIBUTIONS.md',
                'scripts/verify/clean_install_check.py')

EVIDENCE_DOCS = [('README.md', 'README.md'),
                 ('docs/QUICKSTART.md', 'QUICKSTART.md'),
                 ('docs/jury/CLAIM_EVIDENCE_MATRIX.md', 'CLAIM_MATRIX.md'),
                 ('docs/HARDWARE_TEST_MATRIX.md', 'HARDWARE_COMPATIBILITY.md'),
                 ('docs/CLI_REFERENCE.md', 'CLI_REFERENCE.md'),
                 ('docs/HEADLESS_DEPLOYMENT.md', 'HEADLESS_DEPLOYMENT.md'),
                 ('docs/KNOWN_LIMITATIONS.md', 'KNOWN_LIMITATIONS.md'),
                 ('CONTRIBUTIONS.md', 'CONTRIBUTIONS.md'),
                 ('LICENSE', 'LICENSE')]


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def git_rev():
    try:
        out = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                             cwd=ROOT, timeout=15)
        return out.stdout.strip()
    except Exception:
        return 'unknown'


def build_info(artifact):
    return {'artifact': artifact, 'git_rev': git_rev(),
            'built_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'python': sys.version.split()[0]}


def finalize(staging, out, top, info):
    """Manifest + secret scan + checksums + zip. Returns (files, zip_sha)."""
    sums, manifest = [], {'files': []}
    for path in sorted(staging.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(staging).as_posix()
        digest = sha256(path)
        sums.append('%s  %s' % (digest, rel))
        manifest['files'].append({'path': rel, 'sha256': digest, 'bytes': path.stat().st_size})
        blob = path.read_bytes()
        for pattern in SECRET_PATTERNS:
            if pattern.search(blob):
                raise SystemExit('refusing to pack: secret pattern in %s' % rel)
    manifest.update(info)
    (staging / 'RELEASE_MANIFEST.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    sums.append('%s  %s' % (sha256(staging / 'RELEASE_MANIFEST.json'), 'RELEASE_MANIFEST.json'))
    (staging / 'sha256sums.txt').write_text('\n'.join(sums) + '\n', encoding='utf-8')
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob('*')):
            if path.is_file():
                archive.write(path, top + '/' + path.relative_to(staging).as_posix())
    return len(manifest['files']), sha256(out)


def build_app(staging, args):
    for path in sorted(ROOT.rglob('*')):
        if any(part in APP_EXCLUDE_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file() and path.suffix in APP_EXCLUDE_SUFFIXES:
            continue
        if path.is_dir():
            continue
        rel = path.relative_to(ROOT)
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, dest)
    missing = [r for r in APP_REQUIRED if not (staging / r).exists()]
    if missing:
        raise SystemExit('app artifact incomplete, missing: %s' % ', '.join(missing))
    (staging / 'BUILD.json').write_text(json.dumps(build_info('app'), indent=1), encoding='utf-8')


def build_evidence(staging, args):
    (staging / 'config').mkdir(parents=True)
    (staging / 'tools' / 'verify-package').mkdir(parents=True)
    (staging / 'tools' / 'run-jury-tests').mkdir(parents=True)
    (staging / 'source-and-build-info').mkdir(parents=True)
    for src, dest in EVIDENCE_DOCS:
        origin = ROOT / src
        if origin.exists():
            shutil.copy(origin, staging / dest)
    # The repo QUICKSTART is authoritative; generated install notes get their own name.
    (staging / 'START_HERE.md').write_text(
        '# OpenBridge jury evidence\n\nStart with QUICKSTART.md, then CLAIM_MATRIX.md. '
        'Every claim links to evidence in evidence/ or to the public repository.\n',
        encoding='utf-8')
    reqs = []
    for name in ('requirements.txt', 'requirements-dev.txt', 'requirements-optional.txt'):
        origin = ROOT / name
        if origin.exists():
            reqs.append('## %s\n\n```\n%s\n```\n' % (name, origin.read_text(encoding='utf-8')))
    (staging / 'REQUIREMENTS.md').write_text('# Requirements\n\n' + '\n'.join(reqs), encoding='utf-8')
    (staging / 'MODELS_AND_PROVIDERS.md').write_text(
        '# Models and providers\n\nRuntime is Meta-only (config/runtime_models.json):\n'
        '- llama3.2:3b-instruct-q4_K_M on http://127.0.0.1:11437 (LOCAL-FAST)\n'
        '- muse-glimmer:30b-q4_K_M on http://127.0.0.1:11438 (LOCAL-QUALITY)\n'
        '- muse-spark-1.3 on https://api.meta.ai/v1 (CLOUD-HIGH/MAX, key + consent)\n'
        'Tiers and routing: src/ai/router.py. Budget guard: src/ai/cloud_budget.py.\n',
        encoding='utf-8')
    (staging / 'LOCAL_MODEL_SETUP.md').write_text(
        '# Local model setup\n\n1. Install Ollama.\n'
        '2. `python -m dev.start_local_meta --pull-model` (Llama 3.2 3B).\n'
        '3. `python -m dev.start_glimmer --pull-model` (Glimmer 30B).\n'
        'Digests are verified against pinned values before any inference.\n',
        encoding='utf-8')
    (staging / 'CLOUD_API_SETUP.md').write_text(
        '# Cloud API setup\n\n1. Store the key in your OS secret store as '
        'OPENBRIDGE_META_KEY (never a CLI argument).\n'
        '2. Set OPENBRIDGE_CLI_BUDGET_USD to enable spend.\n'
        '3. `openbridge models test --provider meta-cloud` for preflight.\n'
        '4. Paid calls need --spend --consent SPEND-APPROVED each time.\n',
        encoding='utf-8')
    (staging / 'config' / 'example.local').write_text(
        '# Local-only: no key needed.\n# Set OPENBRIDGE_EVIDENCE_DIR to a directory you own.\n',
        encoding='utf-8')
    (staging / 'config' / 'example.cloud').write_text(
        '# Cloud: key from OS secret store, budget cap required.\n'
        '# Set OPENBRIDGE_META_KEY in your OS secret store (never in a file).\n'
        'OPENBRIDGE_CLI_BUDGET_USD=3.00\n',
        encoding='utf-8')
    (staging / 'config' / 'example.headless').write_text(
        '# Headless: serve with no browser.\npython -m src.cli serve --headless --port 18765\n',
        encoding='utf-8')
    test_results = args.test_results or 'see TEST_RESULTS.md in the repository tree'
    (staging / 'TEST_RESULTS.md').write_text('# Test results\n\n%s\n' % test_results, encoding='utf-8')
    (staging / 'tools' / 'run-jury-tests' / 'RUN.md').write_text(
        '# Jury tests\n\nFrom the application distribution root:\n\n```\npython -m src.cli test jury\n```\n',
        encoding='utf-8')
    shutil.copy(ROOT / 'scripts' / 'verify_jury_pack.py',
                staging / 'tools' / 'verify-package' / 'verify_jury_pack.py')
    evidence_src = Path(args.evidence_dir) if args.evidence_dir else None
    if evidence_src and evidence_src.exists():
        shutil.copytree(evidence_src, staging / 'evidence', dirs_exist_ok=True)
    (staging / 'source-and-build-info' / 'BUILD.json').write_text(
        json.dumps(build_info('evidence'), indent=1), encoding='utf-8')


def build_media(staging, args):
    if not args.media_dir or not args.manifest:
        raise SystemExit('media artifact needs --media-dir and --manifest')
    entries = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    if not isinstance(entries, list) or not entries:
        raise SystemExit('media manifest must be a non-empty JSON list')
    media_src = Path(args.media_dir)
    (staging / 'media').mkdir(parents=True)
    out_entries = []
    for entry in entries:
        for key in ('file', 'test_id', 'classification', 'caption'):
            if key not in entry:
                raise SystemExit('media entry missing %s: %r' % (key, entry))
        if entry['classification'] not in ('REAL', 'EMULATOR', 'SIMULATED'):
            raise SystemExit('bad classification (REAL/EMULATOR/SIMULATED): %r' % entry)
        src = media_src / entry['file']
        if not src.exists():
            raise SystemExit('media file missing: %s' % src)
        shutil.copy(src, staging / 'media' / Path(entry['file']).name)
        out_entries.append({**entry, 'file': 'media/' + Path(entry['file']).name,
                            'sha256': sha256(src), 'bytes': src.stat().st_size})
    (staging / 'MEDIA_MANIFEST.json').write_text(
        json.dumps({'entries': out_entries, **build_info('media')}, indent=1), encoding='utf-8')


BUILDERS = {'app': ('OpenBridge-App', build_app),
            'evidence': ('OpenBridge-Jury-Release', build_evidence),
            'media': ('OpenBridge-Media', build_media)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', choices=sorted(BUILDERS))
    parser.add_argument('--out', required=True)
    parser.add_argument('--evidence-dir', default=None)
    parser.add_argument('--test-results', default=None)
    parser.add_argument('--media-dir', default=None)
    parser.add_argument('--manifest', default=None)
    args = parser.parse_args(argv)
    top, builder = BUILDERS[args.artifact]
    staging = Path(tempfile.mkdtemp(prefix='release-pack-'))
    try:
        builder(staging, args)
        info = build_info(args.artifact)
        n, digest = finalize(staging, args.out, top, info)
        print('packed %s (%d files, sha256 %s)' % (args.out, n, digest))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == '__main__':
    main()
