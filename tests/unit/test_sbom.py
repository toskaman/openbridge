"""The release SBOM lists what the download contains and what it can use, in CycloneDX 1.6."""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'release'))
import sbom  # noqa: E402


class Sbom(unittest.TestCase):
    def test_source_sbom(self):
        bom = sbom.build('0.5.0', now='2026-11-23T00:00:00Z')
        self.assertEqual((bom['bomFormat'], bom['specVersion']), ('CycloneDX', '1.6'))
        self.assertEqual(bom['metadata']['component']['version'], '0.5.0')
        by_purl = {c.get('purl'): c for c in bom['components']}
        self.assertEqual(by_purl['pkg:pypi/bleak@3.0.2']['scope'], 'optional')
        self.assertEqual(by_purl['pkg:pypi/playwright@1.63.0']['scope'], 'excluded')
        self.assertEqual(by_purl['pkg:pypi/pillow@12.2.0']['licenses'][0]['license']['id'], 'MIT-CMU')
        kit = next(c for c in bom['components'] if c['bom-ref'] == 'openbridge-integration-kit')
        self.assertEqual(kit['licenses'][0]['license']['id'], 'Apache-2.0')
        json.dumps(bom)

    def test_bundle_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / 'OpenBridge-Windows-x64.zip'
            with zipfile.ZipFile(z, 'w') as zf:
                zf.writestr('OpenBridge/BUILD.json', json.dumps({'git_rev': 'abc123', 'python_version': '3.14.4',
                                                                 'python_embed_sha256': 'f' * 64}))
            bom = sbom.build('0.5.0', str(z))
            self.assertEqual(bom['metadata']['component']['hashes'][0]['content'], sbom.sha256(z))
            python = next(c for c in bom['components'] if c['bom-ref'] == 'python')
            self.assertEqual(python['hashes'][0]['content'], 'f' * 64)
            self.assertEqual(bom, sbom.build('0.5.0', str(z), now=bom['metadata']['timestamp']))   # reproducible


if __name__ == '__main__':
    unittest.main()
