"""§6 Universal Capability Explorer: live statuses, drafted layouts, follow-ups, rendering."""
import unittest

from src.fabric import capability_explorer as X


def dev(key='dev-tv', category='tv', label='TV'):
    return {'key': key, 'category': category, 'label': label}


def links(grants=('read', 'control')):
    return [{'child': 'dev-tv', 'grants': list(grants), 'transport': 'WIFI'}]


def probe_full():
    return {'category': 'tv',
            'actions': {'set:screen_brightness': True, 'set:media_volume': True,
                        'key': ['mute', 'volume_up'], 'text': True, 'tap': True, 'swipe': True,
                        'long_press': True, 'launch_app': True, 'open_url': True,
                        'list_apps': True, 'screen_state': True, 'audio_state': True},
            'ranges': {'media_volume': [0, 25]}}


class Statuses(unittest.TestCase):
    def test_ready_when_probed_supported_and_granted(self):
        r = X.explore([dev()], links(), {}, probes={'dev-tv': probe_full()},
                      fingerprints={'dev-tv': 'fp-tv'})
        caps = {(c['primitive_id'], c['action'], c.get('args', {}).get('key') or c.get('args', {}).get('setting'))
                for c in r['devices'][0]['capabilities'] if c['status'] == 'READY'}
        self.assertIn(('device_action', 'key', 'mute'), caps)
        self.assertIn(('device_action', 'set', 'screen_brightness'), caps)

    def test_measured_range_overrides_catalog(self):
        r = X.explore([dev()], links(), {}, probes={'dev-tv': probe_full()},
                      fingerprints={'dev-tv': 'fp-tv'})
        vol = next(c for c in r['devices'][0]['capabilities']
                   if c['action'] == 'set' and c['args'].get('setting') == 'media_volume')
        self.assertEqual(vol['range'], [0, 25])
        self.assertEqual(vol['widget'], 'slider')

    def test_requires_permission_when_control_missing(self):
        r = X.explore([dev()], links(('read',)), {}, probes={'dev-tv': probe_full()},
                      fingerprints={'dev-tv': 'fp-tv'})
        mute = next(c for c in r['devices'][0]['capabilities'] if c['args'].get('key') == 'mute')
        self.assertEqual(mute['status'], 'REQUIRES_PERMISSION')
        self.assertEqual(mute['requires'], ['control'])
        st = next(c for c in r['devices'][0]['capabilities'] if c['action'] == 'screen_state')
        self.assertEqual(st['status'], 'READY')

    def test_discoverable_when_unprobed_never_ready(self):
        r = X.explore([dev()], links(), {}, probes={}, fingerprints={'dev-tv': 'fp-tv'})
        by_status = {}
        for c in r['devices'][0]['capabilities']:
            by_status[c['status']] = by_status.get(c['status'], 0) + 1
        self.assertEqual(by_status.get('READY', 0), 1)
        self.assertGreater(by_status.get('DISCOVERABLE', 0), 10)
        only_ready = [c for c in r['devices'][0]['capabilities'] if c['status'] == 'READY']
        self.assertEqual(only_ready[0]['primitive_id'], 'device_capabilities')

    def test_unsupported_tv_only_key_on_phone(self):
        r = X.explore([dev('dev-ph', 'phone', 'Phone')],
                      [{'child': 'dev-ph', 'grants': ['read', 'control'], 'transport': 'USB'}],
                      {}, probes={'dev-ph': dict(probe_full(), category='phone')},
                      fingerprints={'dev-ph': 'fp-ph'})
        self.assertEqual(r['devices'][0]['category'], 'phone')
        self.assertFalse(any(c['args'].get('key') == 'channel_up' and c['status'] == 'READY'
                             for c in r['devices'][0]['capabilities']))

    def test_offline_when_no_link(self):
        r = X.explore([dev()], [], {}, probes={'dev-tv': probe_full()}, fingerprints={'dev-tv': 'fp-tv'})
        self.assertFalse(r['devices'][0]['online'])
        self.assertEqual({c['status'] for c in r['devices'][0]['capabilities']}, {'OFFLINE'})

    def test_registry_only_device_is_offline(self):
        r = X.explore([], [], {}, registry=[{'key': 'dev-old', 'category': 'watch', 'label': 'Old watch'}])
        self.assertFalse(r['devices'][0]['online'])
        self.assertTrue(all(c['status'] == 'OFFLINE' for c in r['devices'][0]['capabilities']))

    def test_error_when_write_blocked(self):
        r = X.explore([dev()], links(), {}, probes={'dev-tv': probe_full()},
                      fingerprints={'dev-tv': 'fp-tv'},
                      blocked={'dev-tv': ['blocked by policy']})
        mute = next(c for c in r['devices'][0]['capabilities'] if c['args'].get('key') == 'mute')
        self.assertEqual(mute['status'], 'ERROR')
        self.assertIn('blocked by policy', mute['reason'])

    def test_vacuum_commands_listed_with_model_table_evidence(self):
        vac = dev('dev-vac', 'vacuum', 'Vacuum')
        r = X.explore([vac], [{'child': 'dev-vac', 'grants': ['read', 'control'], 'transport': 'LAN'}],
                      {}, fingerprints={'dev-vac': 'fp-vac'})
        dock = next(c for c in r['devices'][0]['capabilities'] if c['args'].get('command') == 'dock')
        self.assertEqual(dock['status'], 'READY')
        self.assertEqual(dock['evidence'], 'model-table')
        self.assertEqual(dock['label'], 'Return to Dock')


class Layouts(unittest.TestCase):
    def test_draft_layout_groups_and_skips_unusable(self):
        r = X.explore([dev()], links(('read',)), {}, probes={'dev-tv': probe_full()},
                      fingerprints={'dev-tv': 'fp-tv'})
        layout = X.draft_layout(r, name='TV')
        kinds = [w['kind'] for w in layout['widgets']]
        self.assertEqual(kinds[0], 'card')
        self.assertEqual(layout['origin'], 'rules')
        self.assertEqual(layout['version'], 1)
        X.validate_layout(layout)

    def test_validate_layout_rejects_bad_binding(self):
        with self.assertRaises(X.ExplorerError):
            X.validate_layout({'schema_version': 1, 'name': 'x', 'version': 1, 'origin': 'rules',
                               'widgets': [{'kind': 'button'}]})
        with self.assertRaises(X.ExplorerError):
            X.validate_layout({'schema_version': 99, 'name': 'x', 'version': 1, 'origin': 'rules', 'widgets': []})

    def test_followup_add_remove_keep(self):
        r = X.explore([dev()], links(), {}, probes={'dev-tv': probe_full()}, fingerprints={'dev-tv': 'fp-tv'})
        layout = X.draft_layout(r, name='TV')
        n0 = len(layout['widgets'])
        l2 = X.followup(layout, 'keep_only', {'match': 'volume'}, expected_version=1)
        self.assertEqual(l2['version'], 2)
        self.assertTrue(0 < len(l2['widgets']) < n0)
        self.assertTrue(all('volume' in w['label'].lower() or w['kind'] == 'card' for w in l2['widgets']))
        wid = next(w['widget_id'] for w in l2['widgets'] if w['kind'] != 'card')
        l3 = X.followup(l2, 'remove_widget', {'widget_id': wid}, expected_version=2)
        self.assertEqual(len(l3['widgets']), len(l2['widgets']) - 1)
        with self.assertRaises(X.ExplorerError):
            X.followup(l3, 'clear', {}, expected_version=2)

    def test_parse_followup_utterances(self):
        op, args = X.parse_followup('remove everything except volume')
        self.assertEqual((op, args), ('keep_only', {'match': 'volume'}))
        op, args = X.parse_followup('add vacuum Return to Dock')
        self.assertEqual((op, args), ('add_capability', {'match': 'vacuum return to dock'}))
        op, args = X.parse_followup('remove the shutdown button')
        self.assertEqual((op, args), ('remove_match', {'match': 'shutdown'}))
        with self.assertRaises(X.ExplorerError):
            X.parse_followup('please kindly consider the cinematography')

    def test_render_resolves_live_status_and_stale(self):
        r = X.explore([dev()], links(), {}, probes={'dev-tv': probe_full()}, fingerprints={'dev-tv': 'fp-tv'})
        layout = X.draft_layout(r, name='TV')
        rendered = X.render_layout(layout, r)
        self.assertTrue(any(w['enabled'] and w['status'] == 'READY' for w in rendered['widgets'] if w['kind'] == 'button'))
        self.assertTrue(all(w.get('device_key') == 'dev-tv' for w in rendered['widgets'] if w['kind'] == 'button'))
        r2 = X.explore([dev()], links(('read',)), {}, probes={'dev-tv': probe_full()},
                       fingerprints={'dev-tv': 'fp-tv'})
        rendered2 = X.render_layout(layout, r2)
        self.assertFalse(any(w['enabled'] for w in rendered2['widgets'] if w['kind'] == 'button'
                             and w.get('requires') == ['control']))
        layout['widgets'].append({'widget_id': 'w-ghost', 'kind': 'button', 'label': 'Ghost',
                                  'capability_id': 'fp-nope:device_action:key', 'device_fingerprint': 'fp-nope',
                                  'primitive_id': 'device_action', 'action': 'key',
                                  'args': {'key': 'mute'}})
        rendered3 = X.render_layout(layout, r2)
        ghost = next(w for w in rendered3['widgets'] if w['widget_id'] == 'w-ghost')
        self.assertEqual((ghost['status'], ghost['enabled'], ghost['stale']), ('OFFLINE', False, True))
        self.assertNotIn('device_key', ghost)
