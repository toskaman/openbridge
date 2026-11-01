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


import tempfile

from tests.runtime.test_primitives import ctx
from src.runtime.primitives import Executor


class FakeTVAndroid:
    def __init__(self, power="mWakefulness=Awake\n"):
        self._handles = {"SERIAL1": "h1"}
        self.identity = "id-1"
        self.power = power
        self.shell_calls = []

    def stable_identifier(self, handle, salt):
        return self.identity if handle in self._handles.values() else None

    def shell(self, handle, argv, timeout=15, max_bytes=65536):
        assert handle == "h1"
        self.shell_calls.append(tuple(argv))
        if tuple(argv[:2]) == ("dumpsys", "power"):
            return self.power
        return ""


class TvSleep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.c, self.key = ctx(self.tmp)
        self.c.android = FakeTVAndroid(power="mWakefulness=Asleep\n")
        self.ex = Executor(self.c)

    def test_sleep_executes_and_verifies_asleep(self):
        r = self.ex.execute("tv_sleep", self.key, {}, True)
        self.assertEqual(r["state"], "EXECUTED")
        self.assertTrue(r["verified"])
        self.assertEqual(self.c.android.shell_calls[0], ("input", "keyevent", "KEYCODE_SLEEP"))
        self.assertEqual(r["result"]["wakefulness"], "Asleep")

    def test_sleep_needs_consent(self):
        r = self.ex.execute("tv_sleep", self.key, {}, False)
        self.assertEqual(r["state"], "BLOCKED")
        self.assertIn("CONSENT_REQUIRED", r["errors"][0])

    def test_sleep_fails_when_still_awake(self):
        self.c.android.power = "mWakefulness=Awake\n"
        r = self.ex.execute("tv_sleep", self.key, {}, True)
        self.assertEqual(r["state"], "FAILED")

    def test_sleep_blocked_when_adb_down(self):
        def dead(handle, argv, timeout=15, max_bytes=65536):
            raise ValueError("Shell command unavailable")
        self.c.android.shell = dead
        r = self.ex.execute("tv_sleep", self.key, {}, True)
        self.assertEqual(r["state"], "BLOCKED")
        self.assertIn("DEVICE_UNAVAILABLE", r["errors"][0])


if __name__ == "__main__":
    unittest.main()
