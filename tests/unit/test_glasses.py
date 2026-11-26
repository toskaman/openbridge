"""Glasses hub: drawing, messages, menus, the grant, actions through the gate, voice."""
import unittest

from src.glasses import hub as G
from src.glasses import ui
from src.glasses.notifications import Inbox, clean
from src.glasses.panel import Panel, fit, text_width, wrap


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakeExecutor:
    def __init__(self, state='VERIFIED', after=None):
        self.calls, self.state, self.after = [], state, after

    def execute(self, prim, key, params, consent=False):
        self.calls.append((prim, key, params, consent))
        return {'state': self.state, 'verified': self.state == 'VERIFIED', 'after': self.after, 'errors': [],
                'result': {'screen': {'focused_app': 'com.netflix.ninja'}}}


class PanelTests(unittest.TestCase):
    def test_text_never_overflows(self):
        s = fit('A very long sender name that cannot fit on the glasses', 2, 120)
        self.assertTrue(s.endswith('...'))   # ASCII: the glasses' fonts have no '…'
        self.assertLessEqual(text_width(s, 2), 120)
        lines = wrap('word ' * 60, 1, 200, 3)
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(text_width(l, 1) <= 200 for l in lines))

    def test_frames_are_held_then_flushed(self):
        p = Panel().begin()
        p.text(10, 10, 'hi')
        p.end()
        b = p.to_bytes()
        self.assertTrue(b.startswith(bytes([0xFF, 0x39])))
        self.assertIn(bytes([0x39]), b[-8:])

    def test_accents_are_folded_to_ascii(self):
        from src.glasses.panel import ascii_fold
        self.assertEqual(ascii_fold('été à ça « oui » – 3°'), 'ete a ca " oui " - 3o')
        p = Panel(colour=False)
        p.text(10, 10, 'Préférences')
        self.assertIn(b'Preferences\x00', p.frames[-1])

    def test_red_green_colour_encoding(self):
        from src.adapters import activelook as AL
        self.assertEqual((AL.rg(8, 0), AL.rg(0, 8), AL.rg(8, 8)), (0x3c, 0xc3, 0xff))   # API palette
        self.assertEqual(AL.rg_levels(0x3e), (8, 2))
        self.assertEqual(len({v for row in AL.RG_PALETTE for v in row}), 81)

    def test_coloured_tones_use_red_green_commands_on_engo3(self):
        p = Panel(colour=True)
        p.text(10, 10, 'OK', tone='ok')
        self.assertEqual(p.frames[-1][1], 0x3E)              # txtColor
        p.text(10, 40, 'plain', tone='primary')
        self.assertEqual(p.frames[-1][1], 0x37)              # grey text shows yellow on the ENGO 3
        p.line(0, 0, 10, 0, tone='alert')
        self.assertIn(bytes([0xFF, 0x3D]), b''.join(p.frames))

    def test_long_oracle_answer_is_paged(self):
        from src.glasses.ui import ORACLE_LINES_PER_PAGE, oracle_pages
        pages = oracle_pages('mot ' * 120)
        self.assertGreater(len(pages), 1)
        self.assertTrue(all(len(pg) <= ORACLE_LINES_PER_PAGE for pg in pages))

    def test_rotate180_mirrors_coordinates(self):
        # Upright default = ActiveLook native frame (origin bottom-right), measured on a real ENGO 3 on 26 Nov 2026.
        a, b = Panel(x_offset=0), Panel(rotate180=True, x_offset=0)
        a.line(0, 0, 10, 0)
        b.line(0, 0, 10, 0)
        self.assertNotEqual(a.to_bytes(), b.to_bytes())
        self.assertEqual(a._p(0, 0), (303, 255))
        self.assertEqual(b._p(0, 0), (0, 0))
        self.assertEqual(Panel()._p(0, 0), (303, 255))       # default: no offset (whole width visible)

    def test_upright_text_uses_rotation_4_at_flipped_anchor(self):
        import struct
        p = Panel(colour=False, x_offset=0)
        p.text(10, 20, 'HAUT', font=2)
        frame = p.frames[-1]
        x, y, rot = struct.unpack_from('>hhB', frame, 4)
        self.assertEqual((x, y, rot), (303 - 10, 255 - 20, 4))

    def test_emulator_draws_native_frames_upright(self):
        try:
            import PIL  # noqa: F401 - the emulator draws with Pillow (optional in CI)
        except ImportError:
            self.skipTest('Pillow not installed')
        from src.adapters.activelook_emulator import HUDCanvas
        p = Panel(colour=False, x_offset=0).begin()
        p.rect(0, 0, 9, 9, fill=True)          # logical top-left corner
        hud = HUDCanvas(model='ENGO 3')
        hud.dispatch(p.end().to_bytes())
        self.assertNotEqual(hud._img.getpixel((2, 2)), (0, 0, 0))
        self.assertEqual(hud._img.getpixel((300, 250)), (0, 0, 0))

    def test_dim_tones_avoid_palette_bytes(self):
        from src.glasses.panel import TONES
        for name, (_, level) in TONES.items():
            if name != 'black':
                self.assertGreaterEqual(level, 7, name)


class InboxTests(unittest.TestCase):
    def test_allowlist_dedupe_order_privacy(self):
        c = Clock()
        box = Inbox(clock=c)
        self.assertIsNone(box.add({'package': 'com.example.bank', 'sender': 'Bank', 'text': 'code 1234'}))
        a = box.add({'package': 'org.telegram.messenger', 'sender': 'Maman', 'text': 'Salut', 'time': c.t - 100})
        self.assertIsNone(box.add({'package': 'org.telegram.messenger', 'sender': 'Maman', 'text': 'Salut'}))
        b = box.add({'package': 'com.discord', 'sender': 'Léa', 'text': 'Hello', 'time': c.t})
        self.assertEqual([i['id'] for i in box.list()], [b['id'], a['id']])
        self.assertEqual(box.unread(), 2)
        box.privacy = 'sender'
        self.assertEqual(box.list()[0]['text'], 'New message')
        box.privacy = 'off'
        self.assertIsNone(box.add({'package': 'com.discord', 'sender': 'X', 'text': 'Y'}))

    def test_clean_strips_control_and_bidi(self):
        self.assertEqual(clean('a‮b\x00c\n d', 50), 'a b c d')
        self.assertEqual(len(clean('x' * 999, 40)), 40)


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.c = Clock()
        self.box = Inbox(clock=self.c)
        self.box.add({'package': 'com.discord', 'sender': 'Léa', 'text': 'Hi'})
        self.ctx = ui.Context(inbox=self.box, clock=self.c)
        self.m = ui.Menu(self.ctx)

    def test_open_messages_and_read(self):
        self.assertIsNone(self.m.handle('ok'))
        self.assertIsInstance(self.m.screen, ui.Inbox)
        self.m.handle('ok')
        self.assertIsInstance(self.m.screen, ui.MessageView)
        self.m.render()
        self.assertEqual(self.box.unread(), 0)
        self.m.handle('back')
        self.m.handle('back')
        self.assertIsInstance(self.m.screen, ui.Home)

    def test_tv_remote_returns_typed_key_actions(self):
        self.m.handle('next')
        self.m.handle('next')
        self.m.handle('ok')
        self.assertIsInstance(self.m.screen, ui.TVHub)
        self.m.screen.focus = 2
        self.m.handle('ok')
        a = self.m.handle('left')
        self.assertEqual((a.device, a.primitive, a.params), ('tv', 'device_action', {'action': 'key', 'args': {'key': 'left'}}))

    def test_every_screen_renders(self):
        from src.glasses import preview
        for name, frame in preview.gallery(self.c.t):
            self.assertTrue(frame, name)

    def test_gestures(self):
        c = Clock(0)
        g = ui.GestureDecoder(clock=c)
        for n, want in ((1, 'next'), (2, 'ok'), (3, 'back')):
            for _ in range(n):
                g.wave()
                c.t += 0.2
            self.assertIsNone(g.poll())
            c.t += 1
            self.assertEqual(g.poll(), want)


class HubTests(unittest.TestCase):
    def hub(self, grant=('tv_remote', 'tv_apps', 'vacuum'), ex=None):
        self.c = Clock()
        return G.Hub(executor=ex or FakeExecutor(), devices={'tv': 'dev-tv', 'vacuum': 'dev-vac'},
                     settings={'grant': list(grant), 'language': 'en'}, clock=self.c)

    def test_grant_is_exact(self):
        cov = lambda a, g=('tv_remote', 'tv_apps', 'vacuum'): G.grant_covers(g, a)
        self.assertTrue(cov(ui.tv_key('up', 'Up')))
        self.assertFalse(cov(ui.tv_key('power', 'Power')))
        self.assertFalse(cov(ui.Action('device', 'x', 'tv', 'device_action', {'action': 'text', 'args': {'text': 'x'}})))
        self.assertFalse(cov(ui.Action('device', 'x', 'tv', 'device_action', {'action': 'launch_app', 'args': {'package': 'com.evil.app'}})))
        self.assertFalse(cov(ui.vac('empty_dust', 'x')))
        self.assertFalse(cov(ui.tv_key('up', 'Up'), ()))
        self.assertFalse(cov(ui.Action('device', 'TV sleep', 'tv', 'tv_sleep', {})))

    def test_action_goes_through_the_executor_with_consent(self):
        ex = FakeExecutor()
        h = self.hub(ex=ex)
        out = h.run(ui.vac('start', 'Start cleaning'))
        self.assertTrue(out['ok'])
        self.assertEqual(ex.calls, [('tuya_command', 'dev-vac', {'command': 'start'}, True)])

    def test_without_grant_nothing_runs(self):
        ex = FakeExecutor()
        h = self.hub(grant=(), ex=ex)
        out = h.run(ui.tv_key('up', 'Up'))
        self.assertFalse(out['ok'])
        self.assertEqual(ex.calls, [])

    def test_wave_drives_the_menu_and_redraws(self):
        h = self.hub()
        before = h.redraw(force=True)
        h.press('next')
        h.tick()
        self.assertNotEqual(h.link.last, before)

    def test_notification_toast_then_open(self):
        h = self.hub()
        item = h.notify({'package': 'org.telegram.messenger', 'sender': 'Maman', 'text': 'Tu viens ?'})
        self.assertEqual(h.ctx.toast['id'], item['id'])
        h.press('ok')
        h.tick()
        self.assertIsInstance(h.menu.screen, ui.MessageView)

    def test_voice_runs_only_mapped_skills(self):
        ex = FakeExecutor()
        h = self.hub(ex=ex)
        h.understand = lambda t: ('tv_volume_step', {'direction': 'down'})
        self.assertTrue(h.voice('baisse le son')['ok'])
        changes = [c for c in ex.calls if c[2].get('action') == 'key']
        self.assertEqual(changes, [('device_action', 'dev-tv', {'action': 'key', 'args': {'key': 'volume_down'}}, True)])
        n = len(ex.calls)
        h.understand = lambda t: ('home.lock', {})
        self.assertIsNone(h.voice('verrouille la porte'))
        self.assertEqual(h.ctx.voice['state'], 'failed')
        self.assertEqual(len(ex.calls), n)

    def test_tv_state_is_read_back(self):
        h = self.hub(ex=FakeExecutor(after=40))
        h.run(ui.tv_key('volume_up', 'Volume up'))
        self.assertEqual((h.ctx.tv_volume, h.ctx.tv_app), (40, 'Netflix'))
        reads = [c for c in h.executor.calls if c[2].get('action') in ('audio_state', 'screen_state')]
        self.assertEqual(len(reads), 2)

    def test_errors_are_plain_words(self):
        ex = FakeExecutor(state='FAILED')
        ex.execute = lambda *a, **k: {'state': 'FAILED', 'verified': False, 'errors': ['DEVICE_UNAVAILABLE: No live ADB link']}
        h = self.hub(ex=ex)
        self.assertEqual(h.run(ui.tv_key('up', 'Up'))['text'], 'Up: TV not reachable')


if __name__ == '__main__':
    unittest.main()
