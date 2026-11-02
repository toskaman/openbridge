"""Voice -> watch button layout (opt-in): match, Meta propose/apply, drain hook. Doubles only."""
import json
import re
import unittest

from src.forge import v4_schemas as S
from src.runtime import voice_layout as L
from tests.runtime.test_command_drain import RID, FakeRelay, make_server, text_cmd


class FakeRC:
    def __init__(self):
        self.calls = []

    def set_controls(self, body):
        self.calls.append(body)
        return {'controls': []}


def layout_server(fake, caps=('command_submit', 'remote_controls')):
    s = make_server(fake, caps=caps)
    s.remote_controls = FakeRC()
    s.skill_router = type('R', (), {'resolve_target': staticmethod(lambda t: t)})()
    s.fabric_snapshot = {'devices': [{'key': 'dev-tv', 'label': 'Android TV', 'category': 'tv',
                                      'facts': {'mdns_services': {'value': ['_openbridge-relay._tcp']}}},
                                     {'key': 'dev-tv2', 'label': 'LG TV', 'category': 'tv'},
                                     {'key': 'dev-watch', 'label': 'Galaxy Watch7', 'category': 'watch'}]}
    return s


def meta(reply_fn):
    """Fake pinned Meta transport: reply_fn(prompt, first_offered_opaque_id) -> dict reply."""
    calls = []

    def run(prompt):
        calls.append(prompt)
        ids = re.findall(r'opaque:[0-9a-f]{16}', prompt)
        return {'content': json.dumps(reply_fn(prompt, ids[0] if ids else None))}
    run.calls = calls
    return run


def proposal(target, widgets=(('Vol +', 'up'), ('Vol -', 'down'))):
    return {'outcome': 'proposal', 'patch': {
        'schema_version': S.SCHEMA_VERSION, 'patch_id': 'p-1', 'target_opaque_id': target,
        'origin': 'meta_generated', 'model_run_id': 'mr-1',
        'widgets': [{'widget_id': 'w-%d' % i, 'kind': 'button', 'label': lab,
                     'binding_primitive': 'tv_volume_step', 'params': {'direction': d}}
                    for i, (lab, d) in enumerate(widgets)]}}


class MatchTests(unittest.TestCase):
    def test_create_including_observed_stt_errors(self):
        for t in ('mets les boutons de volume sur la montre', 'mas les boutons de volume sur la tellée',
                  'mais les boutons de volume sur la tellée', 'crée le menu volume télé',
                  'crée un menu pour la télé', 'add the volume buttons'):
            self.assertEqual(L.match(t, 'fr')['op'], 'create', t)

    def test_remove(self):
        for t in ('enlève les boutons', 'retire les menus de la montre', 'remove the buttons'):
            self.assertEqual(L.match(t, 'fr')['op'], 'remove', t)

    def test_ambiguous_fails_closed(self):
        m = L.match('enlève les boutons de volumes de la montre et met les bouton', 'fr')
        self.assertEqual((m['op'], m['why']), ('clarify', 'both'))

    def test_not_layout_never_matches(self):
        for t in ('appuie sur volume plus', 'appuie sur le bouton volume', 'quelle heure est-il',
                  'mais pourquoi', 'allume la lampe du salon', ''):
            self.assertIsNone(L.match(t, 'fr'), t)


class ApplyTests(unittest.TestCase):
    def _create(self, s, reply_fn, text='mets les boutons volume télé'):
        m = dict(L.match(text, 'fr'), text=text)
        t = meta(reply_fn)
        return L.apply(s, RID, s.relays.relays[RID], m, transport=t), t

    def test_meta_proposal_installs_on_speaking_relay(self):
        s = layout_server(FakeRelay())
        (st, txt), t = self._create(s, lambda p, oid: proposal(oid))
        self.assertEqual(st, 'resolved')
        self.assertIn('Meta', txt)
        self.assertEqual(len(t.calls), 1)
        self.assertIn('mets les boutons volume', t.calls[0])          # the transcript reached Meta
        (body,) = s.remote_controls.calls
        self.assertEqual(body['relay_id'], RID)
        self.assertIs(body['consent'], True)
        self.assertEqual([(c['label'], c['target'], c['params']['direction']) for c in body['controls']],
                         [('Vol +', 'dev-tv', 'up'), ('Vol -', 'dev-tv', 'down')])

    def test_meta_non_proposals_install_nothing(self):
        replies = [lambda p, oid: {'outcome': 'refusal', 'reason': 'not offered'},
                   lambda p, oid: {'outcome': 'clarification', 'clarifying_question': 'Which TV?'},
                   lambda p, oid: proposal('opaque:' + 'f' * 16),                 # hallucinated target
                   lambda p, oid: {'outcome': 'proposal', 'patch': {'widgets': []}},  # bad schema
                   lambda p, oid: {'outcome': 'proposal', 'patch': dict(
                       proposal(oid)['patch'], widgets=[{'widget_id': 'w', 'kind': 'button', 'label': 'x',
                                                         'binding_primitive': 'shell_exec', 'params': {}}])}]
        for fn in replies:
            s = layout_server(FakeRelay())
            (st, _), _ = self._create(s, fn)
            self.assertNotEqual(st, 'resolved')
            self.assertEqual(s.remote_controls.calls, [])

    def test_remove_is_deterministic_no_model(self):
        s = layout_server(FakeRelay())
        t = meta(lambda p, oid: self.fail('model must not be called'))
        st, _ = L.apply(s, RID, s.relays.relays[RID], L.match('enlève les boutons', 'fr'), transport=t)
        self.assertEqual(st, 'resolved')
        self.assertEqual(s.remote_controls.calls, [{'relay_id': RID, 'controls': [], 'consent': True}])
        self.assertEqual(t.calls, [])

    def test_one_self_correction_then_install(self):
        s = layout_server(FakeRelay())
        n = []

        def fn(p, oid):
            n.append(p)
            if len(n) == 1:
                bad = proposal(oid)
                bad['patch']['reason'] = 'extra key'
                return bad
            assert 'REJECTED by the validator with: PATCH_SHAPE' in p
            return proposal(oid)
        (st, _), t = self._create(s, fn)
        self.assertEqual((st, len(t.calls)), ('resolved', 2))
        self.assertEqual(len(s.remote_controls.calls), 1)

    def test_offer_is_scoped_to_tv_and_vacuum(self):
        s = layout_server(FakeRelay())
        s.fabric_snapshot['devices'].append({'key': 'dev-vac', 'label': 'Robot vacuum', 'category': 'vacuum'})
        s.fabric_snapshot['devices'].append({'key': 'dev-pc', 'label': 'PC', 'category': 'pc'})
        (st, _), t = self._create(s, lambda p, oid: proposal(oid))
        self.assertIn('Robot vacuum', t.calls[0])
        for absent in ('LG TV', 'Galaxy Watch7', '- PC', 'pc_wallpaper', 'file_push'):
            self.assertNotIn(absent, t.calls[0])

    def test_relay_without_remote_controls_refused(self):
        s = layout_server(FakeRelay(), caps=('command_submit',))
        (st, _), t = self._create(s, lambda p, oid: proposal(oid))
        self.assertEqual(st, 'unsupported')
        self.assertEqual((s.remote_controls.calls, t.calls), ([], []))


class SemanticGuardTests(unittest.TestCase):
    W = staticmethod(lambda l, p, d: {'label': l, 'binding_primitive': p, 'params': d})

    def test_honest_labels_pass(self):
        W = self.W
        self.assertIsNone(L.label_check([W('Volume +', 'tv_volume_step', {'direction': 'up'}),
                                         W('Baisser le son', 'tv_volume_step', {'direction': 'down'}),
                                         W('Volume 20', 'tv_volume_set', {'value': 20}), W('TV sleep', 'tv_sleep', {})]))

    def test_lying_labels_rejected(self):
        W = self.W
        for ws in ([W('Volume up', 'tv_volume_set', {'value': 1})], [W('Mute', 'tv_sleep', {})],
                   [W('Volume down', 'tv_volume_step', {'direction': 'up'})]):
            self.assertTrue(L.label_check(ws).startswith('LABEL_MISMATCH'), ws)

    def test_lying_proposal_is_retried_then_refused(self):
        s = layout_server(FakeRelay())
        m = dict(L.match('mets les boutons volume', 'fr'), text='mets les boutons volume')
        t = meta(lambda p, oid: proposal(oid, widgets=(('Mute', 'up'),)))
        st, _ = L.apply(s, RID, s.relays.relays[RID], m, transport=t)
        self.assertNotEqual(st, 'resolved')
        self.assertEqual((len(t.calls), s.remote_controls.calls), (2, []))
        self.assertIn('LABEL_MISMATCH', t.calls[1])

    def test_schema_pins_offered_ids_and_typed_params(self):
        sch = L.response_schema(['opaque:aa'], ('tv_volume_step', 'tv_volume_set'))
        patch = sch['properties']['patch']['properties']
        self.assertEqual(patch['target_opaque_id']['enum'], ['opaque:aa'])
        v = patch['widgets']['items']['anyOf']
        self.assertEqual([x['properties']['binding_primitive']['enum'] for x in v],
                         [['tv_volume_step'], ['tv_volume_set']])
        self.assertEqual(v[1]['properties']['params']['properties']['value']['type'], 'integer')


class DrainHookTests(unittest.TestCase):
    def test_off_by_default_reports_only(self):
        from src.runtime import command_drain as D
        fake = FakeRelay([text_cmd('enlève les boutons')])
        s = layout_server(fake)
        D.poll_once(s, parse_fn=lambda srv, b: {'intent': {'status': 'unsupported', 'ambiguities': ['x']}},
                    sync=True)
        self.assertEqual(s.remote_controls.calls, [])
        self.assertEqual(fake.reports[0][1], 'unsupported')

    def test_enabled_meta_creates_then_voice_removes(self):
        from src.runtime import command_drain as D
        fake = FakeRelay([text_cmd('mets les boutons de volume sur la télé'), text_cmd('allume la lampe')])
        s = layout_server(fake)
        L.enable(s, transport=meta(lambda p, oid: proposal(oid)))
        D.poll_once(s, parse_fn=lambda srv, b: {'intent': {'status': 'resolved', 'outcome': 'parsed'}},
                    sync=True)
        self.assertEqual(len(s.remote_controls.calls), 1)
        self.assertEqual([r[1] for r in fake.reports], ['resolved', 'resolved'])
        self.assertIn('Meta', fake.reports[0][2])
        self.assertEqual(fake.reports[1][2], 'parsed')   # non-layout orders still go to the parser
        fake.commands = [text_cmd('enlève les boutons')]
        D.poll_once(s, sync=True)
        self.assertEqual(s.remote_controls.calls[-1]['controls'], [])


if __name__ == '__main__':
    unittest.main()
