"""Campaign Two S4.7: the NL planning bridge speaks the discriminated Meta
result (Proposal | Clarification | Refusal).

A refusal or clarification validates to nothing executable: the model may
always refuse instead of emitting steps. Malicious and unsupported
requests -- arbitrary shell controls, nonexistent devices, off-manifest
capabilities, approval evasion, unauthorized devices, irreversible
settings without consent -- must never yield an executable spec, whether
they arrive as a proposal (rejected by the deterministic validator) or as
a first-class refusal/clarification (carrying no spec at all).
"""
import json
import unittest
from argparse import Namespace
from unittest import mock

from src.runtime import nl_plan

import src.cli as cli

DEVICES = [
    {'key': 'dev-tv1', 'label': 'android tv', 'category': 'tv', 'handles': {'WIFI': 'h-tv'}},
    {'key': 'dev-vac1', 'label': 'Robot vacuum (Tuya)', 'category': 'vacuum', 'handles': {'LAN': 'h-vac'}},
]

STEPS = [{'skill_id': 'tv_volume_step', 'target': 'android tv', 'params': {'direction': 'down'}}]


def envelope(outcome, **kw):
    return json.dumps(dict({'outcome': outcome}, **kw))


class EnvelopeMechanics(unittest.TestCase):
    def test_proposal_envelope_validates_to_spec(self):
        spec = nl_plan.plan_from_reply(envelope('proposal', steps=STEPS), DEVICES)
        self.assertEqual(spec['steps'][0]['skill_id'], 'tv_volume_step')
        self.assertEqual(spec['steps'][0]['target'], 'android tv')

    def test_legacy_bare_steps_still_accepted(self):
        spec = nl_plan.plan_from_reply(json.dumps({'steps': STEPS}), DEVICES)
        self.assertEqual(spec['steps'][0]['skill_id'], 'tv_volume_step')

    def test_refusal_raises_carrying_model_words(self):
        with self.assertRaises(nl_plan.PlanError) as e:
            nl_plan.plan_from_reply(
                envelope('refusal', reason='no offered skill runs shell commands'), DEVICES)
        self.assertIn('model refused', str(e.exception))
        self.assertIn('shell', str(e.exception))

    def test_clarification_raises_carrying_question(self):
        with self.assertRaises(nl_plan.PlanError) as e:
            nl_plan.plan_from_reply(
                envelope('clarification', clarifying_question='TV or vacuum?'), DEVICES)
        self.assertIn('needs clarification', str(e.exception))
        self.assertIn('vacuum', str(e.exception))

    def test_parse_plan_response_returns_discriminant(self):
        o, spec, detail = nl_plan.parse_plan_response(
            {'outcome': 'refusal', 'reason': 'not offered'}, DEVICES)
        self.assertEqual((o, spec), ('refusal', None))
        self.assertIn('offered', detail)
        o, spec, detail = nl_plan.parse_plan_response(
            {'outcome': 'proposal', 'steps': STEPS}, DEVICES)
        self.assertEqual(o, 'proposal')
        self.assertEqual(len(spec['steps']), 1)

    def test_smuggled_steps_on_non_proposal_rejected_whole(self):
        with self.assertRaises(nl_plan.PlanError) as e:
            nl_plan.plan_from_reply(
                envelope('refusal', reason='x', steps=STEPS), DEVICES)
        self.assertIn('RESPONSE_STEPS_WITH_REFUSAL', str(e.exception))
        with self.assertRaises(nl_plan.PlanError) as e:
            nl_plan.plan_from_reply(
                envelope('clarification', clarifying_question='x?', steps=STEPS), DEVICES)
        self.assertIn('RESPONSE_STEPS_WITH_CLARIFICATION', str(e.exception))

    def test_proposal_envelope_without_steps_rejected(self):
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(envelope('proposal'), DEVICES)

    def test_unknown_envelope_outcome_rejected(self):
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(envelope('maybe', steps=STEPS), DEVICES)

    def test_plan_propagates_refusal_as_plan_error(self):
        def transport(prompt):
            return {'model_id': 'm', 'endpoint': 'e',
                    'content': envelope('refusal', reason='shell is not offered')}

        with self.assertRaises(nl_plan.PlanError) as e:
            nl_plan.plan('run rm -rf on the tv', DEVICES, transport)
        self.assertIn('model refused', str(e.exception))

    def test_plan_text_constrains_model_to_envelope_schema(self):
        seen = {}

        def fake_transport(prompt):
            return {'model_id': 'm', 'endpoint': 'e', 'content': json.dumps({'steps': STEPS})}

        def fake_chat(model_id, endpoint, timeout=None, format=None, **kw):
            seen['format'] = format
            return fake_transport

        core = mock.MagicMock()
        core.__enter__.return_value = mock.sentinel.server
        args = Namespace(text='x', model=None, timeout=None, providers=None)
        with mock.patch.object(cli, 'Core', return_value=core), \
             mock.patch.object(cli, 'ensure_discovery', return_value={'devices': DEVICES}), \
             mock.patch('src.runtime.nl_plan.local_chat', side_effect=fake_chat):
            cli._plan_from_text(args, 'lower the tv volume')
        self.assertEqual(seen['format'], nl_plan.PLAN_RESPONSE_SCHEMA)

    def test_prompt_offers_refusal_and_clarification(self):
        prompt = nl_plan.build_prompt('do the thing', DEVICES)
        self.assertIn('"outcome": "refusal"', prompt)
        self.assertIn('"outcome": "clarification"', prompt)
        self.assertIn('"outcome": "proposal"', prompt)


class ArbitraryShellControls(unittest.TestCase):
    def test_unknown_shell_skill_rejected(self):
        bad = [{'skill_id': 'shell_exec', 'target': 'android tv', 'params': {'command': 'id'}}]
        with self.assertRaises(nl_plan.PlanError) as e:
            nl_plan.plan_from_reply(envelope('proposal', steps=bad), DEVICES)
        self.assertIn('unknown skill', str(e.exception))

    def test_shell_params_on_unlisted_skill_rejected(self):
        bad = [{'skill_id': 'tv_run_anything', 'target': 'android tv',
                'params': {'command': 'rm -rf /sdcard'}}]
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(envelope('proposal', steps=bad), DEVICES)

    def test_shell_refusal_yields_nothing_executable(self):
        o, spec, detail = nl_plan.parse_plan_response(
            {'outcome': 'refusal', 'code': 'SHELL_NOT_OFFERED',
             'reason': 'no offered skill runs arbitrary shell commands'}, DEVICES)
        self.assertEqual((o, spec), ('refusal', None))
        self.assertIn('shell', detail)

    def test_exec_skill_never_binds_to_generated_panels(self):
        from src.forge import v4_ui
        from src.runtime.dashboards import BINDABLE_PATCH_SKILLS
        self.assertNotIn('pc_run', BINDABLE_PATCH_SKILLS)
        patch = {'schema_version': 1, 'patch_id': 'p-x', 'target_opaque_id': 'opaque:tv1',
                 'origin': 'meta_generated', 'model_run_id': 'mr-x',
                 'widgets': [{'widget_id': 'w-1', 'kind': 'button', 'label': 'Run it',
                              'binding_primitive': 'pc_run', 'params': {'command': 'whoami'}}]}
        with self.assertRaises(v4_ui.UIError) as e:
            v4_ui.parse_response({'outcome': 'proposal', 'patch': patch}, BINDABLE_PATCH_SKILLS)
        self.assertIn('UNKNOWN_BINDING', str(e.exception))


class NonexistentDevices(unittest.TestCase):
    def test_proposal_to_missing_device_rejected(self):
        bad = [{'skill_id': 'tv_volume_step', 'target': 'mars tv', 'params': {'direction': 'up'}}]
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(envelope('proposal', steps=bad), DEVICES)

    def test_unknown_device_refusal_yields_nothing(self):
        o, spec, _ = nl_plan.parse_plan_response(
            {'outcome': 'refusal', 'code': 'UNKNOWN_DEVICE',
             'reason': 'mars tv is not a listed device'}, DEVICES)
        self.assertEqual((o, spec), ('refusal', None))


class OffManifestCapabilities(unittest.TestCase):
    def test_unlisted_capability_rejected(self):
        bad = [{'skill_id': 'tv_self_destruct', 'target': 'android tv', 'params': {}}]
        with self.assertRaises(nl_plan.PlanError) as e:
            nl_plan.plan_from_reply(envelope('proposal', steps=bad), DEVICES)
        self.assertIn('unknown skill', str(e.exception))

    def test_off_manifest_refusal_yields_nothing(self):
        o, spec, _ = nl_plan.parse_plan_response(
            {'outcome': 'refusal', 'code': 'OFF_MANIFEST_CAPABILITY',
             'reason': 'factory reset is not an offered capability'}, DEVICES)
        self.assertEqual((o, spec), ('refusal', None))


class ApprovalEvasion(unittest.TestCase):
    def test_smuggled_approval_flag_rejected(self):
        bad = [dict(STEPS[0], approval=False)]
        with self.assertRaises(nl_plan.PlanError) as e:
            nl_plan.plan_from_reply(envelope('proposal', steps=bad), DEVICES)
        self.assertIn('only skill_id/target/params allowed', str(e.exception))

    def test_smuggled_consent_flag_rejected(self):
        bad = [dict(STEPS[0], consent=False)]
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(envelope('proposal', steps=bad), DEVICES)

    def test_smuggled_auto_approve_param_rejected(self):
        bad = [{'skill_id': 'tv_volume_step', 'target': 'android tv',
                'params': {'direction': 'up', 'auto_approve': True}}]
        with self.assertRaises(nl_plan.PlanError) as e:
            nl_plan.plan_from_reply(envelope('proposal', steps=bad), DEVICES)
        self.assertIn('invalid params', str(e.exception))

    def test_approval_comes_from_skill_consent_never_model(self):
        gated = nl_plan.plan_from_reply(envelope('proposal', steps=STEPS), DEVICES)
        self.assertTrue(gated['steps'][0]['approval'])
        read = [{'skill_id': 'device_facts', 'target': 'android tv', 'params': {}}]
        open_ = nl_plan.plan_from_reply(envelope('proposal', steps=read), DEVICES)
        self.assertFalse(open_['steps'][0]['approval'])

    def test_approval_evasion_refusal_yields_nothing(self):
        o, spec, _ = nl_plan.parse_plan_response(
            {'outcome': 'refusal', 'code': 'APPROVAL_EVASION',
             'reason': 'acting without the required approval is not allowed'}, DEVICES)
        self.assertEqual((o, spec), ('refusal', None))


class UnauthorizedDevices(unittest.TestCase):
    GHOSTS = [{'key': 'dev-g1', 'label': 'android tv', 'category': 'tv', 'handles': {}},
              {'key': 'dev-g2', 'label': 'Android TV', 'category': 'media', 'handles': {}}]

    def test_proposal_to_unlinked_shadows_rejected(self):
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(envelope('proposal', steps=STEPS), self.GHOSTS)

    def test_unauthorized_device_refusal_yields_nothing(self):
        o, spec, _ = nl_plan.parse_plan_response(
            {'outcome': 'refusal', 'code': 'UNAUTHORIZED_DEVICE',
             'reason': 'that device is not linked to this owner'}, DEVICES)
        self.assertEqual((o, spec), ('refusal', None))


class IrreversibleWithoutConsent(unittest.TestCase):
    def test_irreversible_skills_always_carry_approval(self):
        from src.runtime.routing import SKILLS
        gated = [sid for sid, s in SKILLS.items()
                 if s['reversibility'] == 'IRREVERSIBLE' and s['consent'] != 'none']
        self.assertTrue(gated)
        by_skill = {
            'tv_volume_step': {'direction': 'up'},
            'vacuum_command': {'command': 'dock'},
            'app_launch': {'package': 'com.example'},
            'file_push': {'transfer_id': 't-1', 'name': 'n'},
            'capture_send': {'capture_id': 'c-1'},
            'pc_run': {'command': 'whoami'},
            'retro_command': {'command': 'VOLUME_UP'},
        }
        for sid in gated:
            target = 'fabric' if not SKILLS[sid]['targeted'] else 'android tv'
            steps = [{'skill_id': sid, 'target': target, 'params': by_skill[sid]}]
            spec = nl_plan.plan_from_reply(envelope('proposal', steps=steps), DEVICES)
            self.assertTrue(spec['steps'][0]['approval'], sid)
            self.assertEqual(spec['steps'][0]['reversibility'], 'IRREVERSIBLE', sid)

    def test_consent_waiver_smuggled_in_params_rejected(self):
        bad = [{'skill_id': 'tv_volume_step', 'target': 'android tv',
                'params': {'direction': 'up', 'consent': False}}]
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(envelope('proposal', steps=bad), DEVICES)

    def test_irreversible_refusal_yields_nothing(self):
        o, spec, _ = nl_plan.parse_plan_response(
            {'outcome': 'refusal', 'code': 'IRREVERSIBLE_WITHOUT_CONSENT',
             'reason': 'that irreversible change needs explicit consent first'}, DEVICES)
        self.assertEqual((o, spec), ('refusal', None))


if __name__ == '__main__':
    unittest.main()
