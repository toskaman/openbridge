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

    def test_cli_error_exit_names_are_valid(self):
        # fail() indexes EXIT[exc.exit_name] with no fallback: an unknown
        # name turns any handler error into a KeyError crash.
        import re
        from pathlib import Path
        src = Path(cli.__file__).read_text(encoding='utf-8')
        names = set(re.findall(r"CliError\('([a-z_]+)'", src))
        self.assertTrue(names <= set(cli.EXIT), names - set(cli.EXIT))

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


class DashboardsPatchCliTests(unittest.TestCase):
    PATCH = {'schema_version': 1, 'patch_id': 'p-9', 'target_opaque_id': 'opaque:vac1',
             'origin': 'meta_generated', 'model_run_id': 'mr-9',
             'widgets': [{'widget_id': 'w-1', 'kind': 'button', 'label': 'Return to dock',
                          'binding_primitive': 'vacuum_command',
                          'params': {'command': 'dock'}}]}
    OFFERED = ['opaque:vac1', 'opaque:tv1']

    def patch_file(self, tmp, patch=None, offered=None):
        import json as _json
        from pathlib import Path as _Path
        p = _Path(tmp) / 'panel.json'
        p.write_text(_json.dumps({'patch': patch or self.PATCH,
                                  'offered_opaque_ids': offered if offered is not None else self.OFFERED,
                                  'model_run': {'model_id': 'llama3.2:3b-test'}}),
                     encoding='utf-8')
        return str(p)

    def install_args(self, **kw):
        base = {'patch': None, 'relay': 'r-tv', 'target': 'Robot vacuum (Tuya)',
                'consent': None, 'yes': False}
        base.update(kw)
        return Namespace(**base)

    def install_token(self):
        preview = {'relay_id': 'r-tv', 'target': 'Robot vacuum (Tuya)',
                   'controls': [{'label': 'Return to dock', 'skill_id': 'vacuum_command',
                                 'params': {'command': 'dock'}}]}
        return cli.preview_hash(preview)

    def core_ctx(self):
        core = mock.MagicMock()
        core.__enter__.return_value = mock.sentinel.server
        return core

    def test_install_consent_mismatch_discloses_token(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            args = self.install_args(patch=self.patch_file(tmp), consent='nope')
            with self.assertRaises(cli.CliError) as e:
                cli.cmd_dashboards_install(args)
        self.assertEqual(e.exception.code, 'CONSENT_REQUIRED')
        self.assertIn(self.install_token(), str(e.exception))

    def test_install_hallucinated_opaque_target_refused_before_any_core_use(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            args = self.install_args(patch=self.patch_file(tmp, offered=['opaque:other']),
                                      consent=self.install_token())
            with mock.patch.object(cli, 'Core') as core:
                with self.assertRaises(cli.CliError) as e:
                    cli.cmd_dashboards_install(args)
        self.assertEqual(e.exception.code, 'PATCH_TARGET_UNKNOWN')
        core.assert_not_called()

    def test_install_bad_schema_refused(self):
        import copy
        import tempfile
        bad = copy.deepcopy(self.PATCH)
        bad['widgets'][0]['binding_primitive'] = 'shell_exec'
        with tempfile.TemporaryDirectory() as tmp:
            args = self.install_args(patch=self.patch_file(tmp, patch=bad),
                                      consent=self.install_token())
            with self.assertRaises(cli.CliError) as e:
                cli.cmd_dashboards_install(args)
        self.assertEqual(e.exception.code, 'PATCH_REJECTED')

    def test_install_valid_calls_bridge_with_resolved_target(self):
        import tempfile
        router = mock.Mock()
        router.resolve_target.return_value = 'dev-live-vac'
        with tempfile.TemporaryDirectory() as tmp:
            args = self.install_args(patch=self.patch_file(tmp),
                                      consent=self.install_token())
            with mock.patch.object(cli, 'Core', return_value=self.core_ctx()), \
                 mock.patch.object(cli, 'ensure_discovery', return_value={}), \
                 mock.patch('src.runtime.api_v2.remote_controls',
                            return_value=mock.sentinel.controls), \
                 mock.patch('src.runtime.api_v2.router', return_value=router), \
                 mock.patch('src.runtime.dashboards.install_patch',
                            return_value={'ok': True}) as bridge:
                out = cli.cmd_dashboards_install(args)
        bridge.assert_called_once_with(
            mock.sentinel.controls, 'r-tv', self.PATCH, 'Robot vacuum (Tuya)',
            mock.ANY, consent=True, resolve_target=router.resolve_target)
        self.assertEqual(out['controls'][0]['skill_id'], 'vacuum_command')

    def test_revoke_needs_consent_then_clears(self):
        preview = {'relay_id': 'r-tv', 'action': 'revoke-all'}
        token = cli.preview_hash(preview)
        args = Namespace(relay='r-tv', consent='wrong', yes=False)
        with self.assertRaises(cli.CliError) as e:
            cli.cmd_dashboards_revoke(args)
        self.assertEqual(e.exception.code, 'CONSENT_REQUIRED')
        self.assertIn(token, str(e.exception))
        controls = mock.Mock()
        args = Namespace(relay='r-tv', consent=token, yes=False)
        with mock.patch.object(cli, 'Core', return_value=self.core_ctx()), \
             mock.patch('src.runtime.api_v2.remote_controls', return_value=controls):
            cli.cmd_dashboards_revoke(args)
        controls.set_controls.assert_called_once_with(
            {'relay_id': 'r-tv', 'controls': [], 'consent': True})

    def test_propose_builds_patch_from_model_reply(self):
        import json as _json
        reply = _json.dumps(self.PATCH)
        devices = [{'key': 'dev-v', 'label': 'Robot vacuum (Tuya)', 'category': 'vacuum',
                    'capabilities': [], 'facts': {}}]
        transport = mock.Mock(return_value={'model_id': 'm', 'endpoint': 'e',
                                             'content': reply})
        args = Namespace(text='vacuum panel', model=None, timeout=None)
        with mock.patch.object(cli, 'Core', return_value=self.core_ctx()), \
             mock.patch.object(cli, 'ensure_discovery',
                               return_value={'devices': devices}), \
             mock.patch('src.runtime.nl_plan.local_chat',
                        return_value=transport) as chat:
            out = cli.cmd_dashboards_propose(args)
        chat.assert_called_once()
        self.assertEqual(chat.call_args[1]['options']['num_ctx'], 4096)
        self.assertNotIn('num_gpu', chat.call_args[1]['options'])
        transport.assert_called_once()
        prompt = transport.call_args[0][0]
        self.assertIn('vacuum panel', prompt)
        self.assertIn('vacuum_command', prompt)
        self.assertIn('command=', prompt)
        self.assertEqual(out['patch']['patch_id'], 'p-9')
        self.assertEqual(len(out['offered_opaque_ids']), 1)
        self.assertIn('model_run', out)

    def test_propose_medium_tier_uses_pinned_partial_offload(self):
        # Full offload dies on a 3.7GB pinned CUDA_Host alloc (01:34/01:40
        # 500s); num_gpu=28 is the proven split (21s load, 14.9GB VRAM).
        import json as _json
        devices = [{'key': 'dev-v', 'label': 'V', 'category': 'vacuum',
                    'capabilities': [], 'facts': {}}]
        transport = mock.Mock(return_value={'model_id': 'm', 'endpoint': 'e',
                                             'content': _json.dumps(self.PATCH)})
        args = Namespace(text='vacuum panel', model='muse-glimmer:30b-q4_K_M', timeout=None)
        with mock.patch.object(cli, 'Core', return_value=self.core_ctx()), \
             mock.patch.object(cli, 'ensure_discovery',
                               return_value={'devices': devices}), \
             mock.patch('src.runtime.nl_plan.local_chat',
                        return_value=transport) as chat:
            cli.cmd_dashboards_propose(args)
        self.assertEqual(chat.call_args[1]['options']['num_gpu'], 28)
        self.assertEqual(chat.call_args[1]['options']['num_ctx'], 4096)
        self.assertEqual(chat.call_args[1]['options']['num_predict'], 1024)

    def test_propose_garbage_reply_rejected(self):
        devices = [{'key': 'dev-v', 'label': 'V', 'category': 'vacuum',
                    'capabilities': [], 'facts': {}}]
        transport = mock.Mock(return_value={'model_id': 'm', 'endpoint': 'e',
                                             'content': 'no json here'})
        args = Namespace(text='vacuum panel', model=None, timeout=None)
        with mock.patch.object(cli, 'Core', return_value=self.core_ctx()), \
             mock.patch.object(cli, 'ensure_discovery',
                               return_value={'devices': devices}), \
             mock.patch('src.runtime.nl_plan.local_chat', return_value=transport):
            with self.assertRaises(cli.CliError) as e:
                cli.cmd_dashboards_propose(args)
        self.assertEqual(e.exception.code, 'PATCH_REJECTED')
