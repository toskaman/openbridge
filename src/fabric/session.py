"""Session change journal: every environment change OpenBridge makes outside the transaction engine is recorded with its
original state, so the owner is asked before finishing whether to restore it. Restores use fixed commands and are verified."""
import json
import os
import threading
import time
import uuid
from pathlib import Path

KINDS = {
    'companion_installed': 'OpenBridge Companion app installed',
    'adb_network_connected': 'ADB Wi-Fi connection from this PC',
    'system_package_enabled': 'System app re-enabled',
    'bluetooth_turned_on': 'Bluetooth turned on by the Companion',
    'freebox_app_authorized': 'OpenBridge authorized on the Freebox (read-only)',
}


class SessionJournal:
    def __init__(self, path=None):
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
        self.path = Path(path) if path else root / 'session-changes.json'
        self._lock = threading.Lock()

    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return []

    def _save(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp'); tmp.write_text(json.dumps(rows, indent=1), encoding='utf-8'); os.replace(tmp, self.path)

    def record(self, kind, device_label, target, before, after):
        """target: dict with the fixed parameters needed to undo (serial/ip/package). Duplicate open entries are not repeated."""
        if kind not in KINDS:
            raise ValueError('Unknown change kind')
        with self._lock:
            rows = self._load()
            for r in rows:
                if r['kind'] == kind and r['target'] == target and r['state'] == 'OPEN':
                    return r['id']
            entry = {'id': 'chg-' + uuid.uuid4().hex[:10], 'kind': kind, 'title': KINDS[kind], 'device': device_label,
                     'target': target, 'before': before, 'after': after, 'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'state': 'OPEN'}
            rows.append(entry); self._save(rows)
            return entry['id']

    def open_changes(self):
        with self._lock:
            return [r for r in self._load() if r['state'] == 'OPEN']

    def close(self, change_id, state, detail=''):
        with self._lock:
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
