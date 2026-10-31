"""GUI/CLI parity: HTTP (GUI path) and in-process (CLI path) must agree.

The GUI talks HTTP to a served core; the CLI calls the same handlers
in-process by default and over HTTP with --server. Both must return the
same data, and concurrent clients must never double-execute.
"""
import io
import json
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout

from src import cli


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class ParityTests(unittest.TestCase):
    def test_http_and_in_process_devices_list_agree(self):
        from src.server import create_server
        server = create_server(0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05},
                                  daemon=True)
        thread.start()
        try:
            code_local, out_local, _ = run(['--json', 'devices', 'list'])
            code_http, out_http, _ = run(['--json', '--server',
                                          'http://127.0.0.1:%d' % port, 'devices', 'list'])
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        self.assertEqual(code_local, 0)
        self.assertEqual(code_http, 0)
        local = json.loads(out_local)['data']
        http = json.loads(out_http)['data']
        self.assertEqual(local['relays'], http['relays'])
        self.assertEqual(local['devices'], http['devices'])

    def test_ask_dry_run_is_idempotent(self):
        code1, out1, _ = run(['--json', '--dry-run', '--providers', 'android',
                              'ask', 'fabric status summary'])
        code2, out2, _ = run(['--json', '--dry-run', '--providers', 'android',
                              'ask', 'fabric status summary'])
        # Discovery-dependent: both succeed or both fail identically, never diverge.
        self.assertEqual(code1, code2)
        if code1 == 0:
            data1, data2 = json.loads(out1)['data'], json.loads(out2)['data']
            self.assertEqual(data1.get('request_id'), data2.get('request_id'))
            self.assertEqual(data1.get('resolved', True), data2.get('resolved', True))

    def test_concurrent_claim_executes_once(self):
        # Atomicity at the store level: redirect_stdout is process-global,
        # so cli.main itself is never invoked from two threads at once.
        rows = cli.pending_load()
        rows['req-parity-test'] = {'text': 't', 'intent': {}, 'preview': {}, 'hash': 'h',
                                   'created': 0}
        cli.pending_save(rows)

        def claim(rid):
            def _claim(rows):
                return rows.pop(rid, None)

            return cli.pending_mutate(_claim)

        results = []
        lock = threading.Lock()

        def claim_once():
            found = claim('req-parity-test')
            with lock:
                results.append(found is not None)

        threads = [threading.Thread(target=claim_once) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(sorted(results), [False, False, False, True])
        code, out, _ = run(['--json', 'approvals', 'deny', 'req-parity-test'])
        self.assertEqual(code, 2)  # already claimed: nothing left to deny

    def test_label_targets_validated_and_kept_for_dispatch(self):
        # Labels are the stable ref: keys rotate every discovery, so a
        # validate-time rewrite would strand approval-parked workflows with
        # dead keys (observed live: ROUTE_NOT_SELECTED). Resolution to the
        # live key happens at dispatch (Router.resolve_target), in every
        # process, on both the GUI and CLI paths.
        snap = {'devices': [{'key': 'dev-aaa', 'label': 'Phone X'},
                            {'key': 'dev-bbb', 'label': 'Phone Y'}]}
        spec = {'workflow_id': 'wf-t', 'steps': [
            {'id': 'a', 'skill_id': 'screen_capture', 'target': 'phone x', 'params': {}},
            {'id': 'm', 'skill_id': 'capture_montage', 'target': 'fabric', 'params': {}}]}
        resolved = cli._resolve_workflow_targets(spec, snap)
        self.assertEqual(resolved['steps'][0]['target'], 'Phone X')
        self.assertEqual(resolved['steps'][1]['target'], 'fabric')
        with self.assertRaises(cli.CliError):
            cli._resolve_workflow_targets(
                {'workflow_id': 'wf-t', 'steps': [
                    {'id': 'a', 'skill_id': 'screen_capture', 'target': 'ghost', 'params': {}}]},
                snap)

    def test_unknown_approve_never_executes(self):
        code, out, _ = run(['--json', 'approvals', 'approve', 'req-does-not-exist',
                            '--consent', 'anything'])
        self.assertEqual(code, 5)
        self.assertIn('Unknown request', json.loads(out)['error']['message'])
