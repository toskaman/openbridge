"""Home Assistant bridge against a simulated Home Assistant REST API (SIMULATED_VERIFIED; no real instance in CI)."""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from src.adapters import home_assistant as HA
from src.fabric.home_assistant_ingest import ingest_home_assistant
from src.fabric.registry import Registry
from src.runtime.primitives import Executor

TOKEN = 'good-token'


def initial_states():
    def e(eid, state, **attrs):
        return {'entity_id': eid, 'state': state, 'attributes': attrs}
    return {s['entity_id']: s for s in (
        e('light.living_room', 'on', brightness=128, supported_color_modes=['brightness'], friendly_name='Living room'),
        e('light.desk', 'on', brightness=102, color_mode='color_temp', color_temp_kelvin=2700,
          supported_color_modes=['color_temp', 'hs'], friendly_name='Desk'),
        e('light.strip', 'on', brightness=255, color_mode='hs', hs_color=[240.0, 80.0],
          supported_color_modes=['hs'], friendly_name='Strip'),
        e('switch.coffee', 'off', friendly_name='Coffee machine'),
        e('climate.hall', 'heat', temperature=19.0, min_temp=7, max_temp=30, friendly_name='Hall'),
        e('media_player.tv', 'playing', volume_level=0.2, friendly_name='TV'),
        e('cover.garage', 'closed', device_class='garage', friendly_name='Garage'),
        e('cover.blinds', 'closed', device_class='blind', friendly_name='Blinds'),
        e('lock.front_door', 'unlocked', friendly_name='Front door'),
        e('vacuum.robot', 'docked', friendly_name='Robot'),
        e('alarm_control_panel.home', 'armed_away', friendly_name='Alarm'),
        e('camera.door', 'idle', friendly_name='Door camera'),
        e('person.owner', 'home', friendly_name='Owner'),
        e('sensor.outside', '21.5', unit_of_measurement='°C', device_class='temperature', friendly_name='Outside'),
    )}


class FakeHA:
    states, calls, ignore_calls, redirect, ignore_fields, delays = {}, [], False, False, (), {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body=None, headers=()):
            raw = json.dumps(body).encode() if body is not None else b''
            self.send_response(code)
            for k, v in headers:
                self.send_header(k, v)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _auth(self):
            if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
                self._send(401, {'message': 'unauthorized'})
                return False
            return True

        def do_GET(self):
            if FakeHA.redirect:
                return self._send(302, {}, (('Location', 'http://example.com/'),))
            if not self._auth():
                return
            if self.path == '/api/':
                return self._send(200, {'message': 'API running.'})
            if self.path == '/api/states':
                return self._send(200, list(FakeHA.states.values()))
            if self.path.startswith('/api/states/'):
                s = FakeHA.states.get(self.path[len('/api/states/'):])
                return self._send(200, s) if s else self._send(404, {'message': 'Entity not found.'})
            self._send(404, {'message': 'not found'})

        def do_POST(self):
            if not self._auth():
                return
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
            _, _, _, domain, service = self.path.split('/')
            FakeHA.calls.append((domain, service, body))
            s = FakeHA.states.get(body.get('entity_id'))
            if s is None:
                return self._send(400, {'message': 'bad entity'})
            if (domain, service) in FakeHA.delays:      # a slow device: the state changes later
                apply = lambda: FakeHA.apply(s, domain, service, body)
                threading.Timer(FakeHA.delays[(domain, service)], apply).start()
            elif not FakeHA.ignore_calls:
                FakeHA.apply(s, domain, service, body)
            self._send(200, [s])

    @staticmethod
    def apply(s, domain, service, body):
            if True:
                a = s['attributes']
                if service == 'turn_on':
                    s['state'] = 'on'
                    if 'brightness_pct' in body and 'brightness' not in FakeHA.ignore_fields:
                        a['brightness'] = round(body['brightness_pct'] * 255 / 100)
                    elif domain == 'light' and not a.get('brightness'):
                        a['brightness'] = 255                       # back on at full brightness, as many bulbs do
                    if 'color_temp_kelvin' in body and 'color' not in FakeHA.ignore_fields:
                        a['color_mode'], a['color_temp_kelvin'] = 'color_temp', body['color_temp_kelvin']
                    if 'hs_color' in body and 'color' not in FakeHA.ignore_fields:
                        a['color_mode'], a['hs_color'] = 'hs', list(body['hs_color'])
                elif service == 'turn_off':
                    s['state'] = 'off'
                    if domain == 'light':                           # like Home Assistant: no brightness while off
                        a['brightness'] = None
                elif service == 'set_temperature':
                    a['temperature'] = body['temperature']
                elif service == 'volume_set':
                    a['volume_level'] = body['volume_level']
                else:
                    s['state'] = {'media_play': 'playing', 'media_pause': 'paused', 'open_cover': 'open', 'close_cover': 'closed',
                                  'lock': 'locked', 'start': 'cleaning', 'return_to_base': 'returning'}.get(service, s['state'])


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), FakeHA.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = 'http://127.0.0.1:%d' % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        FakeHA.states, FakeHA.calls, FakeHA.ignore_calls, FakeHA.redirect = initial_states(), [], False, False
        FakeHA.ignore_fields, FakeHA.delays = (), {}
        HA._sleep = lambda s: None

    def tearDown(self):
        import time
        HA._sleep = time.sleep

    def ha(self, token=TOKEN, **kw):
        kw.setdefault('windows', {})
        return HA.HomeAssistant(self.url, token, poll_s=0.01, verify_s=0.2, **kw)


class Configuration(Base):
    def test_url_rules(self):
        self.assertEqual(HA.validate_url('http://homeassistant.local:8123/'), 'http://homeassistant.local:8123')
        self.assertEqual(HA.validate_url('http://192.168.1.10:8123'), 'http://192.168.1.10:8123')
        self.assertEqual(HA.validate_url('https://ha.example.com'), 'https://ha.example.com')
        self.assertEqual(HA.validate_url('http://100.101.102.103:8123'), 'http://100.101.102.103:8123')   # Tailscale
        self.assertEqual(HA.validate_url('http://homeassistant.tail1234.ts.net:8123'), 'http://homeassistant.tail1234.ts.net:8123')
        for bad in ('http://ha.example.com', 'http://100.128.0.1:8123', 'ftp://192.168.1.10', 'http://user:pw@192.168.1.10', 'http://192.168.1.10/?x=1', ''):
            with self.subTest(bad=bad), self.assertRaises(HA.HABlocked):
                HA.validate_url(bad)

    def test_config_file_and_token_sources(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'home_assistant.json'
            self.assertIsNone(HA.load_config(p))
            HA.save_config('http://192.168.1.10:8123', 'MY_HA_TOKEN', path=p)
            cfg = HA.load_config(p)
            self.assertEqual(cfg, {'url': 'http://192.168.1.10:8123', 'token_env': 'MY_HA_TOKEN'})
            self.assertNotIn('token', p.read_text(encoding='utf-8').replace('token_env', ''))
        vault = SimpleNamespace(get=lambda name: 'from-vault' if name == HA.SECRET_NAME else None)
        self.assertEqual(HA.resolve_token(cfg, vault), 'from-vault')
        import os
        empty = SimpleNamespace(get=lambda name: None)
        os.environ['MY_HA_TOKEN'] = 'from-env'
        try:
            self.assertEqual(HA.resolve_token(cfg, empty), 'from-env')
        finally:
            del os.environ['MY_HA_TOKEN']
        with self.assertRaises(HA.HABlocked):
            HA.HomeAssistant('http://192.168.1.10:8123', None)

    def test_bad_token_and_redirect_refused(self):
        with self.assertRaises(HA.HABlocked):
            self.ha('wrong').ping()
        self.assertEqual(self.ha().ping()['ok'], True)
        FakeHA.redirect = True
        with self.assertRaises(HA.HAError):
            self.ha().ping()


class Bridge(Base):
    def test_listing_excludes_private_domains(self):
        ids = {s['entity_id'] for s in self.ha().states()}
        self.assertIn('light.living_room', ids)
        self.assertNotIn('camera.door', ids)
        self.assertNotIn('person.owner', ids)

    def test_brightness_with_readback_and_exact_undo(self):
        ha = self.ha()
        r = ha.act('light.living_room', 'set_brightness', 80)
        self.assertTrue(r['verified'])
        self.assertEqual(FakeHA.states['light.living_room']['attributes']['brightness'], 204)
        with self.assertRaises(HA.HABlocked):
            ha.act('light.living_room', 'set_brightness', 30)          # one pending Undo per device
        u = ha.undo('light.living_room')
        self.assertTrue(u['exact'])
        self.assertEqual(round(FakeHA.states['light.living_room']['attributes']['brightness'] * 100 / 255), 50)
        with self.assertRaises(HA.HABlocked):
            ha.undo('light.living_room')

    def test_on_off_temperature_and_volume(self):
        ha = self.ha()
        self.assertTrue(ha.act('switch.coffee', 'turn_on')['verified'])
        self.assertTrue(ha.undo('switch.coffee')['exact'])
        self.assertEqual(FakeHA.states['switch.coffee']['state'], 'off')
        self.assertTrue(ha.act('climate.hall', 'set_temperature', 21)['verified'])
        self.assertTrue(ha.undo('climate.hall')['exact'])
        self.assertEqual(FakeHA.states['climate.hall']['attributes']['temperature'], 19.0)
        self.assertTrue(ha.act('media_player.tv', 'set_volume', 35)['verified'])
        self.assertTrue(ha.act('media_player.tv', 'pause')['verified'])

    def test_policy_refusals_happen_before_anything_is_sent(self):
        ha = self.ha()
        for eid, action, value in (('lock.front_door', 'unlock', None), ('cover.garage', 'open', None),
                                   ('alarm_control_panel.home', 'disarm', None), ('light.living_room', 'explode', None),
                                   ('climate.hall', 'set_temperature', 45), ('light.living_room', 'set_brightness', 0),
                                   ('sensor.outside', 'turn_on', None), ('switch.coffee', 'turn_on', 5)):
            with self.subTest(eid=eid, action=action), self.assertRaises(HA.HABlocked):
                ha.act(eid, action, value)
        self.assertEqual(FakeHA.calls, [])
        self.assertIn('never unlocks', HA.policy_refusal('lock', 'unlock'))

    def test_allowed_physical_commands(self):
        ha = self.ha()
        self.assertTrue(ha.act('lock.front_door', 'lock')['verified'])
        self.assertTrue(ha.act('cover.blinds', 'open')['verified'])
        self.assertTrue(ha.act('vacuum.robot', 'return_to_base')['verified'])
        self.assertFalse(ha.act('vacuum.robot', 'start')['reversible'])

    def test_device_that_does_not_react_is_never_reported_done(self):
        FakeHA.ignore_calls = True
        r = self.ha().act('switch.coffee', 'turn_on')
        self.assertIs(r['verified'], False)
        self.assertEqual(r['after'], 'off')


class ExactUndoAndSlowDevices(Base):
    def test_light_undo_restores_brightness_and_colour_temperature(self):
        ha = self.ha()
        self.assertTrue(ha.act('light.desk', 'turn_off')['verified'])
        u = ha.undo('light.desk')
        self.assertTrue(u['exact'])
        a = FakeHA.states['light.desk']['attributes']
        self.assertEqual((FakeHA.states['light.desk']['state'], round(a['brightness'] * 100 / 255), a['color_temp_kelvin']),
                         ('on', 40, 2700))
        self.assertEqual(FakeHA.calls[-1][2], {'entity_id': 'light.desk', 'brightness_pct': 40, 'color_temp_kelvin': 2700})

    def test_light_undo_restores_hue_and_saturation(self):
        ha = self.ha()
        self.assertTrue(ha.act('light.strip', 'set_brightness', 30)['verified'])
        self.assertTrue(ha.undo('light.strip')['exact'])
        self.assertEqual(FakeHA.states['light.strip']['attributes']['hs_color'], [240.0, 80.0])

    def test_undo_that_loses_the_colour_is_not_called_exact(self):
        ha = self.ha()
        self.assertTrue(ha.act('light.desk', 'turn_off')['verified'])
        FakeHA.ignore_fields = ('brightness',)              # the bulb comes back on, but at 100 %
        self.assertFalse(ha.undo('light.desk')['exact'])

    def test_media_player_undo_resumes_playback(self):
        ha = self.ha()
        self.assertTrue(ha.act('media_player.tv', 'turn_off')['verified'])
        u = ha.undo('media_player.tv')
        self.assertTrue(u['exact'])
        self.assertEqual(FakeHA.states['media_player.tv']['state'], 'playing')
        self.assertEqual([c[1] for c in FakeHA.calls[-2:]], ['turn_on', 'media_play'])

    def test_read_back_windows(self):
        ha = HA.HomeAssistant(self.url, TOKEN)
        self.assertEqual(ha.window('switch.coffee', 'turn_on'), 6.0)
        self.assertEqual(ha.window('vacuum.robot', 'start'), 20.0)
        self.assertEqual(ha.window('cover.blinds', 'open'), 60.0)
        slow = HA.HomeAssistant(self.url, TOKEN, latency_hint=lambda eid, act: 14.0 if eid == 'switch.coffee' else None)
        self.assertEqual(slow.window('switch.coffee', 'turn_on'), 29.0)      # 2 x learned p95 + 1
        huge = HA.HomeAssistant(self.url, TOKEN, latency_hint=lambda eid, act: 500)
        self.assertEqual(huge.window('switch.coffee', 'turn_on'), HA.MAX_VERIFY_S)
        broken = HA.HomeAssistant(self.url, TOKEN, latency_hint=lambda eid, act: 1 / 0)
        self.assertEqual(broken.window('switch.coffee', 'turn_on'), 6.0)

    def test_slow_device_is_verified_inside_its_window(self):
        FakeHA.delays = {('vacuum', 'start'): 0.4}
        fast = self.ha().act('vacuum.robot', 'start')
        self.assertIsNot(fast['verified'], True)                          # 0.2 s window: too short
        FakeHA.states = initial_states()
        r = self.ha(windows={('vacuum', 'start'): 2.0}).act('vacuum.robot', 'start')
        self.assertTrue(r['verified'])
        self.assertEqual(r['window_s'], 2.0)

    def test_confirm_reads_again_later(self):
        FakeHA.delays = {('switch', 'turn_on'): 0.3}
        ha = self.ha()
        self.assertIs(ha.act('switch.coffee', 'turn_on')['verified'], False)
        import time
        time.sleep(0.5)
        self.assertTrue(ha.confirm('switch.coffee', 'turn_on')['verified'])


class Fabric(Base):
    def setUp(self):
        super().setUp()
        self.reg, self.bridge = Registry(), self.ha()
        self.assertEqual(ingest_home_assistant(self.reg, self.bridge, b'salt')['status'], 'OK')
        self.keys = {d['ha_entity']: k for k, d in self.reg.devices.items() if d.get('ha_entity')}
        ctx = SimpleNamespace(fabric_registry=self.reg, fabric_snapshot=self.reg.snapshot(),
                              fabric_adapters=lambda p=None: {'home_assistant': self.bridge})
        self.ex = Executor(ctx)

    def test_graph_is_pseudonymized_and_categorized(self):
        snap = self.reg.snapshot()
        self.assertNotIn('light.living_room', json.dumps(snap))
        cats = {self.reg.devices[k]['category'] for k in self.keys.values()}
        self.assertTrue({'light', 'plug', 'thermostat', 'media_player', 'cover', 'lock', 'robot', 'sensor', 'alarm'} <= cats)
        garage = self.reg.devices[self.keys['cover.garage']]
        self.assertEqual([c.status for (n, _), c in garage['capabilities'].items() if n == 'ha_control'], ['BLOCKED'])

    def test_primitives_go_through_consent_readback_and_undo(self):
        key = self.keys['light.living_room']
        self.assertEqual(self.ex.execute('ha_set', key, {'action': 'turn_off'})['state'], 'BLOCKED')     # no consent
        self.assertEqual(FakeHA.calls, [])
        r = self.ex.execute('ha_set', key, {'action': 'turn_off'}, consent=True)
        self.assertEqual((r['state'], r['before'], r['after'], r['verified']), ('VERIFIED', 'on', 'off', True))
        r = self.ex.execute('ha_undo', key, {}, consent=True)
        self.assertEqual((r['state'], r['after']), ('REVERTED', 'on'))
        self.assertEqual(self.ex.execute('read_facts', key, {})['state'], 'VERIFIED')
        r = self.ex.execute('ha_command', self.keys['cover.garage'], {'action': 'open'}, consent=True)
        self.assertEqual(r['state'], 'BLOCKED')
        self.assertIn('Garage', r['errors'][0])
        self.assertEqual(self.ex.execute('ha_command', self.keys['lock.front_door'], {'action': 'lock'}, consent=True)['state'], 'VERIFIED')
        self.assertEqual(self.ex.execute('ha_set', key, {'action': 'unlock'}, consent=True)['state'], 'BLOCKED')   # not in schema


if __name__ == '__main__':
    unittest.main()
