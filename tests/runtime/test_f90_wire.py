"""F90 wiring (e3-wire): the four formerly dead modules invoked end-to-end.

Each test drives a production entry point (an api_v2 route or a CLI command)
and asserts on real module behavior — relay sends counted, reports quoted,
records transitioned — never on imports alone.
"""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from types import SimpleNamespace
from unittest import mock

from src import cli
from src.fabric import relay as R
from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.fabric.registry import Registry
from src.fabric.relay import RelayManager
from src.forge.fixtures import manifest
from src.runtime.api_v2 import get, post

from tests.fabric.test_diagnostics import dev, fact
from tests.fabric.test_route_intel import PHONE_KEY, TARGET, TV_KEY, SimRelay
from tests.forge.test_transplant import NOW, PRIMS, bundle, companions, links
from tests.runtime.test_nl_followup import VAC_PRIOR, prior_doc


def relay_server(phone=None, tv=None):
    phone = phone if phone is not None else SimRelay(PHONE_KEY)
    tv = tv if tv is not None else SimRelay(TV_KEY)
    manager = R.RelayManager(lambda entry, msg: entry['sim'](entry, msg))
    manager.enroll('phone', PHONE_KEY, 'dev-phone',
                   {'capabilities': ['ble_scan'],
                    'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True},
                    'battery_powered': True})
    manager.enroll('tv', TV_KEY, 'dev-tv',
                   {'capabilities': ['ble_scan'],
                    'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
    manager.relays['phone']['sim'] = phone
    manager.relays['tv']['sim'] = tv
    return SimpleNamespace(relays=manager), phone, tv


def registry_server():
    reg = Registry()
    for name, cat, serial in (('Living room TV', 'tv', 'tv-1'), ('Roborock', 'vacuum', 'vac-1')):
        key = reg.upsert([Identifier('android_serial', serial, True)], category=cat,
                         label=name,
                         observations=[DeviceObservation('model', name, 'ADB', 'WIFI', now(), True)])
        reg.devices[key]['handles'] = {'WIFI': 'h-' + serial}
        reg.link(Link('pc', key, 'WIFI', ('observe', 'read', 'control'), 'ADB:device'))
    return SimpleNamespace(fabric_registry=reg, fabric_snapshot=reg.snapshot(),
                           command_low=None, command_medium=None, command_cloud=None,
                           command_cloud_enabled=True, model_broker=None)


def transplant_request(**over):
    req = {'companions': companions(), 'links': links(),
           'source_capability_id': 'tv.ble.observations', 'target_id': 'tgt-1',
           'intent': 'mirror ble observations', 'bundle': bundle(),
           'primitive_ids': list(PRIMS), 'manifest': manifest(),
           'model_run': {'model': 'stub-meta-1', 'run_id': 'run-1'},
           'title': 'Mirror observations', 'facts_required': [],
           'expires_at': NOW + 60, 'target_category': 'tv', 'consent': True}
    req.update(over)
    return json.loads(json.dumps(req))  # must survive an HTTP round-trip


def battery_bundle():
    return {'devices': [dev('phone-1', 'phone', 'Pixel',
                            fact('battery_percent', 18),
                            fact('battery_charging', False),
                            fact('battery_discharge_pct_per_hour', 8.0),
                            fact('top_consumer', 'Maps'))]}


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class RouteIntelAPI(unittest.TestCase):
    def test_enumerate_over_get_route(self):
        server, _, _ = relay_server()
        status, body = get(server, '/api/v2/route_intel', 'target=' + TARGET)
        self.assertEqual(status, 200)
        self.assertEqual([r['relay_id'] for r in body['routes']], ['tv', 'phone'])
        self.assertEqual(body['selected']['relay_id'], 'tv')
        self.assertEqual(body['routes'][0]['hops'], ['pc', 'tv', TARGET])

    def test_enumerate_needs_target(self):
        server, _, _ = relay_server()
        self.assertEqual(get(server, '/api/v2/route_intel', '')[0], 400)

    def test_dispatch_transmits_exactly_once_on_best_route(self):
        server, phone, tv = relay_server()
        status, body = post(server, '/api/v2/route_intel/dispatch',
                            {'target': TARGET, 'op': 'get_status'})
        self.assertEqual(status, 200)
        self.assertEqual(body['outcome'], 'ACKED')
        self.assertEqual(body['route']['relay_id'], 'tv')
        self.assertEqual(body['reply'], {'ok': True})
        self.assertEqual(len(tv.sends), 1)
        self.assertEqual(phone.sends, [])

    def test_dispatch_to_unknown_relay_sends_nothing(self):
        server, phone, tv = relay_server()
        status, body = post(server, '/api/v2/route_intel/dispatch',
                            {'target': TARGET, 'op': 'get_status', 'relay_id': 'nope'})
        self.assertEqual(status, 200)
        self.assertEqual(body['outcome'], 'NOT_SENT')
        self.assertEqual(phone.sends, [])
        self.assertEqual(tv.sends, [])

    def test_failover_redispatches_not_sent_as_fresh_command(self):
        server, phone, tv = relay_server()
        _, blocked = post(server, '/api/v2/route_intel/dispatch',
                          {'target': TARGET, 'op': 'get_status',
                           'relay_id': 'tv', 'down': ['tv']})
        self.assertEqual(blocked['outcome'], 'NOT_SENT')
        self.assertIsNotNone(blocked['command'])
        status, body = post(server, '/api/v2/route_intel/failover',
                            {'record': blocked, 'down': ['tv']})
        self.assertEqual(status, 200)
        self.assertEqual(body['outcome'], 'ACKED')
        self.assertEqual(body['route']['relay_id'], 'phone')
        self.assertNotEqual(body['command']['nonce'], blocked['command']['nonce'])
        self.assertEqual(len(phone.sends), 1)
        self.assertEqual(tv.sends, [])

    def test_failover_refuses_uncertain_without_transmitting(self):
        flaky = SimRelay(PHONE_KEY, fail=OSError('link dropped mid-send'))
        server, _, _ = relay_server(phone=flaky, tv=SimRelay(TV_KEY, fail=OSError('x')))
        _, first = post(server, '/api/v2/route_intel/dispatch',
                        {'target': TARGET, 'op': 'get_status', 'relay_id': 'phone'})
        self.assertEqual(first['outcome'], 'UNCERTAIN')
        sends_before = len(flaky.sends)
        status, body = post(server, '/api/v2/route_intel/failover', {'record': first})
        self.assertEqual(status, 409)
        self.assertEqual(len(flaky.sends), sends_before)

    def test_simulate_loss_reports_survivor(self):
        server, _, _ = relay_server()
        status, body = post(server, '/api/v2/route_intel/simulate_loss',
                            {'target': TARGET, 'lost_relay': 'tv'})
        self.assertEqual(status, 200)
        self.assertEqual(body['lost']['relay_id'], 'tv')
        self.assertEqual(body['alternate']['relay_id'], 'phone')
        self.assertEqual([r['relay_id'] for r in body['remaining']], ['phone'])

    def test_unknown_route_intel_route_is_404(self):
        server, _, _ = relay_server()
        self.assertEqual(post(server, '/api/v2/route_intel/nope', {})[0], 404)


class DiagnoseAPI(unittest.TestCase):
    def test_diagnose_answers_from_observed_facts(self):
        server = SimpleNamespace()
        status, body = post(server, '/api/v2/diagnose',
                            {'question': 'battery_drain', 'bundle': battery_bundle()})
        self.assertEqual(status, 200)
        self.assertEqual(body['confidence'], 'high')
        self.assertIn('8.0', body['explanation'])
        self.assertIn('Maps', body['explanation'])
        ids = [r['id'] for r in body['recommendations']]
        self.assertIn('check_top_consumer', ids)
        self.assertIn('plug_in_charger', ids)
        self.assertEqual(body['mode'], 'deterministic')
        self.assertEqual(body['model'], 'stub-meta-1')

    def test_diagnose_rejects_unknown_question(self):
        server = SimpleNamespace()
        status, body = post(server, '/api/v2/diagnose',
                            {'question': 'why_is_the_sky_blue', 'bundle': battery_bundle()})
        self.assertEqual(status, 400)
        self.assertIn('error', body)


class TransplantAPI(unittest.TestCase):
    def test_full_lifecycle_over_api(self):
        server = SimpleNamespace()
        status, out = post(server, '/api/v2/transplant/run', transplant_request())
        self.assertEqual(status, 200)
        self.assertEqual(out['state'], 'active')
        tid = out['transplant_id']
        self.assertTrue(tid.startswith('tx-'))
        stages = {k: v['status'] for k, v in out['report'].items()}
        self.assertEqual(stages['discover_source'], 'ok')
        self.assertEqual(stages['dispatch'], 'ok')
        self.assertEqual(stages['verify'], 'ok')
        self.assertIn("via stub-meta-1", out['report']['propose']['detail'])
        status, rep = post(server, '/api/v2/transplant/report', {'transplant_id': tid})
        self.assertEqual(status, 200)
        self.assertEqual(rep['report']['verify']['status'], 'ok')
        status, got = post(server, '/api/v2/transplant/get', {'transplant_id': tid})
        self.assertEqual((status, got['state']), (200, 'active'))
        status, rev = post(server, '/api/v2/transplant/revoke', {'transplant_id': tid})
        self.assertEqual((status, rev['state']), (200, 'revoked'))
        status, got = post(server, '/api/v2/transplant/get', {'transplant_id': tid})
        self.assertEqual((status, got['state']), (200, 'revoked'))

    def test_run_ids_are_server_unique(self):
        server = SimpleNamespace()
        _, first = post(server, '/api/v2/transplant/run', transplant_request())
        _, second = post(server, '/api/v2/transplant/run', transplant_request())
        self.assertNotEqual(first['transplant_id'], second['transplant_id'])
        post(server, '/api/v2/transplant/revoke', {'transplant_id': first['transplant_id']})
        _, got = post(server, '/api/v2/transplant/get',
                      {'transplant_id': second['transplant_id']})
        self.assertEqual(got['state'], 'active')

    def test_run_needs_consent(self):
        server = SimpleNamespace()
        status, body = post(server, '/api/v2/transplant/run',
                            transplant_request(consent=False))
        self.assertEqual(status, 409)
        self.assertIn('CONSENT', body['error'])

    def test_unknown_transplant_is_404(self):
        server = SimpleNamespace()
        self.assertEqual(post(server, '/api/v2/transplant/get', {'transplant_id': 'tx-9999'})[0], 404)
        self.assertEqual(post(server, '/api/v2/transplant/revoke', {'transplant_id': 'tx-9999'})[0], 404)

    def test_run_rejects_malformed_bodies(self):
        server = SimpleNamespace()
        bad = transplant_request()
        bad['companions'] = {}
        self.assertEqual(post(server, '/api/v2/transplant/run', bad)[0], 400)
        bad = transplant_request()
        bad['bundle'] = {'devices': []}
        self.assertEqual(post(server, '/api/v2/transplant/run', bad)[0], 400)


class FollowupAPI(unittest.TestCase):
    def test_parse_with_prior_resolves_followup_without_models(self):
        from src.runtime import nl_router as N

        def explode(prompt):
            raise N.TransportError('must not be called on a context hit')

        server = registry_server()
        server.command_low = explode
        server.command_medium = explode
        prior = json.loads(json.dumps(prior_doc('vacuum.start', VAC_PRIOR)))
        status, body = post(server, '/api/v2/command/parse',
                            {'text': 'pause it', 'lang': 'en', 'prior': prior})
        self.assertEqual(status, 200)
        intent = body['intent']
        self.assertEqual(intent['status'], 'resolved')
        self.assertEqual(intent['skill_id'], 'vacuum.pause')
        self.assertEqual(intent['targets'], VAC_PRIOR)
        self.assertTrue(any('context-resolved' in a for a in intent['ambiguities']))

    def test_parse_rejects_malformed_prior(self):
        server = registry_server()
        self.assertEqual(post(server, '/api/v2/command/parse',
                             {'text': 'pause it', 'prior': {'nope': 1}})[0], 400)
        self.assertEqual(post(server, '/api/v2/command/parse',
                             {'text': 'pause it', 'prior': 'x'})[0], 400)


class F90WireCLI(unittest.TestCase):
    def test_parser_accepts_new_commands(self):
        parser = cli.build_parser()
        args = parser.parse_args(['routes', 'list', '--target', 't'])
        self.assertEqual(args.target, 't')
        args = parser.parse_args(['routes', 'dispatch', '--target', 't', '--op', 'get_status'])
        self.assertEqual(args.op, 'get_status')
        args = parser.parse_args(['routes', 'simulate-loss', '--target', 't', '--lost-relay', 'r'])
        self.assertEqual(args.lost_relay, 'r')
        args = parser.parse_args(['diagnose', '--question', 'battery_drain', '--bundle', 'b.json'])
        self.assertEqual(args.question, 'battery_drain')
        args = parser.parse_args(['transplant', 'run', '--request', 'r.json'])
        self.assertEqual(args.request, 'r.json')
        args = parser.parse_args(['ask', 'pause it', '--prior', 'p.json'])
        self.assertEqual(args.prior, 'p.json')

    def test_routes_list_runs_against_live_core(self):
        code, out, _ = run_cli(['--json', 'routes', 'list', '--target', 'ble:AA'])
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertTrue(doc['ok'])
        self.assertEqual(doc['data']['target'], 'ble:AA')
        self.assertEqual(doc['data']['routes'], [])

    def test_diagnose_runs_end_to_end(self):
        path = tempfile.mkdtemp() + '/facts.json'
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(battery_bundle(), fh)
        code, out, _ = run_cli(['--json', 'diagnose', '--question', 'battery_drain',
                                '--bundle', path])
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertIn('Maps', doc['data']['explanation'])
        self.assertEqual(doc['data']['confidence'], 'high')

    def test_transplant_run_runs_end_to_end(self):
        path = tempfile.mkdtemp() + '/request.json'
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(transplant_request(), fh)
        code, out, _ = run_cli(['--json', 'transplant', 'run', '--request', path])
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(doc['data']['state'], 'active')
        self.assertEqual(doc['data']['report']['verify']['status'], 'ok')

    def test_ask_prior_reaches_parse_request(self):
        path = tempfile.mkdtemp() + '/prior.json'
        prior = json.loads(json.dumps(prior_doc('vacuum.start', VAC_PRIOR)))
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(prior, fh)
        seen = {}
        from src.runtime import command as cmdmod

        def fake_parse(server, body):
            seen.update(body)
            return {'intent': {'status': 'unresolved', 'ambiguities': []}}

        with mock.patch.object(cmdmod, 'parse_request', side_effect=fake_parse), \
                mock.patch.object(cli, 'ensure_discovery', return_value={}):
            code, out, _ = run_cli(['--json', 'ask', 'pause it', '--prior', path])
        self.assertEqual(code, 0)
        self.assertEqual(seen.get('prior'), prior)

    def test_missing_inputs_are_exit_2(self):
        self.assertEqual(run_cli(['routes', 'list'])[0], 2)
        self.assertEqual(run_cli(['diagnose', '--question', 'battery_drain'])[0], 2)
        self.assertEqual(run_cli(['transplant', 'run'])[0], 2)


if __name__ == '__main__':
    unittest.main()
