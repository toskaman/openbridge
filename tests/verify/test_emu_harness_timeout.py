"""Fail-fast: emu_harness.sh must verdict (not hang) when adb wedges.

Regression test for Android run 41313438904 (phone): the harness printed
``stage=evidence`` then hung 26+ minutes on an unbounded ``adb`` call after
the guest/adb channel died, and the job was timeout-cancelled with no
verdict. Every adb invocation in the harness must now be bounded by
``timeout(1)`` so a wedged channel yields EVIDENCE_FAIL_AFTER_PASS
(or an earlier verdict) instead of a hang.
"""
import os
import shutil
import subprocess
import tempfile
import time
import unittest

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
HARNESS = os.path.join(REPO_ROOT, "scripts", "verify", "emu_harness.sh")

STUB_ADB = """#!/usr/bin/env bash
# Fake adb: healthy until the evidence-stage package probe, then wedged.
case "$*" in
  "shell dumpsys package fr.openbridge.companion")
    sleep 600 ;;                       # THE WEDGE (run 41313438904)
  "shell getprop sys.boot_completed")
    echo 1 ;;
  "devices"|"devices -l"|"wait-for-device")
    echo "emulator-5554 device" ;;
  "install --no-incremental "*)
    echo Success ;;
  "shell pm grant "*|"shell am start "*)
    exit 0 ;;
  "shell pidof fr.openbridge.companion")
    echo 1234 ;;
  "shell dumpsys activity activities")
    echo "mFocusedApp=fr.openbridge.companion/.MainActivity" ;;
  "logcat -d -t 300"|"logcat -d")
    echo "fake logcat" ;;
  "bugreport "*)
    exit 1 ;;                          # fast fail, like a dead channel
  "shell dumpsys package "*)
    echo "versionName=0.2.0" ;;
  *)
    echo "stubadb: unhandled: $*" >&2; exit 1 ;;
esac
"""


def _bash():
    seen = set()
    for cand in (
        shutil.which("bash"),
        r"C:\Program Files\Git\bin\bash.exe",
        "/bin/bash",
    ):
        if not cand or cand in seen or not os.path.exists(cand):
            continue
        seen.add(cand)
        try:
            proc = subprocess.run(
                [cand, "-c", "command -v timeout"],
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0:
            return cand
    return None


BASH = _bash()


@unittest.skipUnless(BASH, "bash with timeout(1) required")
class EmuHarnessFailFastTest(unittest.TestCase):
    def test_evidence_stage_wedge_verdicts_fast(self):
        tmp = tempfile.mkdtemp(prefix="emu-hang-")
        try:
            stub = os.path.join(tmp, "adb")
            with open(stub, "w", newline="\n", encoding="utf-8") as fh:
                fh.write(STUB_ADB)
            os.chmod(stub, 0o755)
            apk = os.path.join(tmp, "dummy.apk")
            open(apk, "wb").close()
            env = dict(
                os.environ,
                PATH=tmp + os.pathsep + os.environ.get("PATH", ""),
                EMU_DEVICE="phone",
                EMU_APK=apk,
            )
            start = time.time()
            try:
                proc = subprocess.run(
                    [BASH, HARNESS],
                    cwd=tmp,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                self.fail(
                    "harness hung >300s on wedged adb (no verdict) "
                    "— run 41313438904 reproduced"
                )
            elapsed = time.time() - start
            self.assertEqual(
                proc.returncode, 1, f"expected exit 1, got {proc.returncode}\n"
                f"{proc.stdout[-2000:]}"
            )
            verdict = os.path.join(tmp, "phone-verdict.txt")
            self.assertTrue(
                os.path.exists(verdict),
                f"no verdict file after {elapsed:.0f}s\n{proc.stdout[-2000:]}",
            )
            with open(verdict, encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("EVIDENCE_FAIL_AFTER_PASS", body)
            self.assertLess(
                elapsed, 240, f"fail-fast took {elapsed:.0f}s, want <240s"
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
