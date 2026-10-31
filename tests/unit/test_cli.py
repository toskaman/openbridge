"""CLI contract: envelope, exit codes, hermetic handlers, no GUI imports."""
import io
import json
import sys
import unittest
from argparse import Namespace
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

from src import cli


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def test_version_json_envelope(self):
        code, out, _ = run(['--json', 'version'])
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(doc['cli_version'], 1)
        self.assertTrue(doc['ok'])
        self.assertIn('openbridge', doc['data']['name'].lower())

    def test_unknown_command_is_exit_2(self):
        code, _, _ = run(['frobnicate'])
        self.assertEqual(code, 2)

    def test_help_is_exit_0(self):
        code, out, _ = run(['--help'])
        self.assertEqual(code, 0)
        self.assertIn('devices', out)

    def test_json_stdout_is_pure(self):
        code, out, _ = run(['--json', 'models', 'list'])
        self.assertEqual(code, 0)
        doc = json.loads(out)  # raises if polluted
        self.assertIn('muse-spark-1.3', doc['data']['pinned'])

    def test_doctor_json_statuses(self):
        code, out, _ = run(['--json', 'doctor'])
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertIn(doc['global'] if 'global' in doc else doc['data']['global'],
                      ['READY', 'MISSING', 'BLOCKED', 'NOT_TESTED', 'INVALID', 'INCOMPATIBLE',
                       'PERMISSION_REQUIRED', 'AUTH_REQUIRED', 'MODEL_NOT_FOUND',
                       'INSUFFICIENT_RESOURCES', 'API_UNAVAILABLE'])

    def test_models_test_local_reports_probe_not_fiction(self):
        code, out, _ = run(['--json', 'models', 'test', '--provider', 'local'])
        self.assertIn(code, (0, 8))
        doc = json.loads(out)
        self.assertEqual(doc['data']['provider'], 'local')

    def test_models_test_cloud_never_spends_without_consent(self):
        code, out, _ = run(['--json', 'models', 'test', '--provider', 'meta-cloud'])
        doc = json.loads(out)
        self.assertFalse(doc['data'].get('spent', False))
        if not doc['ok']:
            self.assertTrue(doc['error']['code'].startswith('CLOUD_'))

    def test_devices_list_hermetic(self):
        code, out, _ = run(['--json', 'devices', 'list'])
        self.assertEqual(code, 0)
        self.assertIsInstance(json.loads(out)['data']['devices'], list)

    def test_capabilities_list(self):
        code, out, _ = run(['--json', 'capabilities', 'list'])
        self.assertEqual(code, 0)
        self.assertIsInstance(json.loads(out)['data']['capabilities'], list)

    def test_yes_cannot_bypass_privileged_approval(self):
        code, out, _ = run(['--json', '--yes', 'approvals', 'approve', 'req-none'])
        self.assertEqual(code, 5)
        self.assertIn('consent', json.loads(out)['error']['message'].lower())

    def test_no_gui_imports(self):
        for name in list(sys.modules):
            self.assertNotIn('tkinter', name)
            self.assertNotIn('PyQt', name)

    def test_dry_run_changes_nothing(self):
        code, out, _ = run(['--json', '--dry-run', 'workflows', 'run', 'wf-none'])
        doc = json.loads(out)
        self.assertTrue(doc['data'].get('dry_run'))

    def test_extract_json_plain_and_fenced(self):
        doc, extracted = cli.extract_json('{"a": 1}')
        self.assertEqual(doc, {'a': 1})
        self.assertFalse(extracted)
        doc, extracted = cli.extract_json('Here:\n```json\n{"a": {"b": [1, 2]}}\n```\ntrailing')
        self.assertEqual(doc, {'a': {'b': [1, 2]}})
        self.assertTrue(extracted)
        with self.assertRaises(ValueError):
            cli.extract_json('no braces here')

    def test_build_bundle_validates_and_carries_no_values(self):
        from src.forge import v4_schemas as schemas
        devices = [{'key': 'dev-1', 'category': 'phone',
                    'capabilities': [{'level': 'read'}],
                    'facts': {'battery_percent': {'value': 88, 'sources': ['ADB']}}}]
        bundle = cli.build_bundle(devices, ['screen_capture'])
        schemas.validate_bundle(bundle)
        blob = json.dumps(bundle)
        self.assertNotIn('"value": 88', blob)
        self.assertNotIn('"dev-1"', blob)
        for device in bundle['devices']:
            for fact in device['facts']:
                self.assertNotIn('value', fact)
        self.assertIn('opaque:', blob)


class ResolveTargetsTests(unittest.TestCase):
    SNAP = {'devices': [
        {'key': 'dev-new-tv', 'label': 'android tv', 'category': 'tv',
         'handles': {'WIFI': 'h'}},
        {'key': 'dev-ghost', 'label': 'Android TV', 'category': 'media', 'handles': {}},
        {'key': 'dev-new-vac', 'label': 'Robot vacuum (Tuya)', 'category': 'vacuum',
         'handles': {'LAN': 'v'}},
    ]}

    def spec(self, target):
        return {'consent': True, 'steps': [
            {'id': 'step1', 'skill_id': 'tv_volume_step', 'target': target,
             'params': {'direction': 'down'}}]}

    def test_label_validated_but_kept_for_dispatch_resolution(self):
        # Labels are the stable ref: kept in the spec (stable consent hash),
        # resolved to the live key at dispatch, even across processes.
        out = cli._resolve_workflow_targets(self.spec('android tv'), self.SNAP)
        step = out['steps'][0]
        self.assertEqual(step['target'], 'android tv')
        self.assertTrue(step['disambiguated'])

    def test_unknown_label_rejected(self):
        with self.assertRaises(cli.CliError):
            cli._resolve_workflow_targets(self.spec('mars tv'), self.SNAP)

    def test_stale_key_is_rejected_not_guessed(self):
        with self.assertRaises(cli.CliError):
            cli._resolve_workflow_targets(self.spec('dev-stale-key'), self.SNAP)


class WorkflowApproveTests(unittest.TestCase):
    RECORD = {
        'workflow_id': 'wf-abc', 'status': 'waiting_approval',
        'spec': {'levels': [[{'id': 'step1', 'skill_id': 'tv_volume_step',
                               'target': 'android tv',
                               'params': {'direction': 'down'},
                               'needs': [], 'when': None, 'approval': True,
                               'timeout_s': 120, 'on_fail': 'fail'}]],
                 'steps': {'step1': {'id': 'step1', 'skill_id': 'tv_volume_step',
                                      'target': 'android tv',
                                      'params': {'direction': 'down'}}}},
        'steps': [{'id': 'step1', 'state': 'WAITING'}],
    }

    def args(self, **kw):
        base = {'workflow_id': 'wf-abc', 'step_id': 'step1', 'deny': False,
                'consent': None, 'yes': False}
        base.update(kw)
        return Namespace(**base)

    def preview_token(self):
        step = self.RECORD['spec']['steps']['step1']
        return cli.preview_hash({'workflow_id': 'wf-abc', 'step_id': 'step1',
                                 'skill_id': step['skill_id'],
                                 'target': step['target'],
                                 'params': step['params']})

    def test_unknown_workflow_is_not_found(self):
        store = mock.Mock()
        store.get.return_value = None
        with mock.patch.object(cli, 'workflow_store', return_value=store):
            with self.assertRaises(cli.CliError) as e:
                cli.cmd_workflows_approve(self.args(consent='x'))
        self.assertEqual(e.exception.code, 'NOT_FOUND')

    def test_consent_mismatch_discloses_expected_token(self):
        import copy
        store = mock.Mock()
        store.get.return_value = copy.deepcopy(self.RECORD)
        with mock.patch.object(cli, 'workflow_store', return_value=store):
            with self.assertRaises(cli.CliError) as e:
                cli.cmd_workflows_approve(self.args(consent='wrong-token'))
        self.assertEqual(e.exception.code, 'CONSENT_REQUIRED')
        self.assertIn(self.preview_token(), str(e.exception))

    def test_matching_consent_drives_approval(self):
        import copy
        store = mock.Mock()
        store.get.return_value = copy.deepcopy(self.RECORD)
        core = mock.MagicMock()
        core.__enter__.return_value = mock.sentinel.server
        with mock.patch.object(cli, 'workflow_store', return_value=store), \
             mock.patch.object(cli, 'Core', return_value=core), \
             mock.patch.object(cli, 'ensure_discovery', return_value={}), \
             mock.patch('src.runtime.api_v2.router', return_value=mock.sentinel.router) as router, \
             mock.patch('src.runtime.workflows.approve', return_value={'status': 'done'}) as approve:
            out = cli.cmd_workflows_approve(self.args(consent=self.preview_token()))
        approve.assert_called_once_with('wf-abc', 'step1', True, mock.sentinel.router,
                                        store, actor='cli')
        router.assert_called_once_with(mock.sentinel.server)
        self.assertEqual(out['record']['status'], 'done')

    def test_deny_path_denies_step(self):
        import copy
        store = mock.Mock()
        store.get.return_value = copy.deepcopy(self.RECORD)
        core = mock.MagicMock()
        core.__enter__.return_value = mock.sentinel.server
        with mock.patch.object(cli, 'workflow_store', return_value=store), \
             mock.patch.object(cli, 'Core', return_value=core), \
             mock.patch.object(cli, 'ensure_discovery', return_value={}), \
             mock.patch('src.runtime.api_v2.router', return_value=mock.sentinel.router), \
             mock.patch('src.runtime.workflows.approve', return_value={'status': 'failed'}) as approve:
            cli.cmd_workflows_approve(self.args(consent=self.preview_token(), deny=True))
        approve.assert_called_once_with('wf-abc', 'step1', False, mock.sentinel.router,
                                        store, actor='cli')
