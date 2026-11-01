"""Unit tests for the adaptive emulator harness (Campaign One §3.2)."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "verify"))

from emu_verdict import (  # noqa: E402
    ADB_DEAD,
    APP_BEHAVIOR_FAIL,
    APP_CRASH,
    BOOT_FAIL,
    EVIDENCE_FAIL_AFTER_PASS,
    PASS,
    VERDICTS,
    classify_adb_output,
    is_retryable,
    write_verdict,
)

REPO = os.path.join(os.path.dirname(__file__), "..", "..")
HARNESS = os.path.join(REPO, "scripts", "verify", "emu_harness.sh")
WORKFLOW = os.path.join(REPO, ".github", "workflows", "android.yml")


class TestVerdictTaxonomy(unittest.TestCase):
    def test_six_verdicts(self):
        self.assertEqual(
            set(VERDICTS),
            {BOOT_FAIL, ADB_DEAD, APP_CRASH, APP_BEHAVIOR_FAIL,
             EVIDENCE_FAIL_AFTER_PASS, PASS},
        )

    def test_only_boot_adb_retryable(self):
        self.assertTrue(is_retryable(BOOT_FAIL))
        self.assertTrue(is_retryable(ADB_DEAD))
        for v in (APP_CRASH, APP_BEHAVIOR_FAIL, EVIDENCE_FAIL_AFTER_PASS, PASS):
            self.assertFalse(is_retryable(v), v)


class TestClassify(unittest.TestCase):
    def test_prior_run_error_closed(self):
        # Runs 41256301271 / 41259765640 signature.
        self.assertEqual(classify_adb_output("error: closed"), ADB_DEAD)
        self.assertEqual(classify_adb_output("adb: error: closed"), ADB_DEAD)

    def test_cousins(self):
        for sig in ("device offline", "no devices/emulators found",
                    "error: device not found", "cannot connect to daemon"):
            self.assertEqual(classify_adb_output(sig), ADB_DEAD, sig)

    def test_healthy_output_not_dead(self):
        self.assertIsNone(classify_adb_output("List of devices attached\nemulator-5554\tdevice\n"))
        self.assertIsNone(classify_adb_output(""))


class TestWriteVerdict(unittest.TestCase):
    def test_txt_and_json(self):
        with tempfile.TemporaryDirectory() as td:
            txt = os.path.join(td, "phone-verdict.txt")
            js = os.path.join(td, "phone-verdict.json")
            rec = write_verdict(txt, js, PASS, "done", "phone", "ok", 1)
            with open(txt, encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("VERDICT=PASS", body)
            self.assertIn("STAGE=done", body)
            with open(js, encoding="utf-8") as fh:
                disk = json.load(fh)
            self.assertEqual(disk, rec)
            self.assertFalse(disk["retryable"])

    def test_unknown_verdict_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                write_verdict(os.path.join(td, "a"), os.path.join(td, "b"),
                              "NOPE", "x", "phone")


class TestHarnessScript(unittest.TestCase):
    def test_retry_isolation_documented(self):
        with open(HARNESS, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("BOOT_RETRIES", body)
        self.assertIn("ADB_RETRIES", body)
        self.assertIn("NO retries", body)
        for v in VERDICTS:
            self.assertIn(v, body, v)

    def test_preserves_diag_artifacts(self):
        with open(HARNESS, encoding="utf-8") as fh:
            body = fh.read()
        for name in ("-diag.txt", "-logcat.txt", "-bugreport.zip",
                     "-verdict.txt", "-verdict.json"):
            self.assertIn(name, body, name)


class TestWorkflowWiring(unittest.TestCase):
    def test_yaml_parses(self):
        try:
            import yaml
        except ImportError:
            self.skipTest('pyyaml not installed (stdlib-only runtime)')
        with open(WORKFLOW, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        self.assertIn("phone", doc["jobs"])
        self.assertIn("wear", doc["jobs"])

    def test_phone_wear_use_harness(self):
        with open(WORKFLOW, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("emu_harness.sh", body)
        self.assertIn("phone-verdict.txt", body)
        self.assertIn("wear-verdict.txt", body)

    def test_harness_jobs_check_out_repo_first(self):
        # Run 41275823636: tv had no checkout, so emu_harness.sh was missing
        # (exit 127). Every job invoking the harness must check out first.
        try:
            import yaml
        except ImportError:
            self.skipTest('pyyaml not installed (stdlib-only runtime)')
        with open(WORKFLOW, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        for job in ("phone", "wear", "tv"):
            steps = doc["jobs"][job]["steps"]
            checkout_at = next(
                (i for i, s in enumerate(steps)
                 if str(s.get("uses", "")).startswith("actions/checkout@")),
                None)
            harness_at = next(
                (i for i, s in enumerate(steps)
                 if "emu_harness.sh" in str(s.get("script", s.get("run", "")))),
                None)
            self.assertIsNotNone(harness_at, job)
            self.assertIsNotNone(checkout_at, job)
            self.assertLess(checkout_at, harness_at, job)

    def test_tv_uses_harness_single_line(self):
        with open(WORKFLOW, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("EMU_DEVICE=tv", body)
        self.assertIn("tv-verdict.txt", body)
        # The runner executes script lines via sh -c: no backslash
        # continuations allowed (exit 127, run 41273698943).
        for line in body.splitlines():
            if "emu_harness.sh" in line:
                self.assertFalse(line.rstrip().endswith("\\"), line)


if __name__ == "__main__":
    unittest.main()
