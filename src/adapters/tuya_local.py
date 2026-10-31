"""Tuya robot vacuum over the LOCAL protocol (3.4), owner-linked.

Credentials: the owner's device id + local key obtained from the owner's own Tuya IoT Cloud project (official
"link app account" flow, `python -m dev.tuya_link`). They are stored outside the repo in
%LOCALAPPDATA%/OpenBridge/tuya.json and never returned by any API. No key is ever extracted from the app, its
cache or network traffic.

Scope: read status DPs; reversible settings (suction, volume) with read-back and exact Undo; and, by owner
decision, full control of the robot (start/pause, mode, dock, manual moves, find-my-robot beep, dust emptying,
consumable resets, water level, work mode). Those commands are IRREVERSIBLE (a robot that moved cannot be put back):
each needs owner consent, is typed (no raw DP numbers from clients), read back when the device reports it, and manual
moves always end with an automatic `stop` after at most 3 s. Optional dependency: tinytuya (MIT).
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
        if setting in self._before:
            raise TuyaBlocked('setting already has a pending restore; undo it before changing again')
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


# Typed commands -> (dp, allowed values or None for bool True). Irreversible; owner consent per command.
COMMANDS = {
    'start': ('2', (True,)), 'pause': ('2', (False,)),
    'mode': ('3', ('smart', 'wall_follow', 'spiral', 'bow', 'partial_bow', 'mop', 'random', 'chargego')),
    'dock': ('3', ('chargego',)),
    'move': ('4', ('forward', 'backward', 'turn_left', 'turn_right', 'stop')),
    'seek': ('101', (True,)), 'empty_dust': ('102', (True,)),
    'reset_side_brush': ('11', (True,)), 'reset_main_brush': ('12', (True,)), 'reset_filter': ('13', (True,)),
    'water_level': ('20', ('closed', 'low', 'middle', 'high')), 'work_mode': ('24', ('both_work', 'only_sweep', 'only_mop')),
}
EXPECT_STATUS = {'start': None, 'pause': ('paused', 'standby'), 'dock': ('goto_charge', 'charging', 'charge_done')}
MAX_MOVE_S = 3.0


def refuse_dp(dp):
    """Raw DP numbers are never accepted from clients: only the typed COMMANDS / WRITABLE names."""
    raise TuyaBlocked('raw DP writes are not accepted; use a typed command')


def command(vac, name, value=None, move_s=1.0):
    if name not in COMMANDS:
        raise TuyaBlocked('unknown command')
    dp, allowed = COMMANDS[name]
    v = allowed[0] if len(allowed) == 1 and value is None else value
    if v not in allowed:
        raise TuyaBlocked('value not allowed for this command')
    before = vac.dps()
    dev = vac._dev()
    dev.set_value(int(dp), v)
    stopped = None
    if name == 'move' and v != 'stop':
        _sleep(max(0.2, min(float(move_s), MAX_MOVE_S)))
        dev.set_value(4, 'stop'); stopped = True               # always end a manual move
    _sleep(1.5)
    after = vac.dps()
    if name in EXPECT_STATUS and EXPECT_STATUS[name]:
        verified = after.get('5') in EXPECT_STATUS[name]
    elif name == 'start':
        verified = after.get('2') is True or after.get('5') in BUSY
    elif dp in after and not isinstance(v, bool) and name != 'move':
        verified = after.get(dp) == v
    else:
        verified = None                                     # momentary command: device reports no lasting state
    return {'command': name, 'value': v, 'status_before': before.get('5'), 'status_after': after.get('5'),
            'auto_stopped': stopped, 'verified': verified, 'reversible': False}
