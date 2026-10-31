"""S4 NL->workflow planning bridge: a Meta model proposes multi-step plans, the
deterministic validator admits only registered skills on live devices (no model
calls here; the transport is injected and faked)."""
import json
import unittest

from src.runtime import nl_plan


DEVICES = [
    {'key': 'dev-tv1', 'label': 'android tv', 'category': 'tv', 'handles': {'WIFI': 'h-tv'}},
    {'key': 'dev-vac1', 'label': 'Robot vacuum (Tuya)', 'category': 'vacuum', 'handles': {'LAN': 'h-vac'}},
]

REPLY = json.dumps({'steps': [
    {'skill_id': 'tv_volume_step', 'target': 'android tv', 'params': {'direction': 'down'}},
    {'skill_id': 'vacuum_command', 'target': 'Robot vacuum (Tuya)', 'params': {'command': 'dock'}},
]})


class PromptTest(unittest.TestCase):
    def test_prompt_lists_labels_and_skills_without_device_keys(self):
        prompt = nl_plan.build_prompt('quiet mode', DEVICES)
        self.assertIn('android tv', prompt)
        self.assertIn('tv_volume_step', prompt)
        self.assertIn('vacuum_command', prompt)
        self.assertNotIn('dev-tv1', prompt)
        self.assertNotIn('dev-vac1', prompt)

    def test_prompt_shows_exact_json_example(self):
        prompt = nl_plan.build_prompt('quiet mode', DEVICES)
        self.assertIn('copy the target label EXACTLY', prompt)
        self.assertIn('Example: {"steps": [{"skill_id": "tv_volume_step"', prompt)


class ReplyTest(unittest.TestCase):
    def test_happy_path_resolves_labels_and_marks_write_approval(self):
        spec = nl_plan.plan_from_reply(REPLY, DEVICES)
        self.assertEqual(spec['consent'], True)
        steps = {s['id']: s for s in spec['steps']}
        # Labels are the stable reference: keys rotate every discovery.
        self.assertEqual(steps['step1']['target'], 'android tv')
        self.assertEqual(steps['step2']['target'], 'Robot vacuum (Tuya)')
        self.assertTrue(steps['step1']['approval'])
        self.assertTrue(steps['step2']['approval'])
        self.assertEqual(steps['step1']['reversibility'], 'IRREVERSIBLE')
        self.assertEqual(steps['step2']['reversibility'], 'IRREVERSIBLE')

    def test_read_skill_needs_no_step_approval(self):
        reply = json.dumps({'steps': [
            {'skill_id': 'device_facts', 'target': 'android tv', 'params': {}}]})
        spec = nl_plan.plan_from_reply(reply, DEVICES)
        self.assertFalse(spec['steps'][0]['approval'])
        self.assertEqual(spec['steps'][0]['reversibility'], 'NONE')

    def test_spec_passes_workflow_validation(self):
        from src.runtime.workflows import validate_workflow
        spec = nl_plan.plan_from_reply(REPLY, DEVICES)
        doc = validate_workflow(spec)
        self.assertEqual(len(doc['steps']), 2)

    def test_unknown_skill_rejected(self):
        reply = json.dumps({'steps': [
            {'skill_id': 'tv_self_destruct', 'target': 'android tv', 'params': {}}]})
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(reply, DEVICES)

    def test_unknown_target_rejected(self):
        reply = json.dumps({'steps': [
            {'skill_id': 'tv_volume_step', 'target': 'mars tv', 'params': {'direction': 'down'}}]})
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(reply, DEVICES)

    def test_ambiguous_label_rejected(self):
        devs = DEVICES + [{'key': 'dev-tv2', 'label': 'Android TV', 'category': 'tv',
                           'handles': {'WIFI': 'h-tv2'}}]
        reply = json.dumps({'steps': [
            {'skill_id': 'tv_volume_step', 'target': 'android tv', 'params': {'direction': 'down'}}]})
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(reply, devs)

    def test_ghost_rows_collapse_openly_to_linked_device(self):
        devs = (DEVICES
                + [{'key': 'dev-tv9', 'label': 'Android TV', 'category': 'media', 'handles': {}}])
        reply = json.dumps({'steps': [
            {'skill_id': 'tv_volume_step', 'target': 'android tv', 'params': {'direction': 'down'}}]})
        spec = nl_plan.plan_from_reply(reply, devs)
        self.assertEqual(spec['steps'][0]['target'], 'android tv')
        self.assertTrue(spec['steps'][0]['disambiguated'])

    def test_all_ghost_matches_rejected(self):
        devs = [{'key': 'dev-tv9', 'label': 'Android TV', 'category': 'media', 'handles': {}},
                {'key': 'dev-tv8', 'label': 'android tv', 'category': 'tv', 'handles': {}}]
        reply = json.dumps({'steps': [
            {'skill_id': 'tv_volume_step', 'target': 'android tv', 'params': {'direction': 'down'}}]})
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(reply, devs)

    def test_bad_params_rejected(self):
        reply = json.dumps({'steps': [
            {'skill_id': 'tv_volume_step', 'target': 'android tv', 'params': {'direction': 'sideways'}}]})
        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan_from_reply(reply, DEVICES)

    def test_malformed_and_empty_replies_rejected(self):
        for bad in ('not json{{', json.dumps({'steps': []}),
                    json.dumps({'steps': [{'skill_id': 'device_facts'}]}),
                    json.dumps({'steps': [{'skill_id': 'device_facts', 'target': 'android tv',
                                           'params': {}} for _ in range(9)]})):
            with self.assertRaises(nl_plan.PlanError, msg=bad[:40]):
                nl_plan.plan_from_reply(bad, DEVICES)


class TransportTest(unittest.TestCase):
    def test_local_chat_constrains_json_and_checks_identity(self):
        seen = {}

        def fake_chat(payload):
            seen.update(payload)
            return {'model': 'llama3.2:3b-instruct-q4_K_M', 'done': True, 'done_reason': 'stop',
                    'message': {'content': REPLY}}

        t = nl_plan.local_chat('llama3.2:3b-instruct-q4_K_M', 'http://127.0.0.1:11437',
                               chat=fake_chat)
        res = t('prompt')
        self.assertEqual(res['model_id'], 'llama3.2:3b-instruct-q4_K_M')
        self.assertIn('format', seen)
        self.assertEqual(seen['format']['type'], 'object')

    def test_local_chat_forwards_custom_format(self):
        seen = {}

        def fake_chat(payload):
            seen.update(payload)
            return {'model': 'llama3.2:3b-instruct-q4_K_M', 'done': True, 'done_reason': 'stop',
                    'message': {'content': REPLY}}

        custom = {'type': 'object', 'required': ['widgets']}
        t = nl_plan.local_chat('llama3.2:3b-instruct-q4_K_M', 'http://127.0.0.1:11437',
                               chat=fake_chat, format=custom)
        t('prompt')
        self.assertEqual(seen['format'], custom)

    def test_local_chat_merges_options_over_temp_zero_default(self):
        seen = {}

        def fake_chat(payload):
            seen.update(payload)
            return {'model': 'llama3.2:3b-instruct-q4_K_M', 'done': True, 'done_reason': 'stop',
                    'message': {'content': REPLY}}

        t = nl_plan.local_chat('llama3.2:3b-instruct-q4_K_M', 'http://127.0.0.1:11437',
                               chat=fake_chat, options={'num_ctx': 4096})
        t('prompt')
        self.assertEqual(seen['options']['temperature'], 0)
        self.assertEqual(seen['options']['num_ctx'], 4096)

    def test_local_chat_forwards_every_caller_option_to_payload(self):
        seen = {}

        def fake_chat(payload):
            seen.update(payload)
            return {'model': 'llama3.2:3b-instruct-q4_K_M', 'done': True, 'done_reason': 'stop',
                    'message': {'content': REPLY}}

        t = nl_plan.local_chat('llama3.2:3b-instruct-q4_K_M', 'http://127.0.0.1:11437',
                               chat=fake_chat, options={'num_predict': 512})
        t('prompt')
        self.assertEqual(seen['options']['num_predict'], 512)
        self.assertEqual(seen['options']['temperature'], 0)

    def test_local_chat_disables_thinking_traces(self):
        seen = {}

        def fake_chat(payload):
            seen.update(payload)
            return {'model': 'muse-glimmer:30b-q4_K_M', 'done': True, 'done_reason': 'stop',
                    'message': {'content': REPLY}}

        t = nl_plan.local_chat('muse-glimmer:30b-q4_K_M', 'http://127.0.0.1:11438',
                               chat=fake_chat)
        t('prompt')
        self.assertIs(seen.get('think'), False)

    def test_local_chat_rejects_wrong_model_identity(self):
        def fake_chat(payload):
            return {'model': 'evil:99b', 'done': True, 'done_reason': 'stop',
                    'message': {'content': REPLY}}

        t = nl_plan.local_chat('llama3.2:3b-instruct-q4_K_M', 'http://127.0.0.1:11437',
                               chat=fake_chat)
        with self.assertRaises(nl_plan.TransportError):
            t('prompt')


class PlanTest(unittest.TestCase):
    def test_plan_records_model_provenance(self):
        calls = []

        def fake_transport(prompt):
            calls.append(prompt)
            return {'model_id': 'llama3.2:3b-instruct-q4_K_M',
                    'endpoint': 'http://127.0.0.1:11437', 'content': REPLY}

        out = nl_plan.plan('quiet mode', DEVICES, fake_transport)
        self.assertEqual(len(calls), 1)
        self.assertEqual(out['model_run']['provider'], 'meta')
        self.assertEqual(out['model_run']['model'], 'llama3.2:3b-instruct-q4_K_M')
        self.assertEqual(len(out['spec']['steps']), 2)
        self.assertTrue(out['reply_sha256'])

    def test_transport_failure_is_plan_error_not_guess(self):
        def boom(prompt):
            raise nl_plan.TransportError('endpoint down')

        with self.assertRaises(nl_plan.PlanError):
            nl_plan.plan('quiet mode', DEVICES, boom)


if __name__ == '__main__':
    unittest.main()
