"""V4-03: five process-kill points on the simulated setting, recovered by a fresh process (SIMULATED_VERIFIED)."""
import os
import subprocess
import sys
import unittest

from src.core.transactions import FAILPOINTS, failpoint


class CrashDrill(unittest.TestCase):
    def test_failpoint_inactive_by_default(self):
        os.environ.pop('OPENBRIDGE_FAILPOINT', None)
        for p in FAILPOINTS:
            failpoint(p)          # must not exit

    def test_five_injection_points_recover_exactly(self):
        r = subprocess.run([sys.executable, '-m', 'dev.crash_drill', '--target', 'sim'],
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-400:])
        self.assertIn('"passed": 5', r.stdout)
        self.assertNotIn('NO_CRASH', r.stdout)


if __name__ == '__main__':
    unittest.main()
