"""V4 substrate trust kernel (SIMULATED_VERIFIED: real registry + Executor, fake device runners, fixed test key).
Each security test states the attack it blocks; all were written before kernel.py existed (new module)."""
import copy
import time
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace

from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.fabric.registry import Registry
from src.fabric.session import SessionJournal
from src.runtime.api_v2 import executor
from src.runtime.primitives import Executor
from src.substrate import registry as REG
from src.substrate.kernel import Substrate, SubstrateError, iso, manifest_hash, validate

KEY = b'k' * 32


def world(tv_grants=('observe', 'read', 'control')):
    reg = Registry()
    tv = reg.upsert([Identifier('android_serial', 'tv-1', True)], category='tv', label='Android TV',
                    observations=[DeviceObservation('model', 'Android_TV', 'ADB', 'WIFI', now(), True)])
    reg.devices[tv]['handles'] = {'WIFI': 'h-tv'}
    reg.link(Link('pc', tv, 'WIFI', tuple(tv_grants), 'ADB:device'))
    ph = reg.upsert([Identifier('android_serial', 'ph-1', True)], category='phone', label='BV9300',
                    observations=[DeviceObservation('model', 'BV9300', 'ADB', 'USB', now(), True)])
    reg.devices[ph]['handles'] = {'USB': 'h-ph'}
    reg.link(Link('pc', ph, 'USB', ('observe', 'read', 'control'), 'ADB:device'))
    server = SimpleNamespace(fabric_registry=reg, fabric_snapshot=reg.snapshot(), relays=SimpleNamespace(relays={}), relay_ledger=None,
                             session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'), runtime_executor=None, v4_substrate=None)
    return server, tv, ph


class Base(unittest.TestCase):
    def setUp(self, grants=('observe', 'read', 'control')):
        self.t = [1_800_000_000.0]
        self.server, self.tv, self.ph = world(grants)
        self.s = Substrate(self.server, clock=lambda: self.t[0], key=KEY)
        self.calls, self.next_state = [], 'VERIFIED'
        def fake(name):
            def run(_self, key, params):
                self.calls.append((name, key, params))
                st = self.next_state
                if st == 'RAISE':
                    raise OSError('link lost')
                return st, None, None, st == 'VERIFIED', {}
            return run
        ex = executor(self.server)
        ex.RUNNERS = dict(Executor.RUNNERS, device_action=fake('device_action'), read_facts=fake('read_facts'))
        self.fp = self.s.fingerprint(self.tv)
        self.facts = self.s.facts(self.tv)
        self.cat_fact = next(f for f in self.facts if f['name'] == 'category')

    def manifest(self, **over):
        m = {'manifest_version': 'obv4.1', 'capability_id': 'tv.mute_toggle', 'title': 'Mute the TV', 'origin': 'meta_generated',
             'model_run': {'provider': 'meta', 'model': 'muse-spark-1.3', 'run_id': 'run_0001abc'},
             'target': {'device_fingerprint': self.fp, 'category': 'tv'}, 'inputs': {},
             'steps': [{'step_id': 'mute', 'primitive_id': 'input.key', 'args': {'key': 'mute'}, 'on_uncertain': 'INCONCLUSIVE'},
                       {'step_id': 'check', 'primitive_id': 'state.screen', 'args': {}, 'on_uncertain': 'INCONCLUSIVE'}],
             'facts_required': [self.cat_fact['fact_id']], 'max_fact_age_s': 600,
             'evidence_refs': [self.cat_fact['fact_id'], 'src:android/keyevent/KEYCODE_VOLUME_MUTE'],
             'permissions_requested': ['control', 'read'], 'expires_at': iso(self.t[0] + 3600)}
        m.update(over)
        return m

    def request(self, m, grant, inputs=None, op='0' * 32):
        return {'operation_id': 'op-' + op, 'principal': 'owner', 'manifest_hash': manifest_hash(m), 'grant_id': grant['grant_id'],
                'inputs': inputs or {}, 'trace_id': 'trace01'}

    def rejects(self, code, fn, *a):
        with self.assertRaises(SubstrateError) as e:
            fn(*a)
        self.assertEqual(e.exception.code, code, str(e.exception))
        return e.exception


class Catalog(Base):
    def test_every_descriptor_matches_the_contract_and_no_shell_for_models(self):
        for d in REG.catalog():
            self.assertEqual(validate('PrimitiveDescriptor', d), [], d['id'])
        allowed = {d['id'] for d in REG.catalog() if d['manifest_allowed']}
        self.assertNotIn('pc.job', allowed)
        self.assertFalse(any('shell' in i or 'adb' in i for i in allowed))
        self.assertTrue(all(d['status'] in ('REAL_HARDWARE_VERIFIED', 'SIMULATED_VERIFIED') for d in REG.catalog() if d['id'] in REG.BACKEND))

    def test_signed_facts_validate(self):
        for f in self.facts:
            self.assertEqual(validate('Fact', f), [])


class Compiler(Base):
    def test_valid_manifest_compiles(self):
        c = self.s.compile(self.manifest(), self.facts)
        self.assertEqual((c['permissions'], c['origin'], c['dispatches']), (['control', 'read'], 'meta_generated', 2))

    def test_unknown_hypothesis_or_owner_only_primitive_returns_engineering_request(self):
        for pid, reason in (('tv.secret_call_audio', 'UNKNOWN_PRIMITIVE'), ('calls.place_call_with_confirmation', 'PRIMITIVE_HYPOTHESIS'),
                            ('pc.job', 'NOT_MANIFEST_ALLOWED'), ('remote.request_shutdown', 'NOT_MANIFEST_ALLOWED')):
            m = self.manifest(steps=[{'step_id': 'x', 'primitive_id': pid, 'args': {}, 'on_uncertain': 'ABORT'}])
            e = self.rejects('REJECTED_UNSUPPORTED_PRIMITIVE', self.s.compile, m, self.facts)
            self.assertEqual(e.extra['engineering_request']['reason'], reason)
            self.assertEqual(validate('EngineeringPrimitiveRequest', e.extra['engineering_request']), [])

    def test_privilege_escalation_on_read_only_device(self):
        self.setUp(grants=('observe', 'read'))
        self.rejects('PRIVILEGE_ESCALATION', self.s.compile, self.manifest(), self.facts)

    def test_undeclared_permission(self):
        self.rejects('UNDECLARED_PERMISSION', self.s.compile, self.manifest(permissions_requested=['read']), self.facts)

    def test_static_bounds(self):
        many = [{'step_id': f's{i}', 'primitive_id': 'state.screen', 'args': {}, 'on_uncertain': 'ABORT'} for i in range(13)]
        self.rejects('SCHEMA', self.s.compile, self.manifest(steps=many), self.facts)
        rep = [{'step_id': 'k', 'primitive_id': 'input.key', 'args': {'key': 'volume_up'}, 'repeat': 5, 'on_uncertain': 'ABORT'}]
        self.rejects('UNBOUNDED_EFFECT', self.s.compile, self.manifest(steps=rep), self.facts)
        loop = [{'step_id': f'r{i}', 'primitive_id': 'state.screen', 'args': {}, 'repeat': 5, 'on_uncertain': 'ABORT'} for i in range(5)]
        self.rejects('UNBOUNDED_EFFECT', self.s.compile, self.manifest(steps=loop), self.facts)

    def test_injection_and_untyped_args(self):
        self.rejects('INJECTION', self.s.compile, self.manifest(title='Mute $(reboot)'), self.facts)
        bad = [{'step_id': 'u', 'primitive_id': 'url.open', 'args': {'url': 'https://x/{{token}}'}, 'on_uncertain': 'ABORT'}]
        self.rejects('INJECTION', self.s.compile, self.manifest(steps=bad), self.facts)
        bad = [{'step_id': 'k', 'primitive_id': 'input.key', 'args': {'key': 'KEYCODE_POWER; reboot'}, 'on_uncertain': 'ABORT'}]
        self.rejects('INVALID_ARGS', self.s.compile, self.manifest(steps=bad), self.facts)
        bad = [{'step_id': 'k', 'primitive_id': 'input.key', 'args': {'key': 'mute', 'shell': 'id'}, 'on_uncertain': 'ABORT'}]
        self.rejects('INVALID_ARGS', self.s.compile, self.manifest(steps=bad), self.facts)

    def test_forged_swapped_or_wrong_target(self):
        self.rejects('UNKNOWN_TARGET', self.s.compile, self.manifest(target={'device_fingerprint': 'fp-' + '0' * 16, 'category': 'tv'}), self.facts)
        self.rejects('TARGET_MISMATCH', self.s.compile, self.manifest(target={'device_fingerprint': self.fp, 'category': 'phone'}), self.facts)
        other = Substrate(self.server, clock=lambda: self.t[0], key=b'x' * 32)          # fingerprints are keyed: not guessable
        self.assertNotEqual(other.fingerprint(self.tv), self.fp)

    def test_facts_forged_stale_changed_or_from_another_device(self):
        forged = dict(self.cat_fact, value='phone')
        self.rejects('FORGED_FACT', self.s.compile, self.manifest(), [forged])
        self.rejects('MISSING_FACT', self.s.compile, self.manifest(), [])
        m = self.manifest()
        self.t[0] += 10_000
        self.rejects('MANIFEST_EXPIRED', self.s.compile, m, self.facts)
        self.t[0] -= 10_000
        m = self.manifest(max_fact_age_s=5)
        old_fact = dict(self.cat_fact, observed_at=iso(self.t[0] - 60)); old_fact['signature'] = self.s._sign('fact', {k: v for k, v in old_fact.items() if k != 'signature'})
        m['facts_required'] = [old_fact['fact_id']]
        self.rejects('STALE_FACT', self.s.compile, m, [old_fact])
        ph_fact = next(f for f in self.s.facts(self.ph) if f['name'] == 'category')
        m = self.manifest(facts_required=[ph_fact['fact_id']])
        self.rejects('FACT_OTHER_DEVICE', self.s.compile, m, [ph_fact])

    def test_references_must_be_declared(self):
        st = [{'step_id': 'k', 'primitive_id': 'input.key', 'args': {'key': {'$input': 'k'}}, 'on_uncertain': 'ABORT'}]
        self.rejects('BAD_REFERENCE', self.s.compile, self.manifest(steps=st), self.facts)
        m = self.manifest(steps=st, inputs={'k': {'type': 'string', 'enum': ['volume_up', 'volume_down']}})
        self.s.compile(m, self.facts)
        self.rejects('INVALID_INPUT', self.s.compile, m, self.facts, {'k': 'power'})
        self.rejects('INPUTS', self.s.compile, self.manifest(inputs={'k': {'type': 'object'}}), self.facts)

    def test_primitive_must_fit_the_device(self):
        st = [{'step_id': 'v', 'primitive_id': 'vendor.tuya.command', 'args': {'command': 'dock'}, 'on_uncertain': 'ABORT'}]
        self.rejects('PRIMITIVE_NOT_FOR_DEVICE', self.s.compile, self.manifest(steps=st), self.facts)


class Grants(Base):
    def test_owner_grant_then_invoke_dispatches_exact_primitives(self):
        m = self.manifest()
        g, _ = self.s.issue_grant(m, self.facts, True)
        self.assertEqual(validate('Grant', g), [])
        rec = self.s.invoke(m, g, self.facts, self.request(m, g))
        self.assertEqual(validate('Receipt', rec), [])
        self.assertTrue(self.s.verify_receipt(rec))
        self.assertEqual(rec['status'], 'VERIFIED')
        self.assertEqual([c[2] for c in self.calls], [{'action': 'key', 'args': {'key': 'mute'}}, {'action': 'screen_state'}])
        self.assertEqual(rec['origin'], 'meta_generated')

    def test_model_cannot_approve_itself(self):
        m = self.manifest()
        self.rejects('CONSENT_REQUIRED', self.s.issue_grant, m, self.facts, False)
        g, _ = self.s.issue_grant(m, self.facts, True)
        fake = dict(g, max_uses=100)                                   # widened by a model: signature breaks
        self.rejects('GRANT_FORGED', self.s.invoke, m, fake, self.facts, self.request(m, fake))
        minted = dict(g, grant_id='g-' + 'a' * 16, signature='0' * 64)
        self.rejects('GRANT_FORGED', self.s.invoke, m, minted, self.facts, self.request(m, minted))
        self.assertEqual(self.calls, [])

    def test_grant_bound_to_hash_device_uses_expiry_and_revocation(self):
        m = self.manifest()
        g, _ = self.s.issue_grant(m, self.facts, True, max_uses=1, ttl_s=60)
        m2 = self.manifest(title='Mute the TV now')                    # any edit = another manifest version
        self.rejects('GRANT_OTHER_MANIFEST', self.s.invoke, m2, g, self.facts, self.request(m2, g))
        self.s.invoke(m, g, self.facts, self.request(m, g))
        self.rejects('GRANT_USED', self.s.invoke, m, g, self.facts, self.request(m, g, op='1' * 32))
        g2, _ = self.s.issue_grant(m, self.facts, True, ttl_s=60)
        self.t[0] += 120
        self.rejects('GRANT_EXPIRED', self.s.invoke, m, g2, self.facts, self.request(m, g2, op='2' * 32))
        self.t[0] -= 120
        g3, _ = self.s.issue_grant(m, self.facts, True)
        self.s.revoke(g3['grant_id'])
        self.rejects('GRANT_REVOKED', self.s.invoke, m, g3, self.facts, self.request(m, g3, op='3' * 32))
        self.assertEqual(len(self.calls), 2)

    def test_operation_replay_and_hash_mismatch(self):
        m = self.manifest()
        g, _ = self.s.issue_grant(m, self.facts, True, max_uses=5)
        self.s.invoke(m, g, self.facts, self.request(m, g))
        self.rejects('OPERATION_REPLAY', self.s.invoke, m, g, self.facts, self.request(m, g))
        r = dict(self.request(m, g, op='4' * 32), manifest_hash='sha256:' + '0' * 64)
        self.rejects('HASH_MISMATCH', self.s.invoke, m, g, self.facts, r)

    def test_device_swap_after_grant(self):
        m = self.manifest()
        g, _ = self.s.issue_grant(m, self.facts, True)
        dev = self.server.fabric_registry.devices[self.tv]
        dev['identifiers'] = {Identifier('android_serial', 'other-tv', True)}   # same key, different physical device
        self.rejects('UNKNOWN_TARGET', self.s.invoke, m, g, self.facts, self.request(m, g))
        self.assertEqual(self.calls, [])

    def test_uncertain_outcome_is_inconclusive_and_never_retried(self):
        st = [{'step_id': 'up', 'primitive_id': 'input.key', 'args': {'key': 'volume_up'}, 'repeat': 3, 'on_uncertain': 'INCONCLUSIVE'}]
        m = self.manifest(steps=st, permissions_requested=['control'])
        g, _ = self.s.issue_grant(m, self.facts, True)
        self.next_state = 'RAISE'
        rec = self.s.invoke(m, g, self.facts, self.request(m, g))
        self.assertEqual(rec['status'], 'INCONCLUSIVE')
        self.assertEqual(len(self.calls), 1)                            # stopped at the first uncertain press

    def test_permission_revoked_between_steps_blocks_the_rest(self):
        m = self.manifest()
        g, _ = self.s.issue_grant(m, self.facts, True)
        orig = executor(self.server).RUNNERS['device_action']
        def downgrade(_self, key, params):
            r = orig(_self, key, params)
            for l in self.server.fabric_snapshot['links']:
                if l['child'] == self.tv:
                    l['grants'] = ['observe']
            return r
        executor(self.server).RUNNERS = dict(executor(self.server).RUNNERS, device_action=downgrade)
        rec = self.s.invoke(m, g, self.facts, self.request(m, g))
        self.assertEqual(rec['status'], 'BLOCKED')
        self.assertEqual(len(self.calls), 1)


class Http(unittest.TestCase):
    def test_catalog_public_grant_needs_csrf(self):
        from src.server import create_server
        s = create_server(0, fabric_salt=b't', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        threading.Thread(target=s.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{s.server_port}'
        try:
            cat = json.loads(urllib.request.urlopen(base + '/api/v2/primitives/catalog').read())
            self.assertEqual(cat['contract_version'], 'obv4.1')
            self.assertIn('input.key', [p['id'] for p in cat['primitives']])
            body = json.dumps({'manifest': {}, 'facts': [], 'consent': True}).encode()
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(base + '/api/v2/manifests/grant', body, {'Content-Type': 'application/json'}))
            self.assertEqual(e.exception.code, 403); e.exception.close()
            csrf = json.loads(urllib.request.urlopen(base + '/api/session').read())['csrf_token']
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(base + '/api/v2/manifests/compile', body,
                                                              {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Origin': base}))
            self.assertEqual(e.exception.code, 400); e.exception.close()
        finally:
            s.shutdown(); s.server_close()


if __name__ == '__main__':
    unittest.main()


class UIPlan(Base):
    """Meta UIViewPlan -> Companion buttons -> approved manifest executions (fake Companion mirroring RelayServer.java)."""
    def setUp(self):
        super().setUp()
        import time as _t
        from src.fabric import relay as R
        from src.fabric.relay import RelayManager
        from src.runtime.api_v2 import remote_controls
        from tests.runtime.test_remote_controls import FakeCompanion, KEY as RKEY
        self.R = R
        self.server.relays = RelayManager(transport=lambda r, m: {})
        self.server.relays.enroll('r-tv', RKEY, 'h-tv', {'capabilities': ['remote_controls'], 'permissions': {}})
        self.comp = FakeCompanion(); self.comp.clock = lambda: self.t[0]
        self.server.relays.relays['r-tv']['send'] = self.comp
        self.server.v4_substrate = self.s
        self.rc = remote_controls(self.server); self.rc.clock = lambda: self.t[0]; self.rc._ensure_thread = lambda: None

    def plan(self, m, label='Mute', **over):
        p = {'target_device': self.fp, 'profile_id': 'tv.remote', 'layout_version': 1,
             'widgets': [{'widget_id': 'mute', 'kind': 'button', 'label': label, 'binding': {'manifest_hash': manifest_hash(m), 'inputs': {}},
                          'permission_label': 'control TV keys'}],
             'origin_model_run_id': 'run_0002ui', 'evidence_refs': ['src:wear/ui']}
        p.update(over)
        p['plan_hash'] = manifest_hash(p)
        return p

    def install(self, p, m, g):
        return self.s.install_ui_plan({'relay_id': 'r-tv', 'consent': True, 'plan': p,
                                       'bindings': {manifest_hash(m): {'manifest': m, 'grant': g, 'facts': self.facts}}})

    def test_plan_installs_and_press_runs_the_manifest_once(self):
        m = self.manifest()
        g, _ = self.s.issue_grant(m, self.facts, True, max_uses=5)
        out = self.install(self.plan(m), m, g)
        self.assertEqual(len(out['installed']), 1)
        self.assertEqual(self.comp.controls, [{'control_id': out['installed'][0], 'label': 'Mute'}])   # labels only reach the device
        rid = self.comp.press(out['installed'][0], request_id='%032x' % 9)
        self.rc.poll_once()
        self.assertEqual(len(self.calls), 2)                                  # input.key + state.screen
        self.assertEqual(self.s.receipts[-1]['operation_id'], 'op-' + rid)
        self.assertIn('done', self.comp.results[-1]['text'])
        self.t[0] += 2
        self.comp.press(out['installed'][0], request_id=rid)                  # same press re-sent
        self.rc.poll_once()
        self.assertEqual(len(self.calls), 2)
        state = json.dumps(self.rc.state())
        self.assertNotIn('signature', state)                                  # grants are not exposed by GET

    def test_plan_rejections(self):
        m = self.manifest()
        g, _ = self.s.issue_grant(m, self.facts, True)
        p = self.plan(m); p['layout_version'] = 2                              # tampered after hashing
        self.rejects('PLAN_HASH', self.install, p, m, g)
        self.rejects('UI_TARGET', self.install, self.plan(m, target_device=self.s.fingerprint(self.ph)), m, g)
        self.rejects('INJECTION', self.install, self.plan(m, label='<script>x'), m, g)
        forged = dict(g, signature='0' * 64)
        self.rejects('GRANT_FORGED', self.install, self.plan(m), m, forged)
        other = self.manifest(title='Other')
        self.rejects('UI_BINDING', self.s.install_ui_plan, {'relay_id': 'r-tv', 'consent': True, 'plan': self.plan(m),
                                                           'bindings': {manifest_hash(m): {'manifest': other, 'grant': g, 'facts': self.facts}}})
        self.assertEqual(self.comp.controls, [])

    def test_revoked_grant_blocks_presses(self):
        m = self.manifest()
        g, _ = self.s.issue_grant(m, self.facts, True, max_uses=5)
        out = self.install(self.plan(m), m, g)
        self.s.revoke(g['grant_id'])
        self.comp.press(out['installed'][0], request_id='%032x' % 10)
        self.rc.poll_once()
        self.assertEqual(self.calls, [])
        self.assertIn('grant revoked', self.comp.results[-1]['text'])


class SharedFixtures(Base):
    """Fixtures handed to Muse Code: they must stay valid against the contract and the kernel (same test key/clock)."""
    def test_fixtures_validate(self):
        import pathlib
        d = pathlib.Path(__file__).with_name('fixtures')
        load = lambda n: json.loads((d / n).read_text())
        for name, typ in (('manifest_tv_mute.json', 'CandidateManifest'), ('grant_tv_mute.json', 'Grant'), ('uiplan_tv_remote.json', 'UIViewPlan'),
                          ('receipt_tv_mute.json', 'Receipt'), ('invoke_request.json', 'InvokeRequest')):
            self.assertEqual(validate(typ, load(name)), [], name)
        for f in load('facts_tv.json'):
            self.assertEqual(validate('Fact', f), [])
        m = load('manifest_tv_mute.json')
        self.assertEqual(m['target']['device_fingerprint'], self.fp)
        self.s.compile(m, load('facts_tv.json'))
        self.assertTrue(self.s.verify_receipt(load('receipt_tv_mute.json')))


class SolReview(Base):
    """Sol V4 review of PR #72 (head 8a73b8f): both cases passed the kernel before the fix."""
    def test_p1_concurrent_same_operation_id_dispatches_once(self):
        m = self.manifest()
        g, _ = self.s.issue_grant(m, self.facts, True, max_uses=10)
        real = self.s.compile
        def slow(*a, **k):
            r = real(*a, **k); time.sleep(0.05); return r      # widen the window between the replay check and dispatch
        self.s.compile = slow
        out, errs = [], []
        def go():
            try:
                out.append(self.s.invoke(m, g, self.facts, self.request(m, g)))
            except SubstrateError as e:
                errs.append(e.code)
        ths = [threading.Thread(target=go) for _ in range(5)]
        for t in ths: t.start()
        for t in ths: t.join(10)
        self.assertEqual(len(out), 1)
        self.assertEqual(errs, ['OPERATION_REPLAY'] * 4)
        self.assertEqual(len(self.calls), 2)                     # one operation = its two steps, once

    def test_p2_unverified_or_downgraded_fact_is_refused(self):
        self.t[0] = time.time()                                  # registry facts carry real observation times
        self.facts = self.s.facts(self.tv)
        model = next(f for f in self.facts if f['name'] == 'model')
        weak = dict(model, verified=False)
        weak['signature'] = self.s._sign('fact', {k: v for k, v in weak.items() if k != 'signature'})   # legitimately signed, unverified
        m = self.manifest(facts_required=[weak['fact_id']], evidence_refs=[weak['fact_id']])
        self.rejects('UNVERIFIED_FACT', self.s.compile, m, [weak])
        m = self.manifest(facts_required=[model['fact_id']], evidence_refs=[model['fact_id']])
        self.s.compile(m, [model])                               # verified ADB fact: accepted
        dev = next(d for d in self.server.fabric_snapshot['devices'] if d['key'] == self.tv)
        dev['facts']['model'] = dict(dev['facts']['model'], verified=False, sources=['UNKNOWN'])   # same value, trust downgraded
        self.rejects('FACT_CHANGED', self.s.compile, m, [model])
