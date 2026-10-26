"""Opt-in, read-only ADB inventory. Serial numbers never leave this adapter."""
from datetime import datetime, timezone
import re
import secrets
import shutil
import subprocess
import threading


class AndroidAdapter:
    def __init__(self, executable=None, runner=subprocess.run):
        self.executable = executable or shutil.which('adb')
        self.runner = runner
        self._handles = {}
        self._lock = threading.RLock()

    def _run(self, args):
        result = self.runner([self.executable, *args], capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=8,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or len(result.stdout) > 131072:
            raise ValueError('ADB operation unavailable')
        return result.stdout

    def discover(self):
        if not self.executable:
            return {'status': 'ADB_MISSING', 'devices': []}
        try:
            output = self._run(['devices', '-l'])
            devices = []
            with self._lock:
                current = {}
                for line in output.splitlines():
                    fields = line.split()
                    if len(fields) < 2 or fields[1] not in ('device', 'offline', 'unauthorized'):
                        continue
                    serial, state = fields[:2]
                    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', serial):
                        continue
                    # adb devices may include TCP connections. This adapter is USB/emulator only.
                    if ':' in serial:
                        continue
                    handle = self._handles.get(serial, 'android-' + secrets.token_hex(12))
                    current[serial] = handle
                    devices.append({'id': handle, 'name': f'Android · slot {len(devices)+1}',
                                    'state': state, 'source': 'ADB', 'simulated': False,
                                    'transport': 'EMULATOR' if serial.startswith('emulator-') else 'USB',
                                    'capabilities': ['inspect'] if state == 'device' else [],
                                    'observed_at': datetime.now(timezone.utc).isoformat()})
                self._handles = current
            return {'status': 'READY' if devices else 'WAITING_FOR_DEVICE', 'devices': devices}
        except (OSError, ValueError, subprocess.SubprocessError):
            return {'status': 'ADB_UNAVAILABLE', 'devices': []}

    def inspect(self, handle):
        with self._lock:
            inventory = self.discover()
            device = next((d for d in inventory['devices'] if d['id'] == handle), None)
            if not device or device['state'] != 'device':
                raise ValueError('Device unavailable or not authorized')
            serial = next(key for key, value in self._handles.items() if value == handle)
            def read(*command):
                return self._run(['-s', serial, *command]).strip()
            try:
                if read('get-state') != 'device':
                    raise ValueError('Device unavailable')
                facts = {}
                for key, prop in [('manufacturer', 'ro.product.manufacturer'), ('model', 'ro.product.model'),
                                  ('android_version', 'ro.build.version.release'), ('sdk', 'ro.build.version.sdk')]:
                    value = read('shell', 'getprop', prop)
                    if not value or len(value) > 120 or serial in value or any(ord(c) < 32 for c in value):
                        raise ValueError('Invalid device fact')
                    facts[key] = value
                battery = read('shell', 'dumpsys', 'battery')
                level = re.search(r'^\s*level:\s*(\d+)\s*$', battery, re.M)
                scale = re.search(r'^\s*scale:\s*(\d+)\s*$', battery, re.M)
                if level and scale and 0 <= int(level[1]) <= int(scale[1]) and int(scale[1]) > 0:
                    facts['battery_percent'] = round(int(level[1]) * 100 / int(scale[1]))
                storage = read('shell', 'df', '-k', '/data').splitlines()
                if len(storage) >= 2:
                    columns = storage[-1].split()
                    if len(columns) >= 4 and columns[3].isdigit():
                        facts['storage_free_gb'] = round(int(columns[3]) / 1024**2, 2)
                now = datetime.now(timezone.utc).isoformat()
                return {'device_id': handle, 'status': 'READ_ONLY', 'simulated': False, 'source': 'ADB',
                        'model_status': 'NOT_CONNECTED', 'observed_at': now,
                        'summary': 'Real Android inventory, read-only. No device changes.',
                        'evidence': [{'key': key, 'value': value, 'source': 'ADB', 'observed_at': now} for key, value in facts.items()],
                        'checks': [
                            {'name': 'ADB authorization', 'status': 'PASS', 'detail': 'Device authorized at read time.'},
                            {'name': 'Hardware writes', 'status': 'BLOCKED', 'detail': 'Read-only; no modification commands.'},
                            {'name': 'Meta inference', 'status': 'NOT_TESTED', 'detail': 'No model calls using this device data.'},
                            {'name': 'Physical rollback', 'status': 'NOT_TESTED', 'detail': 'No physical transaction performed.'}]}
            except (OSError, ValueError, subprocess.SubprocessError):
                raise ValueError('Device read failed; reconnect and authorize the device') from None
