"""Readiness metadata tests use a fake runner; no device or model calls."""
import subprocess
import unittest
from dev.forge_tv_glimmer_journey import ensure_companion_foreground, JourneyBlocked


FOREGROUND='mResumedActivity: ActivityRecord fr.openbridge.companion/.MainActivity'
BACKGROUND='mResumedActivity: ActivityRecord test.launcher/.Home'


class FakeAndroid:
    def __init__(self,results):self.results=iter(results);self.calls=[]
    def _run(self,args):
        self.calls.append(args)
        value=next(self.results)
        if isinstance(value,Exception):raise value
        return value


class ReadinessTests(unittest.TestCase):
    def test_ready_device_needs_no_launch(self):
        android=FakeAndroid([FOREGROUND]);report={}
        ensure_companion_foreground(android,'fixture',True,report)
        self.assertEqual(report['activity_launch_attempts'],0)
        self.assertEqual(report['activity_launches'],0)
        self.assertEqual(len(android.calls),1)

    def test_missing_foreground_blocks_without_explicit_launch_option(self):
        android=FakeAndroid([BACKGROUND]);report={}
        with self.assertRaisesRegex(JourneyBlocked,'COMPANION_MUST_ALREADY_BE_FOREGROUND'):
            ensure_companion_foreground(android,'fixture',False,report)
        self.assertEqual(len(android.calls),1)
        self.assertEqual(report['activity_launches'],0)

    def test_timed_out_launch_is_not_reported_as_zero(self):
        android=FakeAndroid([BACKGROUND,subprocess.TimeoutExpired('fixture-launch',8)]);report={}
        with self.assertRaises(subprocess.TimeoutExpired):
            ensure_companion_foreground(android,'fixture',True,report)
        self.assertEqual(report['activity_launch_attempts'],1)
        self.assertIsNone(report['activity_launches'])

    def test_launch_return_alone_does_not_prove_foreground(self):
        android=FakeAndroid([BACKGROUND,'Starting existing activity',BACKGROUND]);report={}
        with self.assertRaisesRegex(JourneyBlocked,'COMPANION_MUST_ALREADY_BE_FOREGROUND'):
            ensure_companion_foreground(android,'fixture',True,report)
        self.assertEqual(report['activity_launches'],1)

    def test_explicit_launch_rechecks_foreground(self):
        android=FakeAndroid([BACKGROUND,'Starting existing activity',FOREGROUND]);report={}
        ensure_companion_foreground(android,'fixture',True,report)
        self.assertEqual(report['activity_launch_attempts'],1)
        self.assertEqual(report['activity_launches'],1)
