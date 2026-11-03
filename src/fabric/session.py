"""Session change journal: every environment change OpenBridge makes outside the transaction engine is recorded with its
original state, so the owner is asked before finishing whether to restore it. Restores use fixed commands and are verified."""
import json
import os
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

KINDS = {
    'companion_installed': 'OpenBridge Companion app installed',
    'adb_network_connected': 'ADB Wi-Fi connection from this PC',
    'system_package_enabled': 'System app re-enabled',
    'bluetooth_turned_on': 'Bluetooth turned on by the Companion',
    'freebox_app_authorized': 'OpenBridge authorized on the Freebox (read-only)',
}


class SessionError(OSError):
    def __init__(self, code, detail):
        super().__init__(f'{code}: {detail}')
        self.code = code


class SessionJournal:
    def __init__(self, path=None):
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
        self.path = Path(path) if path else root / 'session-changes.json'
        self._lock = threading.Lock()

    @contextmanager
    def _locked(self):
        """Thread lock + OS file lock (.lock sidecar), mirroring StateStore._locked: the read-modify-write
        in record()/open_changes()/close() is now atomic across processes sharing one journal file."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.with_suffix('.lock').open('a+b') as handle:
                deadline = time.monotonic() + 5
                while True:
                    try:
                        # First-touch setup INSIDE the retry loop: two
                        # processes racing on an empty lock file both see
                        # size 0, and the loser's contended flush raises a
                        # raw OSError that must retry (then fail-closed as
                        # SESSION_LOCK_FAILED), never escape the module
                        # contract. Mirrors transactions.py _exclusive.
                        if os.fstat(handle.fileno()).st_size == 0:
                            handle.write(b'0'); handle.flush()
                        handle.seek(0)
                        if os.name == 'nt':
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise SessionError('SESSION_LOCK_FAILED', 'Session journal is busy; operation blocked') from None
                        time.sleep(.01)
                try:
                    yield
                finally:
                    handle.seek(0)
                    if os.name == 'nt':
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _load(self):
        # B-02b fail-closed (mirrors StateStore STATE_UNREADABLE): a missing
        # file is a fresh journal ([]), but anything unreadable or mis-shaped
        # raises SESSION_CORRUPT -- never silently drop pending restores or
        # overwrite the evidence. Callers map this to 503/FAILED/CliError.
        try:
            rows = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as error:
            raise SessionError('SESSION_CORRUPT', f'Session journal cannot be verified ({type(error).__name__}); preserve the file for review, no update was applied') from None
        if not isinstance(rows, list):
            raise SessionError('SESSION_CORRUPT', 'Session journal is not a change list; preserve the file for review, no update was applied') from None
        return rows

    def _save(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + '.', suffix='.tmp', dir=str(self.path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(json.dumps(rows, indent=1))
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def record(self, kind, device_label, target, before, after):
        """target: dict with the fixed parameters needed to undo (serial/ip/package). Duplicate open entries are not repeated."""
        if kind not in KINDS:
            raise ValueError('Unknown change kind')
        with self._locked():
            rows = self._load()
            for r in rows:
                if r['kind'] == kind and r['target'] == target and r['state'] == 'OPEN':
                    return r['id']
            entry = {'id': 'chg-' + uuid.uuid4().hex[:10], 'kind': kind, 'title': KINDS[kind], 'device': device_label,
                     'target': target, 'before': before, 'after': after, 'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'state': 'OPEN'}
            rows.append(entry); self._save(rows)
            return entry['id']

    def open_changes(self):
        with self._locked():
            return [r for r in self._load() if r['state'] == 'OPEN']

    def close(self, change_id, state, detail=''):
        with self._locked():
            rows = self._load()
            for r in rows:
                if r['id'] == change_id:
                    r['state'] = state; r['closed_detail'] = detail[:200]; r['closed_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
            self._save(rows)


def restore(change, adb):
    """Undo one change with a fixed command, then verify. Returns (state, detail). adb(args)->stdout raises on failure."""
    t = change['target']
    k = change['kind']
    if k == 'companion_installed':
        adb(['-s', t['serial'], 'uninstall', 'fr.openbridge.companion'])
        still = 'package:fr.openbridge.companion' in adb(['-s', t['serial'], 'shell', 'pm', 'list', 'packages', 'fr.openbridge.companion']).split()
        return ('RESTORED', 'Companion uninstalled') if not still else ('FAILED', 'Companion still installed')
    if k == 'adb_network_connected':
        adb(['disconnect', t['address']])
        return 'RESTORED', 'Disconnected (the TV keeps its own authorization list)'
    if k == 'system_package_enabled':
        if change['before'] != 3:
            return 'FAILED', 'Unsupported original state'
        out = adb(['-s', t['serial'], 'shell', 'pm', 'disable-user', '--user', '0', t['package']])
        dump = adb(['-s', t['serial'], 'shell', 'dumpsys', 'package', t['package']])
        ok = 'disabled-user' in out and 'enabled=3' in dump
        return ('RESTORED', 'Back to disabled-user (enabled=3)') if ok else ('FAILED', 'State not verified')
    if k == 'freebox_app_authorized':
        return 'MANUAL', 'Revoke in Freebox OS > Paramètres > Gestion des accès > Applications (OpenBridge also forgets its token)'
    if k == 'bluetooth_turned_on':
        return 'MANUAL', 'Turn Bluetooth off on the device (or use "Restore settings" in the Companion)'
    return 'FAILED', 'Unknown change'
