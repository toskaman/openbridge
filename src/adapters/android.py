"""Opt-in, read-only ADB inventory. Serial numbers never leave this adapter."""
from datetime import datetime, timezone
import re
import secrets
import shutil
import subprocess
import threading


def transport_of(serial):
    """Classify an adb serial without contacting anything. Wi-Fi ADB must already be paired/connected by the owner."""
    if serial.startswith('emulator-'):
        return 'EMULATOR'
    if ':' in serial or '._adb-tls-connect._tcp' in serial or '._adb._tcp' in serial:
        return 'WIFI'
    return 'USB'


def _kb(value):
    units={'K':1,'M':1024,'G':1024**2,'T':1024**3}
    if value.isdigit():
        return int(value)
    if value[-1:].upper() in units:
        try:return round(float(value[:-1])*units[value[-1].upper()])
        except ValueError:return None
    return None


def parse_df_available_kb(text):
    """Available KiB of the filesystem holding /data. `df <path>` reports exactly that filesystem,
    possibly under another mount point (bind mounts) and possibly wrapped over two lines."""
    lines=[l for l in text.splitlines()[1:] if l.strip()]
    tokens=' '.join(lines).split()
    for i in range(len(tokens)-1,0,-1):                     # modern: ... Size Used Avail Use% Mount
        if tokens[i].endswith('%') and i>=1 and i+1<len(tokens):
            return _kb(tokens[i-1])
    if '/data' in tokens:                                    # legacy toolbox: /data Size Used Free Blksize
        i=tokens.index('/data')
        if len(tokens)>i+3:
            return _kb(tokens[i+3])
    return None


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
                    handle = self._handles.get(serial, 'android-' + secrets.token_hex(12))
                    current[serial] = handle
                    devices.append({'id': handle, 'name': f'Android · slot {len(devices)+1}',
                                    'state': state, 'source': 'ADB', 'simulated': False,
                                    'transport': transport_of(serial),
                                    'capabilities': ['inspect'] if state == 'device' else [],
                                    'observed_at': datetime.now(timezone.utc).isoformat()})
                self._handles = current
            return {'status': 'READY' if devices else 'WAITING_FOR_DEVICE', 'devices': devices}
        except (OSError, ValueError, subprocess.SubprocessError):
            return {'status': 'ADB_UNAVAILABLE', 'devices': []}

    def stable_identifier(self, handle, salt):
        """Opaque per-install identifier from ro.serialno (same value over USB and Wi-Fi ADB). None if unreadable."""
        import hashlib, hmac
        with self._lock:
            serial = next((k for k, v in self._handles.items() if v == handle), None)
            if serial is None:
                return None
            try:
                value = self._run(['-s', serial, 'shell', 'getprop', 'ro.serialno']).strip()
            except (OSError, ValueError, subprocess.SubprocessError):
                return None
            if not value or value == 'unknown' or len(value) > 128:
                return None
            return 'android_serial:' + hmac.new(salt, f'android_serial\0{value}'.encode(), hashlib.sha256).hexdigest()[:24]

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
                unavailable = []
                for key, prop in [('manufacturer', 'ro.product.manufacturer'), ('model', 'ro.product.model'),
                                  ('android_version', 'ro.build.version.release'), ('sdk', 'ro.build.version.sdk'),
                                  ('cpu_abi', 'ro.product.cpu.abi'), ('security_patch', 'ro.build.version.security_patch')]:
                    try:
                        value = read('shell', 'getprop', prop)
                    except ValueError:
                        value = ''
                    if not value or len(value) > 120 or serial in value or any(ord(c) < 32 for c in value):
                        unavailable.append(key); continue   # one missing fact never aborts the others
                    facts[key] = value
                def optional(key, reader):
                    try:
                        value = reader()
                    except (ValueError, OSError, subprocess.SubprocessError):
                        value = None
                    if value is None:
                        unavailable.append(key)
                    else:
                        facts[key] = value
                def battery():
                    text = read('shell', 'dumpsys', 'battery')
                    level = re.search(r'^\s*level:\s*(\d+)\s*$', text, re.M)
                    scale = re.search(r'^\s*scale:\s*(\d+)\s*$', text, re.M)
                    present = re.search(r'^\s*present:\s*(true|false)\s*$', text, re.M)
                    if present and present[1] == 'false':
                        return None
                    if level and scale and int(scale[1]) > 0 and 0 <= int(level[1]) <= int(scale[1]):
                        return round(int(level[1]) * 100 / int(scale[1]))
                    return None
                def storage():
                    kb = parse_df_available_kb(read('shell', 'df', '-k', '/data'))
                    if kb is None:
                        kb = parse_df_available_kb(read('shell', 'df', '/data'))
                    return None if kb is None else round(kb / 1024**2, 2)
                def timeout():
                    value = read('shell', 'settings', 'get', 'system', 'screen_off_timeout')
                    return int(value) // 1000 if value.isdigit() and int(value) % 1000 == 0 and 0 < int(value) <= 86400000 else None
                def ram():
                    match = re.search(r'^MemTotal:\s+(\d+)\s+kB', read('shell', 'cat', '/proc/meminfo'), re.M)
                    return round(int(match[1]) / 1024**2, 1) if match else None
                feature_list = None
                def feature(name):
                    def reader():
                        nonlocal feature_list
                        if feature_list is None:
                            feature_list = {line.split(':', 1)[1].split('=')[0].strip() for line in read('shell', 'pm', 'list', 'features').splitlines() if line.startswith('feature:')}
                        if not feature_list:
                            return None
                        return name in feature_list
                    return reader
                optional('battery_percent', battery)
                optional('storage_free_gb', storage)
                optional('screen_timeout_seconds', timeout)
                optional('ram_total_gb', ram)
                optional('is_television', feature('android.software.leanback'))
                optional('bluetooth_le', feature('android.hardware.bluetooth_le'))
                if not facts:
                    raise ValueError('No readable facts')
                now = datetime.now(timezone.utc).isoformat()
                return {'device_id': handle, 'status': 'READ_ONLY', 'simulated': False, 'source': 'ADB',
                        'model_status': 'NOT_CONNECTED', 'observed_at': now,
                        'summary': 'Real Android inventory, read-only. No device changes.',
                        'transport': device['transport'], 'unavailable': sorted(set(unavailable)),
                        'evidence': [{'key': key, 'value': value, 'source': 'ADB', 'observed_at': now} for key, value in facts.items()],
                        'checks': [
                            {'name': 'ADB authorization', 'status': 'PASS', 'detail': 'Device authorized at read time.'},
                            {'name': 'Hardware writes', 'status': 'BLOCKED', 'detail': 'Read-only; no modification commands.'},
                            {'name': 'Meta inference', 'status': 'NOT_TESTED', 'detail': 'No model calls using this device data.'},
                            {'name': 'Physical rollback', 'status': 'NOT_TESTED', 'detail': 'No physical transaction performed.'}]}
            except (OSError, ValueError, subprocess.SubprocessError):
                raise ValueError('Device read failed; reconnect and authorize the device') from None
