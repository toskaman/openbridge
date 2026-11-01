"""TV power + companion foreground skills (SIMULATED_VERIFIED: fake android; no adb calls)."""
import unittest

from src.adapters.android import AndroidAdapter


class RecordingRunner:
    def __init__(self, stdout="", returncode=0):
        self.calls = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, argv, **kw):
        from types import SimpleNamespace
        self.calls.append(argv)
        return SimpleNamespace(stdout=self.stdout, returncode=self.returncode)


class AdapterShell(unittest.TestCase):
    def test_shell_runs_fixed_argv_on_serial(self):
        run = RecordingRunner(stdout="mWakefulness=Asleep\n")
        ad = AndroidAdapter(executable="adb-stub", runner=run)
        ad._handles = {"192.168.1.15:5555": "h1"}
        out = ad.shell("h1", ("dumpsys", "power"))
        self.assertIn("mWakefulness", out)
        self.assertEqual(run.calls[0][:4], ["adb-stub", "-s", "192.168.1.15:5555", "shell"])

    def test_shell_rejects_metacharacters(self):
        run = RecordingRunner()
        ad = AndroidAdapter(executable="adb-stub", runner=run)
        ad._handles = {"S1": "h1"}
        with self.assertRaises(ValueError):
            ad.shell("h1", ("input", "keyevent", "A;B"))
        with self.assertRaises(ValueError):
            ad.shell("h1", ("dumpsys power",))
        with self.assertRaises(ValueError):
            ad.shell("h1", ())
        self.assertEqual(run.calls, [])

    def test_shell_raises_on_adb_failure(self):
        run = RecordingRunner(stdout="error: device offline", returncode=1)
        ad = AndroidAdapter(executable="adb-stub", runner=run)
        ad._handles = {"S1": "h1"}
        with self.assertRaises(ValueError):
            ad.shell("h1", ("dumpsys", "power"))


if __name__ == "__main__":
    unittest.main()
