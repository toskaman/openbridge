"""Software bill of materials (CycloneDX 1.6, JSON) for an OpenBridge release.

    python scripts/release/sbom.py --version 0.5.0 --bundle dist/OpenBridge-Windows-x64.zip \
        --out dist/OpenBridge-Windows-x64.cdx.json

Lists what a release contains and what it can use: OpenBridge itself (and its Apache-2.0 integration kit), the
embedded Python of the Windows download (with the SHA-256 recorded at build time), the optional packages an owner
may install (marked optional, not bundled), the web fonts of the site, and the development tools (excluded).
OpenBridge's runtime is the Python standard library only. Model weights are never bundled and are not listed.
Standard library only.
"""
import argparse
import hashlib
import json
import re
import time
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = 'https://github.com/toskaman/openbridge'
LICENSES = {'bleak': 'MIT', 'tinytuya': 'MIT', 'pillow': 'MIT-CMU', 'playwright': 'Apache-2.0', 'pyee': 'MIT',
            'greenlet': 'MIT', 'typing_extensions': 'PSF-2.0'}
FONTS = (('Bricolage Grotesque', 'site/fonts/BricolageGrotesque.woff2'), ('Instrument Sans', 'site/fonts/InstrumentSans.woff2'))


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def requirements(name):
    out = []
    for line in (ROOT / name).read_text(encoding='utf-8').splitlines():
        m = re.match(r'^\s*([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)', line)
        if m:
            out.append((m.group(1).lower(), m.group(2)))
    return out


def _lic(spdx=None, name=None, url=None):
    lic = {'id': spdx} if spdx else {'name': name}
    if url:
        lic['url'] = url
    return [{'license': lic}]


def lic_for(package):
    return _lic(LICENSES[package]) if package in LICENSES else _lic(name='see upstream')


def build(version, bundle=None, now=None):
    build_info, bundle_hash = {}, None
    if bundle:
        bundle_hash = sha256(bundle)
        with zipfile.ZipFile(bundle) as z:
            try:
                build_info = json.loads(z.read('OpenBridge/BUILD.json').decode('utf-8'))
            except KeyError:
                build_info = {}
    main = {'type': 'application', 'bom-ref': 'openbridge', 'name': 'OpenBridge', 'version': version,
            'description': 'Local AI interoperability layer for home and personal devices (demo release, not the final '
                           'version with the dedicated model)',
            'licenses': _lic(name='PolyForm Strict 1.0.0', url='https://polyformproject.org/licenses/strict/1.0.0'),
            'purl': 'pkg:github/toskaman/openbridge@v%s' % version,
            'externalReferences': [{'type': 'vcs', 'url': REPO}, {'type': 'website', 'url': 'https://toskaman.github.io/openbridge/'}]}
    if build_info.get('git_rev'):
        main['properties'] = [{'name': 'openbridge:git_rev', 'value': build_info['git_rev']}]
    if bundle_hash:
        main['hashes'] = [{'alg': 'SHA-256', 'content': bundle_hash}]
    comps = [{'type': 'library', 'bom-ref': 'openbridge-integration-kit', 'name': 'OpenBridge integration kit',
              'version': version, 'licenses': _lic('Apache-2.0'),
              'description': 'src/partner_kit.py, src/partner_kit_api.py, site/js/integrate*.js and the files they generate'}]
    py = build_info.get('python_version', '3.14.4')
    python = {'type': 'platform', 'bom-ref': 'python', 'name': 'CPython', 'version': py,
              'licenses': _lic('PSF-2.0'), 'purl': 'pkg:generic/cpython@%s' % py,
              'description': 'Python runtime; the Windows download embeds the official embeddable package',
              'externalReferences': [{'type': 'distribution', 'url': build_info.get('python_source') or
                                      'https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip' % (py, py)}],
              'properties': [{'name': 'openbridge:bundled', 'value': 'true' if bundle else 'false'}]}
    if build_info.get('python_embed_sha256'):
        python['hashes'] = [{'alg': 'SHA-256', 'content': build_info['python_embed_sha256']}]
    comps.append(python)
    for name, ver in requirements('requirements-optional.txt'):
        comps.append({'type': 'library', 'bom-ref': 'pypi-%s' % name, 'name': name, 'version': ver, 'scope': 'optional',
                      'purl': 'pkg:pypi/%s@%s' % (name, ver), 'licenses': lic_for(name),
                      'properties': [{'name': 'openbridge:bundled', 'value': 'false'}]})
    for name, ver in requirements('requirements-dev.txt'):
        comps.append({'type': 'library', 'bom-ref': 'pypi-dev-%s' % name, 'name': name, 'version': ver, 'scope': 'excluded',
                      'purl': 'pkg:pypi/%s@%s' % (name, ver), 'licenses': lic_for(name),
                      'description': 'development and CI only'})
    for name, rel in FONTS:
        if (ROOT / rel).exists():
            comps.append({'type': 'file', 'bom-ref': 'font-' + name.lower().replace(' ', '-'), 'name': name,
                          'licenses': _lic('OFL-1.1'), 'hashes': [{'alg': 'SHA-256', 'content': sha256(ROOT / rel)}],
                          'description': 'web font of the project website (%s), not in the Windows download' % rel})
    deps = [{'ref': 'openbridge', 'dependsOn': ['python', 'openbridge-integration-kit']}]
    seed = '%s|%s' % (version, bundle_hash or build_info.get('git_rev') or '')
    return {'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
            'serialNumber': 'urn:uuid:%s' % uuid.uuid5(uuid.NAMESPACE_URL, REPO + '#' + seed),
            'metadata': {'timestamp': now or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                         'tools': {'components': [{'type': 'application', 'name': 'openbridge-sbom', 'version': '1'}]},
                         'component': main},
            'components': comps, 'dependencies': deps}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--version', required=True, help='release version without the v, e.g. 0.5.0')
    ap.add_argument('--bundle', default=None, help='the Windows download, to record its hash and the embedded Python')
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[-.][A-Za-z0-9.]+)?', a.version):
        raise SystemExit('version looks wrong: %r' % a.version)
    bom = build(a.version, a.bundle)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(bom, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'sbom': a.out, 'components': len(bom['components'])}))


if __name__ == '__main__':
    main()
