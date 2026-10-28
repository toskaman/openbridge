"""Runner input helpers: owner-supplied observation time (immutable) and authz file."""
import unittest
from datetime import timezone

import dev.run_explain_eval as R


class RunnerInputs(unittest.TestCase):
    def test_observed_at_parses_iso(self):
        dt = R.parse_observed_at('2026-10-28T18:00:00+00:00')
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_observed_at_rejects_naive_and_garbage(self):
        with self.assertRaises(ValueError):
            R.parse_observed_at('2026-10-28 18:00:00')
        with self.assertRaises(ValueError):
            R.parse_observed_at('soon')

    def test_authz_file_read_never_creates(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / 'nope.txt'
            with self.assertRaises(FileNotFoundError):
                R.read_authz_file(str(missing))
            self.assertFalse(missing.exists())
            ok = Path(d) / 'authz.txt'
            ok.write_text('  owner-ref-1\n', encoding='utf-8')
            self.assertEqual(R.read_authz_file(str(ok)), 'owner-ref-1')


if __name__ == '__main__':
    unittest.main()
