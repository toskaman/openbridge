"""Companion 0.15 on the PC side: modules hide glasses menus, device cards, phone sensors fed into the sport engine,
standalone sessions, the visual Oracle command, and the standalone hand-back (RESUMED)."""
import threading
import unittest

from src.fabric import relay as R
from src.glasses import ui
from src.glasses.hub import Hub, PhoneLink
from src.glasses.phone_feed import PhoneFeed
from src.runtime import companion_modules as M


class FakeLink:
    def write(self, b):
        pass

    def close(self):
        pass


class FakeServer:
    def __init__(self, caps=('modules', 'cards', 'phone_sensors')):
        self.relays = type('X', (), {})()
        self.relays.relays = {'r1': {'online': True, 'capabilities': list(caps)}}


def hub():
    return Hub(link=FakeLink(), settings={'apps': ['telegram']}, clock=lambda: 1000.0)


class ModulesTests(unittest.TestCase):
    def test_module_switched_off_hides_its_home_entry(self):
        h = hub()
        names = [i[3] for i in ui.Home().items(h.ctx)]
        self.assertIn(ui.TVHub, names)
        h.ctx.modules = {'tv': False, 'vacuum': False, 'messages': True}
        names = [i[3] for i in ui.Home().items(h.ctx)]
        self.assertNotIn(ui.TVHub, names)
        self.assertNotIn(ui.VacuumScreen, names)
        self.assertIn(ui.Inbox, names)

    def test_home_focus_survives_a_shorter_list(self):
        h = hub()
        home = ui.Home()
        home.focus = 5
        h.ctx.modules = {'tv': False, 'vacuum': False, 'sport': False}
        from src.glasses.panel import Panel
        home.render(Panel(colour=True).begin(), h.ctx)
        self.assertLess(home.focus, len(home.items(h.ctx)))

    def test_toggle_words_for_new_modules(self):
        self.assertEqual(M.parse_toggle('désactive le module télé'), ('tv', False))
        self.assertEqual(M.parse_toggle('active le menu aspirateur'), ('vacuum', True))
        self.assertEqual(M.parse_toggle('retire le module capteurs'), ('sensors', False))
        self.assertEqual(M.parse_toggle("active l'Oracle"), ('oracle', True))
        # an order for the device itself is never taken as a module switch
        self.assertIsNone(M.parse_toggle('éteins la télé'))
        self.assertIsNone(M.parse_toggle("arrête l'aspirateur"))
        self.assertIsNone(M.parse_toggle('allume la tele'))

    def test_relay_accepts_all_six_modules_and_refuses_others(self):
        key = b'k' * 32
        R.command(key, 'r1', 'set_modules', {'sport': False, 'sensors': True})
        with self.assertRaises(R.RelayError):
            R.command(key, 'r1', 'set_modules', {'camera': True})


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.h = hub()
        self.server = FakeServer()
        self.feed = PhoneFeed(self.server, self.h, threading.RLock(), clock=lambda: 1000.0)
        self.sent = []

    def test_status_sets_modules_on_the_hub(self):
        self.feed._send = lambda rid, op, p=None: {'modules': {'tv': False, 'oracle': True}, 'profile': 'bike',
                                                    'capabilities': ['modules', 'cards']}
        self.feed.read_status('r1')
        self.assertEqual(self.h.ctx.modules, {'tv': False, 'oracle': True})
        self.assertEqual(self.feed.profile['r1'], 'bike')

    def test_cards_are_sent_once_until_they_change(self):
        self.feed._send = lambda rid, op, p=None: self.sent.append((op, p)) or {}
        self.h.ctx.tv_app, self.h.ctx.tv_volume = 'YouTube', 12
        self.feed.push_cards('r1')
        self.feed.push_cards('r1')
        self.assertEqual(len(self.sent), 1)
        op, p = self.sent[0]
        self.assertEqual(op, 'set_cards')
        ids = [c['id'] for c in p['cards']]
        self.assertIn('tv', ids)
        self.assertIn('messages', ids)
        R.command(b'k' * 32, 'r1', 'set_cards', p)          # passes the relay's own checks
        self.h.ctx.tv_volume = 13
        self.feed.push_cards('r1')
        self.assertEqual(len(self.sent), 2)

    def test_relay_refuses_malformed_cards(self):
        with self.assertRaises(R.RelayError):
            R.command(b'k' * 32, 'r1', 'set_cards', {'cards': [{'id': 'x', 'title': 'y' * 200}]})
        with self.assertRaises(R.RelayError):
            R.command(b'k' * 32, 'r1', 'set_cards', {'cards': [{'id': 'x', 'run': 'rm'}]})

    def test_phone_gps_and_heart_rate_feed_the_sport_engine(self):
        self.h.menu.stack.append(ui.SportDashboard('ride'))
        self.feed.modules['r1'] = {'sensors': True}
        self.assertTrue(self.feed.wants_sensors('r1'))
        t = [1000.0]
        self.feed.clock = lambda: t[0]
        for i in range(5):
            t[0] = 1000.0 + i
            self.feed.feed('r1', {'location': {'lat': 45.0 + i * 0.0001, 'lon': 5.0, 'age_s': 0.2, 'accuracy_m': 4},
                                  'sport': [{'kind': 'heart_rate', 'raw': '0096', 'age_s': 0.1}]})
        snap = self.h.sport.snapshot()
        self.assertGreater(snap['distance_m'] or 0, 30)
        self.assertEqual(snap.get('heart_rate'), 150)

    def test_sensors_not_read_when_the_module_is_off(self):
        self.h.menu.stack.append(ui.SportDashboard('run'))
        self.feed.modules['r1'] = {'sensors': False}
        self.assertFalse(self.feed.wants_sensors('r1'))

    def test_fall_shows_a_banner_once(self):
        self.feed.feed('r1', {'fall_age_s': 3})
        self.assertFalse(self.h.ctx.banner['ok'])
        self.h.ctx.banner = None
        self.feed.feed('r1', {'fall_age_s': 4})
        self.assertIsNone(self.h.ctx.banner)

    def test_standalone_sessions_are_saved(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.environ['OB_DATA_DIR'] = d
            try:
                self.feed._send = lambda rid, op, p=None: {'sessions': [{'start': 1700000000, 'end': 1700000600,
                                                                          'distance_m': 4200, 'source': 'phone_standalone'}]}
                self.feed.pull_sessions('r1')
                self.assertEqual(self.feed.saved_sessions, 1)
                self.assertTrue(os.listdir(os.path.join(d, 'sport_sessions')))
            finally:
                del os.environ['OB_DATA_DIR']


class VisionAndResumeTests(unittest.TestCase):
    def test_vision_command_is_validated(self):
        ok = {'request_id': 'a' * 32, 'kind': 'vision', 'clip_id': 'p0a1b2c3d4e5f', 'bytes': 120000,
              'sha256': 'f' * 64, 'text': "Qu'est-ce que c'est ?", 'lang': 'fr', 'quality': 'auto'}
        out = R.validate_commands({'commands': [ok]})
        self.assertEqual(out[0]['kind'], 'vision')
        self.assertEqual(out[0]['text'], "Qu'est-ce que c'est ?")
        self.assertEqual(R.validate_commands({'commands': [dict(ok, bytes=R.VOICE_MAX_BYTES + 1)]}), [])
        self.assertEqual(R.validate_commands({'commands': [dict(ok, clip_id='../x')]}), [])

    def test_resumed_event_triggers_a_redraw(self):
        link = PhoneLink.__new__(PhoneLink)
        link.stats = {'gestures': 0}
        called = []
        link.on_resumed = lambda: called.append(1)
        link._handle([{'t': 'state', 'v': 'RESUMED'}])
        self.assertEqual(called, [1])


if __name__ == '__main__':
    unittest.main()
