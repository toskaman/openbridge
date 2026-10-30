"""§6 explorer API: explore/layouts/render/followup over a fake live graph."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.fabric.registry import Registry
from src.runtime import api_v2


def snap(grants=('read', 'control')):
    return {'devices': [{'key': 'dev-tv', 'category': 'tv', 'label': 'TV',
                         'capabilities': [{'name': 'inspect', 'status': 'REAL_HARDWARE_VERIFIED',
                                           'level': 'read'}]}],
            'links': [{'child': 'dev-tv', 'grants': list(grants), 'transport': 'WIFI', 'source': 'adb'}]}


def srv(snapshot, probes=None, tmp='.'):
    reg = Registry()
    for d in (snapshot or {}).get('devices', []):
        reg.devices[d['key']] = {'key': d['key'], 'category': d['category'], 'label': d['label']}
    return SimpleNamespace(fabric_snapshot=snapshot, fabric_registry=reg,
                           runtime_executor=SimpleNamespace(probes=dict(probes or {})),
                           session_journal=SimpleNamespace(path=str(Path(tmp) / 'sess.sqlite')))


PROBE = {'category': 'tv', 'actions': {'key': ['mute'], 'set:screen_brightness': True,
        'audio_state': True, 'screen_state': True, 'list_apps': True, 'text': True,
        'tap': True, 'swipe': True, 'long_press': True, 'launch_app': True,
        'open_url': True}, 'ranges': {}}


class Explore(unittest.TestCase):
    def test_lists_statuses_unprobed(self):
        code, body = api_v2.get(srv(snap()), '/api/v2/capabilities/explore', '')
        self.assertEqual(code, 200)
        caps = body['devices'][0]['capabilities']
        by_action = {}
        for c in caps:
            by_action.setdefault((c['primitive_id'], c['action']), c['status'])
        self.assertEqual(by_action[('device_capabilities', 'probe')], 'READY')
        self.assertEqual(by_action[('device_action', 'key')], 'DISCOVERABLE')
        self.assertTrue(any(c['args'].get('key') == 'channel_up' for c in caps))

    def test_filters_device(self):
        code, body = api_v2.get(srv(snap()), '/api/v2/capabilities/explore', 'device=dev-tv')
        self.assertEqual((code, len(body['devices'])), (200, 1))
        code, body = api_v2.get(srv(snap()), '/api/v2/capabilities/explore', 'device=nope')
        self.assertEqual((code, body['devices']), (200, []))

    def test_probed_key_ready(self):
        code, body = api_v2.get(srv(snap(), {'dev-tv': PROBE}), '/api/v2/capabilities/explore', '')
        mute = next(c for c in body['devices'][0]['capabilities'] if c['args'].get('key') == 'mute')
        self.assertEqual(mute['status'], 'READY')
        self.assertTrue(mute['effect'])
        probe = next(c for c in body['devices'][0]['capabilities']
                     if c['primitive_id'] == 'device_capabilities')
        self.assertFalse(probe['effect'])

    def test_no_graph_409(self):
        code, body = api_v2.get(srv(None), '/api/v2/capabilities/explore', '')
        self.assertEqual(code, 409)


class Layouts(unittest.TestCase):
    def test_save_list_render(self):
        with tempfile.TemporaryDirectory() as d:
            s = srv(snap(), {'dev-tv': PROBE}, d)
            code, saved = api_v2.post(s, '/api/v2/capabilities/layouts', {'draft': True, 'name': 'TV'})
            self.assertEqual(code, 200)
            self.assertTrue(saved['layout_id'].startswith('lay-'))
            self.assertEqual(saved['version'], 1)
            code, listed = api_v2.get(s, '/api/v2/capabilities/layouts', '')
            self.assertEqual([l['layout_id'] for l in listed['layouts']], [saved['layout_id']])
            code, rendered = api_v2.get(s, '/api/v2/capabilities/render', 'layout=' + saved['layout_id'])
            self.assertEqual(code, 200)
            mute = next(w for w in rendered['widgets'] if w.get('args', {}).get('key') == 'mute')
            self.assertEqual((mute['status'], mute['enabled']), ('READY', True))

    def test_save_rejects_bad_widgets(self):
        with tempfile.TemporaryDirectory() as d:
            code, body = api_v2.post(srv(snap(), tmp=d), '/api/v2/capabilities/layouts',
                                     {'name': 'x', 'widgets': [{'kind': 'button'}]})
            self.assertEqual(code, 400)

    def test_render_after_revoke_disables(self):
        with tempfile.TemporaryDirectory() as d:
            s = srv(snap(), {'dev-tv': PROBE}, d)
            _, saved = api_v2.post(s, '/api/v2/capabilities/layouts', {'draft': True, 'name': 'TV'})
            s.fabric_snapshot['links'][0]['grants'] = ['read']
            _, rendered = api_v2.get(s, '/api/v2/capabilities/render', 'layout=' + saved['layout_id'])
            mute = next(w for w in rendered['widgets'] if w.get('args', {}).get('key') == 'mute')
            self.assertEqual((mute['status'], mute['enabled']), ('REQUIRES_PERMISSION', False))

    def test_unknown_layout_404(self):
        with tempfile.TemporaryDirectory() as d:
            s = srv(snap(), tmp=d)
            code, _ = api_v2.get(s, '/api/v2/capabilities/render', 'layout=lay-deadbeef')
            self.assertEqual(code, 404)
            code, _ = api_v2.post(s, '/api/v2/capabilities/followup',
                                  {'layout_id': 'lay-deadbeef', 'op': 'clear', 'expected_version': 1})
            self.assertEqual(code, 404)

    def test_followup_text_and_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            s = srv(snap(), {'dev-tv': PROBE}, d)
            _, saved = api_v2.post(s, '/api/v2/capabilities/layouts', {'draft': True, 'name': 'TV'})
            code, out = api_v2.post(s, '/api/v2/capabilities/followup',
                                    {'layout_id': saved['layout_id'],
                                     'text': 'remove everything except support', 'expected_version': 1})
            self.assertEqual(code, 200)
            self.assertEqual(out['version'], 2)
            labels = [w['label'] for w in out['widgets']]
            self.assertIn('Measure support', labels)
            self.assertNotIn('Mute', labels)
            code, _ = api_v2.post(s, '/api/v2/capabilities/followup',
                                  {'layout_id': saved['layout_id'], 'op': 'clear', 'expected_version': 1})
            self.assertEqual(code, 409)
