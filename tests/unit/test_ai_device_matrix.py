"""OpenBridge's own model must work with EVERY device (AI x device matrix).

Covers the whole AI understanding stack against every device class, with no
model, no network and no hardware: the official command model identity
(openbridge-intent v4), tier routing, the LAN scheduler, deterministic
voice intents (FR + EN), capability discovery grounding, composer
skill-audience grounding vs route truth, the voice Oracle, the universal
microphone connector, the ENGO AI bridge, visual read-back, local STT
bounds, partner voice profiles, custom providers and adapter presence.

Followers of the repo rule: emulated results stay emulated; nothing here
claims physical proof.
"""
import base64
import json
import os
import struct
import unittest
import zlib
from unittest import mock

from src.ai import broker as AI_BROKER
from src.ai import custom_provider as CP
from src.ai import discovery as DISC
from src.ai import glimmer as GLIMMER
from src.ai import local_meta as LM
from src.ai import mic_oracle as MO
from src.ai import oracle as ORACLE
from src.ai import own_model as OWN
from src.ai import partner_voice as PV
from src.ai import registry as REG
from src.ai import router as ROUTER
from src.ai import scheduler as SCHED
from src.ai import stt_local as STT
from src.ai import visual_readback as VR
from src.ai import voice_intent as VI
from src.ai import voice_normalize as VN
from src.ai import voice_stt as VSTT
from src.runtime import composer as COMP
from src.runtime.routing import SKILLS


def dev(key, label, category, handles=True):
    return {'key': key, 'label': label, 'category': category,
            'handles': {'LINK': 'up'} if handles else {}}


# Every device class the fabric registry can produce, plus the Android
# family the router reasons about. One representative row each.
MATRIX_DEVICES = [
    dev('dev-tv1', 'salon tv', 'tv'),
    dev('dev-phone1', 'my phone', 'phone'),
    dev('dev-watch1', 'my watch', 'watch'),
    dev('dev-android1', 'tablet android', 'android'),
    dev('dev-pc1', 'bureau pc', 'computer'),
    dev('dev-vac1', 'aspirateur', 'vacuum'),
    dev('dev-router1', 'box router', 'router'),
    dev('dev-light1', 'salon lamp', 'iot'),
    dev('dev-nas1', 'home nas', 'nas'),
    dev('dev-print1', 'desk printer', 'printer'),
    dev('dev-media1', 'media box', 'media'),
    dev('dev-hub1', 'home hub', 'hub'),
    dev('dev-net1', 'switch', 'network'),
    dev('dev-mac1', 'macbook', 'apple'),
    dev('dev-ble1', 'ble tag', 'ble'),
    dev('dev-glasses1', 'engo 3', 'glasses'),
    dev('dev-unknown1', 'mystery box', 'unknown'),
]


class OwnModelIdentity(unittest.TestCase):
    def test_manifest_matches_code_constants(self):
        manifest = json.loads(
            (REG.MANIFEST).read_text(encoding='utf-8'))
        rows = {e['model_id']: e for e in manifest['model_calls']}
        self.assertIn(OWN.MODEL_ID, rows)
        self.assertEqual(rows[OWN.MODEL_ID]['manifest_digest'], OWN.MODEL_DIGEST)
        self.assertEqual(rows[OWN.MODEL_ID]['endpoint'], OWN.ENDPOINT)
        self.assertEqual(rows[OWN.MODEL_ID]['execution'], 'local')
        self.assertEqual(manifest['environment'], 'runtime')

    def test_builtin_models_all_pinned_and_local(self):
        pairs = REG.load()
        self.assertTrue(pairs)
        for model_id, endpoint in pairs:
            self.assertIn(model_id, REG.BUILT_IN_MODELS)
            from urllib.parse import urlsplit
            self.assertIn(urlsplit(endpoint).hostname, REG.ALLOWED_HOSTS)
            REG.require(model_id, endpoint)

    def test_names_cover_cli_spellings(self):
        self.assertEqual(OWN.names(), {OWN.MODEL_ID, 'openbridge-intent'})
        self.assertEqual(OWN.LANGUAGES, ('fr', 'en-US', 'en-GB'))

    def test_unknown_model_and_endpoint_rejected(self):
        with self.assertRaises(REG.RegistryInvalid):
            REG.require('evil-model:latest', 'http://127.0.0.1:11434')
        with self.assertRaises(REG.RegistryInvalid):
            REG.require(OWN.MODEL_ID, 'http://203.0.113.9:11434')

    def test_owner_connected_provider_accepted_via_registry(self):
        import tempfile
        from pathlib import Path
        entry = {'name': 'lan-ollama', 'kind': 'ollama',
                 'base_url': 'http://192.168.1.20:11434', 'model': 'qwen:test'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ai_providers.json'
            CP.add(entry, path=str(path))
            url = 'http://192.168.1.20:11434/api/chat'
            self.assertTrue(CP.declared('qwen:test', url, path=str(path)))
            REG.require('qwen:test', url, providers_path=str(path))
            self.assertFalse(CP.declared('qwen:test', url, path=str(path / 'x')))


class RouterMatrix(unittest.TestCase):
    def test_explicit_tier_never_reroutes(self):
        with self.assertRaises(ROUTER.RoutingError):
            ROUTER.route('LOCAL-FAST', 'chat', {})
        with self.assertRaises(ROUTER.RoutingError):
            ROUTER.route('LOCAL-QUALITY', 'planning', {'local_fast': True})
        with self.assertRaises(ROUTER.RoutingError) as ctx:
            ROUTER.route('CUSTOM', 'chat', {})
        self.assertIn('CUSTOM_PROVIDER_MISSING', str(ctx.exception))
        with self.assertRaises(ROUTER.RoutingError):
            ROUTER.route('NOPE', 'chat', {'local_fast': True})

    def test_explicit_tier_returns_pinned_model(self):
        d = ROUTER.route('LOCAL-FAST', 'chat', {'local_fast': True})
        self.assertEqual(d['model_id'], ROUTER.TIER_MODELS['LOCAL-FAST'])
        self.assertFalse(d['needs_cloud_consent'])
        d = ROUTER.route('LOCAL-QUALITY', 'planning', {'local_quality': True})
        self.assertEqual(d['tier'], 'LOCAL-QUALITY')

    def test_auto_simple_prefers_fast_complex_prefers_quality(self):
        both = {'local_fast': True, 'local_quality': True}
        self.assertEqual(ROUTER.route('AUTO', 'chat', both)['tier'], 'LOCAL-FAST')
        for task in sorted(ROUTER.COMPLEX_TASKS):
            self.assertEqual(ROUTER.route('AUTO', task, both)['tier'],
                             'LOCAL-QUALITY')

    def test_auto_falls_back_without_silent_cloud(self):
        only_q = {'local_quality': True}
        self.assertEqual(ROUTER.route('AUTO', 'chat', only_q)['tier'],
                         'LOCAL-QUALITY')
        remote = {'custom': True, 'custom_model': 'm',
                  'custom_execution': 'remote'}
        with self.assertRaises(ROUTER.RoutingError):
            ROUTER.route('AUTO', 'chat', remote, privacy='local-only')
        d = ROUTER.route('AUTO', 'planning', remote, privacy='allow-cloud')
        self.assertEqual(d['tier'], 'CUSTOM')
        self.assertTrue(d['needs_cloud_consent'])
        local_custom = {'custom': True, 'custom_model': 'm',
                        'custom_execution': 'local'}
        d = ROUTER.route('AUTO', 'planning', local_custom, privacy='local-only')
        self.assertEqual(d['tier'], 'CUSTOM')
        self.assertFalse(d['needs_cloud_consent'])

    def test_reasons_never_carry_user_text(self):
        marker = 'SECRET-xy9-user-text'
        d = ROUTER.route('AUTO', 'chat', {'local_fast': True},
                         user_text='please repeat ' + marker)
        self.assertNotIn(marker, ' '.join(d['reasons']))
        self.assertIn('tier=LOCAL-FAST', d['reasons'])


class SchedulerMatrix(unittest.TestCase):
    def test_worker_validation_is_fail_closed(self):
        with self.assertRaises(SCHED.SchedulerBlocked):
            SCHED.Worker('http://127.0.0.1:11438', 'not-a-model', 'local')
        with self.assertRaises(SCHED.SchedulerBlocked):
            SCHED.Worker('http://192.168.1.20:11438', GLIMMER.GLIMMER_ID,
                         'local')
        # NOTE: documentation ranges (203.0.113.x) count as is_private on
        # Python 3.14, so the public-IP probe uses a truly global address.
        with self.assertRaises(SCHED.SchedulerBlocked):
            SCHED.Worker('http://8.8.8.8:11438', GLIMMER.GLIMMER_ID, 'lan')
        with self.assertRaises(SCHED.SchedulerBlocked):
            SCHED.Worker('http://127.0.0.1:11438', GLIMMER.GLIMMER_ID, 'lan')
        with self.assertRaises(SCHED.SchedulerBlocked):
            SCHED.Worker('https://192.168.1.20:11438', GLIMMER.GLIMMER_ID,
                         'lan')
        with self.assertRaises(SCHED.SchedulerBlocked):
            SCHED.Worker('http://192.168.1.20:11438/?x=1', GLIMMER.GLIMMER_ID,
                         'lan')

    def test_probe_checks_pinned_digest(self):
        w = SCHED.Worker('http://127.0.0.1:11438', GLIMMER.GLIMMER_ID, 'local')
        good = lambda ep: {'models': [{'name': GLIMMER.GLIMMER_ID,
                                       'digest': 'sha256:' + GLIMMER.GLIMMER_DIGEST}]}
        self.assertTrue(w.probe(good))
        bad = lambda ep: {'models': [{'name': GLIMMER.GLIMMER_ID,
                                      'digest': 'sha256:' + '0' * 64}]}
        self.assertFalse(w.probe(bad))
        boom = lambda ep: (_ for _ in ()).throw(OSError('down'))
        self.assertFalse(w.probe(boom))
        self.assertIsNotNone(w.latency_ms)

    def test_owner_workers_filters_bad_rows(self):
        import tempfile
        from pathlib import Path
        doc = {'workers': [
            {'endpoint': 'http://192.168.1.20:11438',
             'model_id': GLIMMER.GLIMMER_ID, 'label': 'PC 2'},
            {'endpoint': 'http://203.0.113.9:11434', 'model_id': 'evil'},
            {'endpoint': 'http://192.168.1.21:11434'},
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'workers.json'
            path.write_text(json.dumps(doc), encoding='utf-8')
            workers = SCHED.owner_workers(path=str(path))
            self.assertEqual(len(workers), 1)
            self.assertEqual(workers[0].label, 'PC 2')
            self.assertEqual(SCHED.owner_workers(path=str(path / 'nope')), [])

    def test_raw_data_never_leaves_this_pc(self):
        lan = SCHED.Worker('http://192.168.1.20:11438', GLIMMER.GLIMMER_ID,
                           'lan', 'PC 2')
        lan.ready, lan.latency_ms, lan.tokens_per_s = True, 5, 40.0
        with self.assertRaises(SCHED.SchedulerBlocked):
            SCHED.choose([lan], GLIMMER.GLIMMER_ID, 'raw')
        best, trace = SCHED.choose([lan], GLIMMER.GLIMMER_ID, 'redacted')
        self.assertIs(best, lan)
        self.assertEqual(trace['chosen'], 'PC 2')
        with self.assertRaises(SCHED.SchedulerBlocked):
            SCHED.choose([lan], GLIMMER.GLIMMER_ID, 'nope')

    def test_lowest_expected_latency_wins_local_breaks_ties(self):
        local = SCHED.Worker('http://127.0.0.1:11438', GLIMMER.GLIMMER_ID,
                             'local', 'this PC')
        lan = SCHED.Worker('http://192.168.1.20:11438', GLIMMER.GLIMMER_ID,
                           'lan', 'PC 2')
        local.ready, local.latency_ms, local.tokens_per_s = True, 5, 8.0
        lan.ready, lan.latency_ms, lan.tokens_per_s = True, 5, 80.0
        best, _ = SCHED.choose([local, lan], GLIMMER.GLIMMER_ID, 'redacted')
        self.assertIs(best, lan)
        lan.tokens_per_s = 8.0
        best, _ = SCHED.choose([lan, local], GLIMMER.GLIMMER_ID, 'redacted')
        self.assertIs(best, local)


class VoiceIntentMatrix(unittest.TestCase):
    TV = [dev('dev-tv1', 'salon tv', 'tv')]
    PHONE = [dev('dev-phone1', 'my phone', 'phone')]

    def test_every_intent_reachable_in_french_and_english(self):
        cases = [
            ('discover', 'discover my devices please',
             "decouvre mes appareils s'il te plait", []),
            ('ble_scan_via_tv', 'run a bluetooth scan via the tv please',
             "lance un scan bluetooth via la tele s'il te plait", self.TV),
            ('ble_scan_via_phone', 'bluetooth scan via my phone please',
             'scan bluetooth via mon telephone maintenant', self.PHONE),
            ('diagnose', 'run a full diagnostic report please',
             "fais un diagnostic complet s'il te plait", []),
            ('why_disconnect', 'why does the tv keep disconnecting',
             'pourquoi la tele se deconnecte tout le temps', self.TV),
            ('finish_session', 'finish the session and restore everything',
             'termine la session et restaure tout', []),
        ]
        for name, en, fr, devices in cases:
            for transcript, lang in ((en, 'en'), (fr, 'fr')):
                with self.subTest(intent=name, lang=lang):
                    r = VI.compile_intent(transcript, devices)
                    self.assertEqual(r['outcome'], 'proposal', r)
                    self.assertEqual(r['intent'], name, r)
                    self.assertEqual(r['lang'], lang, r)
                    self.assertEqual(r['primitive_id'],
                                     VI.INTENTS[name]['primitive_id'])
                    self.assertEqual(r['requires_consent'],
                                     VI.INTENTS[name]['consent'])

    def test_scan_targeting_needs_exactly_one_device(self):
        r = VI.compile_intent('run a bluetooth scan via the tv please', [])
        self.assertEqual(r['outcome'], 'needs_clarification')
        self.assertIn('0 tv', r['reason'])
        two = self.TV + [dev('dev-tv2', 'chambre tv', 'tv')]
        r = VI.compile_intent('run a bluetooth scan via the tv please', two)
        self.assertEqual(r['outcome'], 'needs_clarification')
        self.assertIn('2 tv', r['reason'])
        one = VI.compile_intent('run a bluetooth scan via the tv please',
                                self.TV)
        self.assertEqual(one['device_key'], 'dev-tv1')

    def test_refusals_in_both_languages(self):
        for transcript in ('shut down the tv now', 'eteins la tele maintenant',
                           'reboot the phone now', 'formatte le disque dur'):
            with self.subTest(transcript=transcript):
                r = VI.compile_intent(transcript, self.TV + self.PHONE)
                self.assertEqual(r['outcome'], 'refusal', r)
                self.assertIsNone(r['intent'])

    def test_clarification_paths_never_propose(self):
        cases = [
            'bluetooth scan via tv and phone',          # conflicting targets
            'finish the session and discover devices',  # finish vs action
            'press the volume button',                  # control press
            'monte le son de la tele',                  # volume shape
            'where is my phone',                        # locate shape
            'scan',                                     # bare fragment
            'blue tooth via the tellee please',         # repaired-only match
        ]
        for transcript in cases:
            with self.subTest(transcript=transcript):
                r = VI.compile_intent(transcript, self.TV + self.PHONE)
                self.assertEqual(r['outcome'], 'needs_clarification', r)
                self.assertTrue(r['clarifying_question'], r)

    def test_short_command_language_guard(self):
        en = VI.compile_intent('scan bluetooth')
        fr = VI.compile_intent('scan bluetooth', lang_hint='fr')
        self.assertEqual(en['lang'], 'en')
        self.assertEqual(fr['lang'], 'fr')
        self.assertNotEqual(en['clarifying_question'],
                            fr['clarifying_question'])

    def test_empty_and_oversized_transcripts_unsupported(self):
        self.assertEqual(VI.compile_intent('')['outcome'], 'unsupported')
        self.assertEqual(VI.compile_intent('   ')['outcome'], 'unsupported')
        self.assertEqual(VI.compile_intent('x' * 401)['outcome'], 'unsupported')
        r = VI.compile_intent('tell me a joke about robots')
        self.assertEqual(r['outcome'], 'unsupported')
        self.assertIsNone(r['intent'])

    def test_uncertain_verb_and_migration_stay_clarification(self):
        r = VI.compile_intent('mais les boutons montre le diagnostic',
                              self.TV)
        self.assertEqual(r['outcome'], 'needs_clarification', r)
        r = VI.compile_intent('deplace les boutons vers la montre', self.TV)
        self.assertEqual(r['outcome'], 'needs_clarification', r)


class DiscoveryMatrix(unittest.TestCase):
    def test_prompt_grounds_every_device_class(self):
        for d in MATRIX_DEVICES:
            with self.subTest(category=d['category']):
                prompt = DISC.build_prompt(d, MATRIX_DEVICES, [])
                self.assertIn(d['label'], prompt)
                self.assertNotIn(d['key'], prompt)
                cands = COMP.candidates_for(d)
                if cands:
                    self.assertIn('Candidate skills for THIS device', prompt)
                    self.assertIn(cands[0], prompt)
                else:
                    self.assertIn('no live link', prompt)

    def test_unlinked_device_has_no_candidates_anywhere(self):
        ghost = dev('dev-ghost', 'ghost speaker', 'speaker', handles=False)
        self.assertEqual(COMP.candidates_for(ghost), [])
        prompt = DISC.build_prompt(ghost, [], [])
        self.assertIn('no live link', prompt)

    def test_verify_admits_grounded_and_drops_the_rest(self):
        tv = dev('dev-tv1', 'salon tv', 'tv')
        peers = [dev('dev-phone1', 'my phone', 'phone')]
        doc = {'summary': 'A TV that plays media.',
               'capabilities': [
                   {'skill_id': 'tv_volume_step', 'peers': ['my phone'],
                    'needs': ['permission'], 'verify': 'volume changes'},
                   {'skill_id': 'nope_not_a_skill', 'peers': [],
                    'needs': [], 'verify': 'x'},
                   {'skill_id': 'vacuum_command', 'peers': [],
                    'needs': [], 'verify': 'x'},
                   {'skill_id': 'device_facts', 'peers': ['ghost box'],
                    'needs': ['telepathy'], 'verify': 'facts shown'}],
               'combinations': [
                   {'title': 'bad combo', 'skills': ['nope'],
                    'devices': ['ghost box'], 'needs': []}],
               'unknowns': ['firmware version', ''],
               'test_plan': ['press volume up once']}
        rep = DISC.verify_report(doc, tv, peers, [])
        kept = [c['skill_id'] for c in rep['capabilities']]
        self.assertIn('tv_volume_step', kept)
        self.assertIn('device_facts', kept)
        self.assertNotIn('nope_not_a_skill', kept)
        self.assertNotIn('vacuum_command', kept)
        facts = next(c for c in rep['capabilities']
                     if c['skill_id'] == 'device_facts')
        self.assertEqual(facts['peers'], [])
        self.assertEqual(facts['needs'], [])
        self.assertEqual(rep['combinations'], [])
        self.assertEqual(rep['unknowns'], ['firmware version'])
        self.assertTrue(rep['dropped'])
        self.assertIn('salon tv', rep['verified_devices'])

    def test_verify_rejects_malformed_reports(self):
        tv = dev('dev-tv1', 'salon tv', 'tv')
        with self.assertRaises(DISC.DiscoveryError):
            DISC.verify_report({'summary': 'x'}, tv, [], [])
        with self.assertRaises(DISC.DiscoveryError):
            DISC.verify_report('nope', tv, [], [])

    def test_explain_device_with_stub_proposer(self):
        tv = dev('dev-tv1', 'salon tv', 'tv')
        doc = {'summary': 'TV.', 'capabilities': [], 'combinations': [],
               'unknowns': [], 'test_plan': []}
        proposer = lambda prompt: {'content': json.dumps(doc),
                                   'model_id': 'stub', 'endpoint': 'stub'}
        rep = DISC.explain_device(tv, [], [], proposer)
        self.assertEqual(rep['summary'], 'TV.')
        self.assertEqual(rep['model_run']['model'], 'stub')
        self.assertEqual(len(rep['reply_sha256']), 64)

    def test_explain_device_fails_closed(self):
        tv = dev('dev-tv1', 'salon tv', 'tv')
        with self.assertRaises(DISC.DiscoveryError):
            DISC.explain_device({}, [], [], lambda p: {})
        with self.assertRaises(DISC.DiscoveryError):
            DISC.explain_device(tv, [], [], lambda p: {'content': 'not json'})
        with self.assertRaises(DISC.DiscoveryError):
            DISC.explain_device(tv, [], [], lambda p: {'content': ''})
        with self.assertRaises(DISC.DiscoveryError):
            DISC.explain_device(
                tv, [], [], lambda p: (_ for _ in ()).throw(OSError('down')))
        big = lambda p: {'content': 'x' * (DISC.MAX_REPLY_CHARS + 1)}
        with self.assertRaises(DISC.DiscoveryError):
            DISC.explain_device(tv, [], [], big)


class StubRouter:
    """Minimal router double: READY for one (skill, key), else link_down."""

    def __init__(self, skill, key):
        self.skill, self.key = skill, key

    def skill_routes(self, skill_id, target):
        if skill_id == self.skill and target == self.key:
            route = {'route_id': 'r1', 'state': 'READY',
                     'operation_id': 'op:x', 'evidence': 'SIMULATED',
                     'hops': [{'transport': 'WIFI', 'primitive_id': 'p'}]}
            return {'selected_route_id': 'r1', 'routes': [route],
                    'selection': {'rule': 'stub'}}
        return {'selected_route_id': None,
                'routes': [{'route_id': 'r0', 'state': 'UNAVAILABLE',
                            'reason': 'link_down'}],
                'selection': {'rule': 'stub'}}


class ComposerGroundingTruth(unittest.TestCase):
    """The model must be told, per device, exactly the skills route truth
    can serve. No silent 'any linked device' default for new skills."""

    def test_every_skill_declares_an_audience(self):
        missing = [s for s in SKILLS if s not in COMP.SKILL_AUDIENCE]
        self.assertEqual(missing, [], 'skills without audience: %r' % missing)

    def test_audiences_match_route_truth(self):
        aud = COMP.SKILL_AUDIENCE
        self.assertEqual(aud['view_image'], 'android')
        self.assertEqual(aud['pc_open_url'], 'computer')
        self.assertEqual(aud['pc_place_file'], 'computer')
        self.assertEqual(aud['pc_wallpaper'], 'computer')
        self.assertEqual(aud['engo_control'], 'fabric')
        self.assertEqual(aud['tv_sleep'], 'tv')
        self.assertEqual(aud['tv_wake'], 'tv')
        self.assertEqual(aud['vacuum_command'], 'vacuum')
        self.assertEqual(aud['retro_command'], 'fabric')

    def test_candidates_per_device_class(self):
        phone = COMP.candidates_for(dev('k', 'p', 'phone'))
        tv = COMP.candidates_for(dev('k', 't', 'tv'))
        vac = COMP.candidates_for(dev('k', 'v', 'vacuum'))
        pc = COMP.candidates_for(dev('k', 'c', 'computer'))
        router = COMP.candidates_for(dev('k', 'r', 'router'))
        iot = COMP.candidates_for(dev('k', 'l', 'iot'))
        glasses = COMP.candidates_for(dev('k', 'g', 'glasses'))
        # Android family: android skills yes, others no.
        self.assertIn('tv_volume_step', phone)
        self.assertIn('view_image', phone)
        self.assertNotIn('vacuum_command', phone)
        self.assertNotIn('pc_run', phone)
        self.assertIn('tv_sleep', tv)
        self.assertNotIn('tv_sleep', phone)
        self.assertNotIn('tv_wake', phone)
        # Vacuum: its skill only (+ universal reads).
        self.assertIn('vacuum_command', vac)
        self.assertNotIn('tv_volume_step', vac)
        self.assertNotIn('view_image', vac)
        # Computer: pc_* yes, android/vacuum no.
        for sid in ('pc_run', 'pc_open_url', 'pc_place_file', 'pc_wallpaper'):
            self.assertIn(sid, pc)
        self.assertNotIn('view_image', pc)
        self.assertNotIn('vacuum_command', pc)
        # Narrow classes: universal reads only, never actuators.
        for cands in (router, iot, glasses):
            self.assertIn('device_facts', cands)
            self.assertNotIn('view_image', cands)
            self.assertNotIn('pc_run', cands)
            self.assertNotIn('vacuum_command', cands)
            self.assertNotIn('tv_volume_step', cands)
        # Fabric skills are never per-device candidates.
        for cands in (phone, tv, vac, pc, router, iot, glasses):
            self.assertNotIn('engo_control', cands)
            self.assertNotIn('retro_command', cands)
            self.assertNotIn('ble_scan_room', cands)
            self.assertNotIn('capture_montage', cands)

    def test_no_audience_value_is_unknown(self):
        known = {'fabric', 'android', 'computer', 'vacuum', 'tv',
                 'any linked device'}
        for sid, aud in COMP.SKILL_AUDIENCE.items():
            self.assertIn(aud, known, sid)

    def test_compose_enforces_fabric_target_for_untargeted(self):
        devices = [dev('dev-tv1', 'salon tv', 'tv')]
        prop = {'steps': [{'id': 'step1', 'skill_id': 'engo_control',
                           'target': 'salon tv', 'params': {'op': 'show'},
                           'needs': [], 'on_fail': 'fail'}]}
        res = COMP.compose(prop, devices, StubRouter('engo_control', None))
        self.assertEqual(res['steps'][0]['status'], 'refused')
        self.assertIn('fabric', res['steps'][0]['reason'])

    def test_compose_happy_path_targeted(self):
        devices = [dev('dev-tv1', 'salon tv', 'tv')]
        prop = {'steps': [{'id': 'step1', 'skill_id': 'device_facts',
                           'target': 'salon tv', 'params': {},
                           'needs': [], 'on_fail': 'fail'}]}
        res = COMP.compose(prop, devices, StubRouter('device_facts', 'dev-tv1'))
        self.assertEqual(res['allowed'], 1)
        step = res['steps'][0]
        self.assertEqual(step['status'], 'allowed')
        self.assertIn('Physical acts are never atomically rolled back',
                      res['rollback'])
        self.assertEqual(step['authorization']['consent'], 'none')


class OracleMatrix(unittest.TestCase):
    def setUp(self):
        with ORACLE._CACHE_LOCK:
            ORACLE._ANSWER_CACHE.clear()
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for key in ('OB_ORACLE_FORCE_WEB', 'GEMINI_API_KEY', 'GOOGLE_API_KEY',
                    'GROQ_API_KEY'):
            os.environ.pop(key, None)
        os.environ['OB_ORACLE_WEB'] = '0'
        ORACLE._VISION_PICK.clear()

    def tearDown(self):
        self.env.stop()
        ORACLE._VISION_PICK.clear()

    def test_classify_in_french_and_english(self):
        self.assertEqual(ORACLE.classify('combien font 2 fois 6'), 'MATH')
        self.assertEqual(ORACLE.classify('what is 7 times 8'), 'MATH')
        self.assertEqual(ORACLE.classify('what is 12 divided by 4'), 'MATH')
        self.assertEqual(ORACLE.classify('5 minus 3'), 'MATH')
        self.assertEqual(ORACLE.classify('ou est le lac d annecy'), 'LOCATE')
        self.assertEqual(ORACLE.classify('what is the capital of italy'),
                         'LOCATE')
        self.assertEqual(ORACLE.classify('raconte-moi une histoire'), 'GENERAL')
        self.assertEqual(ORACLE.classify('tell me about bicycles'), 'GENERAL')

    def test_spoken_math_french_and_english(self):
        self.assertEqual(ORACLE._try_math('combien font 2 fois 6'), '12')
        self.assertEqual(ORACLE._try_math('12 sur 4'), '3')
        self.assertEqual(ORACLE._try_math('racine de 16'), '4')
        self.assertEqual(ORACLE._try_math('what is 7 times 8'), '56')
        self.assertEqual(ORACLE._try_math('what is 12 divided by 4'), '3')
        self.assertEqual(ORACLE._try_math('5 minus 3'), '2')
        self.assertIsNone(ORACLE._try_math('raconte-moi une histoire'))

    def test_hud_format_invariant(self):
        out = ORACLE._format_hud('**Loud** answer with `code` and # hash\n'
                                 'second line is way too long for the display\n'
                                 'third\nfourth dropped')
        lines = out.splitlines()
        self.assertLessEqual(len(lines), 3)
        for line in lines:
            self.assertLessEqual(len(line), 32, line)
        self.assertNotIn('*', out)
        self.assertEqual(ORACLE._format_hud(''), '')

    def test_needs_web_gating(self):
        self.assertTrue(ORACLE.needs_web('quel temps fait-il demain'))
        self.assertTrue(ORACLE.needs_web('what is the bitcoin price'))
        self.assertFalse(ORACLE.needs_web('combien font 2 fois 6'))
        os.environ['OB_ORACLE_FORCE_WEB'] = '1'
        self.assertTrue(ORACLE.needs_web('combien font 2 fois 6'))

    def test_offline_lookup(self):
        self.assertIn('Annecy', ORACLE._offline_lookup('ou est annecy'))
        self.assertIsNone(ORACLE._offline_lookup('ou est la boulangerie'))
        os.environ['OB_ORACLE_FORCE_WEB'] = '1'
        self.assertIsNone(ORACLE._offline_lookup('ou est annecy'))

    def test_math_answers_end_to_end_offline(self):
        res = ORACLE.oracle_answer('combien font 2 fois 6')
        self.assertEqual(res['query_class'], 'MATH')
        self.assertEqual(res['answer'], '= 12')
        self.assertEqual(res['source'], 'math_eval')
        self.assertLess(res['latency_ms'], 8000)
        again = ORACLE.oracle_answer('combien font 2 fois 6')
        self.assertTrue(again.get('cached'), again)

    def test_unavailable_backends_stay_structured(self):
        with mock.patch.object(ORACLE, '_call_gemini_grounded',
                               return_value=None), \
             mock.patch.object(ORACLE, '_call_groq', return_value=None), \
             mock.patch.object(ORACLE, '_call_ollama', return_value=None), \
             mock.patch.object(ORACLE, '_call_llamacpp', return_value=None):
            res = ORACLE.oracle_answer('tell me about bicycles')
        self.assertEqual(res['query_class'], 'GENERAL')
        self.assertEqual(res['source'], 'unavailable')
        self.assertTrue(res['answer'])
        self.assertLessEqual(len(res['answer'].splitlines()), 3)

    def test_push_to_hud_hub_and_bridge(self):
        calls = []

        class Hub:
            def oracle(self, transcript, data, partial=False):
                calls.append(('hub', transcript, partial))

        class Bridge:
            adapter = None

            def __init__(self):
                self.adapter = self

            def push_oracle_answer(self, **kw):
                calls.append(('bridge', kw['query_class']))
                return True

            def push_neural_voice_assistant_hud(self, **kw):
                calls.append(('partial', kw['state_str']))
                return True

        server = mock.Mock()
        server.glasses_hub = Hub()
        server.engo_bridge = Bridge()
        server.activelook = None
        server.glasses_control_port = None
        ans = {'query_class': 'MATH', 'transcript': '2 fois 6', 'answer': '= 12',
               'source': 'math_eval', 'latency_ms': 3}
        before = len(ORACLE.recent_answers())
        self.assertTrue(ORACLE.push_oracle_to_hud(server, ans, mic_source='pc'))
        self.assertIn(('hub', '2 fois 6', False), calls)
        self.assertIn(('bridge', 'MATH'), calls)
        self.assertEqual(len(ORACLE.recent_answers()), before + 1)
        self.assertTrue(ORACLE.push_oracle_to_hud(server, ans, partial=True))
        self.assertIn(('partial', 'ECOUTE ORACLE'), calls)

    def test_vision_model_none_when_unreachable(self):
        with mock.patch('urllib.request.urlopen',
                        side_effect=OSError('no ollama')):
            self.assertIsNone(ORACLE.vision_model())


class MicOracleMatrix(unittest.TestCase):
    SILENCE = b'\x00' * 960
    LOUD = struct.pack('<480h', *([20000] * 480))

    def test_dispatch_validation(self):
        with self.assertRaises(ValueError):
            MO.send_to_oracle()
        r = MO.send_to_oracle(transcript='   ')
        self.assertEqual(r['source'], 'empty')
        self.assertFalse(r['hud_pushed'])

    def test_partial_dispatch_prefetches_and_pushes(self):
        with mock.patch.object(ORACLE, 'prefetch_web', return_value=True), \
             mock.patch.object(ORACLE, 'push_oracle_to_hud',
                               return_value=True) as push:
            r = MO.send_to_oracle(transcript='quel temps', partial=True,
                                  server='srv', mic_source='watch_mic')
        self.assertEqual(r['status'], 'listening')
        self.assertEqual(r['mic_source'], 'watch_mic')
        self.assertTrue(r['hud_pushed'])
        push.assert_called_once()

    def test_http_dispatch_shape(self):
        body = json.dumps({'answer': 'ok'}).encode()

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return body

        seen = {}

        def fake_urlopen(req, timeout=None):
            seen['url'] = req.full_url
            seen['payload'] = json.loads(req.data.decode())
            return Resp()

        with mock.patch('urllib.request.urlopen', fake_urlopen):
            r = MO.send_to_oracle(transcript='bonjour',
                                  server_url='http://pc:9/')
        self.assertEqual(r, {'answer': 'ok'})
        self.assertTrue(seen['url'].endswith('/api/v2/voice/oracle'))
        self.assertEqual(seen['payload']['transcript'], 'bonjour')
        self.assertEqual(seen['payload']['mic_source'], 'pc_mic')

    def test_handle_utterance_reports_and_never_raises(self):
        got, errors = [], []
        with mock.patch.object(MO, 'send_to_oracle',
                               return_value={'answer': '42'}):
            res = MO._handle_utterance(b'x', 'pc_mic', 'fr', None, None,
                                       got.append, errors.append)
        self.assertEqual(res, {'answer': '42'})
        self.assertEqual(got, [{'answer': '42'}])
        self.assertEqual(errors, [])
        with mock.patch.object(MO, 'send_to_oracle',
                               side_effect=RuntimeError('stt down')):
            res = MO._handle_utterance(b'x', 'pc_mic', 'fr', None, None,
                                       got.append, errors.append)
        self.assertIsNone(res)
        self.assertEqual(len(errors), 1)

    def test_vad_caps_and_flush(self):
        vad = MO.VadRecorder(max_ms=120)
        self.assertIsNone(vad.feed(self.LOUD))
        self.assertIsNone(vad.feed(self.LOUD))
        utt = None
        for _ in range(10):
            utt = vad.feed(self.LOUD)
            if utt is not None:
                break
        self.assertIsNotNone(utt)
        self.assertEqual(len(utt), 960 * max(10, 120 // MO.FRAME_MS))
        vad = MO.VadRecorder()
        vad.feed(self.LOUD)
        vad.feed(self.LOUD)
        self.assertIsNotNone(vad.flush())
        self.assertIsNone(MO.VadRecorder().flush())

    def test_transcribe_fast_no_engine(self):
        import sys
        no_fw = mock.patch.dict(sys.modules, {'faster_whisper': None})
        with no_fw, \
             mock.patch('src.ai.stt_local.available', return_value=False):
            with self.assertRaises(RuntimeError):
                MO.transcribe_fast(b'\x00' * 960)
        with no_fw, \
             mock.patch('src.ai.stt_local.available', return_value=True), \
             mock.patch('src.ai.stt_local.transcribe_pcm',
                        return_value={'transcript': ' allume '}):
            self.assertEqual(MO.transcribe_fast(b'\x00' * 960), 'allume')


class EngoBridgeMatrix(unittest.TestCase):
    def test_hud_text_wrap(self):
        from src.adapters import engo_ai_bridge as EB
        self.assertEqual(EB.wrap_text_for_hud(''), [])
        lines = EB.wrap_text_for_hud('one two three four', max_chars=7,
                                     max_lines=4)
        self.assertEqual(lines, ['one two', 'three', 'four'])
        long_word = EB.wrap_text_for_hud('x' * 40, max_chars=28, max_lines=4)
        self.assertEqual(long_word, ['x' * 28, 'x' * 12])
        many = EB.wrap_text_for_hud('a b c d e f g h', max_chars=3,
                                    max_lines=2)
        self.assertEqual(len(many), 2)

    def test_pcm_decode_all_formats(self):
        from src.adapters import engo_ai_bridge as EB
        proxy = EB.AudioStreamingProxy()
        self.assertEqual(proxy.decode_pcm_samples(b''), [])
        raw16 = struct.pack('<4h', 1000, -1000, 0, 32767)
        self.assertEqual(proxy.decode_pcm_samples(raw16),
                         [1000, -1000, 0, 32767])
        stereo = struct.pack('<4h', 100, 200, 300, 400)
        self.assertEqual(proxy.decode_pcm_samples(stereo, channels=2),
                         [150, 350])
        raw_be = struct.pack('>2h', 1000, -2000)
        self.assertEqual(proxy.decode_pcm_samples(raw_be, is_big_endian=True),
                         [1000, -2000])
        self.assertEqual(proxy.decode_pcm_samples(bytes([128, 255, 0]),
                                                  bit_depth=8),
                         [0, 32512, -32768])
        self.assertEqual(proxy.decode_pcm_samples(b'\x00\x00\x01'),
                         [0])  # trailing byte ignored
        s24 = (65536).to_bytes(3, 'little', signed=True)
        self.assertEqual(proxy.decode_pcm_samples(s24, bit_depth=24), [256])
        f32 = struct.pack('<2f', 0.5, -0.5)
        self.assertEqual(proxy.decode_pcm_samples(f32, bit_depth=32),
                         [16383, -16383])

    def test_audio_vad_and_meter(self):
        from src.adapters import engo_ai_bridge as EB
        proxy = EB.AudioStreamingProxy()
        empty = proxy.process_pcm_frame(b'')
        self.assertFalse(empty.is_speech)
        self.assertEqual(empty.db_level, -100.0)
        loud = struct.pack('<480h', *([20000] * 480))
        chunk = proxy.process_pcm_frame(loud)
        self.assertTrue(chunk.is_speech)
        self.assertGreater(chunk.db_level, -10.0)
        self.assertGreater(chunk.duration_ms, 0)
        quiet = proxy.process_pcm_frame(b'\x00' * 960)
        self.assertFalse(quiet.is_speech)
        self.assertLess(proxy.noise_floor_db, -38.0)
        self.assertEqual(EB.AudioStreamingProxy.db_to_vu_percent(-100.0), 0)
        self.assertEqual(EB.AudioStreamingProxy.db_to_vu_percent(-60.0), 0)
        self.assertEqual(EB.AudioStreamingProxy.db_to_vu_percent(0.0), 100)
        self.assertEqual(EB.AudioStreamingProxy.db_to_vu_percent(-30.0), 50)

    def test_streaming_stt_progression(self):
        from src.adapters import engo_ai_bridge as EB
        stt = EB.StreamingSTTRunner()
        self.assertEqual(stt.get_current_transcript(), '')
        stt.arm_session('alpha beta gamma')
        speech = EB.AudioChunk(b'x', 1.0, -5.0, 30, 16000, True)
        text, done = stt.process_stream_chunk(speech)
        self.assertEqual((text, done), ('alpha', False))
        stt.process_stream_chunk(speech)
        text, done = stt.process_stream_chunk(speech)
        self.assertEqual((text, done), ('alpha beta gamma', True))
        idle = EB.StreamingSTTRunner()
        silence = EB.AudioChunk(b'x', 0.0, -90.0, 30, 16000, False)
        text, done = idle.process_stream_chunk(silence)
        self.assertEqual((text, done), ('', False))

    def test_vision_proxy_every_branch_stays_on_hud(self):
        from src.adapters import engo_ai_bridge as EB
        proxy = EB.MultimodalVisionProxy()
        prompts = ['disjoncteur panneau electrique', 'qr oracle receipt',
                   'erreur lave linge', 'allergene nutri score',
                   'danger vehicule angle mort', 'somnolence conducteur yeux',
                   'colis sku entrepot', 'fil tension mur', 'obstacle trottoir',
                   'something entirely different']
        labels = set()
        for prompt in prompts:
            det = proxy.analyze_frame(b'fake', prompt)
            labels.add(det.target_label)
            x0, y0, x1, y1 = det.bounding_box
            self.assertLess(x0, x1)
            self.assertLess(y0, y1)
            self.assertTrue(0 <= x0 and x1 <= 304, det)
            self.assertTrue(0 <= y0 and y1 <= 256, det)
            self.assertTrue(0 <= det.confidence_pct <= 100)
            self.assertTrue(det.diagnostic)
            self.assertTrue(det.action_hint)
        self.assertGreaterEqual(len(labels), 9)
        custom = EB.MultimodalVisionProxy(
            custom_vision_fn=lambda img, p: 'custom diagnosis text here')
        det = custom.analyze_frame(b'fake', 'something else')
        self.assertEqual(det.target_label, 'OBJECT RECOGNISED')
        self.assertIn('custom diagnosis', det.diagnostic)

    def test_telemetry_priority_order(self):
        from src.adapters.activelook import ActiveLookAdapter
        from src.adapters import engo_ai_bridge as EB
        adapter = ActiveLookAdapter(transport=lambda b: None, model='ENGO 3')
        fabric = EB.OpenBridgeTelemetryFabric(adapter)
        self.assertIsNone(fabric.pop_highest_priority())
        fabric.enqueue('ambient', {}, priority=4)
        fabric.enqueue('critical', {}, priority=1)
        fabric.enqueue('assistant', {}, priority=3)
        self.assertEqual(fabric.pop_highest_priority().event_type, 'critical')
        self.assertEqual(fabric.pop_highest_priority().event_type, 'assistant')
        self.assertEqual(fabric.pop_highest_priority().event_type, 'ambient')
        self.assertIsNone(fabric.pop_highest_priority())

    def test_wave_lifecycle_without_hardware(self):
        from src.adapters.activelook import ActiveLookAdapter
        from src.adapters import engo_ai_bridge as EB
        adapter = ActiveLookAdapter(transport=lambda b: None, model='ENGO 3')
        adapter.native_frame = False
        bridge = EB.EngoAIBridge(
            adapter=adapter, ai_inference_fn=lambda q: 'answer:' + q,
            stt_fn=lambda b: 'allume le salon')
        res = bridge.handle_glasses_interaction('wave')
        self.assertEqual(res['status'], 'LISTENING_STARTED')
        self.assertTrue(bridge.phone_state.mic_listening)
        res = bridge.handle_glasses_interaction('wave')
        self.assertEqual(res['status'], 'AI_ANSWERED')
        self.assertFalse(bridge.phone_state.mic_listening)
        self.assertIn('allume', res['query'])
        self.assertIn('answer:', res['answer'])


def make_png(w, h, ctype=2, depth=8):
    """Minimal valid PNG (filter-0 rows) for read-back tests."""
    chunk = lambda k, d: (struct.pack('>I', len(d)) + k + d +
                          struct.pack('>I', zlib.crc32(k + d) & 0xffffffff))
    bpp = 4 if ctype == 6 else 3
    row = b'\x00' + bytes([200]) * (w * bpp)
    body = zlib.compress(row * h, 6)
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, depth, ctype,
                                       0, 0, 0)) +
            chunk(b'IDAT', body) + chunk(b'IEND', b''))


class ReadbackMatrix(unittest.TestCase):
    def test_crop_removes_status_bar(self):
        png = make_png(8, 16)
        out = VR.crop_status_bar(png)
        self.assertTrue(out.startswith(b'\x89PNG\r\n\x1a\n'))
        ihdr = next(d for k, d in VR._chunks(out) if k == b'IHDR')
        w, h = struct.unpack('>II', ihdr[:8])
        self.assertEqual((w, h), (8, 15))
        small = VR.crop_status_bar(png, step=2)
        ihdr = next(d for k, d in VR._chunks(small) if k == b'IHDR')
        w2, h2 = struct.unpack('>II', ihdr[:8])
        self.assertEqual((w2, h2), (4, 8))

    def test_crop_rejects_bad_frames(self):
        with self.assertRaises(ValueError):
            VR.crop_status_bar(b'not a png')
        with self.assertRaises(ValueError):
            VR.crop_status_bar(make_png(8, 8, depth=16))
        with self.assertRaises(ValueError):
            VR.crop_status_bar(make_png(5000, 4000))

    def test_structured_classes(self):
        self.assertEqual(VR.structured_class('x', 'asleep')[0],
                         'screen_off_or_black')
        self.assertEqual(VR.structured_class('DreamActivity', 'awake')[0],
                         'screensaver')
        focus = 'mCurrentFocus=Window{abc u0 %s/MainActivity}'
        self.assertEqual(VR.structured_class(
            focus % 'com.android.tv.settings', 'awake')[0], 'settings')
        self.assertEqual(VR.structured_class(
            focus % 'com.google.android.youtube', 'awake')[0],
            'media_playback')
        self.assertEqual(VR.structured_class(
            focus % 'com.android.tv.launcher', 'awake')[0], 'home_launcher')
        self.assertEqual(VR.structured_class(
            focus % 'com.example.app', 'awake')[0], 'other_app')
        cls, _ = VR.structured_class('nothing focused here', 'awake')
        self.assertIsNone(cls)
        self.assertEqual(VR.structured_class(
            'mCurrentFocus=Window{abc (Application Not Responding)}',
            'awake')[0], 'dialog')

    def _read(self, *args):
        if args == ('dumpsys', 'power'):
            return 'mWakefulness=Awake'
        return ('mCurrentFocus=Window{abc u0 '
                'com.android.tv.settings/MainActivity}')

    def _broker(self, screen, confidence='high'):
        stub = mock.Mock()
        stub.model_id = 'stub-glimmer'
        stub.extra = {}
        stub.options = {}
        stub.ready.return_value = True
        stub._call.return_value = (
            {'screen': screen, 'evidence': 'a settings page',
             'confidence': confidence}, {})
        return stub

    def test_readback_verdicts(self):
        png = make_png(8, 16)
        ok = VR.readback(lambda: png, self._read, self._broker('settings'))
        self.assertEqual(ok['verdict'], 'CONFIRMED')
        self.assertEqual(len(ok['frame_sha256']), 64)
        self.assertNotIn('settings page', json.dumps(ok))
        bad = VR.readback(lambda: png, self._read,
                          self._broker('media_playback'))
        self.assertEqual(bad['verdict'], 'INCONCLUSIVE')
        no_model = VR.readback(lambda: png, self._read, None)
        self.assertEqual(no_model['verdict'], 'STRUCTURED_ONLY')
        no_capture = VR.readback(lambda: b'junk', self._read,
                                 self._broker('settings'))
        self.assertEqual(no_capture['verdict'], 'STRUCTURED_ONLY')
        no_struct = VR.readback(lambda: png, lambda *a: '', self._broker('dialog'))
        self.assertEqual(no_struct['verdict'], 'VISUAL_ONLY')

    def test_glimmer_classify_validates_shape(self):
        png = make_png(8, 16)
        out = VR.glimmer_classify(self._broker('dialog'), png)
        self.assertEqual(out['screen'], 'dialog')
        self.assertEqual(out['evidence_words'], 3)
        with self.assertRaises(VR.ModelBlocked):
            VR.glimmer_classify(self._broker('not_a_class'), png)


class SttBounds(unittest.TestCase):
    def test_clip_bounds(self):
        self.assertEqual(VSTT.MAX_SECONDS, 15)
        self.assertEqual(VSTT.RATE, 16000)
        self.assertLessEqual(VSTT.MAX_SECONDS * VSTT.RATE * 2, 480002)

    def test_available_honors_kill_switch_and_missing_model(self):
        import tempfile
        with mock.patch.dict(os.environ, {'OB_STT_LOCAL': '0'}):
            self.assertFalse(STT.available())
        with tempfile.TemporaryDirectory() as tmp:
            old, STT._home_override = STT._home_override, tmp
            try:
                self.assertIsNone(STT.find_snapshot())
            finally:
                STT._home_override = old


def sample_profile():
    return {'format': PV.FORMAT, 'id': 'acme', 'partner': 'Acme Robotics',
            'version': '1.0.0', 'languages': ['fr', 'en-US'],
            'products': [{'ref': 'acme x5', 'kind': 'vacuum',
                          'names': {'fr': ["l'Acme X5"], 'en-US': ['the Acme X5']},
                          'misheard': {'fr': ['acme x cinq'],
                                       'en': ['ack me ex five']}}],
            'phrases': [{'family': 'vacuum.start', 'dialect': 'fr',
                         'template': 'Envoie {d} en mission'}]}


class PartnerVoiceMatrix(unittest.TestCase):
    def test_validate_accepts_and_rejects(self):
        PV.validate(sample_profile())
        bad_format = dict(sample_profile(), format='nope')
        with self.assertRaises(PV.ProfileError):
            PV.validate(bad_format)
        bad_id = sample_profile()
        bad_id['id'] = 'ACME!'
        with self.assertRaises(PV.ProfileError):
            PV.validate(bad_id)
        bad_kind = sample_profile()
        bad_kind['products'][0]['kind'] = 'starship'
        with self.assertRaises(PV.ProfileError):
            PV.validate(bad_kind)
        bad_dialect = sample_profile()
        bad_dialect['phrases'][0]['dialect'] = 'de'
        with self.assertRaises(PV.ProfileError):
            PV.validate(bad_dialect)
        dup = sample_profile()
        dup['products'] = [dup['products'][0], dict(dup['products'][0])]
        with self.assertRaises(PV.ProfileError):
            PV.validate(dup)

    def test_repairs_feed_matching_only(self):
        prof = PV.validate(sample_profile())
        vocab = PV.repairs(prof)
        self.assertTrue(vocab)
        fixed, labels = PV.apply('demarre ack me ex five', 'en', vocab)
        self.assertNotIn('ack me ex five', fixed)
        self.assertIn('acme x5', fixed)
        self.assertTrue(labels and 'acme' in labels[0])
        untouched, labels = PV.apply('demarre ack me ex five', 'fr', vocab)
        self.assertEqual(untouched, 'demarre ack me ex five')
        self.assertEqual(labels, [])

    def test_load_dir_and_coverage(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'acme.json'
            path.write_text(json.dumps(sample_profile()), encoding='utf-8')
            (Path(tmp) / 'broken.json').write_text('{nope', encoding='utf-8')
            loaded = PV.load_dir(tmp)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(PV.load_dir(str(path)), [])
        cov = PV.coverage(sample_profile())
        self.assertTrue(cov['fr']['ready'], cov)
        self.assertTrue(cov['en-US']['ready'], cov)


class CustomProviderMatrix(unittest.TestCase):
    def entry(self, **over):
        base = {'name': 'lan-ollama', 'kind': 'ollama',
                'base_url': 'http://192.168.1.20:11434', 'model': 'qwen:test'}
        base.update(over)
        return base

    def test_validate_rules(self):
        clean = CP.validate(self.entry(name='  LAN-Box '))
        self.assertEqual(clean['name'], 'lan-box')
        with self.assertRaises(CP.ProviderError):
            CP.validate(self.entry(api_key='secret'))
        with self.assertRaises(CP.ProviderError):
            CP.validate(self.entry(base_url='http://8.8.8.8:11434'))
        CP.validate(self.entry(base_url='https://example.com'))
        CP.validate(self.entry(base_url='http://127.0.0.1:11434'))
        with self.assertRaises(CP.ProviderError):
            CP.validate(self.entry(kind='nope'))
        with self.assertRaises(CP.ProviderError):
            CP.validate(self.entry(model='bad model!'))
        with self.assertRaises(CP.ProviderError):
            CP.validate(self.entry(timeout_s=2))
        with self.assertRaises(CP.ProviderError):
            CP.validate(self.entry(json_mode='yes'))

    def test_execution_and_endpoint(self):
        self.assertEqual(CP.execution(CP.validate(self.entry())), 'remote')
        local = CP.validate(self.entry(base_url='http://127.0.0.1:11434'))
        self.assertEqual(CP.execution(local), 'local')
        self.assertTrue(CP.endpoint(local).endswith('/api/chat'))
        oc = CP.validate(self.entry(kind='openai',
                                    base_url='http://127.0.0.1:1234'))
        self.assertTrue(CP.endpoint(oc).endswith('/chat/completions'))

    def test_add_get_activate_remove_roundtrip(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'ai_providers.json')
            self.assertIsNone(CP.active(path=path))
            CP.add(self.entry(), path=path)
            self.assertEqual(CP.active(path=path)['name'], 'lan-ollama')
            CP.add(self.entry(name='second'), activate=False, path=path)
            self.assertEqual(CP.active(path=path)['name'], 'lan-ollama')
            CP.set_active('second', path=path)
            self.assertEqual(CP.active(path=path)['name'], 'second')
            with self.assertRaises(CP.ProviderError):
                CP.set_active('ghost', path=path)
            self.assertTrue(CP.remove('second', path=path))
            self.assertIsNone(CP.active(path=path))
            self.assertFalse(CP.remove('ghost', path=path))

    def test_public_view_never_leaks_keys(self):
        clean = CP.validate(self.entry(api_key_env='OB_TEST_KEY_X9'))
        with mock.patch.dict(os.environ, {'OB_TEST_KEY_X9': 's3cret'}):
            view = CP.public_view(clean, vault=mock.Mock(
                **{'get.side_effect': OSError('no vault')}))
        self.assertTrue(view['has_key'])
        dumped = json.dumps(view)
        self.assertNotIn('"api_key":', dumped)
        self.assertNotIn('s3cret', dumped)
        self.assertIn(view['execution'], ('local', 'remote'))

    def test_broker_redirect_and_facts(self):
        with self.assertRaises(AI_BROKER.ModelBlocked):
            AI_BROKER.NoRedirect().redirect_request('req', 'fp', 302, 'msg',
                                                    {}, 'http://x/')
        for fact in ('battery_percent', 'storage_free_gb',
                     'screen_timeout_seconds'):
            self.assertIn(fact, AI_BROKER.ALLOWED_FACTS)


class AdapterPresence(unittest.TestCase):
    ADAPTERS = ['activelook', 'activelook_emulator', 'esphome_light',
                'esphome_light_emulator', 'fritzbox_router',
                'fritzbox_router_emulator', 'openwrt_router',
                'openwrt_router_emulator', 'tuya_local', 'upnp_igd', 'mqtt',
                'freebox', 'home_assistant', 'android', 'retroarch',
                'windows_bridge', 'simulated']

    def test_every_adapter_imports_without_hardware(self):
        import importlib
        for name in self.ADAPTERS:
            with self.subTest(adapter=name):
                mod = importlib.import_module('src.adapters.' + name)
                self.assertTrue(mod.__name__.endswith(name))

    def test_emulator_pairs_exist(self):
        from src.adapters import activelook_emulator as ALE
        from src.adapters import esphome_light_emulator as ESP
        from src.adapters import fritzbox_router_emulator as FRITZ
        from src.adapters import openwrt_router_emulator as OPENWRT
        self.assertTrue(hasattr(ALE, 'parse_frames'))
        self.assertTrue(hasattr(ESP, 'EsphomeLightEmulator'))
        self.assertTrue(hasattr(FRITZ, 'FritzboxRouterEmulator'))
        self.assertTrue(hasattr(OPENWRT, 'OpenwrtRouterEmulator'))
        from src.adapters import simulated
        self.assertTrue(callable(simulated.discover))


if __name__ == '__main__':
    unittest.main()
