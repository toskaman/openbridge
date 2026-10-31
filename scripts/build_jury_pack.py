"""Build the integrity-checked jury release ZIP (Prompt30 #17).

Adapts to existing repo paths (no duplicate docs). Only real content is
packed: no placeholder installers, no dummy evidence, no secrets, no model
weights. Output goes to --out (default E:/OpenBridge-Jury-Release.zip).
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOCS = [('README.md', 'README.md'),
        ('docs/QUICKSTART.md', 'QUICKSTART.md'),
        ('docs/jury/CLAIM_EVIDENCE_MATRIX.md', 'CLAIM_MATRIX.md'),
        ('docs/HARDWARE_TEST_MATRIX.md', 'HARDWARE_COMPATIBILITY.md'),
        ('docs/CLI_REFERENCE.md', 'CLI_REFERENCE.md'),
        ('docs/HEADLESS_DEPLOYMENT.md', 'HEADLESS_DEPLOYMENT.md'),
        ('docs/KNOWN_LIMITATIONS.md', 'KNOWN_LIMITATIONS.md'),
        ('CONTRIBUTIONS.md', 'CONTRIBUTIONS.md'),
        ('LICENSE', 'LICENSE')]

import re as _re

SECRET_PATTERNS = (_re.compile(rb'OPENBRIDGE_META_' + rb'KEY=\S+'),
                   _re.compile(rb'sk-[' + rb'A-Za-z0-9]{16,}'),
                   _re.compile(rb'api_' + rb'key["\']?\s*[:=]\s*["\']?[A-Za-z0-9_\-]{16,}'),
                   _re.compile(rb'BEGIN PRI' + rb'VATE KEY'))


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='E:/OpenBridge-Jury-Release.zip')
    parser.add_argument('--evidence-dir', default=None)
    parser.add_argument('--test-results', default=None)
    args = parser.parse_args()

    staging = Path(tempfile.mkdtemp(prefix='jury-pack-'))
    try:
        (staging / 'config').mkdir(parents=True)
        (staging / 'tools' / 'verify-package').mkdir(parents=True)
        (staging / 'tools' / 'run-jury-tests').mkdir(parents=True)
        (staging / 'source-and-build-info').mkdir(parents=True)

        for src, dest in DOCS:
            origin = ROOT / src
            if origin.exists():
                shutil.copy(origin, staging / dest)

        (staging / 'START_HERE.md').write_text(
            '# OpenBridge jury release\n\nStart with QUICKSTART.md, then CLAIM_MATRIX.md. '
            'Every claim links to evidence in evidence/ or to the public repository.\n',
            encoding='utf-8')
        (staging / 'QUICKSTART.md').write_text(
            '# Quickstart\n\n1. Install Python 3.11+.\n2. `pip install -r requirements.txt`.\n'
            '3. `python -m src.cli doctor`.\n4. `python -m src.cli test jury`.\n'
            'See CLI_REFERENCE.md, LOCAL_MODEL_SETUP.md, CLOUD_API_SETUP.md.\n',
            encoding='utf-8')
        reqs = []
        for name in ('requirements.txt', 'requirements-dev.txt', 'requirements-opt.txt'):
            origin = ROOT / name
            if origin.exists():
                reqs.append('## %s\n\n```\n%s\n```\n' % (name, origin.read_text(encoding='utf-8')))
        (staging / 'REQUIREMENTS.md').write_text('# Requirements\n\n' + '\n'.join(reqs),
                                                 encoding='utf-8')
        (staging / 'MODELS_AND_PROVIDERS.md').write_text(
            '# Models and providers\n\nRuntime is Meta-only (config/runtime_models.json):\n'
            '- llama3.2:3b-instruct-q4_K_M on http://127.0.0.1:11437 (LOCAL-FAST)\n'
            '- muse-glimmer:30b-q4_K_M on http://127.0.0.1:11438 (LOCAL-QUALITY)\n'
            '- muse-spark-1.3 on https://api.meta.ai/v1 (CLOUD-HIGH/MAX, key + consent)\n'
            'Tiers and routing: src/ai/router.py. Budget guard: src/ai/cloud_budget.py.\n',
            encoding='utf-8')
        (staging / 'LOCAL_MODEL_SETUP.md').write_text(
            '# Local model setup\n\n1. Install Ollama.\n'
            '2. `python dev/start_local_meta.py --pull-model` (Llama 3.2 3B).\n'
            '3. `python dev/start_glimmer.py --pull-model` (Glimmer 30B).\n'
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
            '# Local-only: no key needed.\nOPENBRIDGE_EVIDENCE_DIR=E:/OpenBridge-evidence\n',
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
        (staging / 'TEST_RESULTS.md').write_text('# Test results\n\n%s\n' % test_results,
                                                 encoding='utf-8')
        (staging / 'tools' / 'run-jury-tests' / 'RUN.md').write_text(
            '# Jury tests\n\nFrom the repository root:\n\n```\npython -m src.cli test jury\n```\n',
            encoding='utf-8')
        shutil.copy(Path(__file__).resolve().parent / 'verify_jury_pack.py',
                    staging / 'tools' / 'verify-package' / 'verify_jury_pack.py')

        evidence_src = Path(args.evidence_dir) if args.evidence_dir else None
        if evidence_src and evidence_src.exists():
            shutil.copytree(evidence_src, staging / 'evidence', dirs_exist_ok=True)

        info = {'git_rev': git_rev(), 'built_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                                                    time.gmtime()),
                'python': sys.version.split()[0]}
        (staging / 'source-and-build-info' / 'BUILD.json').write_text(json.dumps(info, indent=1),
                                                                      encoding='utf-8')

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
        (staging / 'RELEASE_MANIFEST.json').write_text(json.dumps(manifest, indent=1),
                                                       encoding='utf-8')
        sums.append('%s  %s' % (sha256(staging / 'RELEASE_MANIFEST.json'), 'RELEASE_MANIFEST.json'))
        (staging / 'sha256sums.txt').write_text('\n'.join(sums) + '\n', encoding='utf-8')

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(staging.rglob('*')):
                if path.is_file():
                    archive.write(path, 'OpenBridge-Jury-Release/' + path.relative_to(staging).as_posix())
        print('packed %s (%d files, sha256 %s)' % (out, len(manifest['files']), sha256(out)))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == '__main__':
    main()
