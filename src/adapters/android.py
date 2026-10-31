"""Opt-in, read-only ADB inventory. Serial numbers never leave this adapter."""
from datetime import datetime, timezone
import os
import re
import secrets
import shutil
import subprocess
import tempfile
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

    def _run(self, args, max_bytes=131072):
        result = self.runner([self.executable, *args], capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=8,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or len(result.stdout) > min(max_bytes, 2097152):
            raise ValueError('ADB operation unavailable')
        return result.stdout

    def screencap(self, serial, max_bytes=8 * 1024 * 1024):
        """One PNG frame (binary). Read-only; used only by the consent-gated visual read-back."""
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', serial):
            raise ValueError('invalid serial')
        result = self.runner([self.executable, '-s', serial, 'exec-out', 'screencap', '-p'], capture_output=True, timeout=10,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        start = result.stdout.find(b'\x89PNG\r\n\x1a\n')      # some TV builds print log lines before the PNG
        if result.returncode or start < 0 or start > 4096 or len(result.stdout) > max_bytes:
            raise ValueError('Screen capture unavailable')
        return result.stdout[start:]

    def _serial_for_handle(self, handle):
        with self._lock:
            serial = next((k for k, v in self._handles.items() if v == handle), None)
        if serial is None:
            raise ValueError('Unknown device')
        return serial

    @staticmethod
    def _check_pull_path(remote):
        if not isinstance(remote, str) or not remote.startswith('/sdcard/') or len(remote) > 256 \
                or '..' in remote or not re.fullmatch(r'[A-Za-z0-9_./-]+', remote):
            raise ValueError('remote path must stay under /sdcard/ (no traversal, no shell metacharacters)')
        return remote

    def pull_file(self, handle, remote, max_bytes=8 * 1024 * 1024):
        """Read one file under /sdcard/ as bytes (`exec-out cat`, binary-safe). Consent-gated by callers."""
        serial = self._serial_for_handle(handle)
        self._check_pull_path(remote)
        result = self.runner([self.executable, '-s', serial, 'exec-out', 'cat', remote], capture_output=True,
                             timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or not isinstance(result.stdout, (bytes, bytearray)) \
                or len(result.stdout) > max_bytes:
            raise ValueError('File pull unavailable')
        return bytes(result.stdout)

    def push_file(self, handle, data, name):
        """Push bytes to /sdcard/OpenBridge/<name>. Name is strict (no slashes, no traversal); temp file removed."""
        serial = self._serial_for_handle(handle)
        if not isinstance(name, str) or '..' in name or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', name):
            raise ValueError('bad file name')
        if not isinstance(data, (bytes, bytearray)) or not data or len(data) > 32 * 1024 * 1024:
            raise ValueError('bad file data')
        remote = '/sdcard/OpenBridge/' + name
        tmp = tempfile.NamedTemporaryFile(prefix='ob-push-', suffix='.bin', delete=False)
        try:
            tmp.write(bytes(data))
            tmp.close()
            result = self.runner([self.executable, '-s', serial, 'push', tmp.name, remote], capture_output=True,
                                 text=True, encoding='utf-8', errors='replace', timeout=60,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        if result.returncode:
            raise ValueError('File push failed')
        return remote

    def file_sha256(self, handle, remote):
        """`sha256sum` of a file under /sdcard/ (push verification). Returns 64 hex chars."""
        serial = self._serial_for_handle(handle)
        self._check_pull_path(remote)
        out = self._run(['-s', serial, 'shell', 'sha256sum', remote]).strip().split()
        if not out or not re.fullmatch(r'[0-9a-f]{64}', out[0]):
            raise ValueError('unreadable sha256sum output')
        return out[0]

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

    def serial_for(self, handle):
        with self._lock:
            return next((k for k, v in self._handles.items() if v == handle), None)

    def handle_for(self, serial):
        with self._lock:
            return self._handles.get(serial)

    def install_companion(self, handle, apk_path):
        """Fixed `adb install -r <OpenBridge Companion APK>`; returns raw adb output for classification (never raises on refusal)."""
        with self._lock:
            serial = next((k for k, v in self._handles.items() if v == handle), None)
            if serial is None:
                raise ValueError('Unknown device')
            result = self.runner([self.executable, '-s', serial, 'install', '-r', str(apk_path)], capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            output = (result.stdout or '') + (result.stderr or '')
            if 'Success' in output:
                self._run(['-s', serial, 'shell', 'am', 'start', '-n', 'fr.openbridge.companion/.MainActivity'])
            return output[-2000:]

    def bluetooth_identifier(self, handle, salt):
        """Read-only `settings get secure bluetooth_address` -> opaque mac_global, so a TV seen over ADB merges with its
        mDNS announcement (androidtvremote2 'bt'). None when hidden (most phones on Android 12+) or randomized."""
        import hashlib, hmac
        from src.fabric.contracts import mac_is_randomized
        with self._lock:
            serial = next((k for k, v in self._handles.items() if v == handle), None)
            if serial is None:
                return None
            try:
                mac = self._run(['-s', serial, 'shell', 'settings', 'get', 'secure', 'bluetooth_address']).strip().lower()
            except (OSError, ValueError, subprocess.SubprocessError):
                return None
        if not re.fullmatch(r'([0-9a-f]{2}:){5}[0-9a-f]{2}', mac) or mac_is_randomized(mac):
            return None
        return 'mac_global:' + hmac.new(salt, f'mac_global\0{mac}'.encode(), hashlib.sha256).hexdigest()[:24]

    def connect_network(self, ip, port=5555):
        """One owner-triggered `adb connect` to a device already in the graph. Private IPv4 only; no scanning."""
        import ipaddress, socket
        address = ipaddress.ip_address(ip)
        if address.version != 4 or not address.is_private or address.is_loopback:
            raise ValueError('Only private IPv4 addresses on the local network')
        probe = socket.socket(); probe.settimeout(2)
        try:
            if probe.connect_ex((str(address), port)) != 0:
                return 'PORT_CLOSED'
        finally:
            probe.close()
        out = self._run(['connect', f'{address}:{port}']).strip().lower()
        state = next((d['state'] for d in self.discover()['devices'] if d['transport'] == 'WIFI' and
                      any(k == f'{address}:{port}' for k, v in self._handles.items() if v == d['id'])), None)
        if state == 'device':
            return 'AUTHORIZED'
        if state == 'unauthorized' or 'authenticate' in out:
            return 'WAITING_FOR_TV_APPROVAL'
        return 'CONNECT_FAILED'

    def forward_companion(self, handle, port=None):
        """`adb forward tcp:<local> tcp:47800` so the PC reaches the Companion over ADB without exposing it on Wi-Fi.
        Each device gets its own local port (allocated by adb, then kept stable): with one shared port, the last
        forward silently redirected every relay to the last device, so two relays could never coexist."""
        if port is not None and (not isinstance(port, int) or not 1024 < port < 65536):
            raise ValueError('Invalid port')
        with self._lock:
            serial = next((k for k, v in self._handles.items() if v == handle), None)
            if serial is None:
                raise ValueError('Unknown device')
            ports = self.__dict__.setdefault('_companion_ports', {})
            if port is None:
                listed = self._run(['forward', '--list'])
                known = ports.get(serial)
                if known and f'{serial} tcp:{known} tcp:47800' in listed:
                    return f'http://127.0.0.1:{known}'
                out = self._run(['-s', serial, 'forward', 'tcp:0', 'tcp:47800']).strip()
                if not out.isdigit() or not 1024 < int(out) < 65536:
                    raise ValueError('ADB did not allocate a forward port')
                port = int(out)
            else:
                self._run(['-s', serial, 'forward', f'tcp:{port}', 'tcp:47800'])
            ports[serial] = port
        return f'http://127.0.0.1:{port}'

    def direct_url(self, handle):
        """Direct-LAN relay URL for a Wi-Fi adb serial (`ip:port` -> `http://ip:47800`).

        USB serials have no IP: None (post-pairing, `lan_url_for_relay`
        matches the companion mDNS record by relay id instead). Private
        IPv4 only; never loopback (that tier is the adb forward)."""
        import ipaddress
        with self._lock:
            serial = next((k for k, v in self._handles.items() if v == handle), None)
        if serial is None:
            raise ValueError('Unknown device')
        ip, _, _ = serial.rpartition(':')
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return None
        if address.version != 4 or not address.is_private or address.is_loopback:
            return None
        return f'http://{ip}:47800'

    def relay_urls(self, handle):
        """Ordered relay candidates: direct Wi-Fi/LAN first, adb forward last.

        Owner priority wifi -> lan -> adb-wifi -> adb maps to: the serial IP
        is tried first (whatever medium carries it), then the adb forward for
        that serial (which itself rides adb-over-wifi or adb-over-USB)."""
        urls = []
        direct = self.direct_url(handle)
        if direct:
            urls.append(direct)
        urls.append(self.forward_companion(handle))
        return urls

    @staticmethod
    def lan_url_for_relay(relay_id, timeout=1.0):
        """Direct-LAN URL by mDNS match on the companion TXT relay id.

        Gives USB-paired devices a direct URL after pairing (their serial
        carries no IP). Bounded single browse; any failure or mismatch is
        None (the caller keeps the adb forward)."""
        import ipaddress as _ip
        from src.fabric import mdns
        if not isinstance(relay_id, str) or not re.fullmatch(r'relay-[0-9a-f]{12}', relay_id):
            return None
        try:
            res = mdns.discover(timeout=timeout, services=('_openbridge-relay._tcp',))
        except OSError:
            return None
        scope = mdns.default_scope()
        for inst in res.get('instances', []):
            if inst.get('service') != '_openbridge-relay._tcp':
                continue
            if (inst.get('txt') or {}).get('relay') != relay_id:
                continue
            port = inst.get('port')
            if not isinstance(port, int) or isinstance(port, bool) or not 1024 < port < 65536:
                continue
            for ip in inst.get('addresses', []):
                try:
                    a = _ip.ip_address(ip)
                except ValueError:
                    continue
                if a.version == 4 and a.is_private and not a.is_loopback and mdns.in_scope(ip, scope):
                    return f'http://{ip}:{port}'
        return None

    def pair_wireless(self, ip, pair_port, code):
        """Owner-typed Wear OS / Android 11+ wireless-debugging pairing: `adb pair` with the code shown on the device,
        then connect to the port the device advertises over mDNS. Private IPv4 only; no scanning."""
        import ipaddress, re as _re
        address = ipaddress.ip_address(ip)
        if address.version != 4 or not address.is_private or address.is_loopback:
            raise ValueError('Only private IPv4 addresses on the local network')
        if not (isinstance(pair_port, int) and 1024 < pair_port < 65536) or not _re.fullmatch(r'\d{6}', str(code)):
            raise ValueError('Pairing needs the port and the 6-digit code shown on the device')
        out = self._run(['pair', f'{address}:{pair_port}', str(code)])
        if 'successfully paired' not in out.lower():
            return 'PAIR_FAILED', None
        services = self._run(['mdns', 'services'])
        m = _re.search(rf'_adb-tls-connect\._tcp\s+{_re.escape(str(address))}:(\d+)', services)
        if not m:
            return 'PAIRED_NOT_ADVERTISED', None
        target = f'{address}:{m.group(1)}'
        self._run(['connect', target])
        state = next((d['state'] for d in self.discover()['devices'] if
                      any(k == target for k, v in self._handles.items() if v == d['id'])), None)
        return ('AUTHORIZED' if state == 'device' else 'CONNECT_FAILED'), target

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
                optional('is_watch', feature('android.hardware.type.watch'))
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
