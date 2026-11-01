"""Pack/verify secret-scan regression: realistic leaks are refused, while
*-psk-* test fixtures are not. Samples are concatenated so this file itself
never matches the scan."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SECRET_PATTERNS


PACK = load('release_pack')
VERIFY = load('verify_jury_pack')


def hit(patterns, blob):
    return any(p.search(blob) for p in patterns)


class SecretScan(unittest.TestCase):
    def test_patterns_agree(self):
        self.assertEqual([p.pattern for p in PACK], [p.pattern for p in VERIFY])

    def test_catches_realistic_leaks(self):
        leaks = [
            b'KEY=' + b'sk' + b'-' + b'A' * 48,
            b'token ' + b'sk' + b'-' + b'b' * 32 + b' end',
            b'OPENBRIDGE_META_' + b'KEY=hunter2value',
            b'x' + b'api_' + b'key = ' + b'Z' * 20,
            b'---BEGIN PRI' + b'VATE KEY---',
        ]
        for blob in leaks:
            self.assertTrue(hit(PACK, blob), blob[:20])
            self.assertTrue(hit(VERIFY, blob), blob[:20])

    def test_ignores_psk_fixtures(self):
        fixtures = [
            b"PSK = 'test-psk-0123456789abcdef01234567'",
            b"PSK = 'wrong-psk-0123456789abcdef0123'",
            b"made['psk'], 'env-psk-0123456789abcdef'",
            b"'vault-psk-0123456789abcdef'",
        ]
        for blob in fixtures:
            self.assertFalse(hit(PACK, blob), blob[:30])
            self.assertFalse(hit(VERIFY, blob), blob[:30])


if __name__ == '__main__':
    unittest.main()
