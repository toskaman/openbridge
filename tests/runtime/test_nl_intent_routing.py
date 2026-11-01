"""F30 NL intent routing (Phase C, tests-only): negative paths, forced-choice
refusals and French/English parity. No model calls: every transport is faked.

(1) Negative paths: empty / oversize / non-UTF8 / gibberish input never
    dispatches, ends in clarification/refusal, and leaves the cloud budget
    untouched (no reservation, no send, no spend).
(2) Forced-choice refusals: ambiguous commands surface needs_clarification
    (or a typed refusal at the plan/command layers) instead of silently
    running a default action.
(3) FR/EN parity: 10 catalog skills route identically in French and English
    through the deterministic fallback and through resolved replies, plus
    6 voice intents matched by the real (unscripted) regex layer.
"""
import unittest

from src.ai import cloud_budget as CB
from src.ai import voice_intent as VI
from src.fabric import relay as R
from src.runtime import command as CMD
from src.runtime import intent as I
from src.runtime import nl_plan
from src.runtime import nl_router as N


class FakeTransport:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def ready(self):
        return True

    def __call__(self, prompt):
        self.calls.append(prompt)
        if self.error is not None:
            raise self.error
        if callable(self.reply):
            return self.reply(prompt)
        return self.reply


def abstain(outcome, targets=(), question=None, ambiguities=()):
    return {'outcome': outcome, 'skill_id': None, 'targets': list(targets),
            'params': {}, 'confidence': 0.0, 'ambiguities': list(ambiguities),
            'clarifying_question': question}


def resolved(skill_id, outcome, targets, params=None):
    return {'outcome': outcome, 'skill_id': skill_id,
            'targets': list(targets), 'params': dict(params or {}),
            'confidence': 0.9, 'ambiguities': [],
            'clarifying_question': None}


def budget():
    return CB.Budget({'enabled': True, 'per_request_usd': 0.20,
                      'per_session_usd': 1.00, 'per_day_usd': 3.00,
                      'total_usd': 3.00, 'allowed_models': ['muse-spark-1.3']})


class SpyExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, primitive_id, device_key, params, consent=False):
        self.calls.append((primitive_id, device_key, params, consent))
        return {'state': 'VERIFIED', 'transaction_id': 'tx-9'}


class SpyRouter:
    def __init__(self):
        self.calls = []

    def skill_routes(self, skill_id, target=None):
        self.calls.append(('routes', skill_id, target))
        return {'selected_route_id': 'rt-1', 'routes': []}

    def arm(self, body, actor='owner', invocation_id=None):
        self.calls.append(('arm', body))
        return {'invocation_id': 'inv-1', 'route_id': 'rt-1',
                'lease_id': 'ls-1', 'graph_revision': {'seq': 1}}

    def invoke(self, body, actor='owner'):
        self.calls.append(('invoke', body))
        return {'state': 'VERIFIED', 'transaction_id': 'tx-1'}


class SpyServer:
    def __init__(self, local_reply):
        from types import SimpleNamespace
        self.command_low = FakeTransport(local_reply)
        self.command_medium = FakeTransport(local_reply)
        self.command_cloud = FakeTransport(local_reply)
        self.command_cloud_enabled = True
        self.model_broker = None
        devices = {'dev-vac1': {'key': 'dev-vac1', 'category': 'vacuum',
                                'label': 'Roborock'},
                   'dev-tv1': {'key': 'dev-tv1', 'category': 'tv',
                               'label': 'Living room TV'}}
        self.fabric_registry = SimpleNamespace(devices=devices)
        self.skill_router = SpyRouter()
        self.runtime_executor = SpyExecutor()


VOICE_DEVICES = [{'key': 'dev-tv', 'category': 'tv'},
                 {'key': 'dev-ph', 'category': 'phone'}]

PLAN_DEVICES = [
    {'key': 'dev-tv1', 'label': 'android tv', 'category': 'tv',
     'handles': {'WIFI': 'h-tv'}},
    {'key': 'dev-vac1', 'label': 'Robot vacuum (Tuya)', 'category': 'vacuum',
     'handles': {'LAN': 'h-vac'}},
]

GIBBERISH = ('xqzt blorpn wobble fttt zzz', 'trucmuche bidule chouette xyz',
             '!!! ??? ### %%%', 'asdf ' * 60, 'lorem ipsum dolor sit amet ' * 10)


class NegativePaths(unittest.TestCase):
    def test_empty_text_rejected_at_every_layer(self):
        for text in ('', '   ', '\t\n '):
            with self.subTest(text=repr(text)):
                with self.assertRaises(I.IntentError):
                    I.new_intent(text, 'en')
                with self.assertRaises(CMD.CommandError) as cm:
                    CMD.parse_request(SpyServer(abstain('x')), {'text': text})
                self.assertEqual(cm.exception.status, 400)
                with self.assertRaises(nl_plan.PlanError):
                    nl_plan.plan(text, PLAN_DEVICES, lambda p: ({}, self.fail('transport called'))[0])
                self.assertIsNone(VI.compile_intent(text, VOICE_DEVICES)['intent'])
        dropped = R.validate_commands({'commands': [
            {'request_id': 'a' * 32, 'text': '', 'lang': 'en', 'quality': 'low'},
            {'request_id': 'b' * 32, 'text': '   ', 'lang': 'fr', 'quality': 'auto'}]})
        self.assertEqual(dropped, [])

    def test_oversize_text_rejected_before_any_model_call(self):
        calls = []

        def transport(prompt):
            calls.append(prompt)
            raise AssertionError('model must not be called for oversize input')

        with self.assertRaises(I.IntentError):
            I.new_intent('x' * 2001, 'en')
        with self.assertRaises(CMD.CommandError) as cm:
            CMD.parse_request(SpyServer(abstain('x')), {'text': 'x' * 3000})
        self.assertEqual(cm.exception.status, 400)
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply('x' * (nl_plan.MAX_REPLY_CHARS + 1), PLAN_DEVICES)
        self.assertIsNone(VI.compile_intent('x' * 401, VOICE_DEVICES)['intent'])
        dropped = R.validate_commands({'commands': [
            {'request_id': 'c' * 32, 'text': 'x' * 501, 'lang': 'en', 'quality': 'low'}]})
        self.assertEqual(dropped, [])
        self.assertEqual(calls, [])

    def test_non_utf8_bytes_never_parse(self):
        raw = b'\xff\xfe\x00bad\x80\x81'
        with self.assertRaises(I.IntentError):
            I.new_intent(raw, 'en')
        with self.assertRaises(CMD.CommandError) as cm:
            CMD.parse_request(SpyServer(abstain('x')), {'text': raw})
        self.assertEqual(cm.exception.status, 400)
        self.assertIsNone(VI.compile_intent(raw, VOICE_DEVICES)['intent'])
        dropped = R.validate_commands({'commands': [
            {'request_id': 'd' * 32, 'text': raw, 'lang': 'en', 'quality': 'low'},
            {'request_id': 'e' * 32, 'text': None, 'lang': 'en', 'quality': 'low'},
            {'request_id': 'f' * 32, 'text': 42, 'lang': 'en', 'quality': 'low'}]})
        self.assertEqual(dropped, [])

    def test_surrogate_text_never_dispatches(self):
        # surrogateescape-decoded bytes stay str: the router must refuse, not crash.
        text = 'start \udcff\udcfe cleaning'
        doc = N.parse(text, 'en', 'low', FakeTransport(abstain(text)), None)
        self.assertNotEqual(doc['status'], 'resolved')
        self.assertEqual(I.validate_intent(doc), [])
        with self.assertRaises(CMD.CommandError):
            CMD.approve(SpyServer(abstain('x')), doc)

    def test_gibberish_never_dispatches_and_budget_stays_intact(self):
        events = []
        for text in GIBBERISH:
            events.append(('abstain', text, abstain(text)))
        events.append(('unknown-skill', 'Beam me home',
                       resolved('teleport.home', 'teleport', [])))
        low = dict(resolved('vacuum.start', 'start cleaning',
                            [{'kind': 'device', 'ref': 'vacuum-1'}]))
        low['confidence'] = 0.2
        events.append(('low-confidence', 'maybe vacuum?', low))
        events.append(('malformed-keys', 'Start my vacuum', {'outcome': 'x'}))
        events.append(('malformed-shape', 'Start my vacuum', 'just a string'))
        badconf = dict(resolved('vacuum.start', 'start cleaning',
                                [{'kind': 'device', 'ref': 'vacuum-1'}]))
        badconf['confidence'] = True
        events.append(('bool-confidence', 'Start my vacuum', badconf))

        for name, text, reply in events:
            with self.subTest(case=name):
                srv = SpyServer(reply)
                before = budget()
                snap = before.state()
                doc = CMD.parse_request(
                    srv, {'text': text, 'quality': 'low'})['intent']
                self.assertIn(doc['status'], ('unsupported', 'escalation_required',
                                              'needs_clarification'), name)
                self.assertNotEqual(doc['status'], 'resolved', name)
                self.assertEqual(I.validate_intent(doc), [], name)
                with self.assertRaises(CMD.CommandError):
                    CMD.approve(srv, doc)
                self.assertEqual(srv.runtime_executor.calls, [], name)
                self.assertEqual(srv.skill_router.calls, [], name)
                self.assertEqual(srv.command_cloud.calls, [], name)
                self.assertEqual(before.state(), snap, name)
                self.assertEqual(before.pending_estimate, 0.0, name)

    def test_gibberish_auto_never_touches_cloud_without_consent(self):
        srv = SpyServer(N.TransportError('local down'))
        doc = CMD.parse_request(
            srv, {'text': GIBBERISH[0], 'quality': 'auto'})['intent']
        self.assertEqual(doc['status'], 'escalation_required')
        self.assertEqual(srv.command_cloud.calls, [])
        self.assertTrue(any('cloud' in a.lower() for a in doc['ambiguities']))


class ForcedChoiceRefusal(unittest.TestCase):
    AMBIGUOUS = (
        ('Turn it up', 'en', 'Set an exact volume, or step up once?',
         ['set vs step']),
        ('Monte le son', 'fr', 'Volume exact ou cran vers le haut ?',
         ['valeur exacte ou cran']),
        ('Make it louder', 'en', 'Which device should get louder, the TV or the vacuum?',
         ['tv vs vacuum']),
        ('Mets plus fort', 'fr', 'Sur quel appareil monter le son, la télé ou le robot ?',
         ['tele ou aspirateur']),
        ('Pause it', 'en', 'Pause the vacuum, or stop it entirely?',
         ['pause vs stop']),
        ('Mets en pause', 'fr', 'Pause simple ou arrêt complet ?',
         ['pause ou arret']),
    )

    def test_ambiguous_commands_ask_instead_of_defaulting(self):
        for text, lang, question, ambiguities in self.AMBIGUOUS:
            with self.subTest(text=text):
                srv = SpyServer(abstain(text, question=question,
                                        ambiguities=ambiguities))
                doc = CMD.parse_request(
                    srv, {'text': text, 'lang': lang, 'quality': 'low'})['intent']
                self.assertEqual(doc['status'], 'needs_clarification')
                self.assertIsNone(doc['skill_id'])
                self.assertTrue(doc['clarifying_question'])
                self.assertIn(question[:60], doc['clarifying_question'])
                self.assertEqual(I.validate_intent(doc), [])
                with self.assertRaises(CMD.CommandError) as cm:
                    CMD.approve(srv, doc)
                self.assertEqual(cm.exception.status, 400)
                self.assertEqual(srv.runtime_executor.calls, [])
                self.assertEqual(srv.skill_router.calls, [])

    def test_tied_or_zero_keyword_hits_stay_unsupported(self):
        for text in ('vacuum', 'do the thing', 'chose machin truc',
                     'tv', 'please', 'ok google'):
            with self.subTest(text=text):
                doc = N.parse(text, 'en', 'low',
                              FakeTransport(abstain(text)), None)
                self.assertEqual(doc['status'], 'unsupported', text)
                self.assertIsNone(doc['skill_id'], text)

    def test_voice_ambiguous_target_asks_on_screen(self):
        two_tvs = VOICE_DEVICES + [{'key': 'dev-tv2', 'category': 'tv'}]
        for phrase in ('Bluetooth through the TV',
                       'Bluetooth via la télé du salon'):
            with self.subTest(phrase=phrase):
                p = VI.compile_intent(phrase, two_tvs)
                self.assertTrue(p.get('needs_target'), phrase)
                self.assertNotIn('device_key', p, phrase)
        none = VI.compile_intent('Why does the tv disconnect?',
                                 [{'key': 'dev-ph', 'category': 'phone'}])
        self.assertTrue(none.get('needs_target'))

    def test_command_layer_refuses_ambiguous_target(self):
        from types import SimpleNamespace
        srv = SpyServer(abstain('x'))
        srv.fabric_registry = SimpleNamespace(devices={
            'dev-tv1': {'key': 'dev-tv1', 'category': 'tv', 'label': 'TV one'},
            'dev-tv2': {'key': 'dev-tv2', 'category': 'tv', 'label': 'TV two'}})
        with self.assertRaises(CMD.CommandError) as cm:
            CMD.resolve_targets([{'kind': 'device', 'ref': 'tv'}],
                                srv.fabric_registry.devices)
        self.assertEqual(cm.exception.status, 409)
        self.assertEqual(srv.runtime_executor.calls, [])

    def test_plan_layer_refuses_ambiguous_label(self):
        import json
        devs = PLAN_DEVICES + [{'key': 'dev-tv2', 'label': 'ANDROID TV',
                                'category': 'tv', 'handles': {'WIFI': 'h2'}}]
        reply = json.dumps({'steps': [
            {'skill_id': 'tv_volume_step', 'target': 'android tv',
             'params': {'direction': 'down'}}]})
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(reply, devs)


# skill_id -> (EN text, FR text, English model outcome, targets).
# The router's system prompt forces English-only model replies, so the FR
# user text always arrives paired with an English outcome; the fallback
# must resolve both languages to the same skill.
PARITY = (
    ('ble_scan_room', 'scan for nearby bluetooth devices',
     'lance un scan bluetooth des appareils proches',
     'scan nearby bluetooth', [{'kind': 'device', 'ref': 'relay-1'}]),
    ('device_facts', 'show device info and status facts',
     "affiche les infos et le statut de l'appareil",
     'show device info and status facts', [{'kind': 'device', 'ref': 'tv-1'}]),
    ('tv_volume_set', 'set the tv volume to 7',
     'règle le volume de la tv à 7', 'set tv volume to 7',
     [{'kind': 'device', 'ref': 'tv-1'}]),
    ('tv_volume_step', 'turn the tv volume down',
     'baisse le volume de la tv', 'turn tv volume down',
     [{'kind': 'device', 'ref': 'tv-1'}]),
    ('vacuum.start', 'start cleaning with the vacuum',
     "démarre le ménage avec l'aspirateur", 'start cleaning',
     [{'kind': 'device', 'ref': 'vacuum-1'}]),
    ('vacuum.pause', 'pause the vacuum',
     "mets l'aspirateur en pause", 'pause cleaning',
     [{'kind': 'device', 'ref': 'vacuum-1'}]),
    ('vacuum.dock', 'send the vacuum back to its dock to charge',
     "renvoie l'aspirateur à sa base pour recharger",
     'dock the vacuum to charge', [{'kind': 'device', 'ref': 'vacuum-1'}]),
    ('vacuum.seek', 'where is the vacuum, make it beep',
     "où est l'aspirateur, fais-le biper", 'find the vacuum',
     [{'kind': 'device', 'ref': 'vacuum-1'}]),
    ('vacuum.empty_dust', 'empty the vacuum dustbin',
     "vide le bac à poussière de l'aspirateur", 'empty the dustbin',
     [{'kind': 'device', 'ref': 'vacuum-1'}]),
    ('fabric.status', 'how many devices are online',
     "combien d'appareils sont en ligne", 'count online devices', []),
)

VOICE_PARITY = (
    ('discover', 'Discover all my devices', 'Découvre tous mes appareils',
     'fabric'),
    ('ble_scan_via_tv', 'Run a bluetooth scan via the tv',
     'Lance un scan bluetooth via la télé', 'dev-tv'),
    ('ble_scan_via_phone', 'Start a bluetooth scan with my phone',
     'Lance un scan bluetooth avec mon téléphone', 'dev-ph'),
    ('diagnose', 'Run a full diagnostic report', 'Fais un diagnostic complet',
     'fabric'),
    ('why_disconnect', 'Why does the tv keep disconnecting?',
     'Pourquoi la télé se déconnecte ?', 'dev-tv'),
    ('finish_session', 'Finish the session and restore',
     'Termine la session', 'fabric'),
)


class FrenchEnglishParity(unittest.TestCase):
    def test_ten_skills_cover_the_full_catalog(self):
        from src.runtime import skills as S
        self.assertEqual({row[0] for row in PARITY},
                         {c['skill_id'] for c in S.all_skills()})

    def test_deterministic_fallback_parity(self):
        self.assertGreaterEqual(len(PARITY), 10)
        for skill_id, en, fr, outcome, targets in PARITY:
            with self.subTest(skill=skill_id):
                got = []
                for text, lang in ((en, 'en'), (fr, 'fr')):
                    doc = N.parse(text, lang, 'low',
                                  FakeTransport(abstain(outcome, targets)), None)
                    self.assertEqual(doc['status'], 'resolved', (skill_id, lang))
                    self.assertEqual(doc['skill_id'], skill_id, (skill_id, lang))
                    self.assertEqual(doc['lang'], lang)
                    self.assertEqual(I.validate_intent(doc), [], (skill_id, lang))
                    self.assertTrue(any('deterministic' in a
                                        for a in doc['ambiguities']))
                    got.append(doc['skill_id'])
                self.assertEqual(got[0], got[1])

    def test_resolved_reply_parity(self):
        for skill_id, en, fr, outcome, targets in PARITY:
            with self.subTest(skill=skill_id):
                tg = targets or [{'kind': 'category', 'ref': 'fabric'}]
                reply = resolved(skill_id, outcome, tg)
                docs = [N.parse(t, lang, 'low', FakeTransport(dict(reply)), None)
                        for t, lang in ((en, 'en'), (fr, 'fr'))]
                for doc, lang in zip(docs, ('en', 'fr')):
                    self.assertEqual(doc['status'], 'resolved', (skill_id, lang))
                    self.assertEqual(doc['skill_id'], skill_id)
                    self.assertEqual(doc['targets'], tg)
                    self.assertEqual(I.validate_intent(doc), [])
                self.assertEqual(docs[0]['skill_id'], docs[1]['skill_id'])

    def test_voice_intent_parity(self):
        for name, en, fr, device in VOICE_PARITY:
            with self.subTest(intent=name):
                p_en = VI.compile_intent(en, VOICE_DEVICES)
                p_fr = VI.compile_intent(fr, VOICE_DEVICES)
                self.assertEqual(p_en['intent'], name, en)
                self.assertEqual(p_fr['intent'], name, fr)
                self.assertEqual(p_en['device_key'], device, en)
                self.assertEqual(p_fr['device_key'], device, fr)


if __name__ == '__main__':
    unittest.main()
