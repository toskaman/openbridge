"""Code-freshness guard for the cloud e2e pairing scrape.

Regression: runs 41215688399/41214555252 submitted a dumpsys-only bare-digit
code while no pairing code was rendered on screen; the relay answered 409
'not paired'. Candidates must be corroborated by the on-screen XML dump;
dumpsys-only bare digits are never submitted.
"""
import importlib.util
import os
import unittest

_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '..', '..', 'scripts', 'verify', 'cloud_e2e.py')
_spec = importlib.util.spec_from_file_location('cloud_e2e_vehicle', _SCRIPT)
cloud_e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cloud_e2e)

# Idle Companion screen as dumped in run 41215688399 (trimmed): NOT PAIRED,
# default caption, coordinate-heavy bounds, zero digits in text attributes.
XML_IDLE = (
    "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
    '<hierarchy rotation="0">'
    '<node index="0" text="OpenBridge Companion" bounds="[32,29][331,67]" />'
    '<node index="1" text="?  NOT PAIRED" bounds="[747,173][987,231]" />'
    '<node index="2" text="WAITING FOR YOUR PC" bounds="[80,252][987,285]" />'
    '<node index="3" text="Open OpenBridge on your PC to pair this device."'
    ' bounds="[80,285][987,432]" />'
    '<node index="4" text="Not paired" bounds="[1115,342][1409,399]" />'
    '<node index="5" text="" bounds="[1051,152][1839,552]" />'
    '</hierarchy>'
)

# Same screen with the pairing codeCard rendered (MainActivity.code()).
XML_WITH_CODE = XML_IDLE.replace(
    '</hierarchy>',
    '<node index="6" text="ENTER THIS CODE IN OPENBRIDGE ON YOUR PC"'
    ' bounds="[80,600][987,630]" />'
    '<node index="7" text="839 918" content-desc="Pairing code 839918"'
    ' bounds="[80,630][987,700]" />'
    '</hierarchy>')

# Dumpsys activity top carrying bare-digit noise but no pairing context.
TOP_NOISE = (
    'ACTIVITY fr.openbridge.companion/.MainActivity taskId=5\n'
    '  ViewRootImpl mSeq=839918 mAttachInfo.mSessionId=42\n'
    '  Choreographer mLastFrameTimeNanos=123456789012345\n'
    '  width=1920 height=1080 mPrivateFlags=16777216\n'
)

# Dumpsys activity top where the code view is visible with context.
TOP_CONTEXTUAL = (
    'ACTIVITY fr.openbridge.companion/.MainActivity taskId=5\n'
    '  android.widget.TextView text="Pairing code 123456"\n'
)


class FreshnessGuardTests(unittest.TestCase):
    def test_dumpsys_bare_digits_rejected_when_nothing_on_screen(self):
        self.assertEqual(cloud_e2e.fresh_candidates(XML_IDLE, TOP_NOISE, set()), [])

    def test_bounds_coordinates_are_not_codes(self):
        self.assertEqual(cloud_e2e.extract_codes(XML_IDLE, cloud_e2e.CODE_PATS), [])

    def test_xml_code_accepted_and_normalized(self):
        self.assertEqual(cloud_e2e.fresh_candidates(XML_WITH_CODE, '', set()), ['839918'])

    def test_dumpsys_contextual_match_still_accepted(self):
        self.assertEqual(cloud_e2e.fresh_candidates('', TOP_CONTEXTUAL, set()), ['123456'])

    def test_xml_first_then_dumpsys_without_dupes(self):
        cands = cloud_e2e.fresh_candidates(XML_WITH_CODE, TOP_CONTEXTUAL, set())
        self.assertEqual(cands, ['839918', '123456'])

    def test_seen_codes_are_skipped(self):
        self.assertEqual(cloud_e2e.fresh_candidates(XML_WITH_CODE, TOP_CONTEXTUAL, {'839918'}),
                         ['123456'])

    def test_xml_shows_code(self):
        self.assertFalse(cloud_e2e.xml_shows_code(XML_IDLE))
        self.assertFalse(cloud_e2e.xml_shows_code(''))
        self.assertTrue(cloud_e2e.xml_shows_code(XML_WITH_CODE))


if __name__ == '__main__':
    unittest.main()
