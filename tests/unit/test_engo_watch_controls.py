"""Tests for Wear OS Watch -> ENGO 3 / ActiveLook by Microoled complete controls, gating & NL activation."""
import os
import secrets
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.fabric import relay as R
from src.glasses import hub as G
from src.glasses import watch_controls as WC
from src.runtime import api_v2, command as CMD, command_drain as CD
from src.runtime.companion_commands import CompanionCommands
from src.runtime.remote_controls import RemoteControls
from src.runtime.routing import Router


class _CaptureLink:
    def __init__(self):
        self.writes = []

    def write(self, data: bytes):
        self.writes.append(bytes(data))


class _Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class _FakeRelays:
    def __init__(self):
        self.relays = {}


class _FakeReg:
    def __init__(self, devs):
        self.devices = devs


class _FakeServer:
    def __init__(self, with_watch=True, with_phone=True):
        self.relays = _FakeRelays()
        self.sent_ops = []  # (rid, op, params)
        self.queued_commands = {}  # rid -> list
        self.command_reports = []
        self.control_updates = []
        self.glasses_hub = None
        self.runtime_executor = None
        self.skill_router = None
        self.remote_controls = None
        self.fabric_lock = threading.Lock()
        self.fabric_salt = b'salt'
        devs = {}
        if with_phone:
            key_p = b'P' * 32
            self.relays.relays['relay-phone-1'] = {
                'key': key_p, 'online': True, 'busy': False, 'seen': {},
                'device_key': 'android-phone-1',
                'capabilities': ['ble_scan', 'glasses_link', 'remote_controls', 'command_submit', 'modules'],
                'declared': {'watch': False, 'television': False, 'form_factor': 'phone', 'language': 'fr'},
                'send': lambda r, msg, rid='relay-phone-1': self._handle_send(rid, msg),
            }
            devs['dev-phone'] = {
                'key': 'dev-phone', 'label': 'Blackview Phone', 'category': 'phone',
                'handles': {'COMPANION_RELAY': 'android-phone-1'}, 'links': [{'online': True}],
            }
        if with_watch:
            key_w = b'W' * 32
            self.relays.relays['relay-watch-1'] = {
                'key': key_w, 'online': True, 'busy': False, 'seen': {},
                'device_key': 'android-watch-1',
                'capabilities': ['remote_controls', 'command_submit', 'modules'],
                'declared': {'watch': True, 'television': False, 'form_factor': 'watch', 'language': 'fr'},
                'send': lambda r, msg, rid='relay-watch-1': self._handle_send(rid, msg),
            }
            devs['dev-watch'] = {
                'key': 'dev-watch', 'label': 'Galaxy Watch7', 'category': 'watch',
                'handles': {'COMPANION_RELAY': 'android-watch-1'}, 'links': [{'online': True}],
            }
        self.fabric_registry = _FakeReg(devs)
        self.fabric_snapshot = {'devices': list(devs.values()), 'links': []}

    def _handle_send(self, rid, msg):
        op = msg['op']
        params = msg.get('params') or {}
        self.sent_ops.append((rid, op, params))
        key = self.relays.relays[rid]['key']
        reply_params = {}
        if op == 'set_controls':
            self.control_updates.append((rid, params))
        elif op == 'get_commands':
            cmds = list(self.queued_commands.pop(rid, []))
            reply_params = {'commands': cmds}
        elif op == 'report_command':
            self.command_reports.append((rid, params))
        elif op == 'report_result':
            self.command_reports.append((rid, params))
        elif op == 'update_status':
            self.control_updates.append((rid, params))
        elif op == 'glasses_write':
            reply_params = {'accepted': len(params.get('chunks') or [])}
        rep = {'protocol': R.PROTOCOL, 'relay_id': rid, 'op': 'reply', 'params': reply_params,
               'nonce': secrets.token_hex(12), 'issued_at': int(time.time()), 'expires_at': int(time.time()) + 30}
        return {**rep, 'mac': R.sign(key, rep)}


class EngoWatchControlsTests(unittest.TestCase):
    def test_watch_detection_gating_no_watch_vs_watch(self):
        srv_no = _FakeServer(with_watch=False, with_phone=True)
        det_no = WC.detect_watches(srv_no)
        self.assertFalse(det_no['watch_detected'])
        self.assertEqual(det_no['paired_watches'], [])
        code, body = api_v2.get(srv_no, '/api/v2/engo_watch_controls', {})
        self.assertEqual(code, 200)
        self.assertFalse(body['watch_detected'])
        p_code, p_err = api_v2.post(srv_no, '/api/v2/engo_watch_controls', {'action': 'show', 'consent': True})
        self.assertEqual(p_code, 404)

        srv_yes = _FakeServer(with_watch=True, with_phone=True)
        code, body = api_v2.get(srv_yes, '/api/v2/engo_watch_controls', {})
        self.assertEqual(code, 200)
        self.assertTrue(body['watch_detected'])
        self.assertEqual(body['paired_watches'][0]['relay_id'], 'relay-watch-1')

    def test_all_pages_respect_max_controls_and_push_to_watch(self):
        srv = _FakeServer(with_watch=True)
        clk = _Clock()
        srv.glasses_hub = G.Hub(link=_CaptureLink(), settings={'language': 'fr'}, clock=clk)
        all_ops = set()
        all_screens = set()
        for pid in WC.PAGE_IDS:
            code, res = api_v2.post(
                srv, '/api/v2/engo_watch_controls',
                {'action': 'show', 'page': pid, 'lang': 'fr', 'consent': True},
            )
            self.assertEqual(code, 200, res)
            self.assertEqual(res['relay_id'], 'relay-watch-1')
            self.assertEqual(res['page'], pid)
            _, sent = srv.control_updates[-1]
            self.assertLessEqual(len(sent['controls']), R.MAX_CONTROLS, pid)
            # Every ENGO page includes a status tile + buttons
            self.assertEqual(sent['controls'][-1]['kind'], 'status')
            for cid, g in srv.remote_controls.grants['relay-watch-1'].items():
                self.assertEqual(g['skill_id'], 'engo_control')
                all_ops.add(g['params']['op'])
                if g['params']['op'] == 'open_screen':
                    all_screens.add(g['params']['value'])

        self.assertTrue({'next', 'ok', 'back', 'home', 'display_toggle', 'luma_up', 'luma_down',
                         'als_toggle', 'gesture_toggle', 'rotate_toggle', 'privacy_cycle',
                         'lang_toggle', 'units_toggle', 'clear', 'shift_left', 'shift_right',
                         'shift_up', 'shift_down', 'shift_reset', 'inbox_clear',
                         'switch_page', 'hide_controls'} <= all_ops)
        self.assertEqual(all_screens, {'home', 'inbox', 'oracle', 'voice', 'sport', 'tv', 'vacuum', 'calibration', 'settings'})

    def test_hub_apply_control_hardware_and_screens(self):
        link = _CaptureLink()
        clk = _Clock()
        h = G.Hub(link=link, settings={'language': 'fr', 'luma': 8}, clock=clk)

        h.apply_control('luma_up')
        self.assertEqual(h.settings['luma'], 10)
        self.assertTrue(any(b'\xFF\x10\x00\x06\x0A\xAA' in w for w in link.writes))

        h.apply_control('luma_set', '14')
        self.assertEqual(h.settings['luma'], 14)

        h.apply_control('als_off')
        self.assertFalse(h.settings['als'])
        self.assertTrue(any(b'\xFF\x22\x00\x06\x00\xAA' in w for w in link.writes))

        h.apply_control('gesture_off')
        self.assertFalse(h.settings['gesture'])
        self.assertTrue(any(b'\xFF\x21\x00\x06\x00\xAA' in w for w in link.writes))

        h.apply_control('rotate_toggle')
        self.assertTrue(h.settings['rotate180'])

        h.apply_control('privacy_cycle')
        self.assertEqual(h.settings['privacy'], 'sender')

        h.apply_control('units_toggle')
        self.assertEqual(h.settings['units'], 'imperial')

        h.apply_control('shift_right')
        self.assertEqual(h.settings['shift_x'], 4)
        self.assertTrue(any(b'\xFF\x09' in w for w in link.writes))

        h.apply_control('open_screen', 'tv')
        self.assertEqual(type(h.menu.screen).__name__, 'TVHub')

        h.apply_control('display_off')
        self.assertFalse(h.settings['screen_on'])
        self.assertTrue(any(b'\xFF\x00\x00\x06\x00\xAA' in w for w in link.writes))

    def test_watch_press_executes_engo_control_and_switches_page(self):
        srv = _FakeServer(with_watch=True)
        link = _CaptureLink()
        clk = _Clock()
        srv.glasses_hub = G.Hub(link=link, settings={'language': 'fr', 'luma': 6}, clock=clk)
        WC.show_watch_controls(srv, page='main', lang='fr')
        rc = srv.remote_controls
        rc.clock = clk

        # Find luma_up button on watch and press it via RemoteControls.process()
        luma_cid = next(cid for cid, g in rc.grants['relay-watch-1'].items() if g['params'].get('op') == 'luma_up')
        entry = rc.process('relay-watch-1', {
            'request_id': 'a' * 32, 'control_id': luma_cid,
            'pressed_at': int(clk.t * 1000), 'seq': 1, 'gesture': 'hold',
        })
        self.assertEqual(entry['state'], 'EXECUTED')
        self.assertEqual(srv.glasses_hub.settings['luma'], 8)
        # Status tile received updated ENGO summary
        self.assertTrue(any(p.get('values') and any('Lum 8' in v for v in p['values'].values())
                            for rid, op, p in srv.sent_ops if op == 'update_status'))

        # Switch page from the watch itself -> installs 'screens' page
        clk.t += 2.0
        sw_cid = next(cid for cid, g in rc.grants['relay-watch-1'].items()
                      if g['params'].get('op') == 'switch_page' and g['params'].get('value') == 'screens')
        sw_entry = rc.process('relay-watch-1', {
            'request_id': 'b' * 32, 'control_id': sw_cid,
            'pressed_at': int(clk.t * 1000), 'seq': 2, 'gesture': 'hold',
        })
        self.assertEqual(sw_entry['state'], 'EXECUTED')
        self.assertEqual(srv._engo_watch_pages['relay-watch-1'], 'screens')

    def test_text_and_voice_on_the_fly_via_companion_and_pc(self):
        srv = _FakeServer(with_watch=True)
        srv.glasses_hub = G.Hub(link=_CaptureLink(), settings={'language': 'fr'})
        cc = CompanionCommands(srv)

        # Watch option button toggle via CompanionCommands
        srv.queued_commands['relay-watch-1'] = [{
            'request_id': 'c' * 32, 'kind': 'text', 'mode': 'command',
            'text': '__engo_watch_controls__:toggle', 'lang': 'fr', 'quality': 'low', 'seq': 1,
        }]
        cc.poll_once()
        self.assertEqual(srv._engo_watch_pages.get('relay-watch-1'), 'main')

        # Natural French voice/text switching to optics/display page on watch
        srv.queued_commands['relay-phone-1'] = [{
            'request_id': 'd' * 32, 'kind': 'text', 'mode': 'command',
            'text': 'Affiche la luminosité et les réglages de la ENGO 3 sur la montre',
            'lang': 'fr', 'quality': 'low', 'seq': 2,
        }]
        cc.poll_once()
        self.assertEqual(srv._engo_watch_pages.get('relay-watch-1'), 'display')

        # Hide via command_drain
        hit = CD._handle(srv, srv.relays.relays['relay-watch-1'], 'relay-watch-1',
                         {'request_id': 'e' * 32, 'kind': 'text', 'lang': 'fr',
                          'text': 'Masque les contrôles ENGO de la montre'},
                         None, None, None, None)
        self.assertEqual(hit[0], 'resolved')
        self.assertNotIn('relay-watch-1', srv._engo_watch_pages)

        # PC Ask OpenBridge flow: command.parse -> approve -> execute
        parsed = CMD.parse_request(srv, {'text': 'Montre tous les contrôles ENGO 3 sur ma montre', 'lang': 'fr'})
        doc = parsed['intent']
        self.assertEqual(doc['status'], 'resolved')
        self.assertEqual(doc['skill_id'], 'engo_control')
        prev = CMD.approve(srv, doc)
        receipt = CMD.execute(srv, doc, consent=True, preview=prev)
        self.assertEqual(receipt['state'], 'EXECUTED')
        self.assertEqual(srv._engo_watch_pages.get('relay-watch-1'), 'main')

    def test_companion_and_ui_gating_guards(self):
        root = Path(__file__).resolve().parents[2]
        main_java = (root / 'companion/android/src/fr/openbridge/companion/MainActivity.java').read_text(encoding='utf-8')
        relay_java = (root / 'companion/android/src/fr/openbridge/companion/RelayServer.java').read_text(encoding='utf-8')
        ctrl_js = (root / 'src/ui/views/controls_view.js').read_text(encoding='utf-8')
        set_js = (root / 'src/ui/views/settings_view.js').read_text(encoding='utf-8')

        self.assertIn('.put("watch", watch)', relay_java)
        self.assertIn('if (watch) {\n            engoWatchBtn', main_java)
        self.assertIn('if (C.demo || !C.engoWatch || !C.engoWatch.watch_detected) return null;', ctrl_js)
        self.assertIn('if (!d || !d.watch_detected)', set_js)


if __name__ == '__main__':
    unittest.main()
