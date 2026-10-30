"""§6 Universal Capability Explorer: live statuses, drafted layouts, follow-ups, rendering."""
import pytest

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


def test_ready_when_probed_supported_and_granted():
    r = X.explore([dev()], links(), {}, probes={'dev-tv': probe_full()},
                  fingerprints={'dev-tv': 'fp-tv'})
    caps = {(c['primitive_id'], c['action'], c.get('args', {}).get('key') or c.get('args', {}).get('setting'))
            for c in r['devices'][0]['capabilities'] if c['status'] == 'READY'}
    assert ('device_action', 'key', 'mute') in caps
    assert ('device_action', 'set', 'screen_brightness') in caps


def test_measured_range_overrides_catalog():
    r = X.explore([dev()], links(), {}, probes={'dev-tv': probe_full()},
                  fingerprints={'dev-tv': 'fp-tv'})
    vol = next(c for c in r['devices'][0]['capabilities']
               if c['action'] == 'set' and c['args'].get('setting') == 'media_volume')
    assert vol['range'] == [0, 25]
    assert vol['widget'] == 'slider'


def test_requires_permission_when_control_missing():
    r = X.explore([dev()], links(('read',)), {}, probes={'dev-tv': probe_full()},
                  fingerprints={'dev-tv': 'fp-tv'})
    mute = next(c for c in r['devices'][0]['capabilities'] if c['args'].get('key') == 'mute')
    assert mute['status'] == 'REQUIRES_PERMISSION'
    assert mute['requires'] == ['control']
    st = next(c for c in r['devices'][0]['capabilities'] if c['action'] == 'screen_state')
    assert st['status'] == 'READY'


def test_discoverable_when_unprobed_never_ready():
    r = X.explore([dev()], links(), {}, probes={}, fingerprints={'dev-tv': 'fp-tv'})
    by_status = {}
    for c in r['devices'][0]['capabilities']:
        by_status.setdefault(c['status'], 0)
        by_status[c['status']] += 1
    assert by_status.get('READY', 0) == 1  # only the probe action itself
    assert by_status.get('DISCOVERABLE', 0) > 10
    only_ready = [c for c in r['devices'][0]['capabilities'] if c['status'] == 'READY']
    assert only_ready[0]['primitive_id'] == 'device_capabilities'


def test_unsupported_tv_only_key_on_phone():
    r = X.explore([dev('dev-ph', 'phone', 'Phone')], [{'child': 'dev-ph', 'grants': ['read', 'control'], 'transport': 'USB'}],
                  {}, probes={'dev-ph': dict(probe_full(), category='phone')},
                  fingerprints={'dev-ph': 'fp-ph'})
    assert r['devices'][0]['category'] == 'phone'
    assert not any(c['args'].get('key') == 'channel_up' and c['status'] == 'READY'
                   for c in r['devices'][0]['capabilities'])


def test_offline_when_no_link():
    r = X.explore([dev()], [], {}, probes={'dev-tv': probe_full()}, fingerprints={'dev-tv': 'fp-tv'})
    assert r['devices'][0]['online'] is False
    assert {c['status'] for c in r['devices'][0]['capabilities']} == {'OFFLINE'}


def test_registry_only_device_is_offline():
    r = X.explore([], [], {}, registry=[{'key': 'dev-old', 'category': 'watch', 'label': 'Old watch'}])
    assert r['devices'][0]['online'] is False
    assert all(c['status'] == 'OFFLINE' for c in r['devices'][0]['capabilities'])


def test_error_when_write_blocked():
    r = X.explore([dev()], links(), {}, probes={'dev-tv': probe_full()},
                  fingerprints={'dev-tv': 'fp-tv'},
                  blocked={'dev-tv': ['blocked by policy']})
    mute = next(c for c in r['devices'][0]['capabilities'] if c['args'].get('key') == 'mute')
    assert mute['status'] == 'ERROR'
    assert 'blocked by policy' in mute['reason']


def test_vacuum_commands_listed_with_model_table_evidence():
    vac = dev('dev-vac', 'vacuum', 'Vacuum')
    r = X.explore([vac], [{'child': 'dev-vac', 'grants': ['read', 'control'], 'transport': 'LAN'}],
                  {}, fingerprints={'dev-vac': 'fp-vac'})
    dock = next(c for c in r['devices'][0]['capabilities'] if c['args'].get('command') == 'dock')
    assert dock['status'] == 'READY'
    assert dock['evidence'] == 'model-table'
    assert dock['label'] == 'Return to Dock'


def test_draft_layout_groups_and_skips_unusable():
    r = X.explore([dev()], links(('read',)), {}, probes={'dev-tv': probe_full()},
                  fingerprints={'dev-tv': 'fp-tv'})
    layout = X.draft_layout(r, name='TV')
    kinds = [w['kind'] for w in layout['widgets']]
    assert kinds[0] == 'card'
    assert layout['origin'] == 'rules'
    assert layout['version'] == 1
    X.validate_layout(layout)


def test_validate_layout_rejects_bad_binding():
    with pytest.raises(X.ExplorerError):
        X.validate_layout({'schema_version': 1, 'name': 'x', 'version': 1, 'origin': 'rules',
                           'widgets': [{'kind': 'button'}]})
    with pytest.raises(X.ExplorerError):
        X.validate_layout({'schema_version': 99, 'name': 'x', 'version': 1, 'origin': 'rules', 'widgets': []})


def test_followup_add_remove_keep():
    r = X.explore([dev()], links(), {}, probes={'dev-tv': probe_full()}, fingerprints={'dev-tv': 'fp-tv'})
    layout = X.draft_layout(r, name='TV')
    n0 = len(layout['widgets'])
    l2 = X.followup(layout, 'keep_only', {'match': 'volume'}, expected_version=1)
    assert l2['version'] == 2
    assert 0 < len(l2['widgets']) < n0
    assert all('volume' in w['label'].lower() or w['kind'] == 'card' for w in l2['widgets'])
    wid = next(w['widget_id'] for w in l2['widgets'] if w['kind'] != 'card')
    l3 = X.followup(l2, 'remove_widget', {'widget_id': wid}, expected_version=2)
    assert len(l3['widgets']) == len(l2['widgets']) - 1
    with pytest.raises(X.ExplorerError):
        X.followup(l3, 'clear', {}, expected_version=2)


def test_parse_followup_utterances():
    op, args = X.parse_followup('remove everything except volume')
    assert op == 'keep_only' and args == {'match': 'volume'}
    op, args = X.parse_followup('add vacuum Return to Dock')
    assert op == 'add_capability' and args['match'] == 'vacuum return to dock'
    op, args = X.parse_followup('remove the shutdown button')
    assert op == 'remove_match' and args['match'] == 'shutdown'
    with pytest.raises(X.ExplorerError):
        X.parse_followup('please kindly consider the cinematography')


def test_render_resolves_live_status_and_stale():
    r = X.explore([dev()], links(), {}, probes={'dev-tv': probe_full()}, fingerprints={'dev-tv': 'fp-tv'})
    layout = X.draft_layout(r, name='TV')
    rendered = X.render_layout(layout, r)
    assert any(w['enabled'] and w['status'] == 'READY' for w in rendered['widgets'] if w['kind'] == 'button')
    assert all(w.get('device_key') == 'dev-tv' for w in rendered['widgets'] if w['kind'] == 'button')
    # Revoke control -> the SAME saved buttons become unusable.
    r2 = X.explore([dev()], links(('read',)), {}, probes={'dev-tv': probe_full()},
                   fingerprints={'dev-tv': 'fp-tv'})
    rendered2 = X.render_layout(layout, r2)
    assert not any(w['enabled'] for w in rendered2['widgets'] if w['kind'] == 'button'
                   and w.get('requires') == ['control'])
    # Unknown fingerprint -> stale, disabled, never executed.
    layout['widgets'].append({'widget_id': 'w-ghost', 'kind': 'button', 'label': 'Ghost',
                              'capability_id': 'fp-nope:device_action:key', 'device_fingerprint': 'fp-nope',
                              'primitive_id': 'device_action', 'action': 'key',
                              'args': {'key': 'mute'}})
    rendered3 = X.render_layout(layout, r2)
    ghost = next(w for w in rendered3['widgets'] if w['widget_id'] == 'w-ghost')
    assert ghost['status'] == 'OFFLINE' and ghost['enabled'] is False and ghost['stale'] is True
    assert 'device_key' not in ghost
