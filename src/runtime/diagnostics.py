"""Readable diagnostics. Each finding states whether it is OBSERVED (value returned by the device/API) or INFERRED
(OpenBridge's conclusion, with its basis). Sensitive fields (serials, MACs, SSIDs, keys, IPs) are never returned."""
import json
import os
import re
import time
from datetime import date
from pathlib import Path


def finding(name, value, unit='', source='', inferred=False, basis='', level='info'):
    return {'name': name, 'value': value, 'unit': unit, 'source': source, 'kind': 'INFERRED' if inferred else 'OBSERVED',
            'basis': basis, 'level': level}


# ---------------- Android ----------------
ANDROID_READS = (('dumpsys', 'battery'), ('df', '-k', '/data'), ('cat', '/proc/uptime'), ('cmd', 'wifi', 'status'),
                 ('settings', 'get', 'global', 'airplane_mode_on'), ('cat', '/sys/devices/system/cpu/possible'),
                 ('cat', '/proc/meminfo'), ('am', 'get-current-user'), ('getprop', 'ro.build.version.security_patch'),
                 ('getprop', 'ro.build.version.release'), ('pm', 'list', 'packages', '-3'),
                 ('dumpsys', 'power'), ('dumpsys', 'thermalservice'))
LARGE_READS = (('dumpsys', 'power'), ('dumpsys', 'thermalservice'))
THERMAL = ('none', 'light', 'moderate', 'severe', 'critical', 'emergency', 'shutdown')
HEALTH = {1: 'unknown', 2: 'good', 3: 'overheat', 4: 'dead', 5: 'over voltage', 6: 'failure', 7: 'cold'}
STATUS = {1: 'unknown', 2: 'charging', 3: 'discharging', 4: 'not charging', 5: 'full'}


def android(read, today=None):
    """read(*shell_args) -> stdout or raises ValueError. Every read is optional and independent."""
    today = today or date.today()
    out = []
    def safe(*a):
        try:
            return read(*a)
        except (ValueError, OSError):
            return None
    b = safe('dumpsys', 'battery')
    if b:
        g = lambda k: (re.search(rf'^\s*{k}:\s*(\S+)\s*$', b, re.M) or [None, None])[1]
        present = g('present')
        if present == 'false':
            out.append(finding('battery', 'none', source='dumpsys battery', level='info'))
        else:
            if g('level') and g('scale') and g('scale') != '0':
                out.append(finding('battery_level', round(int(g('level')) * 100 / int(g('scale'))), '%', 'dumpsys battery'))
            if g('temperature') and g('temperature').lstrip('-').isdigit():
                t = int(g('temperature')) / 10
                out.append(finding('battery_temperature', t, '°C', 'dumpsys battery'))
                if t >= 45:
                    out.append(finding('battery_hot', True, '', 'battery_temperature', True, '≥ 45 °C while sampled', 'warning'))
            if g('health') and g('health').isdigit():
                h = HEALTH.get(int(g('health')), 'unknown')
                out.append(finding('battery_health', h, '', 'dumpsys battery', level='info' if h in ('good', 'unknown') else 'warning'))
            if g('status') and g('status').isdigit():
                out.append(finding('battery_status', STATUS.get(int(g('status')), 'unknown'), '', 'dumpsys battery'))
    df = safe('df', '-k', '/data')
    if df:
        toks = ' '.join(df.splitlines()[1:]).split()
        pct = next((i for i, t in enumerate(toks) if t.endswith('%')), None)
        if pct is not None and pct >= 3 and all(x.isdigit() for x in toks[pct - 3:pct]):
            total, used, avail = (int(x) for x in toks[pct - 3:pct])
            out += [finding('storage_total', round(total / 1024 ** 2, 1), 'GB', 'df /data'),
                    finding('storage_free', round(avail / 1024 ** 2, 2), 'GB', 'df /data')]
            if total and avail / total < 0.10:
                out.append(finding('storage_low', True, '', 'storage_free/storage_total', True, 'less than 10% free', 'warning'))
    up = safe('cat', '/proc/uptime')
    if up and re.match(r'^\d+(\.\d+)?', up):
        out.append(finding('uptime', round(float(up.split()[0]) / 3600, 1), 'h', '/proc/uptime'))
    w = safe('cmd', 'wifi', 'status')
    if w:
        state = 'enabled' if 'Wifi is enabled' in w else 'disabled' if 'Wifi is disabled' in w else None
        if state:
            out.append(finding('wifi', state, '', 'cmd wifi status'))
    a = safe('settings', 'get', 'global', 'airplane_mode_on')
    if a in ('0', '1'):
        out.append(finding('airplane_mode', a == '1', '', 'settings global'))
    c = safe('cat', '/sys/devices/system/cpu/possible')
    if c and re.fullmatch(r'0-(\d+)', c.strip()):
        out.append(finding('cpu_cores', int(c.strip().split('-')[1]) + 1, '', '/sys/devices/system/cpu/possible'))
    m = safe('cat', '/proc/meminfo')
    if m:
        tot, av = re.search(r'^MemTotal:\s+(\d+)', m, re.M), re.search(r'^MemAvailable:\s+(\d+)', m, re.M)
        if tot and av:
            out.append(finding('memory_available', round(int(av[1]) / 1024 ** 2, 2), 'GB', '/proc/meminfo'))
    u = safe('am', 'get-current-user')
    if u and u.strip().isdigit():
        out.append(finding('active_android_user', int(u.strip()), '', 'am get-current-user'))
    sp = safe('getprop', 'ro.build.version.security_patch')
    if sp and re.fullmatch(r'\d{4}-\d{2}-\d{2}', sp.strip()):
        out.append(finding('security_patch', sp.strip(), '', 'getprop'))
        y, mo, _ = map(int, sp.strip().split('-'))
        months = (today.year - y) * 12 + today.month - mo
        if months > 12:
            out.append(finding('security_patch_outdated', months, 'months', 'security_patch', True, 'patch older than 12 months', 'warning'))
    p = safe('pm', 'list', 'packages', '-3')
    if p is not None:
        out.append(finding('user_installed_apps', sum(1 for l in p.splitlines() if l.startswith('package:')), '', 'pm list packages -3'))
    pw = safe('dumpsys', 'power')
    if pw:
        w = re.search(r'mWakefulness=(\w+)', pw)
        if w:
            out.append(finding('power_state', w[1].lower(), '', 'dumpsys power'))
    th = safe('dumpsys', 'thermalservice')
    if th:
        t = re.search(r'^Thermal Status: (\d)\s*$', th, re.M)
        if t and int(t[1]) < len(THERMAL):
            out.append(finding('thermal_status', THERMAL[int(t[1])], '', 'dumpsys thermalservice'))
            if int(t[1]) >= 2:
                out.append(finding('thermal_throttling_likely', True, '', 'thermal_status', True, 'Android thermal status moderate or worse', 'warning'))
    return out


# ---------------- Windows PC (BridgeWindows agent, read-only) ----------------
def windows(call):
    """call(method, params=None) -> result dict, or raises. Only allowlisted read methods reach the agent."""
    out = []
    try:
        d = call('sys.diag')
    except Exception:
        d = None
    if d:
        src = 'agent sys.diag'
        if isinstance(d.get('os_build'), int):
            out.append(finding('os_build', d['os_build'], '', src))
        if d.get('architecture'):
            out.append(finding('architecture', str(d['architecture'])[:8], '', src))
        if isinstance(d.get('cpu_cores'), int):
            out.append(finding('cpu_cores', d['cpu_cores'], '', src))
        if isinstance(d.get('cpu_load_percent'), (int, float)):
            out.append(finding('cpu_load', round(d['cpu_load_percent'], 1), '%', src))
        tot, av = d.get('ram_total_bytes'), d.get('ram_avail_bytes')
        if isinstance(tot, int) and isinstance(av, int) and tot > 0:
            out += [finding('memory_total', round(tot / 1024 ** 3, 2), 'GB', src), finding('memory_available', round(av / 1024 ** 3, 2), 'GB', src)]
            if av / tot < 0.10:
                out.append(finding('memory_pressure', True, '', 'memory_available/memory_total', True, 'less than 10% RAM available', 'warning'))
        if isinstance(d.get('uptime_seconds'), (int, float)):
            out.append(finding('uptime', round(d['uptime_seconds'] / 3600, 1), 'h', src))
        for disk in (d.get('disks') or [])[:8]:
            if isinstance(disk, dict) and isinstance(disk.get('total_bytes'), int) and disk['total_bytes'] > 0 and isinstance(disk.get('free_bytes'), int):
                m = str(disk.get('mount', '?'))[:4].rstrip(':\\/') or '?'
                out.append(finding(f'disk_{m}_free', round(disk['free_bytes'] / 1024 ** 3, 1), 'GB', src))
                if disk['free_bytes'] / disk['total_bytes'] < 0.10:
                    out.append(finding(f'disk_{m}_low', True, '', f'disk_{m}_free', True, 'less than 10% free', 'warning'))
        if isinstance(d.get('gpu_temp_c'), (int, float)) and d['gpu_temp_c'] > 0:
            out.append(finding('gpu_temperature', d['gpu_temp_c'], '°C', src))
    try:
        p = call('proc.list')
        procs = p.get('processes') if isinstance(p, dict) else None
        if isinstance(procs, list):
            out.append(finding('process_count', len(procs), '', 'agent proc.list'))   # names are not returned
    except Exception:
        pass
    return out


# ---------------- Freebox ----------------
def freebox(session, state_dir=None):
    out = []
    def get(path):
        try:
            return session.get(path)
        except Exception:
            return None
    c = get('connection/')
    if c:
        out += [finding('internet_state', c.get('state'), '', 'GET connection/'), finding('internet_media', c.get('media'), '', 'GET connection/'),
                finding('internet_type', c.get('type'), '', 'GET connection/')]
        for k, n in (('bandwidth_down', 'bandwidth_down'), ('bandwidth_up', 'bandwidth_up')):
            if isinstance(c.get(k), int):
                out.append(finding(n, round(c[k] / 1e6), 'Mbit/s', 'GET connection/'))
        for k in ('rate_down', 'rate_up'):
            if isinstance(c.get(k), int):
                out.append(finding(k, round(c[k] * 8 / 1e6, 2), 'Mbit/s', 'GET connection/ (instantaneous)'))
        if c.get('state') and c.get('state') != 'up':
            out.append(finding('internet_down', True, '', 'internet_state', True, f"state is {c.get('state')}", 'warning'))
    f = get('connection/ftth/')
    if f:
        out.append(finding('fiber_link', bool(f.get('link')), '', 'GET connection/ftth/'))
        for k in ('sfp_pwr_rx', 'sfp_pwr_tx'):
            if isinstance(f.get(k), int):
                dbm = f[k] / 100
                out.append(finding(k.replace('sfp_pwr_', 'optical_power_'), dbm, 'dBm', 'GET connection/ftth/'))
                if k == 'sfp_pwr_rx' and not -28 <= dbm <= -8:
                    out.append(finding('optical_rx_out_of_typical_range', dbm, 'dBm', k, True, 'typical GPON receive range −28 to −8 dBm', 'warning'))
    s = get('system/')
    if s:
        out.append(finding('firmware', s.get('firmware_version'), '', 'GET system/'))
        if isinstance(s.get('uptime_val'), int):
            out.append(finding('box_uptime', round(s['uptime_val'] / 86400, 1), 'days', 'GET system/'))
        for sensor in (s.get('sensors') or [])[:8]:
            if isinstance(sensor, dict) and isinstance(sensor.get('value'), (int, float)):
                out.append(finding('temperature_' + str(sensor.get('id', 'sensor'))[:20], sensor['value'], '°C', 'GET system/ sensors'))
        for fan in (s.get('fans') or [])[:4]:
            if isinstance(fan, dict) and isinstance(fan.get('value'), (int, float)):
                out.append(finding('fan_' + str(fan.get('id', 'fan'))[:20], fan['value'], 'rpm', 'GET system/ fans'))
    w = get('wifi/config/')
    if w:
        out.append(finding('wifi_enabled', bool(w.get('enabled')), '', 'GET wifi/config/'))
    aps = get('wifi/ap/')
    if isinstance(aps, list):
        for ap in aps[:6]:
            cfg, st = ap.get('config') or {}, ap.get('status') or {}
            band = cfg.get('band') or ap.get('name')
            out.append(finding(f"wifi_radio_{str(band)[:10]}", st.get('state'), '', 'GET wifi/ap/'))
            if isinstance(st.get('primary_channel'), int):
                out.append(finding(f"wifi_channel_{str(band)[:10]}", st['primary_channel'], '', 'GET wifi/ap/'))
    hosts = None
    try:
        hosts = session.lan_hosts()
    except Exception:
        pass
    if hosts is not None:
        active = {h['mac'] for h in hosts if h['active'] and h['mac']}
        out.append(finding('lan_active_hosts', len(active), '', 'GET lan/browser/pub/'))
        path = Path(state_dir or Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge') / 'freebox-presence.json'
        import hashlib
        hashed = sorted(hashlib.sha256(m.encode()).hexdigest()[:16] for m in active)
        try:
            prev = json.loads(path.read_text())
            arrived = len(set(hashed) - set(prev['hosts'])); left = len(set(prev['hosts']) - set(hashed))
            out.append(finding('lan_presence_changes', {'arrived': arrived, 'left': left, 'since_s': int(time.time() - prev['at'])},
                               '', 'compared with previous diagnostic', True, 'difference of active hosts between two runs'))
        except (OSError, ValueError, KeyError):
            pass
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps({'at': time.time(), 'hosts': hashed}))
    return out
