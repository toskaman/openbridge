"""NIGHTFALL B-02b: a corrupt session journal must fail closed (F-13).

Pre-fix contract (residual pinned in test_nightfall_xproc_journals.py):
a corrupt file reads as [] -- pending restores are silently dropped and
record()/close() overwrite the corrupt file, destroying evidence.

Post-fix contract (mirrors StateStore STATE_UNREADABLE):
missing file -> []; corrupt/unparseable/wrong-shape ->
SessionError SESSION_CORRUPT; every caller path surfaces a structured
error instead of dropping the connection or reporting success.
"""
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from src.fabric.session import SessionError, SessionJournal


def _corrupt_file(tmp, payload='{not json'):
    p = os.path.join(tmp, 's.json')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(payload)
    return p


def _live_server(test, journal_path):
    from src.server import create_server
    s = create_server(0, fabric_salt=b't', session_journal=SessionJournal(journal_path))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    test.addCleanup(lambda: (s.shutdown(), s.server_close()))
    return s, f'http://127.0.0.1:{s.server_port}'


def _post(base, path, payload, csrf):
    req = urllib.request.Request(base + path, json.dumps(payload).encode(),
                                 {'Content-Type': 'application/json',
                                  'X-CSRF-Token': csrf, 'Origin': base})
    return req


class CorruptCore(unittest.TestCase):
    def test_open_changes_corrupt_raises(self):
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            sj = SessionJournal(_corrupt_file(d))
            with self.assertRaises(SessionError) as e:
                sj.open_changes()
            self.assertEqual(e.exception.code, 'SESSION_CORRUPT')
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_record_corrupt_raises_and_preserves_file(self):
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            p = _corrupt_file(d)
            before = Path(p).read_bytes()
            sj = SessionJournal(p)
            with self.assertRaises(SessionError):
                sj.record('adb_network_connected', 'sim', {'address': 'a'}, 'down', 'up')
            self.assertEqual(Path(p).read_bytes(), before)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_close_corrupt_raises_and_preserves_file(self):
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            p = _corrupt_file(d)
            before = Path(p).read_bytes()
            sj = SessionJournal(p)
            with self.assertRaises(SessionError):
                sj.close('chg-deadbeef00', 'KEPT', 'test')
            self.assertEqual(Path(p).read_bytes(), before)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_valid_json_wrong_shape_raises(self):
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            sj = SessionJournal(_corrupt_file(d, payload='{"rows": []}'))
            with self.assertRaises(SessionError) as e:
                sj.open_changes()
            self.assertEqual(e.exception.code, 'SESSION_CORRUPT')
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_missing_file_still_empty_and_roundtrips(self):
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            sj = SessionJournal(os.path.join(d, 's.json'))
            self.assertEqual(sj.open_changes(), [])
            cid = sj.record('adb_network_connected', 'sim', {'address': 'a'}, 'down', 'up')
            self.assertEqual(len(sj.open_changes()), 1)
            sj.close(cid, 'KEPT', 'test')
            self.assertEqual(sj.open_changes(), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class CorruptCallers(unittest.TestCase):
    def test_http_session_changes_503(self):
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            _, base = _live_server(self, _corrupt_file(d))
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + '/api/session-changes')
            self.assertEqual(e.exception.code, 503)
            self.assertIn('SESSION_CORRUPT', json.loads(e.exception.read())['error'])
            e.exception.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_http_session_restore_503(self):
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            _, base = _live_server(self, _corrupt_file(d))
            csrf = json.loads(urllib.request.urlopen(base + '/api/session').read())['csrf_token']
            req = _post(base, '/api/session-restore', {'device_id': 'session', 'restore': []}, csrf)
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req)
            self.assertEqual(e.exception.code, 503)
            self.assertIn('SESSION_CORRUPT', json.loads(e.exception.read())['error'])
            e.exception.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_http_tv_connect_reports_journal_error_without_lying(self):
        from unittest import mock
        from src.fabric.registry import Identifier, Registry
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            p = _corrupt_file(d)
            before = Path(p).read_bytes()
            s, base = _live_server(self, p)
            reg = Registry()
            key = reg.upsert([Identifier('tv_ip', 'tv-1', True)], category='tv',
                             label='TV', weak=(('ip', '192.168.1.10'),))
            s.fabric_registry = reg
            csrf = json.loads(urllib.request.urlopen(base + '/api/session').read())['csrf_token']
            req = _post(base, '/api/tv-adb-connect', {'device_id': key}, csrf)
            with mock.patch.object(s.android, 'connect_network', return_value='AUTHORIZED'):
                body = json.loads(urllib.request.urlopen(req).read())
            # The connect really happened: 200 + AUTHORIZED, but the journal
            # failure is reported, not swallowed -- and the file is intact.
            self.assertEqual(body['state'], 'AUTHORIZED')
            self.assertIn('SESSION_CORRUPT', body['journal_error'])
            self.assertEqual(Path(p).read_bytes(), before)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_v2_recovery_503(self):
        from src.runtime import api_v2
        from src.server import create_server
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            s = create_server(0, fabric_salt=b't', session_journal=SessionJournal(_corrupt_file(d)))
            try:
                status, body = api_v2.get(s, '/api/v2/recovery', '')
            finally:
                s.server_close()
            self.assertEqual(status, 503)
            self.assertIn('SESSION_CORRUPT', body['error'])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_session_cleanup_primitive_fails_honest(self):
        from src.runtime.primitives import Executor
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            c = SimpleNamespace(session_journal=SessionJournal(_corrupt_file(d)),
                                android=SimpleNamespace(), fabric_lock=threading.Lock())
            out = Executor(c).execute('session_cleanup', 'session', {'restore': []}, consent=True)
            self.assertEqual(out['state'], 'FAILED')
            self.assertIn('SESSION_CORRUPT', out['errors'][0])
            self.assertFalse(out['verified'])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_freebox_grant_reports_journal_error(self):
        import time
        from src.server import create_server
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            p = _corrupt_file(d)
            before = Path(p).read_bytes()
            s = create_server(0, fabric_salt=b't', session_journal=SessionJournal(p))
            try:
                fake = SimpleNamespace(state=lambda: 'PENDING',
                                       request_authorization=lambda: None,
                                       poll_authorization=lambda: 'granted')
                code, _ = s.start_freebox_authorization(session_factory=lambda: fake)
                self.assertEqual(code, 202)
                deadline = time.monotonic() + 10
                while s.freebox_auth.get('state') == 'PENDING' and time.monotonic() < deadline:
                    time.sleep(0.05)
                # The grant really happened, but the journal failure is
                # reported instead of killing the poll thread silently.
                self.assertEqual(s.freebox_auth.get('state'), 'GRANTED')
                self.assertIn('SESSION_CORRUPT', s.freebox_auth.get('journal_error', ''))
                self.assertEqual(Path(p).read_bytes(), before)
            finally:
                s.server_close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_companion_install_reports_journal_error(self):
        import time
        from unittest import mock
        from src.server import create_server
        d = tempfile.mkdtemp(prefix='n02b-')
        try:
            p = _corrupt_file(d)
            before = Path(p).read_bytes()
            apk = os.path.join(d, 'companion.apk')
            Path(apk).write_bytes(b'fake-apk')
            old = os.environ.get('OPENBRIDGE_COMPANION_APK')
            os.environ['OPENBRIDGE_COMPANION_APK'] = apk
            try:
                s = create_server(0, fabric_salt=b't', session_journal=SessionJournal(p))
                try:
                    s.android._handles = {'serial-1': 'handle-1'}
                    with mock.patch.object(s.android, '_run', side_effect=OSError('no adb')), \
                         mock.patch.object(s.android, 'install_companion', return_value='Success'):
                        code, _ = s.start_companion_install('handle-1', attempts=1, delay=0)
                        self.assertEqual(code, 202)
                        deadline = time.monotonic() + 10
                        while s.companion_install.get('state') == 'RETRYING' and time.monotonic() < deadline:
                            time.sleep(0.05)
                    self.assertEqual(s.companion_install.get('state'), 'INSTALLED')
                    self.assertIn('SESSION_CORRUPT', s.companion_install.get('journal_error', ''))
                    self.assertEqual(Path(p).read_bytes(), before)
                finally:
                    s.server_close()
            finally:
                if old is None:
                    del os.environ['OPENBRIDGE_COMPANION_APK']
                else:
                    os.environ['OPENBRIDGE_COMPANION_APK'] = old
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_cli_sessions_list_corrupt(self):
        from src.cli import CliError, cmd_sessions_list
        d = tempfile.mkdtemp(prefix='n02b-')
        os.makedirs(os.path.join(d, 'OpenBridge'), exist_ok=True)
        with open(os.path.join(d, 'OpenBridge', 'cli_sessions.json'), 'w', encoding='utf-8') as f:
            f.write('{not json')
        old = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = d
        try:
            with self.assertRaises(CliError) as e:
                cmd_sessions_list(SimpleNamespace())
            self.assertEqual(e.exception.code, 'SESSION_CORRUPT')
        finally:
            if old is None:
                del os.environ['LOCALAPPDATA']
            else:
                os.environ['LOCALAPPDATA'] = old
            shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
