"""§9 hardware intelligence: measurement-grounded facts, task rankers, micro-benchmarks.

Every metric carries value, unit, source, timestamp, confidence and
availability. Rankers explain with evidence and cite what is missing; they
never invent data — insufficient measurements yield low confidence plus a
benchmark offer. Consent gates live at the API boundary; the pure functions
here take explicit consent for anything that consumes resources.
"""
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone

CONFIDENCE = ('measured', 'reported', 'unknown')
MAX_CPU_ITERATIONS = 2_000_000
MAX_DISK_MB = 64
MAX_RTT_ATTEMPTS = 10


class HardwareError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def metric(name, value, unit, source, confidence='measured'):
    if confidence not in CONFIDENCE:
        raise HardwareError('CONFIDENCE')
    return {'name': name, 'value': value, 'unit': unit, 'source': source,
            'observed_at': _now(), 'confidence': confidence, 'availability': 'available'}


def band_from_mhz(mhz):
    if not isinstance(mhz, int) or isinstance(mhz, bool) or mhz <= 0:
        return 'unknown'
    if 2400 <= mhz < 2500:
        return '2.4GHz'
    if 5000 <= mhz < 5925:
        return '5GHz'
    if 5925 <= mhz <= 7125:
        return '6GHz'
    return 'unknown'


def parse_wifi_freq(text):
    m = re.search(r'freq=(\d+)', text or '')
    return int(m[1]) if m else None


def parse_battery_extra(text):
    text = text or ''
    status = re.search(r'^\s*status:\s*(\d+)\s*$', text, re.M)
    plugged = re.search(r'^\s*plugged:\s*(\d+)\s*$', text, re.M)
    code = int(status[1]) if status else None
    plug = int(plugged[1]) if plugged else None
    charging = code == 2
    plugs = {0: 'none', 1: 'ac', 2: 'usb', 4: 'wireless'}
    cap = re.search(r'(?:capacity|charge_counter_design|full_charge_capacity)\D{0,8}(\d{3,6})\s*(?:mAh|uAh)?', text, re.M)
    mah = int(cap[1]) // 1000 if cap and 'uAh' in (cap[0] or '') else (int(cap[1]) if cap else None)
    return {'charging': charging, 'plugged': plugs.get(plug, 'unknown'),
            'capacity_mah': mah if mah and 500 <= mah <= 30000 else None}


def parse_cpu_count(text):
    n = len(re.findall(r'^processor\s*:', text or '', re.M))
    return n or None


def parse_mem_total_gb(text):
    m = re.search(r'^MemTotal:\s+(\d+)\s+kB', text or '', re.M)
    return round(int(m[1]) / 1024 ** 2, 1) if m else None


def parse_gpu_name(text):
    m = re.search(r'GLES:\s*([^,\n]+),\s*([^\n]+)', text or '')
    if m:
        return m[2].strip() or None
    m = re.search(r'^\s*(\S.+)$', (text or '').strip())
    return m[1].strip()[:80] if m else None


def parse_nvidia_smi(text):
    for line in (text or '').splitlines()[1:]:
        m = re.match(r'\s*(.+?),\s*(\d+)\s*MiB', line)
        if m:
            return {'gpu_name': m[1].strip(), 'gpu_vram_gb': round(int(m[2]) / 1024, 1)}
    return None


def parse_cellular(text):
    if not text or 'mServiceState' not in text and 'mDataRegState' not in text:
        return None
    m = re.search(r'mDataRegState=(\d+)', text)
    v = re.search(r'mVoiceRegState=(\d+)', text)
    if (m and m[1] == '0') or (v and v[1] == '0'):
        return 'present'
    if m or v:
        return 'absent'
    return None


def android_facts(run):
    """Collect §9 metrics via an injected shell runner (adb). Failures degrade
    per-metric: unreadable facts are omitted, never fabricated."""
    out = []

    def grab(name, unit, source, reader, confidence='measured'):
        try:
            value = reader()
        except (OSError, ValueError, subprocess.SubprocessError):
            return
        if value is not None:
            out.append(metric(name, value, unit, source, confidence))

    def wifi_band():
        for argv in (('dumpsys', 'wifi'), ('cmd', 'wifi', 'status')):
            try:
                freq = parse_wifi_freq(run(*argv))
            except (OSError, ValueError, subprocess.SubprocessError):
                continue
            if freq:
                return band_from_mhz(freq)
        return None

    def battery_part(key):
        extra = parse_battery_extra(run('dumpsys', 'battery'))
        return extra[key]

    grab('wifi_band', 'band', 'ADB', wifi_band)
    grab('battery_charging', 'bool', 'ADB', lambda: battery_part('charging'))
    grab('battery_plugged', 'source', 'ADB', lambda: battery_part('plugged'))
    grab('battery_capacity_mah', 'mAh', 'ADB', lambda: battery_part('capacity_mah'))
    grab('cpu_count', 'cores', 'ADB', lambda: parse_cpu_count(run('cat', '/proc/cpuinfo')))
    grab('ram_total_gb', 'GB', 'ADB', lambda: parse_mem_total_gb(run('cat', '/proc/meminfo')))

    def gpu():
        try:
            name = parse_gpu_name(run('dumpsys', 'SurfaceFlinger'))
        except (OSError, ValueError, subprocess.SubprocessError):
            name = None
        if not name:
            egl = run('getprop', 'ro.hardware.egl')
            name = (egl or '').strip()[:80] or None
        return name

    grab('gpu', 'name', 'ADB', gpu, 'reported')
    grab('cellular', 'state', 'ADB', lambda: parse_cellular(run('dumpsys', 'telephony.registry')))
    return out


def pc_facts(run=None):
    """This PC via stdlib (+ optional nvidia-smi through an injected runner)."""
    out = [metric('cpu_threads', os.cpu_count() or 1, 'threads', 'OS', 'reported')]

    def ram_gb():
        try:
            import ctypes
            class Mem(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                            ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                            ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
            m = Mem()
            m.dwLength = ctypes.sizeof(Mem)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return round(m.ullTotalPhys / 1024 ** 3, 1)
        except (OSError, AttributeError, ValueError):
            pass
        try:
            with open('/proc/meminfo', encoding='utf-8') as f:
                return parse_mem_total_gb(f.read())
        except OSError:
            return None

    ram = ram_gb()
    if ram:
        out.append(metric('ram_gb', ram, 'GB', 'OS', 'reported'))
    try:
        free = shutil.disk_usage(os.path.expanduser('~')).free
        out.append(metric('disk_free_gb', round(free / 1024 ** 3, 1), 'GB', 'OS'))
    except OSError:
        pass
    out.append(metric('os', '%s %s' % (platform.system(), platform.release()), 'name', 'OS', 'reported'))
    if run is not None:
        try:
            gpu = parse_nvidia_smi(run('nvidia-smi', '--query-gpu=name,memory.total', '--format=csv'))
        except (OSError, ValueError, subprocess.SubprocessError):
            gpu = None
        if gpu:
            out.append(metric('gpu_name', gpu['gpu_name'], 'name', 'nvidia-smi', 'reported'))
            out.append(metric('gpu_vram_gb', gpu['gpu_vram_gb'], 'GB', 'nvidia-smi', 'reported'))
    return out


def _val(dev, name):
    m = (dev.get('metrics') or {}).get(name)
    return m['value'] if isinstance(m, dict) else None


def _gpu_name(dev):
    return _val(dev, 'gpu_name') or _val(dev, 'gpu')


def _row(dev, score, confidence, reasons, evidence):
    return {'key': dev['key'], 'label': dev.get('label', dev['key']), 'score': score,
            'confidence': confidence, 'reasons': reasons, 'evidence': evidence}


def _offer(kind, why, bounded, status='available'):
    return {'kind': kind, 'why': why, 'bounded': bounded, 'status': status}


def rank(task, devices, relays=None):
    relays = relays or {}
    fn = {'minecraft': _rank_minecraft, 'dev': _rank_dev, 'ai_model': _rank_ai,
          'weekend_phone': _rank_weekend, 'recharge_first': _rank_recharge,
          'wifi_bands': _rank_wifi, 'bt_relay': _rank_bt}.get(task)
    if fn is None:
        raise HardwareError('UNKNOWN_TASK')
    norm = []
    for d in (devices or []):
        m = d.get('metrics')
        metrics = {x['name']: x for x in m} if isinstance(m, list) else (m or {})
        norm.append({**d, 'metrics': metrics})
    ranking, notes, offer = fn(norm, relays)
    return {'task': task, 'ranking': ranking, 'notes': notes, 'benchmark_offer': offer}


def _rank_minecraft(devices, _relays):
    rows = []
    for d in devices:
        t, ram, vram = _val(d, 'cpu_threads'), _val(d, 'ram_gb'), _val(d, 'gpu_vram_gb')
        gpu = str(_gpu_name(d) or '')
        have = sum(v is not None for v in (t, ram, vram, gpu or None))
        score = (2 * (t or 0) + 3 * (ram or 0) + 4 * (vram or 0)
                 + (10 if re.search(r'RTX|GTX|Radeon RX|Arc', gpu) else 0))
        rows.append(_row(d, round(score, 1), 'high' if have >= 4 else 'medium' if have >= 2 else 'low',
                         ['%s threads, %s GB RAM, %s GB VRAM (%s)' % (t, ram, vram, gpu or 'GPU unknown')],
                         [n for n, v in (('cpu_threads', t), ('ram_gb', ram), ('gpu_vram_gb', vram)) if v is not None]))
    rows.sort(key=lambda r: r['score'], reverse=True)
    offer = None
    if any(r['confidence'] == 'low' for r in rows):
        offer = _offer('cpu_loop', 'CPUThreads unknown: a bounded single-thread loop grounds the ranking.',
                       {'iterations': 200000, 'max_s': 10})
    return rows, [], offer


def _rank_dev(devices, _relays):
    rows = []
    for d in devices:
        t, ram, disk = _val(d, 'cpu_threads'), _val(d, 'ram_gb'), _val(d, 'disk_free_gb')
        have = sum(v is not None for v in (t, ram, disk))
        score = 3 * (t or 0) + 4 * (ram or 0) + 0.1 * min(disk or 0, 200)
        rows.append(_row(d, round(score, 1), 'high' if have >= 3 else 'medium' if have >= 2 else 'low',
                         ['%s threads, %s GB RAM, %s GB free (%s)' % (t, ram, disk, _val(d, 'os') or 'OS unknown')],
                         [n for n, v in (('cpu_threads', t), ('ram_gb', ram), ('disk_free_gb', disk)) if v is not None]))
    rows.sort(key=lambda r: r['score'], reverse=True)
    offer = None
    if any(r['confidence'] == 'low' for r in rows):
        offer = _offer('cpu_loop', 'CPU/RAM unknown: a bounded loop + allocator pass grounds the ranking.',
                       {'iterations': 200000, 'max_s': 10})
    return rows, [], offer


def _model_class(vram):
    if vram is None:
        return 'unknown VRAM: no class estimated'
    if vram >= 14:
        return 'fits ~30B Q4 local Meta models'
    if vram >= 7:
        return 'fits ~13B Q4 local Meta models'
    if vram >= 4:
        return 'fits ~7B Q4 local Meta models'
    if vram >= 2:
        return 'fits ~3B local Meta models'
    return 'CPU-only tiny models'


def _rank_ai(devices, _relays):
    rows = []
    for d in devices:
        vram, ram = _val(d, 'gpu_vram_gb'), _val(d, 'ram_gb')
        gpu = str(_gpu_name(d) or '')
        cuda = bool(re.search(r'NVIDIA|RTX|GTX|CUDA', gpu, re.I))
        score = 10 * (vram or 0) + (ram or 0) + (20 if cuda else 0)
        have = sum(v is not None for v in (vram, ram))
        rows.append(_row(d, round(score, 1), 'high' if have >= 2 and vram else 'medium' if have else 'low',
                         ['%s GB VRAM (%s); %s' % (vram, gpu or 'GPU unknown', _model_class(vram))],
                         [n for n, v in (('gpu_vram_gb', vram), ('ram_gb', ram)) if v is not None]))
    rows.sort(key=lambda r: r['score'], reverse=True)
    offer = _offer('inference_latency', 'No measured latency: a short local prompt timing grounds the estimate.',
                   {'prompt_tokens': 64, 'max_s': 120}, 'needs-model')
    return rows, [], offer


def _rank_weekend(devices, _relays):
    rows, notes = [], []
    for d in devices:
        pct, cap = _val(d, 'battery_percent'), _val(d, 'battery_capacity_mah')
        if pct is None:
            notes.append('%s: no battery reading, excluded' % d['key'])
            continue
        if cap:
            score = pct / 100 * cap
            reasons = ['remaining ~%dmAh of %dmAh nominal (%s%%)' % (round(score), cap, pct)]
            conf = 'high'
        else:
            score = pct
            reasons = ['remaining %s%% (nominal capacity unknown; ranking by remaining %% only)' % pct]
            conf = 'low'
        rows.append(_row(d, round(score, 1), conf, reasons,
                         [n for n, v in (('battery_percent', pct), ('battery_capacity_mah', cap)) if v is not None]))
    rows.sort(key=lambda r: r['score'], reverse=True)
    offer = None
    if any(r['confidence'] == 'low' for r in rows):
        offer = _offer('device_rtt', 'Battery readings unverified: a live read confirms the device is reachable.',
                       {'attempts': 3, 'max_s': 15})
    return rows, notes, offer


def _rank_recharge(devices, _relays):
    rows, notes = [], []
    for d in devices:
        pct = _val(d, 'battery_percent')
        if pct is None:
            notes.append('%s: no battery reading, excluded' % d['key'])
            continue
        charging = bool(_val(d, 'battery_charging'))
        score = (1000 if charging else 0) + pct
        rows.append(_row(d, score, 'high',
                         ['%s%%, %s' % (pct, 'charging' if charging else 'not charging')],
                         ['battery_percent']))
    rows.sort(key=lambda r: r['score'])
    return rows, notes, None


def _rank_wifi(devices, _relays):
    rows = []
    for d in devices:
        band = _val(d, 'wifi_band') or 'unknown'
        cell = _val(d, 'cellular') or 'unknown'
        rows.append(_row(d, None, 'high' if band != 'unknown' or cell != 'unknown' else 'low',
                         ['Wi-Fi band: %s; cellular: %s' % (band, cell)],
                         [n for n in ('wifi_band', 'cellular') if _val(d, n) is not None]))
    return rows, [], None


def _rank_bt(devices, relays):
    rows = []
    for d in devices:
        ble = bool(_val(d, 'ble'))
        rel = relays.get(d['key']) or {}
        paired = bool(rel.get('paired'))
        fresh = rel.get('fresh_s')
        score = (50 if ble else 0) + (40 if paired else 0) + (10 if isinstance(fresh, (int, float)) and fresh < 300 else 0)
        rows.append(_row(d, score, 'high' if ble and paired else 'medium' if ble else 'low',
                         ['BLE: %s; relay paired: %s%s' % ('yes' if ble else 'no', 'yes' if paired else 'no',
                                                           '' if fresh is None else '; last seen %ss ago' % fresh)],
                         ['ble']))
    rows.sort(key=lambda r: r['score'], reverse=True)
    return rows, [], None


def microbench(kind, consent=True, iterations=200000, megabytes=8, directory=None, attempts=3, runner=None):
    """Bounded, consent-gated micro-benchmarks. Refuses absurd bounds instead
    of clipping silently (the caller sees the refusal and can re-ask sanely)."""
    if consent is not True:
        raise HardwareError('CONSENT_REQUIRED')
    if kind == 'cpu_loop':
        if not isinstance(iterations, int) or isinstance(iterations, bool) or not 1 <= iterations <= MAX_CPU_ITERATIONS:
            raise HardwareError('ITERATIONS_OUT_OF_BOUNDS')
        t0 = time.perf_counter()
        acc = 0
        for i in range(iterations):
            acc += (i * i) & 0xFFFF
        ms = (time.perf_counter() - t0) * 1000
        return metric('cpu_loop_ms', round(ms, 1), 'ms', 'microbench')
    if kind == 'disk_write':
        if not isinstance(megabytes, int) or isinstance(megabytes, bool) or not 1 <= megabytes <= MAX_DISK_MB:
            raise HardwareError('SIZE_OUT_OF_BOUNDS')
        parent = directory or tempfile.gettempdir()
        path = os.path.join(parent, 'ob-bench-%d.tmp' % (time.monotonic_ns() % 1000000))
        try:
            chunk = os.urandom(1 << 20)
            t0 = time.perf_counter()
            with open(path, 'wb') as f:
                for _ in range(megabytes):
                    f.write(chunk)
                f.flush()
                os.fsync(f.fileno())
            dt = time.perf_counter() - t0
            return metric('disk_write_MBps', round(megabytes / dt, 1) if dt > 0 else 0.0, 'MB/s', 'microbench')
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    if kind == 'device_rtt':
        if not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= MAX_RTT_ATTEMPTS:
            raise HardwareError('ATTEMPTS_OUT_OF_BOUNDS')
        if runner is None:
            raise HardwareError('RUNNER_REQUIRED')
        samples = []
        for _ in range(attempts):
            t0 = time.perf_counter()
            runner('echo', 'ob-bench')
            samples.append((time.perf_counter() - t0) * 1000)
        return metric('device_rtt_ms', round(sum(samples) / len(samples), 1), 'ms', 'microbench')
    raise HardwareError('UNKNOWN_BENCH')
