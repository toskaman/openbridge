import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELAY = ROOT / 'companion' / 'android' / 'src' / 'fr' / 'openbridge' / 'companion' / 'RelayServer.java'
MAIN = ROOT / 'companion' / 'android' / 'src' / 'fr' / 'openbridge' / 'companion' / 'MainActivity.java'


def body_of(src, sig):
    """Brace-matched body of the method starting at signature `sig` (skips comments/strings)."""
    i = src.index(sig)
    i = src.index('{', i)
    depth, j, n = 0, i, len(src)
    while j < n:
        c = src[j]
        if c == '/' and j + 1 < n and src[j + 1] == '/':
            j = src.index('\n', j)
        elif c == '/' and j + 1 < n and src[j + 1] == '*':
            j = src.index('*/', j) + 2
            continue
        elif c in '"\'':
            q = c
            j += 1
            while j < n and src[j] != q:
                j += 2 if src[j] == '\\' else 1
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    raise AssertionError('unbalanced braces after %s' % sig)


class RelayCodeReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.relay = RELAY.read_text(encoding='utf-8')
        cls.main = MAIN.read_text(encoding='utf-8')

    def test_reattach_replays_pending_code_to_live_sink(self):
        get = body_of(self.relay, 'static synchronized RelayServer get(')
        self.assertIn('instance.ui = ui', get)
        # A (re-)attached screen must be re-delivered the pending code: direct
        # .code() delivery or a dedicated replay helper, never silently dropped.
        self.assertTrue('replayPendingCode(' in get
                        or ('.code(' in get and 'pending' in get),
                        'get() attaches the sink but never replays a live pending code')

    def test_replay_gated_on_live_pending_code(self):
        # The replay source must be a synchronized accessor that returns the
        # code only while live (set + unexpired), null otherwise.
        accs = [b for b in re.findall(
            r'private synchronized String \w+\(\) \{(.*?)\n    \}', self.relay, re.S)
            if 'pendingCode' in b and 'pendingUntil' in b]
        self.assertTrue(accs, 'no synchronized live-pending-code accessor gating on expiry')
        self.assertIn('return null', accs[0])
        self.assertIn('return pendingCode', accs[0])

    def test_pair_request_still_delivers_code_once(self):
        pair = body_of(self.relay, 'private synchronized JSONObject pairRequest(')
        self.assertEqual(pair.count('ui.code(pendingCode)'), 1)

    def test_activity_attach_paths_go_through_get(self):
        # onCreate + onResume both attach via get(): the replay in get() covers
        # first attach, stacked-instance re-attach (no launchMode) and resume.
        self.assertIn('relay = RelayServer.get(this, this);', self.main)
        self.assertIn('relay = RelayServer.get(this, this); relay.foreground = true;', self.main)

    def test_no_replay_to_headless_lookup(self):
        get = body_of(self.relay, 'static synchronized RelayServer get(')
        # Service lookups pass null: replay must be guarded so NOOP never wins.
        self.assertIn('ui != null', get)
        self.assertNotIn('sink.code(', get.replace('replayPendingCode(ui)', ''))
