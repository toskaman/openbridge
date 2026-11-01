"""Hardware -> agent/companion artifact matrix (SIMULATED_VERIFIED: temp-dir fixtures).

The matrix answers "which working build for this hardware": every entry that
claims VERIFIED-backed status must cite test_ids that exist in
docs/DEVICE_EVIDENCE.json with status VERIFIED (honesty gate below).
"""
import json
import tempfile
import unittest
from pathlib import Path

from src.fabric import agent_matrix as mx
from src.fabric.contracts import DeviceObservation, now
from src.fabric.registry import Registry

REPO = Path(__file__).resolve().parents[2]


def stage(folder, *names):
    for n in names:
        (Path(folder) / n).write_bytes(b'fixture-only:' + n.encode())
    return Path(folder)


class NormalizeArch(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(mx.normalize_arch('x64 (64-bit)'), 'x64')
        self.assertEqual(mx.normalize_arch('x86 (32-bit)'), 'x86')
        self.assertEqual(mx.normalize_arch('AMD64'), 'x64')
        self.assertEqual(mx.normalize_arch('aarch64'), 'arm64')
        self.assertEqual(mx.normalize_arch('i686'), 'x86')

    def test_unknown_values(self):
        self.assertIsNone(mx.normalize_arch('unknown'))
        self.assertIsNone(mx.normalize_arch(''))
        self.assertIsNone(mx.normalize_arch(None))
        self.assertIsNone(mx.normalize_arch('armv7l'))


class Resolve(unittest.TestCase):
    def test_windows_x64_ready_when_staged(self):
        with tempfile.TemporaryDirectory() as d:
            f = stage(d, 'agent_x64.exe')
            hit = mx.resolve('windows', 'x64', Path(d) / 'no.apk', f)
            self.assertEqual(hit['id'], 'windows-x64')
            self.assertEqual(hit['status'], 'READY')
            self.assertTrue(hit['evidence'])
            self.assertEqual(len(hit['sha256']), 64)
            self.assertIn('agent_x64.exe', hit['run'])

    def test_windows_x86_picks_legacy_build(self):
        with tempfile.TemporaryDirectory() as d:
            f = stage(d, 'agent-win-x86-legacy.exe')
            hit = mx.resolve('windows', 'x86', Path(d) / 'no.apk', f)
            self.assertEqual(hit['id'], 'windows-x86-legacy')
            self.assertEqual(hit['status'], 'READY')
            self.assertIn('legacy-agent-xp-vm-proof', hit['evidence'])
            self.assertIn('legacy-agent-win7-vm-proof', hit['evidence'])

    def test_missing_file_is_needs_step(self):
        with tempfile.TemporaryDirectory() as d:
            hit = mx.resolve('windows', 'x64', Path(d) / 'no.apk', Path(d))
            self.assertEqual(hit['status'], 'NEEDS_STEP')
            self.assertIn('agent_x64.exe', hit['reason'])
            self.assertNotIn('sha256', hit)

    def test_unverified_build_is_experimental_even_when_staged(self):
        with tempfile.TemporaryDirectory() as d:
            f = stage(d, 'agent-linux-x64', 'agent-linux-arm64', 'agent_arm64.exe')
            for os_, arch in (('linux', 'x64'), ('linux', 'arm64'), ('windows', 'arm64')):
                hit = mx.resolve(os_, arch, Path(d) / 'no.apk', f)
                self.assertEqual(hit['status'], 'NEEDS_STEP', (os_, arch))
                self.assertIn('not yet verified', hit['reason'])

    def test_unknown_platform_has_no_entry(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(mx.resolve('windows', 'arm', Path(d) / 'no.apk', Path(d)))
            self.assertIsNone(mx.resolve('plan9', 'x64', Path(d) / 'no.apk', Path(d)))
            self.assertIsNone(mx.resolve(None, None, Path(d) / 'no.apk', Path(d)))
            self.assertIsNone(mx.resolve('../../etc', 'x64', Path(d) / 'no.apk', Path(d)))

    def test_android_apk_uses_apk_path(self):
        with tempfile.TemporaryDirectory() as d:
            apk = Path(d) / 'openbridge-companion.apk'
            apk.write_bytes(b'PK\x03\x04fake')
            hit = mx.resolve('android', None, apk, Path(d))
            self.assertEqual(hit['id'], 'android-apk')
            self.assertEqual(hit['status'], 'READY')

    def test_resolved_paths_never_escape_staging_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            f = stage(d, 'agent_x64.exe')
            for entry in mx.matrix_status(Path(d) / 'no.apk', f):
                if 'path' in entry:
                    self.assertEqual(Path(entry['path']).resolve().parent, f.resolve())


class HonestyGate(unittest.TestCase):
    def test_evidence_ids_are_verified_registry_rows(self):
        rows = {r['test_id']: r for r in json.loads((REPO / 'docs' / 'DEVICE_EVIDENCE.json').read_text(encoding='utf-8'))}
        self.assertTrue(rows)
        for entry in mx.ARTIFACTS:
            for tid in entry['evidence']:
                self.assertIn(tid, rows, entry['id'])
                self.assertEqual(rows[tid]['status'], 'VERIFIED', tid)


class DetectPlatform(unittest.TestCase):
    def reg(self):
        return Registry()

    def test_windows_agent_handle_with_diag(self):
        reg = self.reg()
        k = reg.upsert([], category='computer', label='PC')
        reg.devices[k]['handles'] = {'WINDOWS_AGENT': 'windows-agent'}
        reg.observe(k, DeviceObservation('architecture', 'x64 (64-bit)', 'WINDOWS_AGENT', 'LAN', now(), True))
        self.assertEqual(mx.detect_platform(k, reg)[:2], ('windows', 'x64'))

    def test_adb_link_is_android_universal(self):
        reg = self.reg()
        k = reg.upsert([], category='phone', label='P')
        reg.devices[k]['handles'] = {'WIFI': 'h1'}
        self.assertEqual(mx.detect_platform(k, reg)[:2], ('android', None))

    def test_bare_inventory_host_is_unknown(self):
        reg = self.reg()
        k = reg.upsert([], category='computer', label='DESKTOP-X')
        self.assertEqual(mx.detect_platform(k, reg)[:2], (None, None))


if __name__ == '__main__':
    unittest.main()
