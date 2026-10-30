"""Verify a jury release ZIP: structure, hashes, no secrets, no placeholders.

Usage: python verify_jury_pack.py OpenBridge-Jury-Release.zip
Exit 0 when the package validates, 1 otherwise.
"""
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

REQUIRED = ('START_HERE.md', 'QUICKSTART.md', 'README.md', 'REQUIREMENTS.md', 'CLAIM_MATRIX.md',
            'HARDWARE_COMPATIBILITY.md', 'MODELS_AND_PROVIDERS.md', 'CLOUD_API_SETUP.md',
            'LOCAL_MODEL_SETUP.md', 'CLI_REFERENCE.md', 'HEADLESS_DEPLOYMENT.md',
            'KNOWN_LIMITATIONS.md', 'TEST_RESULTS.md', 'RELEASE_MANIFEST.json', 'sha256sums.txt')
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


def main():
    if len(sys.argv) != 2:
        print('usage: verify_jury_pack.py PACK.zip')
        return 1
    pack = Path(sys.argv[1])
    if not pack.exists():
        print('missing pack: %s' % pack)
        return 1
    failures = []
    with tempfile.TemporaryDirectory(prefix='jury-verify-') as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(pack) as archive:
            archive.extractall(root)
        tops = [p for p in root.iterdir() if p.is_dir()]
        base = tops[0] if len(tops) == 1 else root
        names = {p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()}
        for required in REQUIRED:
            if required not in names:
                failures.append('missing required file: %s' % required)
        sums_path = base / 'sha256sums.txt'
        if sums_path.exists():
            for line in sums_path.read_text(encoding='utf-8').splitlines():
                parts = line.split()
                if len(parts) != 2:
                    continue
                digest, name = parts
                target = base / name
                if not target.exists():
                    failures.append('listed but absent: %s' % name)
                elif sha256(target) != digest:
                    failures.append('hash mismatch: %s' % name)
        manifest_path = base / 'RELEASE_MANIFEST.json'
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                if not manifest.get('files') or not manifest.get('git_rev'):
                    failures.append('manifest incomplete')
            except ValueError:
                failures.append('manifest is not JSON')
        for path in base.rglob('*'):
            if not path.is_file():
                continue
            blob = path.read_bytes()
            for pattern in SECRET_PATTERNS:
                if pattern.search(blob):
                    failures.append('secret pattern in %s' % path.relative_to(base))
            if path.suffix == '.zip' and path.stat().st_size == 0:
                failures.append('empty placeholder: %s' % path.relative_to(base))
    if failures:
        print('VERIFY FAILED:')
        for failure in failures[:20]:
            print(' -', failure)
        return 1
    print('VERIFY OK: %s' % pack)
    return 0


if __name__ == '__main__':
    sys.exit(main())
