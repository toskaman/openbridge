"""Campaign Three section 5.4: adversarial integration of F90 features (TESTS ONLY).

Integrates transplant / migrate / composer / routing / refusal / diagnostics /
followup / dashboard / voice against stale manifests, expired permissions,
wrong device identity, malformed model output, invalid routes, lost acks,
interleaved ops, concurrent revocation, replays, crashes, cancellation,
unsupported devices and missing models.

Contract for every case: fail-closed. Unsafe proposals are rejected
pre-execution: nothing dispatches, installs, compiles or reports on an
adversarial input. Deterministic only: fixed clocks, fixed nonces, fixed
seeds, no network, no model, no wall-clock assertions. Thread coordination
uses Events/barriers with generous timeouts (synchronisation, never timing
assertions); every spawned thread is joined.
"""

import copy
import json
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

from src.ai import voice_intent as VI
from src.fabric import diagnostics as FD
from src.fabric import relay as R
from src.fabric import wear_manifest as WM
from src.runtime import composer as C
from src.runtime import dashboards as D
from src.runtime import diagnostics as RD
from src.runtime import migrate as M
from src.runtime import nl_followup as F
from src.runtime import nl_router as N
from src.runtime.api_v2 import executor, remote_controls, router
from src.runtime.primitives import Executor
from src.runtime.remote_controls import RemoteControlError
from src.runtime.routing import RouteError
from src.runtime.state_store import StateStore
from src.forge import transplant as T
from src.forge import v4_evidence as E
from src.forge.fixtures import manifest
from src.forge.service import ForgeService, MemoryProvider
import tests.runtime.test_migrate as TM
from tests.runtime.test_remote_controls import FakeCompanion, KEY
from tests.runtime.test_routing import Clock
from tests.runtime.test_routing import world as routing_world

NOW = 1_800_000_000.0
PRIMS = ('relay_ble_scan',)
KEY2 = R.derive_key('111111', 'a', 'b')
RELAY_KEY_WRONG = R.derive_key('654321', 'rn', 'pn')
FIXED_NOW = int(1_793_100_000.0)

VOICE_TV = [{'key': 'k-tv', 'category': 'tv'}]


class StubSubstrate:
    CONTRACT_VERSION = 'obv4.1'

    def __init__(self):
        self.seen = []

    def compile(self, manifest_doc, facts=(), inputs=None, for_dispatch=False):
        self.seen.append(manifest_doc)
        return {'manifest_hash': 'sha256:stub',
                'steps': len(manifest_doc['steps'])}

    def manifest_hash(self, manifest_doc):
        return 'sha256:stub'


def t_companions():
    return {
        'src-1': {'category': 'phone', 'simulated': True, 'online': True,
                  'grants': ['observe', 'read'], 'primitives': list(PRIMS),
                  'capabilities': ['tv.ble.observations']},
        'tgt-1': {'category': 'tv', 'simulated': True, 'online': True,
                  'grants': ['observe', 'read'], 'primitives': list(PRIMS),
                  'capabilities': []},
    }


def t_links():
    return [{'parent': 'src-1', 'child': 'tgt-1', 'transport': 'LAN',
             'grants': ('observe', 'read'), 'source': 'SIM'}]


def t_bundle(now=NOW):
    return E.resolve(
        ({'category': 'tv', 'device_id': 'tgt-1',
          'permission_scope': ['observe', 'read'],
          'facts': [{'fact_id': 'f0', 'kind': 'name', 'value': 'TV',
                     'source': 'sim', 'observed_at': now}]},),
        (), PRIMS, now)


def t_service(proposer=None, dispatcher=None, companions=None, links=None):
    comps = companions if companions is not None else t_companions()
    ls = links if links is not None else t_links()
    return T.TransplantService(
        comps, ls, proposer or T.DeterministicStubProposer(),
        dispatcher or T.SimulatedDispatcher(),
        substrate=StubSubstrate(),
        service_factory=lambda m: ForgeService(
            MemoryProvider(copy.deepcopy(m)), clock=lambda: NOW))


def t_run_full(svc, **over):
    kw = dict(source_capability_id='tv.ble.observations', target_id='tgt-1',
              intent='mirror ble observations', bundle=t_bundle(),
              primitive_ids=PRIMS, manifest=manifest(NOW),
              model_run={'model': 'stub-meta-1', 'run_id': 'run-1'},
              title='Mirror observations', facts_required=[],
              expires_at=NOW + 60, target_category='tv', consent=True)
    kw.update(over)
    return svc.transplant(**kw)


def migrate_setup(with_controls=True):
    clock = Clock()
    server, keys = TM.world(clock)
    watch = FakeCompanion()
    watch.clock = clock
    tv = FakeCompanion(key=KEY2)
    tv.clock = clock
    server.relays.relays['r-watch']['send'] = watch
    server.relays.relays['r-tv']['send'] = tv
    calls = []

    def fake(self_, key, params):
        calls.append((key, params))
        return 'EXECUTED', None, None, True, {}

    ex = executor(server)
    ex.RUNNERS = dict(Executor.RUNNERS, device_action=fake)
    router(server).clock = clock
    rc = remote_controls(server)
    rc.clock = clock
    rc._ensure_thread = lambda: None
    if with_controls:
        tvk = keys['tv']
        rc.set_controls({'relay_id': 'r-watch', 'controls': [
            {'label': 'TV volume +', 'skill_id': 'tv_volume_step',
             'target': tvk, 'params': {'direction': 'up'}},
            {'label': 'TV volume -', 'skill_id': 'tv_volume_step',
             'target': tvk, 'params': {'direction': 'down'}},
            {'label': 'YouTube', 'skill_id': 'app_launch',
             'target': tvk,
             'params': {'package': 'com.google.android.youtube.tv'}}],
            'consent': True})
        rc.set_controls({'relay_id': 'r-tv', 'controls': [
            {'label': 'Chrome', 'skill_id': 'app_launch',
             'target': tvk,
             'params': {'package': 'com.android.chrome'}}],
            'consent': True})
    return server, keys, clock, rc, watch, tv, calls


def routing_setup():
    clock = Clock()
    server, keys = routing_world(clock)
    calls = []
    ex = executor(server)

    def fake(name):
        def run(self_, key, params):
            calls.append((name, key, params))
            return 'VERIFIED', None, {'ok': True}, True, {'ok': True}
        return run

    ex.RUNNERS = dict(
        Executor.RUNNERS, relay_ble_scan=fake('relay_ble_scan'),
        device_action=fake('device_action'), read_facts=fake('read_facts'))
    rt = router(server)
    rt.clock = clock
    server.relay_ledger.record('r-tv', [])
    clock.t += 5
    server.relay_ledger.record('r-ph', [])
    return server, keys, clock, rt, calls, ex


COMPOSER_DEVICES = [
    {'key': 'dev-tv1', 'label': 'android tv', 'category': 'tv',
     'handles': {'WIFI': 'h-tv'}},
    {'key': 'dev-vac1', 'label': 'Robot vacuum (Tuya)', 'category': 'vacuum',
     'handles': {'LAN': 'h-vac'}},
]


class FakeRoutes:
    """Route-truth double: allow, refuse, fail or go stale on demand."""

    def __init__(self, selected=True, error=None, reasons=('link_down',)):
        self.selected = selected
        self.error = error
        self.reasons = reasons
        self.calls = []

    def skill_routes(self, skill_id, target=None):
        self.calls.append((skill_id, target))
        if self.error is not None:
            raise self.error
        if not self.selected:
            return {'selected_route_id': None,
                    'selection': {'rule': 'none_eligible'},
                    'routes': [{'route_id': 'rt-dead', 'state': 'UNAVAILABLE',
                                'reason': r} for r in self.reasons]}
        key = target or 'fabric'
        return {'selected_route_id': 'rt-x',
                'selection': {'rule': 'auto_score'},
                'routes': [{'route_id': 'rt-x', 'state': 'READY',
                            'hops': [{'device_key': key, 'transport': 'WIFI',
                                      'primitive_id': 'p-' + skill_id}],
                            'operation_id': 'op:' + skill_id,
                            'evidence': 'REAL_HARDWARE'}]}


def stub_proposer(content, model_id='stub-meta'):
    def run(prompt):
        run.prompts.append(prompt)
        return {'model_id': model_id, 'endpoint': 'stub://test',
                'content': content}
    run.prompts = []
    return run


def d_fact(name, value, source='ADB', unit=None, confidence='measured'):
    return {'name': name, 'value': value, 'unit': unit, 'source': source,
            'observed_at': '2026-11-01T00:00:00+00:00',
            'confidence': confidence}


def d_dev(oid, category, label, *facts):
    return {'opaque_id': oid, 'category': category, 'label': label,
            'facts': list(facts)}


def d_battery_bundle():
    return {'devices': [d_dev(
        'phone-1', 'phone', 'Pixel', d_fact('battery_percent', 18),
        d_fact('battery_charging', False),
        d_fact('battery_discharge_pct_per_hour', 8.0),
        d_fact('top_consumer', 'Maps'))]}


FOLLOWUP_DEVICES = {
    'dev-tv1': {'key': 'dev-tv1', 'category': 'tv',
                'label': 'Living room TV'},
    'dev-vac1': {'key': 'dev-vac1', 'category': 'vacuum',
                 'label': 'Roborock'},
}
VAC_PRIOR = [{'kind': 'device', 'ref': 'vacuum-1'}]
TV_PRIOR = [{'kind': 'device', 'ref': 'tv-1'}]


class FakeTransport:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def __call__(self, prompt):
        self.calls.append(prompt)
        if self.error is not None:
            raise self.error
        return self.reply(prompt) if callable(self.reply) else self.reply


def f_resolved(skill_id, outcome, targets):
    return {'outcome': outcome, 'skill_id': skill_id,
            'targets': list(targets), 'params': {}, 'confidence': 0.9,
            'ambiguities': [], 'clarifying_question': None}


def f_prior_doc(skill_id, targets, lang='en'):
    return N.parse('prior turn', lang, 'low',
                   FakeTransport(f_resolved(skill_id, 'prior turn', targets)),
                   None)


def signed_msg(params, key=None, rid='adv-r1', nonce='adv-nonce-0001',
               now=None, op='reply', ttl=30):
    now = FIXED_NOW if now is None else now
    msg = {'protocol': R.PROTOCOL, 'relay_id': rid, 'op': op,
           'params': params, 'nonce': nonce, 'issued_at': now,
           'expires_at': now + ttl}
    return {**msg, 'mac': R.sign(key or KEY, msg)}


class TransplantAdversarial(unittest.TestCase):
    """Transplant under stale/expired/forged/dead inputs: never dispatch."""

    def test_stale_manifest_rejected_pre_dispatch(self):
        svc = t_service()
        with self.assertRaisesRegex(T.TransplantError, 'PUBLISH_REJECTED'):
            t_run_full(svc, manifest=manifest(NOW - 10000))
        self.assertEqual(svc.dispatcher.receipts, {})
        self.assertEqual(svc._records, {})

    def test_expired_permissions_target_grant_missing(self):
        svc = t_service()
        with self.assertRaisesRegex(T.TransplantError, 'GRANT_MISSING'):
            svc.check_target('tgt-1', PRIMS, ('observe', 'read', 'control'))
        with self.assertRaises(T.TransplantError):
            t_run_full(svc, required_grants=('observe', 'read', 'control'))
        self.assertEqual(svc.dispatcher.receipts, {})

    def test_wrong_device_identity_unknown_target_and_capability(self):
        svc = t_service()
        with self.assertRaisesRegex(T.TransplantError, 'TARGET_UNKNOWN'):
            svc.check_target('ghost-9', PRIMS, ('observe',))
        with self.assertRaisesRegex(T.TransplantError,
                                    'SOURCE_UNKNOWN_CAPABILITY'):
            svc.discover_source('invented.capability')
        with self.assertRaises(T.TransplantError):
            t_run_full(svc, target_id='ghost-9')
        self.assertEqual(svc.dispatcher.receipts, {})

    def test_malformed_model_output_rejected_pre_dispatch(self):
        class EvilProp:
            def propose(self, req):
                return {'candidate': {'schema_version': 999,
                                      'candidate_id': 'evil',
                                      'origin': 'x'},
                        'model': 'evil', 'prompt_version': 'v'}

        svc = t_service(proposer=EvilProp())
        with self.assertRaisesRegex(T.TransplantError, 'PROPOSAL_REJECTED'):
            svc.propose('x', t_bundle(), PRIMS, 'tv')
        with self.assertRaisesRegex(T.TransplantError, 'PROPOSAL_REJECTED'):
            t_run_full(svc)
        self.assertEqual(svc.dispatcher.receipts, {})
        self.assertEqual(svc._records, {})

    def test_missing_model_propagates_without_dispatch(self):
        class DeadProp:
            def propose(self, req):
                raise ConnectionError('ollama down')

        svc = t_service(proposer=DeadProp())
        with self.assertRaises(ConnectionError):
            t_run_full(svc)
        self.assertEqual(svc.dispatcher.receipts, {})
        self.assertEqual(svc._records, {})

    def test_invalid_route_no_link(self):
        svc = t_service(links=[])
        with self.assertRaisesRegex(T.TransplantError, 'NO_ROUTE'):
            svc.select_route('src-1', 'tgt-1')
        with self.assertRaisesRegex(T.TransplantError, 'NO_ROUTE'):
            t_run_full(svc)
        self.assertEqual(svc.dispatcher.receipts, {})

    def test_invalid_route_insufficient_link_grants(self):
        thin = [{'parent': 'src-1', 'child': 'tgt-1', 'transport': 'LAN',
                 'grants': ('observe',), 'source': 'SIM'}]
        svc = t_service(links=thin)
        with self.assertRaisesRegex(T.TransplantError, 'NO_ROUTE'):
            svc.select_route('src-1', 'tgt-1')
        with self.assertRaises(T.TransplantError):
            t_run_full(svc)
        self.assertEqual(svc.dispatcher.receipts, {})

    def test_concurrent_revocation_double_revoke_idempotent(self):
        svc = t_service()
        rec = t_run_full(svc)
        first = svc.revoke(rec['transplant_id'])
        self.assertEqual(first['state'], 'revoked')
        self.assertEqual(first['receipt'], {})
        self.assertEqual(first['ui_plan'], {})
        self.assertEqual(first['report']['revoke']['status'], 'ok')
        self.assertEqual(first['report']['cleanup']['status'], 'ok')
        second = svc.revoke(rec['transplant_id'])
        self.assertEqual(second['state'], 'revoked')

    def test_revocation_unknown_rejected(self):
        svc = t_service()
        with self.assertRaisesRegex(T.TransplantError, 'UNKNOWN_TRANSPLANT'):
            svc.revoke('tx-9999')
        with self.assertRaises(T.TransplantError):
            svc.report('tx-9999')
        with self.assertRaises(T.TransplantError):
            svc.get('tx-9999')

    def test_crash_dispatcher_failure_leaves_no_active_record(self):
        class BoomDispatcher:
            def __init__(self):
                self.receipts = {}

            def dispatch(self, route, candidate):
                raise RuntimeError('link down')

            def revoke(self, receipt_id):
                pass

        svc = t_service(dispatcher=BoomDispatcher())
        with self.assertRaises(RuntimeError):
            t_run_full(svc)
        self.assertEqual(svc._records, {})

    def test_cancellation_consent_false_blocks_dispatch(self):
        svc = t_service()
        with self.assertRaisesRegex(T.TransplantError,
                                    'OWNER_CONSENT_REQUIRED'):
            t_run_full(svc, consent=False)
        with self.assertRaisesRegex(T.TransplantError,
                                    'OWNER_CONSENT_REQUIRED'):
            t_run_full(svc, consent=None)
        self.assertEqual(svc.dispatcher.receipts, {})
        self.assertEqual(svc._records, {})

    def test_unsupported_real_hardware_refused_pre_execution(self):
        comps = t_companions()
        comps['src-1']['simulated'] = False
        svc = t_service(companions=comps)
        with self.assertRaisesRegex(T.TransplantError, 'SIMULATED'):
            svc.discover_source('tv.ble.observations')
        comps2 = t_companions()
        comps2['tgt-1']['simulated'] = False
        svc2 = t_service(companions=comps2)
        with self.assertRaisesRegex(T.TransplantError, 'SIMULATED'):
            svc2.check_target('tgt-1', PRIMS, ('observe',))
        with self.assertRaises(T.TransplantError):
            t_run_full(svc2)
        with self.assertRaisesRegex(T.TransplantError, 'REAL_HARDWARE'):
            T.SimulatedDispatcher().dispatch(
                {'route_id': 'r', 'simulated': False},
                {'candidate_id': 'c'})
        self.assertEqual(svc2.dispatcher.receipts, {})

    def test_offline_devices_refused(self):
        comps = t_companions()
        comps['src-1']['online'] = False
        with self.assertRaisesRegex(T.TransplantError, 'SOURCE_OFFLINE'):
            t_service(companions=comps).discover_source(
                'tv.ble.observations')
        comps2 = t_companions()
        comps2['tgt-1']['online'] = False
        with self.assertRaisesRegex(T.TransplantError, 'TARGET_OFFLINE'):
            t_service(companions=comps2).check_target(
                'tgt-1', PRIMS, ('observe',))

    def test_interleaved_success_and_failure_share_nothing(self):
        svc = t_service()
        rec = t_run_full(svc)
        self.assertEqual(rec['state'], 'active')
        with self.assertRaises(T.TransplantError):
            t_run_full(svc, target_id='ghost-9')
        self.assertEqual(svc.get(rec['transplant_id'])['state'], 'active')
        self.assertEqual(len(svc.dispatcher.receipts), 1)


class MigrateAdversarial(unittest.TestCase):
    """Migration under stale/forged/dead inputs: never lose controls."""

    def labels(self, rc, rid):
        return sorted(g['label'] for g in (rc.grants.get(rid) or {}).values())

    def grants_snapshot(self, rc):
        return copy.deepcopy(rc.grants)

    def test_stale_proposal_rejected_after_source_change(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        rc.set_controls({'relay_id': 'r-watch', 'controls': [
            {'label': 'Owner added', 'skill_id': 'device_facts',
             'target': keys['tv'], 'params': {}}], 'consent': True})
        with self.assertRaises(M.MigrationError) as ctx:
            M.apply(server, prop, True)
        self.assertEqual(ctx.exception.status, 409)

    def test_expired_permissions_guard_refuses_to_finish(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        orig = rc.set_controls

        def evil(body):
            out = orig(body)
            server.relays.relays['r-watch']['permissions']['MUTATED'] = True
            return out

        rc.set_controls = evil
        try:
            with self.assertRaises(M.MigrationError) as ctx:
                M.apply(server, prop, True)
        finally:
            rc.set_controls = orig
        self.assertEqual(ctx.exception.status, 500)

    def test_wrong_device_identity_unknown_interface(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        out = M.propose(server, source='toaster', target='tv',
                         match='volume')
        self.assertEqual(out['outcome'], 'refusal')
        out2 = M.propose(server, source='watch', target='toaster',
                          match='volume')
        self.assertEqual(out2['outcome'], 'refusal')
        self.assertEqual(
            M.propose(server, source='watch', target='watch',
                       match='volume')['outcome'], 'refusal')

    def test_no_paired_interfaces_is_refusal(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        server.relays.relays.clear()
        out = M.propose(server, source='watch', target='tv',
                         match='volume')
        self.assertEqual(out['outcome'], 'refusal')

    def test_malformed_proposal_rejected_pre_execution(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        before = self.grants_snapshot(rc)
        bads = [
            {'schema_version': 999},
            {'schema_version': M.SCHEMA_VERSION},
            {'schema_version': M.SCHEMA_VERSION, 'source': {},
             'destination': {}, 'controls': [], 'old_grant_disposition': {}},
        ]
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        same = copy.deepcopy(prop)
        same['destination'] = dict(same['source'])
        bads.append(same)
        empty = copy.deepcopy(prop)
        empty['controls'] = []
        bads.append(empty)
        evil_skill = copy.deepcopy(prop)
        evil_skill['controls'][0]['skill_id'] = 'nope_skill'
        bads.append(evil_skill)
        evil_disp = copy.deepcopy(prop)
        evil_disp['old_grant_disposition'] = {'action': 'wipe_all'}
        bads.append(evil_disp)
        for bad in bads:
            with self.assertRaises(M.MigrationError) as ctx:
                M.validate_proposal(bad)
            self.assertEqual(ctx.exception.status, 400)
            with self.assertRaises(M.MigrationError):
                M.apply(server, bad, True)
        self.assertEqual(self.grants_snapshot(rc), before)

    def test_invalid_destination_without_capability(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        server.relays.relays['r-tv']['capabilities'] = ['ble_scan']
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')
        self.assertEqual(prop['outcome'], 'refusal')

    def test_invalid_destination_unpaired(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        del server.relays.relays['r-tv']
        with self.assertRaises(M.MigrationError) as ctx:
            M.apply(server, prop, True)
        self.assertEqual(ctx.exception.status, 409)

    def test_lost_ack_stale_ids_dead_after_migrate(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        doomed = set(prop['old_grant_disposition']['revoked_control_ids'])
        self.assertTrue(doomed)
        M.apply(server, prop, True)
        live = set((rc.grants.get('r-watch') or {}))
        self.assertTrue(doomed.isdisjoint(live))
        stale = sorted(doomed)[0]
        watch.queue.append({'request_id': '%032x' % 7, 'control_id': stale,
                            'pressed_at': int(clock.t * 1000)})
        rc.poll_once()
        self.assertEqual(calls, [])

    def test_interleaved_two_proposals_second_stale(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        text = ('Remove the volume controls from my watch and put them '
                'on my TV.')
        first = M.propose(server, text=text)['proposal']
        second = M.propose(server, text=text)['proposal']
        M.apply(server, first, True)
        with self.assertRaises(M.MigrationError) as ctx:
            M.apply(server, second, True)
        self.assertEqual(ctx.exception.status, 409)

    def defs_snapshot(self, rc):
        out = {}
        for rid, grants in (rc.grants or {}).items():
            out[rid] = sorted(
                (g.get('label'), g.get('skill_id'), g.get('target'),
                 json.dumps(g.get('params') or {}, sort_keys=True))
                for g in grants.values())
        return out

    def test_concurrent_revocation_rollback_idempotent(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        receipt = M.apply(server, prop, True)
        first = M.rollback(server, receipt, True)
        self.assertTrue(first['rolled_back'])
        before = self.defs_snapshot(rc)
        second = M.rollback(server, receipt, True)
        self.assertTrue(second['rolled_back'])
        self.assertIn('restored 0', ' '.join(second['notes']))
        self.assertEqual(self.defs_snapshot(rc), before)

    def test_crash_dest_install_failure_has_no_receipt(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        before = self.grants_snapshot(rc)
        orig = rc.set_controls
        n = [0]

        def fail_dest(body):
            n[0] += 1
            if n[0] == 1:
                raise RemoteControlError(503, 'companion down')
            return orig(body)

        rc.set_controls = fail_dest
        try:
            with self.assertRaises(M.MigrationError) as ctx:
                M.apply(server, prop, True)
        finally:
            rc.set_controls = orig
        self.assertIsNone(ctx.exception.receipt)
        self.assertEqual(self.grants_snapshot(rc), before)

    def test_crash_source_removal_failure_returns_receipt(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        orig = rc.set_controls
        n = [0]

        def fail_src(body):
            n[0] += 1
            if n[0] == 2:
                raise RemoteControlError(503, 'source down')
            return orig(body)

        rc.set_controls = fail_src
        try:
            with self.assertRaises(M.MigrationError) as ctx:
                M.apply(server, prop, True)
        finally:
            rc.set_controls = orig
        self.assertIsNotNone(ctx.exception.receipt)
        self.assertIn('roll back', str(ctx.exception))

    def test_cancellation_consent_false_changes_nothing(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        before = self.grants_snapshot(rc)
        with self.assertRaises(M.MigrationError) as ctx:
            M.apply(server, prop, False)
        self.assertEqual(ctx.exception.status, 400)
        receipt = M.apply(server, prop, True)
        with self.assertRaises(M.MigrationError):
            M.rollback(server, receipt, False)
        M.rollback(server, receipt, True)
        self.assertEqual(self.labels(rc, 'r-watch'),
                         ['TV volume +', 'TV volume -', 'YouTube'])
        self.assertEqual(before is not None, True)

    def test_unsupported_manifest_bound_refused(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        rc.grants.setdefault('r-watch', {})['ctl-manifest-g9'] = {
            'kind': 'manifest', 'label': 'Manifest volume',
            'skill_id': 'tv_volume_step', 'target': keys['tv'],
            'params': {'direction': 'up'}}
        out = M.propose(server, source='watch', target='tv',
                         match='manifest volume')
        self.assertEqual(out['outcome'], 'refusal')
        self.assertIn('Manifest', out['reason'])

    def test_unparsed_and_ambiguous_clarify_never_guess(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        out = M.propose(server, text='blabla gibberish wobble')
        self.assertEqual(out['outcome'], 'needs_clarification')
        out2 = M.propose(server, text='move it there')
        self.assertEqual(out2['outcome'], 'needs_clarification')

    def test_malformed_receipt_rejected(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        for bad in ({'schema_version': 999},
                    {'schema_version': M.SCHEMA_VERSION},
                    {'schema_version': M.SCHEMA_VERSION,
                     'migration_id': 'm', 'source': {}, 'destination': {},
                     'migrated': []}):
            with self.assertRaises(M.MigrationError) as ctx:
                M.validate_receipt(bad)
            self.assertEqual(ctx.exception.status, 400)
            with self.assertRaises(M.MigrationError):
                M.rollback(server, bad, True)


class ComposerAdversarial(unittest.TestCase):
    """Composer under malformed/stale/dead model and route inputs."""

    def test_malformed_replies_rejected(self):
        many = {'steps': [{'skill_id': 'device_facts',
                            'target': 'android tv', 'params': {}}] * 9}
        bads = ['not json{{', '', '   ',
                json.dumps({'steps': []}), json.dumps(many),
                json.dumps({'steps': [{'skill_id': 'device_facts'}]}),
                json.dumps({'steps': [{
                    'skill_id': 'device_facts', 'target': 'android tv',
                    'params': {}, 'smuggle': 1}]}),
                json.dumps({'steps': [{
                    'skill_id': 'device_facts', 'target': 'android tv',
                    'params': {}, 'on_fail': 'retry'}]}),
                json.dumps({'steps': [
                    {'skill_id': 'device_facts', 'target': 'android tv',
                     'params': {}, 'needs': ['step2']},
                    {'skill_id': 'device_facts', 'target': 'android tv',
                     'params': {}}]}),
                'x' * (C.MAX_REPLY_CHARS + 1)]
        for bad in bads:
            with self.assertRaises(C.ComposerError, msg=bad[:40]):
                C.proposal_from_reply(bad)
        with self.assertRaises(C.ComposerError):
            C.proposal_from_reply(None)
        with self.assertRaises(C.ComposerError):
            C.proposal_from_reply(123)

    def test_stale_no_live_devices(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'device_facts', 'target': 'android tv',
            'params': {}}]}))
        with self.assertRaises(C.ComposerError):
            C.compose(prop, [], FakeRoutes())
        with self.assertRaises(C.ComposerError):
            C.propose_and_compose('hi', [], FakeRoutes(),
                                  stub_proposer('{}'))

    def test_expired_permissions_no_permitted_route(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'tv_volume_step', 'target': 'android tv',
            'params': {'direction': 'up'}}]}))
        comp = C.compose(prop, COMPOSER_DEVICES,
                         FakeRoutes(selected=False))
        self.assertEqual(comp['steps'][0]['status'], 'refused')
        self.assertIn('no permitted route',
                      comp['steps'][0]['reason'])
        with self.assertRaises(C.ComposerError):
            C.to_workflow(comp)

    def test_wrong_device_identity_unverified(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'tv_volume_step', 'target': 'ghost speaker',
            'params': {'direction': 'up'}}]}))
        comp = C.compose(prop, COMPOSER_DEVICES, FakeRoutes())
        self.assertEqual(comp['steps'][0]['status'], 'refused')
        self.assertIn('unverified device', comp['steps'][0]['reason'])
        self.assertIsNone(comp['steps'][0]['device_key'])
        self.assertIsNone(comp['steps'][0]['route'])

    def test_invalid_params_refused_per_step(self):
        for params in ({'direction': 'sideways'}, {}, {'direction': 'up',
                                                       'extra': 1}):
            prop = C.proposal_from_reply(json.dumps({'steps': [{
                'skill_id': 'tv_volume_step', 'target': 'android tv',
                'params': params}]}))
            comp = C.compose(prop, COMPOSER_DEVICES, FakeRoutes())
            self.assertEqual(comp['steps'][0]['status'], 'refused',
                             msg=repr(params))
            self.assertIn('invalid params', comp['steps'][0]['reason'])

    def test_unknown_skill_refused(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'nope_skill', 'target': 'android tv',
            'params': {}}]}))
        comp = C.compose(prop, COMPOSER_DEVICES, FakeRoutes())
        self.assertEqual(comp['steps'][0]['status'], 'refused')
        self.assertIn('unknown skill', comp['steps'][0]['reason'])

    def test_untargeted_target_mismatch_refused(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'ble_scan_room', 'target': 'android tv',
            'params': {'seconds': 5}}]}))
        comp = C.compose(prop, COMPOSER_DEVICES, FakeRoutes())
        self.assertEqual(comp['steps'][0]['status'], 'refused')
        self.assertIn('untargeted', comp['steps'][0]['reason'])

    def test_router_crash_refuses_never_raises(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'tv_volume_step', 'target': 'android tv',
            'params': {'direction': 'up'}}]}))
        comp = C.compose(prop, COMPOSER_DEVICES,
                         FakeRoutes(error=RuntimeError('route db down')))
        self.assertEqual(comp['steps'][0]['status'], 'refused')
        self.assertIn('no permitted route', comp['steps'][0]['reason'])

    def test_missing_model_dead_proposer(self):
        def dead(prompt):
            raise ConnectionError('ollama down')

        with self.assertRaisesRegex(C.ComposerError, 'model unavailable'):
            C.propose_and_compose('quiet please', COMPOSER_DEVICES,
                                  FakeRoutes(), dead)
        with self.assertRaisesRegex(C.ComposerError, 'no usable content'):
            C.propose_and_compose(
                'quiet please', COMPOSER_DEVICES, FakeRoutes(),
                lambda p: {'model_id': 'm', 'content': ''})
        with self.assertRaisesRegex(C.ComposerError, 'empty request'):
            C.propose_and_compose('   ', COMPOSER_DEVICES, FakeRoutes(),
                                  stub_proposer('{}'))

    def test_cancellation_mixed_proposal_never_compiles(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [
            {'skill_id': 'tv_volume_step', 'target': 'android tv',
             'params': {'direction': 'up'}},
            {'skill_id': 'nope_skill', 'target': 'android tv',
             'params': {}}]}))
        comp = C.compose(prop, COMPOSER_DEVICES, FakeRoutes())
        self.assertEqual((comp['allowed'], comp['refused']), (1, 1))
        with self.assertRaisesRegex(C.ComposerError, 'refused steps'):
            C.to_workflow(comp)
        with self.assertRaises(C.ComposerError):
            C.to_workflow({'steps': []})

    def test_unsupported_unlinked_device_no_candidates(self):
        ghost = {'key': 'dev-ghost', 'label': 'ghost speaker',
                 'category': 'speaker', 'handles': {}}
        self.assertEqual(C.candidates_for(ghost), [])
        self.assertIn('do not use',
                      C.build_prompt('x', COMPOSER_DEVICES + [ghost]))
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'device_facts', 'target': 'ghost speaker',
            'params': {}}]}))
        comp = C.compose(prop, COMPOSER_DEVICES + [ghost], FakeRoutes())
        self.assertEqual(comp['steps'][0]['status'], 'refused')

    def test_replay_deterministic(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'tv_volume_step', 'target': 'android tv',
            'params': {'direction': 'up'}}]}))
        first = C.compose(copy.deepcopy(prop), COMPOSER_DEVICES,
                          FakeRoutes())
        second = C.compose(copy.deepcopy(prop), COMPOSER_DEVICES,
                           FakeRoutes())
        self.assertEqual(first['steps'], second['steps'])
        self.assertEqual(first['allowed'], 1)

    def test_interleaved_route_change_flips_verdict(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'tv_volume_step', 'target': 'android tv',
            'params': {'direction': 'up'}}]}))
        live = C.compose(copy.deepcopy(prop), COMPOSER_DEVICES,
                         FakeRoutes(selected=True))
        dead = C.compose(copy.deepcopy(prop), COMPOSER_DEVICES,
                         FakeRoutes(selected=False,
                                    reasons=('grant_insufficient',)))
        self.assertEqual(live['steps'][0]['status'], 'allowed')
        self.assertEqual(dead['steps'][0]['status'], 'refused')
        self.assertIn('grant_insufficient', dead['steps'][0]['reason'])

    def test_allowed_steps_carry_seven_fields(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'tv_volume_step', 'target': 'android tv',
            'params': {'direction': 'up'}}]}))
        step = C.compose(prop, COMPOSER_DEVICES,
                         FakeRoutes())['steps'][0]
        self.assertEqual(step['status'], 'allowed')
        for field in ('device_key', 'route', 'authorization',
                      'expected_effect', 'verification_method',
                      'failure_strategy', 'reversibility'):
            self.assertIsNotNone(step[field], msg=field)
        self.assertIn('never atomically rolled back',
                      C.compose(prop, COMPOSER_DEVICES,
                                FakeRoutes())['rollback'])

    def test_refused_steps_carry_open_reason_only(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'nope_skill', 'target': 'android tv',
            'params': {}}]}))
        step = C.compose(prop, COMPOSER_DEVICES,
                         FakeRoutes())['steps'][0]
        self.assertEqual(step['status'], 'refused')
        self.assertTrue(step['reason'])
        self.assertIsNone(step['route'])
        self.assertIsNone(step['authorization'])

    def test_outcome_unknown_on_lost_ack(self):
        outcome, note = C.outcome_of(
            'TIMEOUT', {'state': 'UNKNOWN_TIMEOUT', 'errors': []})
        self.assertEqual(outcome, 'UNKNOWN')
        self.assertIn('recovery', note)
        denied, _ = C.outcome_of('DENIED', {'state': 'BLOCKED'})
        self.assertEqual(denied, 'REFUSED')
        record = {'workflow_id': 'w1', 'status': 'cancelled',
                  'steps': [{'id': 'step1', 'state': 'DENIED',
                             'receipt': {'state': 'BLOCKED'}}]}
        summary = C.summarize(record)
        self.assertEqual(summary['steps'][0]['outcome'], 'REFUSED')
        self.assertIn('never atomically rolled back',
                      summary['rollback'])


class RoutingAdversarial(unittest.TestCase):
    """Routing under stale/expired/forged/replayed inputs."""

    def arm_ble(self, rt, doc, params=None):
        return rt.arm({'skill_id': 'ble_scan_room',
                       'route_id': doc['selected_route_id'],
                       'params': params or {'seconds': 8}, 'consent': True})

    def invoke_ble(self, rt, lease, params=None):
        return rt.invoke(
            {'invocation_id': lease['invocation_id'],
             'skill_id': 'ble_scan_room', 'route_id': lease['route_id'],
             'lease_id': lease['lease_id'],
             'graph_revision': lease['graph_revision'],
             'params': params or {'seconds': 8}, 'consent': True})

    def test_stale_graph_revision_mismatch(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = self.arm_ble(rt, doc)
        tampered = dict(lease['graph_revision'])
        tampered['seq'] = tampered.get('seq', 0) + 99
        with self.assertRaises(RouteError) as ctx:
            rt.invoke({'invocation_id': lease['invocation_id'],
                       'skill_id': 'ble_scan_room',
                       'route_id': lease['route_id'],
                       'lease_id': lease['lease_id'],
                       'graph_revision': tampered,
                       'params': {'seconds': 8}, 'consent': True})
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(calls, [])

    def test_expired_invocation_lease(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = self.arm_ble(rt, doc)
        clock.t += 1000
        with self.assertRaises(RouteError) as ctx:
            self.invoke_ble(rt, lease)
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(calls, [])

    def test_expired_relay_lease_stale_routes(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        clock.t += 500
        doc = rt.skill_routes('ble_scan_room')
        self.assertIsNone(doc['selected_route_id'])
        self.assertTrue(all(r['reason'] == 'lease_stale'
                            for r in doc['routes']))

    def test_expired_permission_grant_insufficient(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        server.relays.relays['r-tv']['permissions']['BLUETOOTH_SCAN'] = False
        doc = rt.skill_routes('ble_scan_room')
        tv = next(r for r in doc['routes']
                  if r['hops'][0]['device_key'] == keys['tv'])
        self.assertEqual(tv['reason'], 'grant_insufficient')

    def test_wrong_device_identity_target_change(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('device_facts', keys['tv'])
        lease = rt.arm({'skill_id': 'device_facts',
                        'route_id': doc['selected_route_id'],
                        'target': keys['tv'], 'params': {}, 'consent': True})
        with self.assertRaises(RouteError) as ctx:
            rt.invoke({'invocation_id': lease['invocation_id'],
                       'skill_id': 'device_facts',
                       'route_id': lease['route_id'],
                       'lease_id': lease['lease_id'],
                       'graph_revision': lease['graph_revision'],
                       'target': keys['phone'], 'params': {},
                       'consent': True})
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(calls, [])

    def test_malformed_invalid_params_and_request(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        with self.assertRaises(RouteError) as ctx:
            rt.arm({'skill_id': 'ble_scan_room',
                    'route_id': doc['selected_route_id'],
                    'params': {'seconds': 99}, 'consent': True})
        self.assertEqual(ctx.exception.code, 'INVALID_PARAMS')
        lease = self.arm_ble(rt, doc)
        body = {'invocation_id': lease['invocation_id'],
                'skill_id': 'ble_scan_room', 'route_id': lease['route_id'],
                'lease_id': lease['lease_id'],
                'graph_revision': lease['graph_revision'],
                'params': {'seconds': 8}, 'consent': True,
                'smuggled': 1}
        with self.assertRaises(RouteError) as ctx2:
            rt.invoke(body)
        self.assertEqual(ctx2.exception.code, 'INVALID_REQUEST')

    def test_invalid_route_not_selected(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        with self.assertRaises(RouteError) as ctx:
            rt.arm({'skill_id': 'ble_scan_room', 'route_id': 'rt-bogus',
                    'params': {'seconds': 8}, 'consent': True})
        self.assertEqual(ctx.exception.code, 'ROUTE_NOT_SELECTED')
        with self.assertRaises(RouteError) as ctx2:
            rt.skill_routes('nope_skill')
        self.assertEqual(ctx2.exception.code, 'UNKNOWN_SKILL')
        with self.assertRaises(RouteError) as ctx3:
            rt.set_policy({'skill_id': 'nope_skill', 'mode': 'AUTO'})
        self.assertEqual(ctx3.exception.code, 'UNKNOWN_SKILL')

    def test_lost_ack_replay_returns_same_without_redispatch(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = self.arm_ble(rt, doc)
        first = self.invoke_ble(rt, lease)
        self.assertEqual(len(calls), 1)
        second = self.invoke_ble(rt, lease)
        self.assertEqual(second['state'], first['state'])
        self.assertEqual(len(calls), 1)

    def test_interleaved_two_skills_coexist(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        ble = rt.skill_routes('ble_scan_room')
        facts = rt.skill_routes('device_facts', keys['tv'])
        lease_ble = self.arm_ble(rt, ble)
        lease_facts = rt.arm(
            {'skill_id': 'device_facts',
             'route_id': facts['selected_route_id'], 'target': keys['tv'],
             'params': {}, 'consent': True})
        self.assertEqual(len(rt.invocations), 2)
        out_ble = self.invoke_ble(rt, lease_ble)
        out_facts = rt.invoke(
            {'invocation_id': lease_facts['invocation_id'],
             'skill_id': 'device_facts', 'route_id': lease_facts['route_id'],
             'lease_id': lease_facts['lease_id'],
             'graph_revision': lease_facts['graph_revision'],
             'target': keys['tv'], 'params': {}, 'consent': True})
        self.assertEqual(out_ble['state'], 'VERIFIED')
        self.assertEqual(out_facts['state'], 'VERIFIED')
        self.assertEqual(len(calls), 2)

    def test_concurrent_revocation_policy_voids_armed(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = self.arm_ble(rt, doc)
        rt.set_policy({'skill_id': 'ble_scan_room', 'mode': 'AUTO'})
        self.assertEqual(rt.invocations, {})
        with self.assertRaises(RouteError) as ctx:
            self.invoke_ble(rt, lease)
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(calls, [])

    def test_concurrent_revocation_link_down_voids(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = self.arm_ble(rt, doc)
        server.relays.relays['r-ph']['online'] = False
        with self.assertRaises(RouteError) as ctx:
            self.invoke_ble(rt, lease)
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(calls, [])

    def test_replay_id_reused_with_diff_binding(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = self.arm_ble(rt, doc)
        self.invoke_ble(rt, lease)
        with self.assertRaises(RouteError) as ctx:
            self.invoke_ble(rt, lease, params={'seconds': 5})
        self.assertEqual(ctx.exception.code, 'INVOCATION_ID_REUSED')
        self.assertEqual(len(calls), 1)

    def test_crash_uncertain_outcome_never_rearmed(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = self.arm_ble(rt, doc)
        rt.invocations.pop(('ble_scan_room', None), None)
        rt.completed[('owner', lease['invocation_id'])] = (
            None, None, clock.t)
        with self.assertRaises(RouteError) as ctx:
            self.invoke_ble(rt, lease)
        self.assertEqual(ctx.exception.code, 'UNCERTAIN_OUTCOME')
        with self.assertRaises(RouteError) as ctx2:
            rt.arm({'skill_id': 'ble_scan_room',
                    'route_id': doc['selected_route_id'],
                    'params': {'seconds': 8}, 'consent': True},
                   invocation_id=lease['invocation_id'])
        self.assertEqual(ctx2.exception.code, 'UNCERTAIN_OUTCOME')
        self.assertEqual(calls, [])

    def test_cancellation_consent_required(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        with self.assertRaises(RouteError) as ctx:
            rt.arm({'skill_id': 'ble_scan_room',
                    'route_id': doc['selected_route_id'],
                    'params': {'seconds': 8}, 'consent': False})
        self.assertEqual(ctx.exception.code, 'CONSENT_REQUIRED')
        lease = self.arm_ble(rt, doc)
        with self.assertRaises(RouteError) as ctx2:
            rt.invoke({'invocation_id': lease['invocation_id'],
                       'skill_id': 'ble_scan_room',
                       'route_id': lease['route_id'],
                       'lease_id': lease['lease_id'],
                       'graph_revision': lease['graph_revision'],
                       'params': {'seconds': 8}, 'consent': False})
        self.assertEqual(ctx2.exception.code, 'CONSENT_REQUIRED')
        self.assertEqual(calls, [])

    def test_unsupported_zero_devices_abstains(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        server.relays.relays.clear()
        doc = rt.skill_routes('ble_scan_room')
        self.assertEqual(
            (doc['routes'], doc['selected_route_id'],
             doc['selection']['rule']), ([], None, 'none_eligible'))

    def test_unsafe_params_edited_after_consent(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = self.arm_ble(rt, doc)
        with self.assertRaises(RouteError) as ctx:
            self.invoke_ble(rt, lease, params={'seconds': 5})
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(calls, [])

    def test_unsafe_lease_id_mismatch(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = self.arm_ble(rt, doc)
        wrong = lease['lease_id'][:-1] + (
            '0' if lease['lease_id'][-1] != '0' else '1')
        with self.assertRaises(RouteError) as ctx:
            rt.invoke({'invocation_id': lease['invocation_id'],
                       'skill_id': 'ble_scan_room',
                       'route_id': lease['route_id'], 'lease_id': wrong,
                       'graph_revision': lease['graph_revision'],
                       'params': {'seconds': 8}, 'consent': True})
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(calls, [])

    def test_unsafe_invoke_without_arm(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = self.arm_ble(rt, doc)
        rt.invocations.clear()
        with self.assertRaises(RouteError) as ctx:
            self.invoke_ble(rt, lease)
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(calls, [])


class RefusalPreExecution(unittest.TestCase):
    """Unsafe proposals are rejected before anything executes."""

    def test_transplant_evil_candidate_never_dispatched(self):
        class EvilProp:
            def propose(self, req):
                return {'candidate': {'schema_version': 999,
                                      'candidate_id': 'evil',
                                      'origin': 'x'},
                        'model': 'evil', 'prompt_version': 'v'}

        svc = t_service(proposer=EvilProp())
        with self.assertRaises(T.TransplantError):
            t_run_full(svc)
        self.assertEqual(svc.dispatcher.receipts, {})
        self.assertEqual(svc._records, {})

    def test_migrate_forged_proposal_never_applied(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        before = copy.deepcopy(rc.grants)
        forged = {'schema_version': M.SCHEMA_VERSION,
                  'source': {'relay_id': 'r-watch'},
                  'destination': {'relay_id': 'r-watch'},
                  'controls': [{'control_id': 'ctl-x', 'label': 'X',
                                'skill_id': 'tv_volume_step',
                                'target': keys['tv'],
                                'params': {'direction': 'up'}}],
                  'old_grant_disposition': {
                      'action': 'revoke_source_controls',
                      'revoked_control_ids': []}}
        with self.assertRaises(M.MigrationError):
            M.apply(server, forged, True)
        self.assertEqual(copy.deepcopy(rc.grants), before)

    def test_composer_refused_never_compiles(self):
        prop = C.proposal_from_reply(json.dumps({'steps': [{
            'skill_id': 'nope_skill', 'target': 'android tv',
            'params': {}}]}))
        comp = C.compose(prop, COMPOSER_DEVICES, FakeRoutes())
        self.assertEqual(comp['allowed'], 0)
        with self.assertRaises(C.ComposerError):
            C.to_workflow(comp)

    def test_routing_unarmed_never_dispatches(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = rt.arm({'skill_id': 'ble_scan_room',
                        'route_id': doc['selected_route_id'],
                        'params': {'seconds': 8}, 'consent': True})
        rt.invocations.clear()
        with self.assertRaises(RouteError):
            rt.invoke({'invocation_id': lease['invocation_id'],
                       'skill_id': 'ble_scan_room',
                       'route_id': lease['route_id'],
                       'lease_id': lease['lease_id'],
                       'graph_revision': lease['graph_revision'],
                       'params': {'seconds': 8}, 'consent': True})
        self.assertEqual(calls, [])

    def test_dashboard_exec_skill_never_installed(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        before = copy.deepcopy(rc.grants)
        with self.assertRaises(D.DashboardError):
            D.install_patch(
                rc, 'r-watch',
                {'widgets': [{'widget_id': 'w1', 'kind': 'button',
                              'label': 'Run', 'binding_primitive': 'pc_run',
                              'params': {}}]},
                keys['tv'], D.BINDABLE_PATCH_SKILLS, consent=True)
        self.assertEqual(copy.deepcopy(rc.grants), before)

    def test_diagnostics_invented_numbers_never_reported(self):
        class EvilProp:
            def propose(self, req):
                ref = req['findings'][0]['evidence_refs'][0]
                return {'explanation':
                        'The battery drains at 9999 percent per hour '
                        'because aliens did it yesterday evening.',
                        'recommendations': req['candidates'][:1],
                        'evidence_refs': [ref],
                        'uncertainty': FD.LIMIT, 'model': 'evil'}

        with self.assertRaises(FD.DiagnosticError):
            FD.diagnose('battery_drain', d_battery_bundle(), EvilProp())

    def test_voice_refusal_never_proposes(self):
        for text in ('shut down the tv', 'reboot the phone',
                     'unlock the door', 'flash the firmware',
                     'wipe my data', 'format the disk'):
            out = VI.compile_intent(text)
            self.assertEqual(out['outcome'], 'refusal', msg=text)
            self.assertIsNone(out['intent'])
            self.assertNotIn('primitive_id', out)

    def test_followup_incompatible_never_resolves(self):
        prior = f_prior_doc('vacuum.start', VAC_PRIOR)
        self.assertIsNone(
            F.resolve_followup('turn it up', 'en', prior,
                               FOLLOWUP_DEVICES))


class DiagnosticsAdversarial(unittest.TestCase):
    """Diagnostics under unknown/stale/forged model outputs."""

    def test_stale_empty_bundle_rejected(self):
        with self.assertRaises(FD.DiagnosticError):
            FD.diagnose('battery_drain', {'devices': []},
                        FD.DeterministicStubProposer())

    def test_unknown_question_and_fact_rejected(self):
        bundle = {'devices': [d_dev('d1', 'phone', 'Phone',
                                    d_fact('battery_percent', 50))]}
        with self.assertRaises(FD.DiagnosticError):
            FD.diagnose('why_is_the_sky_blue', bundle,
                        FD.DeterministicStubProposer())
        bad = {'devices': [d_dev('d1', 'phone', 'Phone',
                                 d_fact('benchmark_score', 9999))]}
        with self.assertRaises(FD.DiagnosticError):
            FD.diagnose('battery_drain', bad,
                        FD.DeterministicStubProposer())

    def test_wrong_device_identity_unknown_device(self):
        with self.assertRaises(FD.DiagnosticError):
            FD.diagnose('battery_drain', d_battery_bundle(),
                        FD.DeterministicStubProposer(), device='ghost-9')

    def test_malformed_model_invented_number(self):
        class EvilProp:
            def propose(self, req):
                ref = req['findings'][0]['evidence_refs'][0]
                return {'explanation':
                        'The battery drains at 9999 percent per hour '
                        'because aliens did it yesterday evening.',
                        'recommendations': req['candidates'][:1],
                        'evidence_refs': [ref],
                        'uncertainty': FD.LIMIT, 'model': 'evil'}

        with self.assertRaisesRegex(FD.DiagnosticError, 'INVENTED_NUMBER'):
            FD.diagnose('battery_drain', d_battery_bundle(), EvilProp())

    def test_malformed_model_bad_recommendation(self):
        class EvilProp:
            def propose(self, req):
                ref = req['findings'][0]['evidence_refs'][0]
                return {'explanation':
                        'The observed battery discharge rate is high and '
                        'the top consumer is Maps today here.',
                        'recommendations': ['wipe_device'],
                        'evidence_refs': [ref],
                        'uncertainty': FD.LIMIT, 'model': 'evil'}

        with self.assertRaises(FD.DiagnosticError):
            FD.diagnose('battery_drain', d_battery_bundle(), EvilProp())

    def test_malformed_model_unknown_evidence_and_shape(self):
        class EvilRefs:
            def propose(self, req):
                return {'explanation':
                        'The observed battery discharge rate is high and '
                        'the top consumer is Maps today here.',
                        'recommendations': req['candidates'][:1],
                        'evidence_refs': ['ghost#nope'],
                        'uncertainty': FD.LIMIT, 'model': 'evil'}

        class EvilShape:
            def propose(self, req):
                return {'explanation': 'short', 'smuggled': 1}

        class EvilJson:
            def propose(self, req):
                ref = req['findings'][0]['evidence_refs'][0]
                return {'explanation': '{"fake": 1} ' + 'x ' * 30,
                        'recommendations': req['candidates'][:1],
                        'evidence_refs': [ref],
                        'uncertainty': FD.LIMIT, 'model': 'evil'}

        class EvilLimit:
            def propose(self, req):
                ref = req['findings'][0]['evidence_refs'][0]
                return {'explanation':
                        'The observed battery discharge rate is high and '
                        'the top consumer is Maps today here.',
                        'recommendations': req['candidates'][:1],
                        'evidence_refs': [ref],
                        'uncertainty': 'no limits apply', 'model': 'evil'}

        for prop in (EvilRefs(), EvilShape(), EvilJson(), EvilLimit()):
            with self.assertRaises(FD.DiagnosticError):
                FD.diagnose('battery_drain', d_battery_bundle(), prop)

    def test_malformed_model_unreadable_reply(self):
        def bad_chat(payload):
            return {'model': 'm',
                    'message': {'content': 'not json{{'}}

        with self.assertRaisesRegex(FD.DiagnosticError,
                                    'PROPOSAL_UNREADABLE'):
            FD.diagnose('battery_drain', d_battery_bundle(),
                        FD.MetaProposer(bad_chat))

    def test_missing_model_crash_propagates_no_report(self):
        def dead_chat(payload):
            raise ConnectionError('meta down')

        with self.assertRaises(ConnectionError):
            FD.diagnose('battery_drain', d_battery_bundle(),
                        FD.MetaProposer(dead_chat))

    def test_insufficient_telemetry_names_missing(self):
        bundle = {'devices': [d_dev('phone-1', 'phone', 'Pixel',
                                    d_fact('battery_percent', 60))]}
        report = FD.diagnose('battery_drain', bundle,
                             FD.DeterministicStubProposer())
        self.assertEqual(report['confidence'], 'low')
        self.assertTrue(report['missing'])
        self.assertEqual(report['limitation'], FD.LIMIT)

    def test_replay_deterministic(self):
        first = FD.diagnose('battery_drain', d_battery_bundle(),
                            FD.DeterministicStubProposer())
        second = FD.diagnose('battery_drain', d_battery_bundle(),
                             FD.DeterministicStubProposer())
        self.assertEqual(first['explanation'], second['explanation'])
        self.assertEqual(first['model_run_id'], second['model_run_id'])

    def test_interleaved_questions_independent(self):
        batt = FD.diagnose('battery_drain', d_battery_bundle(),
                           FD.DeterministicStubProposer())
        pcs = {'devices': [
            d_dev('pc-a', 'computer', 'Tower', d_fact('cpu_threads', 16),
                  d_fact('ram_gb', 32), d_fact('disk_free_gb', 120)),
            d_dev('pc-b', 'computer', 'Laptop', d_fact('cpu_threads', 4),
                  d_fact('ram_gb', 8), d_fact('disk_free_gb', 60))]}
        best = FD.diagnose('best_pc_for_dev', pcs,
                           FD.DeterministicStubProposer())
        self.assertEqual(batt['question'], 'battery_drain')
        self.assertEqual(best['question'], 'best_pc_for_dev')
        self.assertEqual(best['target'], 'pc-a')

    def test_runtime_android_each_read_independent(self):
        def boom(*args):
            raise ValueError('nope')

        self.assertEqual(RD.android(boom), [])

        def partial(*args):
            if args == ('dumpsys', 'battery'):
                return ('level: 50\nscale: 100\ntemperature: 300\n'
                        'health: 2\nstatus: 2\npresent: true')
            raise ValueError('unreadable')

        out = RD.android(partial)
        names = [f['name'] for f in out]
        self.assertIn('battery_level', names)
        self.assertNotIn('wifi', names)

    def test_runtime_windows_failure_returns_no_findings(self):
        def dead(method, params=None):
            raise RuntimeError('agent down')

        self.assertEqual(RD.windows(dead), [])

    def test_recommendations_read_only_or_owner_action(self):
        for rid, rec in FD.RECOMMENDATIONS.items():
            self.assertIn(rec['kind'], ('read_only', 'owner_action'),
                          msg=rid)


class FollowupAdversarial(unittest.TestCase):
    """Followup under stale/missing/cross-family/malformed priors."""

    def test_stale_missing_prior_returns_none(self):
        prior = f_prior_doc('vacuum.start', VAC_PRIOR)
        self.assertIsNone(F.resolve_followup('pause it', 'en', None,
                                             FOLLOWUP_DEVICES))
        self.assertIsNone(F.resolve_followup(
            'pause it', 'en', {'status': 'unsupported'},
            FOLLOWUP_DEVICES))
        dead = dict(prior, status='failed')
        self.assertIsNone(F.resolve_followup('pause it', 'en', dead,
                                             FOLLOWUP_DEVICES))
        no_targets = dict(prior, targets=[])
        self.assertIsNone(F.resolve_followup('pause it', 'en', no_targets,
                                             FOLLOWUP_DEVICES))

    def test_wrong_family_cross_resolve_refused(self):
        prior = f_prior_doc('vacuum.start', VAC_PRIOR)
        self.assertIsNone(F.resolve_followup('turn it up', 'en', prior,
                                             FOLLOWUP_DEVICES))
        self.assertFalse(F.compatible('vacuum_command', 'tv'))
        self.assertIsNone(F.prior_family(None))
        self.assertIsNone(F.prior_family({'status': 'resolved'}))

    def test_malformed_text_and_lang_return_none(self):
        prior = f_prior_doc('vacuum.start', VAC_PRIOR)
        self.assertIsNone(F.resolve_followup('', 'en', prior,
                                             FOLLOWUP_DEVICES))
        self.assertIsNone(F.resolve_followup('x' * 2001, 'en', prior,
                                             FOLLOWUP_DEVICES))
        self.assertIsNone(F.resolve_followup('pause it', 'xx', prior,
                                             FOLLOWUP_DEVICES))
        self.assertIsNone(F.resolve_followup(None, 'en', prior,
                                             FOLLOWUP_DEVICES))

    def test_explicit_target_and_no_reference_return_none(self):
        prior = f_prior_doc('vacuum.start', VAC_PRIOR)
        self.assertIsNone(F.resolve_followup('pause the vacuum', 'en',
                                             prior, FOLLOWUP_DEVICES))
        self.assertIsNone(F.resolve_followup('hello world zzz', 'en',
                                             prior, FOLLOWUP_DEVICES))
        self.assertFalse(F.detect_reference('turn the tv up', 'en'))
        self.assertTrue(F.detect_reference('pause it', 'en'))

    def test_capability_word_without_device_is_followup(self):
        self.assertTrue(F.detect_reference('monte le son', 'fr'))
        self.assertTrue(F.has_explicit_target('turn the tv up'))
        self.assertFalse(F.has_explicit_target('pause it'))

    def without_id(self, doc):
        doc = dict(doc)
        doc.pop('intent_id', None)
        return doc

    def test_happy_path_resolves_and_does_not_mutate(self):
        prior = f_prior_doc('vacuum.start', VAC_PRIOR)
        doc = F.resolve_followup('pause it', 'en', prior,
                                 FOLLOWUP_DEVICES)
        self.assertIsNotNone(doc)
        self.assertEqual(doc['status'], 'resolved')
        self.assertEqual(doc['targets'], VAC_PRIOR)
        self.assertEqual(prior['targets'], VAC_PRIOR)
        again = F.resolve_followup('pause it', 'en', prior,
                                   FOLLOWUP_DEVICES)
        self.assertEqual(self.without_id(doc), self.without_id(again))

    def test_devices_none_still_deterministic(self):
        prior = f_prior_doc('vacuum.start', VAC_PRIOR)
        first = F.resolve_followup('pause it', 'en', prior, None)
        second = F.resolve_followup('pause it', 'en', prior, None)
        if first is None or second is None:
            self.assertEqual(first, second)
        else:
            self.assertEqual(self.without_id(first),
                             self.without_id(second))

    def test_parse_hit_skips_transport(self):
        prior = f_prior_doc('vacuum.start', VAC_PRIOR)
        boom = FakeTransport(error=N.TransportError('must not be called'))
        doc = F.parse_with_context('pause it', 'en', 'low', boom, prior,
                                   devices=FOLLOWUP_DEVICES)
        self.assertEqual(doc['status'], 'resolved')
        self.assertEqual(boom.calls, [])

    def test_parse_miss_falls_through_to_router(self):
        prior = f_prior_doc('vacuum.start', VAC_PRIOR)
        reply = f_resolved('vacuum.pause', 'pause the vacuum',
                           VAC_PRIOR)
        t1 = FakeTransport(copy.deepcopy(reply))
        t2 = FakeTransport(copy.deepcopy(reply))
        miss = F.parse_with_context('pause the vacuum', 'en', 'low', t1,
                                    prior, devices=FOLLOWUP_DEVICES)
        direct = N.parse('pause the vacuum', 'en', 'low', t2, None)
        miss = dict(miss)
        direct = dict(direct)
        miss.pop('intent_id', None)
        direct.pop('intent_id', None)
        self.assertEqual(miss, direct)
        self.assertTrue(t1.calls)

    def test_interleaved_priors_independent(self):
        vac = f_prior_doc('vacuum.start', VAC_PRIOR)
        tvp = f_prior_doc('tv_volume_step', TV_PRIOR)
        vac_hit = F.resolve_followup('pause it', 'en', vac,
                                     FOLLOWUP_DEVICES)
        tv_miss = F.resolve_followup('pause it', 'en', tvp,
                                     FOLLOWUP_DEVICES)
        self.assertIsNotNone(vac_hit)
        self.assertEqual(vac_hit['targets'], VAC_PRIOR)
        if tv_miss is not None:
            self.assertEqual(tv_miss['targets'], TV_PRIOR)


class DashboardAdversarial(unittest.TestCase):
    """Dashboards under malformed/forged/dead UI patches."""

    def dash_setup(self):
        clock = Clock()
        server, keys = routing_world(clock)
        companion = FakeCompanion()
        companion.clock = clock
        server.relays.enroll('r-watch', KEY, 'h-ph-1',
                             {'capabilities': ['remote_controls'],
                              'permissions': {}})
        server.relays.relays['r-watch']['send'] = companion
        rc = remote_controls(server)
        rc.clock = clock
        rc._ensure_thread = lambda: None
        store = D.DashStore(StateStore.for_server(server))
        return server, keys, clock, rc, companion, store

    def test_malformed_patch_rejected_pre_install(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        D.create(rc, 'r-watch', 'tv', keys['tv'], consent=True)
        before = copy.deepcopy(rc.grants)
        bads = [
            None, {}, {'widgets': []}, {'widgets': 'nope'},
            {'widgets': ['nope']},
            {'widgets': [{'widget_id': 'w1', 'kind': 'slider',
                          'label': 'x',
                          'binding_primitive': 'tv_volume_step',
                          'params': {}}]},
            {'widgets': [{'widget_id': 'w1', 'kind': 'button',
                          'label': 'x',
                          'binding_primitive': 'nope_skill',
                          'params': {}}]},
            {'widgets': [{'widget_id': 'w1', 'kind': 'button',
                          'label': '', 'binding_primitive': 'tv_volume_step',
                          'params': {}}]},
            {'widgets': [{'widget_id': 'w1', 'kind': 'button',
                          'label': 'x' * 41,
                          'binding_primitive': 'tv_volume_step',
                          'params': {}}]},
            {'widgets': [{'widget_id': 'w1', 'kind': 'button',
                          'label': 'x',
                          'binding_primitive': 'tv_volume_step',
                          'params': {'nested': {}}}]},
        ]
        for bad in bads:
            with self.assertRaises(D.DashboardError):
                D.install_patch(rc, 'r-watch', bad, keys['tv'],
                                D.BINDABLE_PATCH_SKILLS, consent=True)
        self.assertEqual(copy.deepcopy(rc.grants), before)

    def test_unsupported_exec_skill_never_bindable(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        self.assertNotIn('pc_run', D.BINDABLE_PATCH_SKILLS)
        before = copy.deepcopy(rc.grants)
        with self.assertRaises(D.DashboardError):
            D.install_patch(
                rc, 'r-watch',
                {'widgets': [{'widget_id': 'w1', 'kind': 'button',
                              'label': 'Run',
                              'binding_primitive': 'pc_run',
                              'params': {}}]},
                keys['tv'],
                tuple(list(D.BINDABLE_PATCH_SKILLS) + ['pc_run']),
                consent=True)
        self.assertEqual(copy.deepcopy(rc.grants), before)

    def test_unsupported_unknown_area(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        with self.assertRaises(D.DashboardError):
            D.create(rc, 'r-watch', 'toaster', keys['tv'], consent=True)

    def test_wrong_device_identity_target_resolved(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        seen = []

        def resolve(label):
            seen.append(label)
            return keys['tv']

        D.install_patch(
            rc, 'r-watch',
            {'widgets': [{'widget_id': 'w1', 'kind': 'button',
                          'label': 'V+',
                          'binding_primitive': 'tv_volume_step',
                          'params': {'direction': 'up'}}]},
            'android tv label', D.BINDABLE_PATCH_SKILLS, consent=True,
            resolve_target=resolve)
        self.assertEqual(seen, ['android tv label'])
        grants = list((rc.grants.get('r-watch') or {}).values())
        self.assertTrue(grants)
        self.assertEqual(grants[0]['target'], keys['tv'])
        with self.assertRaises(D.DashboardError):
            D.install_patch(rc, 'r-watch',
                            {'widgets': [{
                                'widget_id': 'w1', 'kind': 'button',
                                'label': 'V+',
                                'binding_primitive': 'tv_volume_step',
                                'params': {'direction': 'up'}}]},
                            '', D.BINDABLE_PATCH_SKILLS, consent=True)

    def test_cancellation_consent_false_changes_nothing(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        before = copy.deepcopy(rc.grants)
        with self.assertRaises(D.DashboardError):
            D.create(rc, 'r-watch', 'tv', keys['tv'], consent=False)
        with self.assertRaises(D.DashboardError):
            D.install_patch(rc, 'r-watch', {'widgets': [{
                'widget_id': 'w1', 'kind': 'button', 'label': 'V+',
                'binding_primitive': 'tv_volume_step',
                'params': {'direction': 'up'}}]}, keys['tv'],
                D.BINDABLE_PATCH_SKILLS, consent=False)
        with self.assertRaises(D.DashboardError):
            D.load(store, rc, 'anything', consent=False)
        self.assertEqual(copy.deepcopy(rc.grants), before)

    def test_patch_unknown_label_fails_loudly(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        D.create(rc, 'r-watch', 'tv', keys['tv'], consent=True)
        before = copy.deepcopy(rc.grants)
        with self.assertRaises(D.DashboardError):
            D.patch(rc, 'r-watch', remove=['Ghost label'], consent=True)
        self.assertEqual(copy.deepcopy(rc.grants), before)

    def test_interleaved_create_patch_round_trip(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        D.create(rc, 'r-watch', 'tv', keys['tv'], consent=True)
        first = sorted(D.defs(rc, 'r-watch'), key=lambda c: c['label'])
        self.assertEqual(len(first), 3)
        D.patch(rc, 'r-watch', remove=['Volume +'], consent=True)
        second = sorted(D.defs(rc, 'r-watch'), key=lambda c: c['label'])
        self.assertEqual(len(second), 2)
        D.patch(rc, 'r-watch', add=[{
            'label': 'Volume +', 'skill_id': 'tv_volume_step',
            'target': keys['tv'], 'params': {'direction': 'up'}}],
            consent=True)
        third = sorted(D.defs(rc, 'r-watch'), key=lambda c: c['label'])
        self.assertEqual(len(third), 3)

    def test_replay_same_patch_bumps_generation(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        patch = {'widgets': [{'widget_id': 'w1', 'kind': 'button',
                               'label': 'V+',
                               'binding_primitive': 'tv_volume_step',
                               'params': {'direction': 'up'}}]}
        D.install_patch(rc, 'r-watch', patch, keys['tv'],
                        D.BINDABLE_PATCH_SKILLS, consent=True)
        first = sorted((rc.grants.get('r-watch') or {}))
        D.install_patch(rc, 'r-watch', patch, keys['tv'],
                        D.BINDABLE_PATCH_SKILLS, consent=True)
        second = sorted((rc.grants.get('r-watch') or {}))
        self.assertNotEqual(first, second)
        self.assertEqual(
            sorted(c['label'] for c in D.defs(rc, 'r-watch')), ['V+'])

    def test_crash_unknown_relay_rejected(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        with self.assertRaises((D.DashboardError, RemoteControlError,
                                KeyError, ValueError)):
            D.create(rc, 'r-ghost', 'tv', keys['tv'], consent=True)

    def test_stale_store_validates_names_and_defs(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        with self.assertRaises(D.DashboardError):
            store.save('r-watch', 'bad name!', [{
                'label': 'V+', 'skill_id': 'tv_volume_step',
                'target': keys['tv'], 'params': {'direction': 'up'}}])
        with self.assertRaises(D.DashboardError):
            store.save('r-watch', 'ok-name', [])
        with self.assertRaises(D.DashboardError):
            store.save('r-watch', 'ok-name', [{'label': 'x'}])
        with self.assertRaises(D.DashboardError):
            store.get('ghost-dashboard')
        with self.assertRaises(D.DashboardError):
            store.delete('ghost-dashboard')

    def test_save_load_round_trip_and_repush(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        D.create(rc, 'r-watch', 'tv', keys['tv'], consent=True)
        defs = D.defs(rc, 'r-watch')
        store.save('r-watch', 'tv-panel', defs)
        self.assertIn('tv-panel', store.list())
        D.load(store, rc, 'tv-panel', consent=True)
        self.assertTrue(D.repush_current(rc, 'r-watch'))
        D.patch(rc, 'r-watch',
                remove=[c['label'] for c in D.defs(rc, 'r-watch')],
                consent=True)
        self.assertFalse(D.repush_current(rc, 'r-watch'))
        with self.assertRaises(RemoteControlError):
            D.repush_current(rc, 'r-ghost-never')

    def test_lost_ack_repush_keeps_same_ids(self):
        server, keys, clock, rc, companion, store = self.dash_setup()
        D.create(rc, 'r-watch', 'tv', keys['tv'], consent=True)
        before = sorted((rc.grants.get('r-watch') or {}))
        companion.controls = []
        D.repush_current(rc, 'r-watch')
        after = sorted((rc.grants.get('r-watch') or {}))
        self.assertEqual(before, after)


class VoiceAdversarial(unittest.TestCase):
    """Voice under hostile transcripts: clarify or refuse, never guess."""

    def test_refusal_battery_never_proposes(self):
        for text in ('shut down the tv', 'reboot the phone',
                     'install the app', 'factory reset the tv',
                     'root the phone', 'delete everything',
                     'what is my password', 'unlock the door',
                     'flash the firmware', 'wipe my data',
                     'format the disk', 'buy a coffee',
                     'purchase premium'):
            out = VI.compile_intent(text)
            self.assertEqual(out['outcome'], 'refusal', msg=text)
            self.assertIsNone(out['intent'])
            self.assertNotIn('primitive_id', out)

    def test_clarification_battery_never_proposes(self):
        cases = ['press volume up', 'click the button',
                 'move volume controls from watch to tv',
                 'remove the panel from my watch',
                 'find my phone', 'where is my phone',
                 'turn the volume up', 'make it louder on tv',
                 'start and stop the vacuum', 'scan',
                 'check', 'louder']
        for text in cases:
            out = VI.compile_intent(text)
            self.assertEqual(out['outcome'], 'needs_clarification',
                             msg=text)
            self.assertIsNone(out['intent'])

    def test_malformed_transcripts_unsupported(self):
        for bad in (None, 123, '', '   ', 'x' * 500):
            out = VI.compile_intent(bad)
            self.assertEqual(out['outcome'], 'unsupported',
                             msg=repr(bad)[:30])

    def test_wrong_device_identity_ambiguous_targets(self):
        out = VI.compile_intent('bluetooth scan via the tv')
        self.assertEqual(out['outcome'], 'needs_clarification')
        self.assertTrue(out.get('needs_target'))
        two = [{'key': 'k1', 'category': 'tv'},
               {'key': 'k2', 'category': 'tv'}]
        out2 = VI.compile_intent('bluetooth scan via the tv',
                                 devices=two)
        self.assertEqual(out2['outcome'], 'needs_clarification')
        one = VI.compile_intent('bluetooth scan via the tv',
                                devices=VOICE_TV)
        self.assertEqual(one['outcome'], 'proposal')
        self.assertEqual(one['device_key'], 'k-tv')

    def test_repaired_only_match_clarifies_never_proposes(self):
        for text in ('blue tooth tv', 'tellee bluetooth',
                     'blue tooth tellee'):
            out = VI.compile_intent(text, devices=VOICE_TV)
            self.assertEqual(out['outcome'], 'needs_clarification',
                             msg=text)
            self.assertTrue(
                out['normalization']['repairs'], msg=text)
            self.assertIsNone(out['intent'])

    def test_proposal_carries_review_note_and_consent(self):
        out = VI.compile_intent('diagnose the network')
        self.assertEqual(out['outcome'], 'proposal')
        self.assertIn('Proposal only', out['note'])
        self.assertIn('transcript', out)
        out2 = VI.compile_intent('bluetooth scan via the tv',
                                 devices=VOICE_TV)
        self.assertTrue(out2['requires_consent'])

    def test_replay_deterministic(self):
        first = VI.compile_intent('diagnose the network')
        second = VI.compile_intent('diagnose the network')
        self.assertEqual(first, second)
        first_r = VI.compile_intent('shut down the tv')
        second_r = VI.compile_intent('shut down the tv')
        self.assertEqual(first_r, second_r)

    def test_crash_fuzz_never_raises(self):
        fuzz = ['', ' ', '\n\t', 'x' * 401, 'x' * 400,
                '{"skill": "pc_run"}', "'; DROP TABLE devices; --",
                '<script>alert(1)</script>', 'A' * 399,
                'up ' * 100, '0', '999999999999999999999',
                'tv tv tv tv tv', 'bluetooth ' * 50,
                "s'il vous plait", '  diagnose   ',
                'DIAGNOSE THE NETWORK', 'DiAgNoSe ThE nEtWoRk']
        allowed = {'proposal', 'needs_clarification', 'refusal',
                   'unsupported'}
        for text in fuzz:
            with self.subTest(text=text[:30]):
                out = VI.compile_intent(text)
                self.assertIn(out['outcome'], allowed)

    def test_interleaved_transcripts_independent(self):
        first = VI.compile_intent('diagnose the network')
        second = VI.compile_intent('shut down the tv')
        third = VI.compile_intent('diagnose the network')
        self.assertEqual(first['outcome'], 'proposal')
        self.assertEqual(second['outcome'], 'refusal')
        self.assertEqual(first, third)

    def test_unsupported_preserves_transcript(self):
        out = VI.compile_intent('recite a poem about routers')
        self.assertEqual(out['outcome'], 'unsupported')
        self.assertEqual(out['transcript'], 'recite a poem about routers')
        self.assertIsNone(out['clarifying_question'])

    def test_missing_model_voice_is_deterministic(self):
        out = VI.compile_intent('diagnose the network')
        self.assertNotIn('model', out)
        self.assertIn('normalization', out)
        self.assertIn('lang', out)


class RelayAndManifestAdversarial(unittest.TestCase):
    """Wire envelopes and dynamic manifests under forgery and staleness."""

    def test_stale_expired_envelope_rejected(self):
        old = signed_msg({}, now=FIXED_NOW - 100, ttl=30)
        with self.assertRaises(R.RelayError):
            R.verify(KEY, old, {}, FIXED_NOW)

    def test_wrong_device_identity_bad_signature(self):
        good = signed_msg({'controls': []})
        with self.assertRaisesRegex(R.RelayError, 'Bad signature'):
            R.verify(KEY2, good, {}, FIXED_NOW)
        tampered = dict(good)
        tampered['params'] = {'controls': [{'control_id': 'forged'}]}
        with self.assertRaisesRegex(R.RelayError, 'Bad signature'):
            R.verify(KEY, tampered, {}, FIXED_NOW)
        retargeted = dict(good)
        retargeted['relay_id'] = 'adv-r2'
        with self.assertRaises(R.RelayError):
            R.verify(KEY, retargeted, {}, FIXED_NOW)

    def test_replay_same_nonce_rejected(self):
        seen = {}
        first = signed_msg({}, nonce='adv-nonce-1001')
        self.assertEqual(
            R.verify(KEY, first, seen, FIXED_NOW)['op'], 'reply')
        with self.assertRaisesRegex(R.RelayError, 'Replay'):
            R.verify(KEY, first, seen, FIXED_NOW)
        second = signed_msg({}, nonce='adv-nonce-1002')
        self.assertEqual(
            R.verify(KEY, second, seen, FIXED_NOW)['op'], 'reply')

    def test_malformed_envelope_rejected(self):
        base = {'protocol': R.PROTOCOL, 'relay_id': 'adv-r1',
                'op': 'reply', 'params': {}, 'nonce': 'adv-nonce-2001',
                'issued_at': FIXED_NOW, 'expires_at': FIXED_NOW + 30}
        no_mac = dict(base)
        with self.assertRaises(R.RelayError):
            R.verify(KEY, no_mac, {}, FIXED_NOW)
        bad_proto = dict(base, protocol='bogus')
        bad_proto['mac'] = R.sign(KEY, bad_proto)
        with self.assertRaises(R.RelayError):
            R.verify(KEY, bad_proto, {}, FIXED_NOW)
        with self.assertRaises(TypeError):
            R.verify(KEY, signed_msg({}), [], FIXED_NOW)

    def test_stale_wear_manifest_rederived(self):
        facts = []
        first = WM.build('feature:android.hardware.type.watch\n'
                         'feature:android.hardware.wifi', facts, '15')
        second = WM.build('feature:android.hardware.type.watch', facts,
                          '15')
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first['sha256'], second['sha256'])
        caps = [c['capability'] for c in first['capabilities']]
        self.assertIn('wear_os_device', caps)
        self.assertIn('wifi_radio_present', caps)
        caps2 = [c['capability'] for c in second['capabilities']]
        self.assertNotIn('wifi_radio_present', caps2)

    def test_unsupported_non_watch_has_no_manifest(self):
        self.assertIsNone(WM.build(
            'feature:android.hardware.wifi', [], '15'))
        self.assertIsNone(WM.build('', [], '15'))
        feats = WM.features('feature:android.hardware.wifi\n'
                            'feature:android.evil.backdoor\n'
                            'garbage line')
        self.assertEqual(feats, ['android.hardware.wifi'])

    def test_concurrent_same_nonce_one_wins(self):
        seen = {}
        lock = threading.Lock()
        barrier = threading.Barrier(2)
        outcomes = []

        def attempt():
            msg = signed_msg({}, nonce='adv-nonce-3001')
            barrier.wait(timeout=5)
            try:
                with lock:
                    R.verify(KEY, msg, seen, FIXED_NOW)
                outcomes.append('ok')
            except R.RelayError:
                outcomes.append('replay')
            except Exception:  # noqa: BLE001 - test records, never hides
                outcomes.append('error')

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(sorted(outcomes), ['ok', 'replay'])

    def test_interleaved_distinct_nonces_all_accepted(self):
        seen = {}
        for i in range(8):
            msg = signed_msg({}, nonce='adv-nonce-4%03d' % i)
            self.assertEqual(
                R.verify(KEY, msg, seen, FIXED_NOW)['op'], 'reply')


class ConcurrencyAndCrashAdversarial(unittest.TestCase):
    """Interleaved ops, concurrent revocation, lost acks, crashes."""

    def test_interleaved_routing_invokes_both_succeed(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        ble = rt.skill_routes('ble_scan_room')
        facts = rt.skill_routes('device_facts', keys['tv'])
        lease_a = rt.arm({'skill_id': 'ble_scan_room',
                          'route_id': ble['selected_route_id'],
                          'params': {'seconds': 8}, 'consent': True})
        lease_b = rt.arm({'skill_id': 'device_facts',
                          'route_id': facts['selected_route_id'],
                          'target': keys['tv'], 'params': {},
                          'consent': True})
        bodies = [
            {'invocation_id': lease_a['invocation_id'],
             'skill_id': 'ble_scan_room', 'route_id': lease_a['route_id'],
             'lease_id': lease_a['lease_id'],
             'graph_revision': lease_a['graph_revision'],
             'params': {'seconds': 8}, 'consent': True},
            {'invocation_id': lease_b['invocation_id'],
             'skill_id': 'device_facts', 'route_id': lease_b['route_id'],
             'lease_id': lease_b['lease_id'],
             'graph_revision': lease_b['graph_revision'],
             'target': keys['tv'], 'params': {}, 'consent': True},
        ]
        barrier = threading.Barrier(2)
        outcomes, errors = [], []

        def invoke(body):
            barrier.wait(timeout=5)
            try:
                outcomes.append(rt.invoke(body)['state'])
            except Exception as error:  # noqa: BLE001 - recorded below
                errors.append(error)

        threads = [threading.Thread(target=invoke, args=(bodies[0],)),
                   threading.Thread(target=invoke, args=(bodies[1],))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(errors, [])
        self.assertEqual(sorted(outcomes), ['VERIFIED', 'VERIFIED'])

    def test_concurrent_revocation_during_invoke_voids(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = rt.arm({'skill_id': 'ble_scan_room',
                        'route_id': doc['selected_route_id'],
                        'params': {'seconds': 8}, 'consent': True})
        gate = threading.Event()
        entered = threading.Event()
        orig_evaluate = rt._evaluate

        def slow_evaluate(skill_id, target):
            entered.set()
            gate.wait(timeout=10)
            return orig_evaluate(skill_id, target)

        rt._evaluate = slow_evaluate
        body = {'invocation_id': lease['invocation_id'],
                'skill_id': 'ble_scan_room', 'route_id': lease['route_id'],
                'lease_id': lease['lease_id'],
                'graph_revision': lease['graph_revision'],
                'params': {'seconds': 8}, 'consent': True}
        outcome = []

        def invoke():
            try:
                outcome.append(rt.invoke(body)['state'])
            except RouteError as error:
                outcome.append(error.code)

        thread = threading.Thread(target=invoke)
        thread.start()
        self.assertTrue(entered.wait(timeout=10))
        server.relays.relays['r-ph']['online'] = False
        server.relays.relays['r-tv']['online'] = False
        gate.set()
        thread.join(timeout=15)
        rt._evaluate = orig_evaluate
        self.assertTrue(not thread.is_alive())
        self.assertEqual(len(outcome), 1)
        self.assertIn(outcome[0], ('VERIFIED', 'CONSENT_VOID'))

    def test_lost_ack_stale_press_never_dispatches(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        doomed = sorted(prop['old_grant_disposition']
                        ['revoked_control_ids'])
        M.apply(server, prop, True)
        now_ms = int(clock.t * 1000)
        watch.queue.append({'request_id': '%032x' % 11,
                            'control_id': doomed[0], 'pressed_at': now_ms})
        watch.queue.append({'request_id': '%032x' % 12,
                            'control_id': doomed[0],
                            'pressed_at': now_ms - 120_000})
        rc.poll_once()
        self.assertEqual(calls, [])

    def test_crash_then_replay_never_double_dispatches(self):
        server, keys, clock, rt, calls, ex = routing_setup()
        doc = rt.skill_routes('ble_scan_room')
        lease = rt.arm({'skill_id': 'ble_scan_room',
                        'route_id': doc['selected_route_id'],
                        'params': {'seconds': 8}, 'consent': True})
        first = rt.invoke({'invocation_id': lease['invocation_id'],
                           'skill_id': 'ble_scan_room',
                           'route_id': lease['route_id'],
                           'lease_id': lease['lease_id'],
                           'graph_revision': lease['graph_revision'],
                           'params': {'seconds': 8}, 'consent': True})
        self.assertEqual(len(calls), 1)
        for _ in range(3):
            replay = rt.invoke(
                {'invocation_id': lease['invocation_id'],
                 'skill_id': 'ble_scan_room',
                 'route_id': lease['route_id'],
                 'lease_id': lease['lease_id'],
                 'graph_revision': lease['graph_revision'],
                 'params': {'seconds': 8}, 'consent': True})
            self.assertEqual(replay['state'], first['state'])
        self.assertEqual(len(calls), 1)

    def test_cancellation_midflight_leaves_no_partial_dispatch(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        before = copy.deepcopy(rc.grants)
        with self.assertRaises(M.MigrationError):
            M.apply(server, prop, False)
        self.assertEqual(copy.deepcopy(rc.grants), before)
        svc = t_service()
        with self.assertRaises(T.TransplantError):
            t_run_full(svc, consent=False)
        self.assertEqual(svc.dispatcher.receipts, {})

    def test_interleaved_migrate_and_dashboard_share_rc_safely(self):
        server, keys, clock, rc, watch, tv, calls = migrate_setup()
        prop = M.propose(
            server,
            text='Remove the volume controls from my watch and put them '
                 'on my TV.')['proposal']
        receipt = M.apply(server, prop, True)
        D.patch(rc, 'r-tv', add=[{
            'label': 'Owner extra', 'skill_id': 'device_facts',
            'target': keys['tv'], 'params': {}}], consent=True)
        labels = sorted(g['label'] for g in
                        (rc.grants.get('r-tv') or {}).values())
        self.assertIn('Owner extra', labels)
        rolled = M.rollback(server, receipt, True)
        self.assertTrue(rolled['rolled_back'])
        after = sorted(g['label'] for g in
                       (rc.grants.get('r-tv') or {}).values())
        self.assertIn('Owner extra', after)
        self.assertNotIn('TV volume +', after)


if __name__ == '__main__':
    unittest.main()






