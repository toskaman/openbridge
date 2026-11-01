"""UTF-8 regression: JSON with non-ASCII text must be read as UTF-8.

On Windows the locale default is cp1252, so a bare Path.read_text() mangles
curly quotes (U+201C/U+201D) and fails the HonestyGate-style JSON reads.
Every text read/write in the repo must pass encoding='utf-8'; this test pins
both the fixture sensitivity and the fix.
"""
import json
import tempfile
import unittest
from pathlib import Path

CURLY = '“hello”'  # U+201C/U+201D curly quotes


class Utf8ReadRegression(unittest.TestCase):
    def test_curly_quote_json_roundtrips_with_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'q.json'
            p.write_bytes(json.dumps({'note': CURLY}, ensure_ascii=False).encode('utf-8'))
            # Negative control: the cp1252 default on Windows mangles (or raises on)
            # this fixture, so a bare read_text() there would fail the assertion below.
            try:
                mangled = json.loads(p.read_bytes().decode('cp1252'))['note']
            except UnicodeDecodeError:
                mangled = None
            self.assertNotEqual(mangled, CURLY)
            # The fix: an explicit utf-8 read always round-trips.
            self.assertEqual(json.loads(p.read_text(encoding='utf-8'))['note'], CURLY)


if __name__ == '__main__':
    unittest.main()
