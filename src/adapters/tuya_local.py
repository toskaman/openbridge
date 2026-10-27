"""Tuya robot vacuum over the LOCAL protocol (3.4), owner-linked.

Credentials: the owner's device id + local key obtained from the owner's own Tuya IoT Cloud project (official
"link app account" flow, `python -m dev.tuya_link`). They are stored outside the repo in
%LOCALAPPDATA%/OpenBridge/tuya.json and never returned by any API. No key is ever extracted from the app, its
cache or network traffic.

Scope: read status DPs; one reversible setting at a time from a small allowlist (suction power, voice volume),
with read-before, write, independent read-back and exact Undo. Everything that moves the robot or starts/stops a
job (power, mode, direction, seek, dust collection, consumable resets) is BLOCKED: a moving robot has no exact
undo. Optional dependency: tinytuya (MIT), like bleak for PC Bluetooth.
"""
import json
import os
import time
from pathlib import Path

READ_DPS = {'5': 'vacuum_status', '6': 'battery_level', '7': 'main_brush_life', '8': 'side_brush_life', '9': 'filter_life',
            '14': 'suction', '16': 'clean_time_min', '17': 'clean_area_m2', '18': 'fault_code', '20': 'water_level',
            '24': 'work_mode', '104': 'volume'}
UNITS = {'battery_level': '%', 'main_brush_life': '%', 'side_brush_life': '%', 'filter_life': '%', 'clean_time_min': 'min', 'clean_area_m2': 'm²'}
WRITABLE = {'suction': ('14', ('gentle', 'normal', 'strong')), 'volume': ('104', ('vol_mute', 'vol_normal', 'vol_max'))}
BLOCKED_DPS = {'2': 'power', '3': 'mode', '4': 'direction', '11': 'reset', '12': 'reset', '13': 'reset', '101': 'seek', '102': 'dust_collection'}
_sleep = time.sleep
BUSY = ('smart_clean', 'cleaning', 'mop_clean', 'wall_clean', 'spot_clean', 'goto_charge')


class TuyaBlocked(PermissionError):
    pass


def owner_link(path=None):
    p = Path(path or Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'tuya.json')
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not all(isinstance(d.get(k), str) and d[k] for k in ('device_id', 'ip', 'local_key')) or len(d['local_key']) != 16:
        return None
    return {'device_id': d['device_id'], 'ip': d['ip'], 'local_key': d['local_key'], 'version': str(d.get('version', '3.4'))}


class TuyaVacuum:
    def __init__(self, link, device_factory=None):
        if not link:
            raise TuyaBlocked('Tuya device not linked: run python -m dev.tuya_link with your Tuya IoT project')
        self.device_id, self.ip = link['device_id'], link['ip']
        if device_factory is None:
            import tinytuya
            device_factory = lambda: tinytuya.Device(link['device_id'], link['ip'], link['local_key'], version=float(link['version']))
        self._factory = device_factory
        self._before = {}

    def _dev(self):
        d = self._factory()
        try:
            d.set_socketTimeout(3); d.set_socketRetryLimit(1)
        except AttributeError:
            pass
        return d

    def dps(self):
        r = self._dev().status()
        if not isinstance(r, dict) or 'dps' not in r:
            raise OSError('Tuya device did not answer: ' + str((r or {}).get('Error', 'no status'))[:60])
        return {str(k): v for k, v in r['dps'].items()}

    def facts(self):
        d = self.dps()
        out = [{'name': n, 'value': d[k], 'unit': UNITS.get(n, '')} for k, n in READ_DPS.items() if k in d]
        return out

    def set_reversible(self, setting, value):
        if setting not in WRITABLE:
            raise TuyaBlocked(f'{setting} is not an allowlisted reversible setting')
        dp, allowed = WRITABLE[setting]
        if value not in allowed:
            raise TuyaBlocked('value not allowed')
        before = self.dps()
        if before.get('5') in BUSY:
            raise TuyaBlocked('robot is working; settings are changed only when idle or docked')
        if dp not in before:
            raise TuyaBlocked('setting not reported by this device')
        self._before[setting] = before[dp]
        self._dev().set_value(int(dp), value)
        _sleep(1.0)
        after = self.dps().get(dp)
        return {'setting': setting, 'before': before[dp], 'after': after, 'verified': after == value}

    def undo(self, setting):
        if setting not in self._before:
            raise TuyaBlocked('nothing to undo')
        dp, _ = WRITABLE[setting]
        target = self._before[setting]
        self._dev().set_value(int(dp), target)
        _sleep(1.0)
        now = self.dps().get(dp)
        if now == target:
            self._before.pop(setting)
        return {'setting': setting, 'restored': now, 'exact': now == target}


def refuse_dp(dp):
    """Any request for a movement/job DP is refused before a byte is sent."""
    if str(dp) in BLOCKED_DPS:
        raise TuyaBlocked(f'{BLOCKED_DPS[str(dp)]} moves the robot or starts a job; blocked (no exact undo)')
    raise TuyaBlocked('unknown DP')
