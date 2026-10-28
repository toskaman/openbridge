"""Command Center P0 (SIMULATED_VERIFIED: intent/registry/router/cost-guard unit tests, fake transports)."""
import unittest

from src.runtime.intent import (
    INTENT_VERSION, new_intent, validate_intent, IntentError,
    STATUS, RISK, LANGS,
)


def draft(**kw):
    d = {'intent_id': 'int-abc123', 'version': 1, 'raw_text': 'Start my vacuum',
         'lang': 'en', 'outcome': None, 'targets': [], 'skill_id': None, 'params': {},
         'confidence': None, 'ambiguities': [], 'clarifying_question': None,
         'risk_level': 'low', 'status': 'draft',
         'provenance': {'parser': 'rules', 'model_id': None}}
    d.update(kw)
    return d


class IntentContract(unittest.TestCase):
    def test_version_constant_is_1(self):
        self.assertEqual(INTENT_VERSION, 1)

    def test_valid_draft_passes(self):
        self.assertEqual(validate_intent(draft()), [])

    def test_new_intent_builds_versioned_draft(self):
        d = new_intent('Allume mon aspirateur', 'fr')
        self.assertEqual(d['version'], 1)
        self.assertEqual(d['lang'], 'fr')
        self.assertEqual(d['status'], 'draft')
        self.assertTrue(d['intent_id'].startswith('int-'))
        self.assertEqual(validate_intent(d), [])

    def test_new_intent_rejects_bad_lang_and_empty_text(self):
        with self.assertRaises(IntentError):
            new_intent('hi', 'de')
        with self.assertRaises(IntentError):
            new_intent('   ', 'en')

    def test_validate_rejects_unknown_fields_and_bad_enums(self):
        d = draft(evil=True)
        self.assertTrue(any('evil' in e for e in validate_intent(d)))
        self.assertTrue(validate_intent(draft(lang='xx')))
        self.assertTrue(validate_intent(draft(status='magic')))
        self.assertTrue(validate_intent(draft(risk_level='extreme')))
        self.assertTrue(validate_intent(draft(confidence=2.0)))

    def test_resolved_intent_needs_skill_outcome_and_confidence(self):
        self.assertTrue(validate_intent(draft(status='resolved')))
        d = draft(status='resolved', skill_id='vacuum.start', outcome='start cleaning',
                  confidence=0.9, targets=[{'kind': 'device', 'ref': 'vacuum-1'}])
        self.assertEqual(validate_intent(d), [])

    def test_needs_clarification_requires_a_question(self):
        self.assertTrue(validate_intent(draft(status='needs_clarification')))
        d = draft(status='needs_clarification', clarifying_question='Power on or start cleaning?',
                  ambiguities=['power vs clean'])
        self.assertEqual(validate_intent(d), [])

    def test_status_risk_lang_vocabularies(self):
        self.assertIn('escalation_required', STATUS)
        self.assertIn('unsupported', STATUS)
        self.assertEqual(RISK, ('low', 'medium', 'high'))
        self.assertEqual(LANGS, ('en', 'fr'))


class SkillRegistry(unittest.TestCase):
    def test_b2_skills_are_registered_with_contracts(self):
        from src.runtime.skills import get, validate_contract
        for sid in ('ble_scan_room', 'device_facts', 'tv_volume_set', 'tv_volume_step'):
            c = get(sid)
            self.assertIsNotNone(c, sid)
            self.assertEqual(validate_contract(c), [], sid)

    def test_vacuum_skills_exist_with_typed_commands(self):
        from src.runtime.skills import get, validate_contract
        c = get('vacuum.start')
        self.assertIsNotNone(c)
        self.assertEqual(c['primitive_id'], 'tuya_command')
        self.assertEqual(c['params'], {'command': 'start'})
        self.assertEqual(validate_contract(c), [])
        self.assertIsNotNone(get('vacuum.pause'))
        self.assertIsNotNone(get('vacuum.dock'))

    def test_verification_status_is_honest(self):
        from src.runtime.skills import get, VERIFICATION
        self.assertIn(get('ble_scan_room')['verification'], VERIFICATION)
        self.assertIn(get('vacuum.start')['verification'], VERIFICATION)
        # Nothing may claim verified_physical without a cited receipt.
        self.assertNotEqual(get('vacuum.start')['verification'], 'verified_physical')

    def test_match_finds_skills_by_keyword(self):
        from src.runtime.skills import match
        self.assertIn('vacuum.start', [c['skill_id'] for c in match('vacuum')])
        self.assertIn('ble_scan_room', [c['skill_id'] for c in match('bluetooth')])
        self.assertEqual(match('teleport'), [])

    def test_unknown_or_unavailable_never_resolves(self):
        from src.runtime.skills import resolve, SkillError
        with self.assertRaises(SkillError):
            resolve('does.not.exist', {})
        with self.assertRaises(SkillError):
            resolve('screens.off', {})


class FakeTransport:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def ready(self):
        return True

    def __call__(self, prompt):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        return self.reply


def cloud_response(content):
    return {'id': 'req-1', 'model': 'muse-spark-1.3',
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50},
            'choices': [{'message': {'content': content}}]}


def good_reply():
    return {'outcome': 'start cleaning', 'skill_id': 'vacuum.start',
            'targets': [{'kind': 'device', 'ref': 'vacuum-1'}],
            'params': {}, 'confidence': 0.9, 'ambiguities': [],
            'clarifying_question': None}


class NLRouter(unittest.TestCase):
    def test_tier_table_matches_runtime_manifest(self):
        import json
        from src.runtime.nl_router import TIERS
        manifest = json.load(open('config/runtime_models.json', encoding='utf-8'))
        declared = {(e['model_id'], e['endpoint']) for e in manifest['model_calls']}
        for quality in ('low', 'medium', 'high'):
            self.assertIn(TIERS[quality], declared, quality)

    def test_valid_local_reply_resolves_intent(self):
        from src.runtime.nl_router import parse
        d = parse('Start my vacuum', 'en', 'low', FakeTransport(good_reply()), None)
        self.assertEqual(d['status'], 'resolved')
        self.assertEqual(d['skill_id'], 'vacuum.start')
        self.assertEqual(d['provenance']['parser'], 'local')

    def test_unknown_skill_is_unsupported_never_invented(self):
        from src.runtime.nl_router import parse
        r = good_reply(); r['skill_id'] = 'teleport.home'
        d = parse('Beam me home', 'en', 'low', FakeTransport(r), None)
        self.assertEqual(d['status'], 'unsupported')

    def test_low_confidence_escalates(self):
        from src.runtime.nl_router import parse
        r = good_reply(); r['confidence'] = 0.2
        d = parse('maybe vacuum?', 'en', 'low', FakeTransport(r), None)
        self.assertEqual(d['status'], 'escalation_required')

    def test_transport_failure_escalates_without_raising(self):
        from src.runtime.nl_router import parse, TransportError
        d = parse('Start my vacuum', 'en', 'low', FakeTransport(error=TransportError('down')), None)
        self.assertEqual(d['status'], 'escalation_required')

    def test_auto_stays_local_without_cloud_consent(self):
        from src.runtime.nl_router import parse, TransportError
        cloud = FakeTransport(good_reply())
        d = parse('Start my vacuum', 'en', 'auto',
                  FakeTransport(error=TransportError('down')), cloud, cloud_allowed=False)
        self.assertEqual(d['status'], 'escalation_required')
        self.assertEqual(cloud.calls, [])
        self.assertTrue(any('cloud' in a.lower() for a in d['ambiguities']))

    def test_auto_uses_cloud_only_with_consent(self):
        from src.runtime.nl_router import parse, TransportError
        d = parse('Start my vacuum', 'en', 'auto',
                  FakeTransport(error=TransportError('down')),
                  FakeTransport(good_reply()), cloud_allowed=True)
        self.assertEqual(d['status'], 'resolved')
        self.assertEqual(d['provenance']['parser'], 'cloud')

    def test_model_abstention_with_unique_keyword_hit_resolves(self):
        from src.runtime.nl_router import parse
        r = good_reply(); r['skill_id'] = None; r['confidence'] = 0.0
        r['clarifying_question'] = None
        d = parse('Start my vacuum', 'en', 'low', FakeTransport(r), None)
        self.assertEqual(d['status'], 'resolved')
        self.assertEqual(d['skill_id'], 'vacuum.start')
        self.assertTrue(any('deterministic' in a for a in d['ambiguities']))

    def test_model_abstention_without_unique_hit_stays_unsupported(self):
        from src.runtime.nl_router import parse
        r = good_reply(); r['skill_id'] = None; r['confidence'] = 0.0
        r['clarifying_question'] = None; r['outcome'] = 'do the thing'
        d = parse('Do the thing', 'en', 'low', FakeTransport(r), None)
        self.assertEqual(d['status'], 'unsupported')

    def test_prompt_carries_catalog_and_text_without_secrets(self):
        from src.runtime.nl_router import build_prompt
        p = build_prompt('Démarre mon aspirateur', 'fr')
        self.assertIn('Démarre mon aspirateur', p)
        self.assertIn('vacuum.start', p)
        self.assertIn('ble_scan_room', p)
        self.assertNotIn('Bearer', p)
        self.assertNotIn('sk-', p)


class CostGuard(unittest.TestCase):
    def test_estimates_match_broker_reservation(self):
        from src.ai.broker import RESERVATION_MICRO_USD
        from src.runtime.cost_guard import estimate_usd
        self.assertEqual(estimate_usd('low'), 0.0)
        self.assertEqual(estimate_usd('medium'), 0.0)
        self.assertEqual(estimate_usd('high'), RESERVATION_MICRO_USD / 1_000_000)

    def test_cloud_needs_consent_and_kill_switch(self):
        from src.runtime.cost_guard import require_cloud, CostBlocked
        require_cloud(True, cloud_enabled=True)
        with self.assertRaises(CostBlocked):
            require_cloud(False, cloud_enabled=True)
        with self.assertRaises(CostBlocked):
            require_cloud(True, cloud_enabled=False)

    def test_budget_blocks_over_ceiling(self):
        import tempfile, os
        from src.runtime.cost_guard import check_budget, reserve, CostBlocked
        db = os.path.join(tempfile.mkdtemp(), 'b.sqlite')
        check_budget(db, 'obs-1', 200_000, 100_000)
        reserve(db, 'obs-1', 100_000)
        check_budget(db, 'obs-1', 200_000, 100_000)
        reserve(db, 'obs-1', 100_000)
        with self.assertRaises(CostBlocked):
            check_budget(db, 'obs-1', 200_000, 100_000)

    def test_budget_uses_broker_reservations_table(self):
        import tempfile, os, sqlite3
        from src.runtime.cost_guard import reserve
        db = os.path.join(tempfile.mkdtemp(), 'b.sqlite')
        reserve(db, 'obs-9', 50_000)
        con = sqlite3.connect(db)
        row = con.execute('SELECT observation, reserved FROM reservations').fetchone()
        con.close()
        self.assertEqual(row, ('obs-9', 50_000))


def vacuum_intent(**kw):
    d = draft(status='resolved', skill_id='vacuum.start', outcome='start cleaning',
              confidence=0.9, targets=[{'kind': 'device', 'ref': 'vacuum'}])
    d.update(kw)
    return d


def fake_devices():
    return {'dev-vac1': {'key': 'dev-vac1', 'category': 'vacuum', 'label': 'Roborock'},
            'dev-tv1': {'key': 'dev-tv1', 'category': 'tv', 'label': 'Living room TV'}}


class FakeRouter:
    def __init__(self):
        self.calls = []

    def skill_routes(self, skill_id, target=None):
        self.calls.append(('routes', skill_id, target))
        return {'selected_route_id': 'rt-1', 'routes': []}

    def arm(self, body, actor='owner', invocation_id=None):
        self.calls.append(('arm', body))
        return {'invocation_id': 'inv-1', 'route_id': 'rt-1', 'lease_id': 'ls-1',
                'graph_revision': {'seq': 1}}

    def invoke(self, body, actor='owner'):
        self.calls.append(('invoke', body))
        return {'state': 'VERIFIED', 'transaction_id': 'tx-1'}


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, primitive_id, device_key, params, consent=False):
        self.calls.append((primitive_id, device_key, params, consent))
        return {'state': 'VERIFIED', 'transaction_id': 'tx-9'}


class FakeServer:
    def __init__(self):
        from types import SimpleNamespace
        self.reg = SimpleNamespace(devices=fake_devices())
        self.skill_router = FakeRouter()
        self.runtime_executor = FakeExecutor()
        self.fabric_registry = self.reg


class CommandService(unittest.TestCase):
    def test_resolve_exact_label_and_single_category(self):
        from src.runtime.command import resolve_targets
        self.assertEqual(resolve_targets([{'kind': 'device', 'ref': 'Roborock'}], fake_devices()),
                         ['dev-vac1'])
        self.assertEqual(resolve_targets([{'kind': 'device', 'ref': 'vacuum'}], fake_devices()),
                         ['dev-vac1'])

    def test_resolve_rejects_missing_and_ambiguous(self):
        from src.runtime.command import resolve_targets, CommandError
        with self.assertRaises(CommandError):
            resolve_targets([{'kind': 'device', 'ref': 'toaster'}], fake_devices())
        devs = dict(fake_devices())
        devs['dev-tv2'] = {'key': 'dev-tv2', 'category': 'tv', 'label': 'TV'}
        with self.assertRaises(CommandError):
            resolve_targets([{'kind': 'device', 'ref': 'tv'}], devs)

    def test_ollama_transport_parses_strict_json(self):
        from src.runtime.nl_router import OllamaIntentTransport, TransportError
        t = OllamaIntentTransport(
            'llama3.2:3b-instruct-q4_K_M', 'http://127.0.0.1:11437',
            catalog=lambda: {'models': [{'name': 'llama3.2:3b-instruct-q4_K_M',
                                          'digest': 'sha256:a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72'}]},
            chat=lambda p: {'model': 'llama3.2:3b-instruct-q4_K_M', 'done': True, 'done_reason': 'stop',
                            'message': {'content': '{"a": 1}'}, 'prompt_eval_count': 10, 'eval_count': 5})
        self.assertTrue(t.ready())
        self.assertEqual(t('prompt'), {'a': 1})
        bad = OllamaIntentTransport('m', 'e', catalog=lambda: {}, chat=lambda p: {'model': 'evil'})
        with self.assertRaises(TransportError):
            bad('prompt')

    def test_approve_previews_without_dispatch(self):
        from src.runtime.command import approve
        srv = FakeServer()
        prev = approve(srv, vacuum_intent())
        self.assertEqual(prev['device_keys'], ['dev-vac1'])
        self.assertEqual(prev['primitive_id'], 'tuya_command')
        self.assertEqual(srv.runtime_executor.calls, [])

    def test_approve_rejects_unresolved_intent(self):
        from src.runtime.command import approve, CommandError
        with self.assertRaises(CommandError):
            approve(FakeServer(), draft(status='unsupported'))

    def test_execute_needs_consent_and_dispatches_once(self):
        from src.runtime.command import execute, CommandError
        srv = FakeServer()
        with self.assertRaises(CommandError):
            execute(srv, vacuum_intent(), consent=False)
        rc = execute(srv, vacuum_intent(), consent=True)
        self.assertEqual(rc['transaction_id'], 'tx-9')
        self.assertEqual(len(srv.runtime_executor.calls), 1)
        self.assertTrue(srv.runtime_executor.calls[0][3])

    def test_execute_reresolves_fresh_targets(self):
        from src.runtime.command import execute, CommandError
        srv = FakeServer()
        srv.reg.devices = {}
        with self.assertRaises(CommandError):
            execute(srv, vacuum_intent(), consent=True)
        self.assertEqual(srv.runtime_executor.calls, [])


class CloudTransport(unittest.TestCase):
    def test_valid_cloud_reply_parses_with_usage(self):
        import json
        from src.runtime.nl_router import CloudIntentTransport
        t = CloudIntentTransport('muse-spark-1.3', 'https://api.meta.ai/v1/chat/completions',
                                 send=lambda p: cloud_response(json.dumps(good_reply())))
        self.assertEqual(t('prompt'), good_reply())
        self.assertEqual(t.last_usage['usage']['prompt_tokens'], 100)
        self.assertIn('estimated_cost_usd', t.last_usage)

    def test_wrong_model_identity_rejected(self):
        from src.runtime.nl_router import CloudIntentTransport, TransportError
        r = cloud_response('{}'); r['model'] = 'evil-1'
        t = CloudIntentTransport('muse-spark-1.3', 'e', send=lambda p: r)
        with self.assertRaises(TransportError):
            t('prompt')

    def test_before_cloud_gate_blocks_without_calling(self):
        from src.runtime.nl_router import parse, TransportError
        def gate():
            raise TransportError('cloud budget exhausted')
        cloud = FakeTransport(good_reply())
        d = parse('Start my vacuum', 'en', 'auto',
                  FakeTransport(error=TransportError('down')), cloud,
                  cloud_allowed=True, before_cloud=gate)
        self.assertEqual(d['status'], 'escalation_required')
        self.assertEqual(cloud.calls, [])


def api_server():
    srv = FakeServer()
    srv.model_broker = None
    srv.command_cloud_enabled = True
    srv.command_low = FakeTransport(good_reply())
    srv.command_medium = FakeTransport(good_reply())
    srv.command_cloud = None
    return srv


class CommandAPI(unittest.TestCase):
    def test_tiers_reports_readiness(self):
        from src.runtime.api_v2 import get
        status, body = get(api_server(), '/api/v2/command/tiers', '')
        self.assertEqual(status, 200)
        self.assertTrue(body['low']['ready'])
        self.assertEqual(body['low']['model'], 'llama3.2:3b-instruct-q4_K_M')
        self.assertFalse(body['high']['configured'])
        self.assertEqual(body['high']['estimate_usd'], 0.10)

    def test_parse_returns_intent_and_estimate(self):
        from src.runtime.api_v2 import post
        status, body = post(api_server(), '/api/v2/command/parse',
                            {'text': 'Start my vacuum', 'lang': 'en', 'quality': 'low'})
        self.assertEqual(status, 200)
        self.assertEqual(body['intent']['status'], 'resolved')
        self.assertEqual(body['estimate_usd'], 0.0)

    def test_parse_rejects_bad_body(self):
        from src.runtime.api_v2 import post
        self.assertEqual(post(api_server(), '/api/v2/command/parse', {})[0], 400)
        self.assertEqual(post(api_server(), '/api/v2/command/parse', {'text': 'x' * 3000})[0], 400)
        self.assertEqual(post(api_server(), '/api/v2/command/parse', {'text': 'hi', 'quality': 'ultra'})[0], 400)

    def test_parse_high_without_consent_is_409(self):
        from src.runtime.api_v2 import post
        status, body = post(api_server(), '/api/v2/command/parse',
                            {'text': 'Start my vacuum', 'quality': 'high'})
        self.assertEqual(status, 409)

    def test_approve_and_execute_roundtrip(self):
        from src.runtime.api_v2 import post
        srv = api_server()
        status, prev = post(srv, '/api/v2/command/approve', {'intent': vacuum_intent()})
        self.assertEqual(status, 200)
        self.assertEqual(prev['device_keys'], ['dev-vac1'])
        self.assertEqual(srv.runtime_executor.calls, [])
        status, rc = post(srv, '/api/v2/command/execute', {'intent': vacuum_intent(), 'consent': True})
        self.assertEqual(status, 200)
        self.assertEqual(rc['transaction_id'], 'tx-9')

    def test_execute_without_consent_is_400(self):
        from src.runtime.api_v2 import post
        status, body = post(api_server(), '/api/v2/command/execute',
                            {'intent': vacuum_intent(), 'consent': False})
        self.assertEqual(status, 400)

    def test_approve_unknown_skill_is_400(self):
        from src.runtime.api_v2 import post
        d = vacuum_intent(); d['skill_id'] = 'nope.nope'
        self.assertEqual(post(api_server(), '/api/v2/command/approve', {'intent': d})[0], 400)

    def test_approve_without_registry_is_503(self):
        from src.runtime.api_v2 import post
        srv = api_server()
        srv.fabric_registry = None
        self.assertEqual(post(srv, '/api/v2/command/approve', {'intent': vacuum_intent()})[0], 503)
