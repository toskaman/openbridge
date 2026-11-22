"""Device learning: OpenBridge learns what each device really does from its own receipts.

Every executed primitive leaves a receipt (state, verified, before/after, timing). The learner folds them into a
per-device profile: which actions were tried, how often they were verified, how long they take, which states and
values the device was seen in. Profiles feed two things:
- reliability: an action counts as *proven* only after verified runs (default: 3) with a high success rate;
- creation: suggest_recipes() proposes new cross-device features built only from proven capabilities.

Nothing here acts on a device. Profiles are local JSON (no identifiers beyond the pseudonymous device key).
"""
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

MIN_PROVEN_RUNS = 3
MIN_SUCCESS = 0.8
MAX_SAMPLES = 200


def default_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'device_learning.json'


def _seconds(started, finished):
    try:
        return max(0.0, (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds())
    except (TypeError, ValueError):
        return None


class Learner:
    def __init__(self, path=None, persist=True):
        self.path = Path(path) if path else default_path()
        self.persist = persist
        self._lock = threading.Lock()
        self.devices = {}
        if persist:
            try:
                self.devices = json.loads(self.path.read_text(encoding='utf-8')).get('devices', {})
            except (OSError, ValueError):
                self.devices = {}

    # ---------- ingest ----------
    def observe_receipt(self, receipt, category='', action=None):
        """Fold one primitive receipt (dict as returned by Executor.execute) into the device profile."""
        key = receipt.get('device_key')
        if not key:
            return
        action = action or receipt.get('primitive_id')
        state = receipt.get('state')
        with self._lock:
            dev = self.devices.setdefault(key, {'category': category, 'actions': {}, 'states_seen': {}, 'values': {}})
            if category:
                dev['category'] = category
            a = dev['actions'].setdefault(action, {'runs': 0, 'verified': 0, 'blocked': 0, 'failed': 0, 'latency_s': []})
            a['runs'] += 1
            if receipt.get('verified'):
                a['verified'] += 1
            elif state == 'BLOCKED':
                a['blocked'] += 1
            elif state in ('FAILED', 'UNKNOWN_TIMEOUT', 'PARTIAL'):
                a['failed'] += 1
            lat = _seconds(receipt.get('started_at'), receipt.get('finished_at'))
            if lat is not None and state != 'BLOCKED':
                a['latency_s'] = (a['latency_s'] + [round(lat, 3)])[-MAX_SAMPLES:]
            for v in (receipt.get('before'), receipt.get('after')):
                if isinstance(v, str) and len(v) <= 40:
                    dev['states_seen'][v] = dev['states_seen'].get(v, 0) + 1
            dev['last_seen'] = time.time()
        self._save()

    def observe_value(self, key, name, value):
        """Record a numeric reading (battery, temperature, volume...) to learn the device's real range."""
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return
        with self._lock:
            dev = self.devices.setdefault(key, {'category': '', 'actions': {}, 'states_seen': {}, 'values': {}})
            r = dev['values'].setdefault(name, {'min': value, 'max': value, 'n': 0})
            r['min'], r['max'], r['n'] = min(r['min'], value), max(r['max'], value), r['n'] + 1
        self._save()

    def _save(self):
        if not self.persist:
            return
        with self._lock:
            data = json.dumps({'version': 1, 'devices': self.devices}, indent=1)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(data, encoding='utf-8')
        os.replace(tmp, self.path)

    # ---------- read ----------
    def action_profile(self, key, action):
        a = (self.devices.get(key) or {}).get('actions', {}).get(action)
        if not a:
            return None
        attempted = a['runs'] - a['blocked']
        lat = sorted(a['latency_s'])
        return {'runs': a['runs'], 'verified': a['verified'], 'blocked': a['blocked'], 'failed': a['failed'],
                'success_rate': round(a['verified'] / attempted, 3) if attempted else None,
                'latency_p50_s': lat[len(lat) // 2] if lat else None,
                'latency_p95_s': lat[max(0, int(len(lat) * 0.95) - 1)] if lat else None,
                'proven': attempted >= MIN_PROVEN_RUNS and a['verified'] / attempted >= MIN_SUCCESS}

    def proven(self, key, action):
        p = self.action_profile(key, action)
        return bool(p and p['proven'])

    def report(self):
        out = []
        for key, dev in sorted(self.devices.items()):
            acts = {a: self.action_profile(key, a) for a in sorted(dev['actions'])}
            out.append({'device': key, 'category': dev.get('category', ''), 'actions': acts,
                        'states_seen': dict(sorted(dev['states_seen'].items(), key=lambda kv: -kv[1])[:10]),
                        'values': dev['values'],
                        'reliability': round(sum(p['verified'] for p in acts.values()) /
                                             max(1, sum(p['runs'] - p['blocked'] for p in acts.values())), 3)})
        return {'devices': out, 'proven_actions': sum(1 for d in out for p in d['actions'].values() if p['proven'])}


# ---------- creation: new cross-device features from proven capabilities ----------
# (trigger category, trigger state, action category, primitive, params, title, why)
RECIPES = (
    ('media_player', 'playing', 'light', 'ha_set', {'action': 'set_brightness', 'value': 20}, 'Cinema mode',
     'When something starts playing, dim the lights to 20 %.'),
    ('media_player', 'paused', 'light', 'ha_set', {'action': 'set_brightness', 'value': 70}, 'Intermission',
     'When playback pauses, bring the lights back up.'),
    ('robot', 'cleaning', 'media_player', 'ha_command', {'action': 'pause'}, 'Quiet while cleaning',
     'Pause the music while the robot vacuum is cleaning.'),
    ('vacuum', 'cleaning', 'media_player', 'ha_command', {'action': 'pause'}, 'Quiet while cleaning',
     'Pause the music while the robot vacuum is cleaning.'),
    ('cover', 'closed', 'light', 'ha_set', {'action': 'turn_on'}, 'Blinds closed, lights on',
     'When the blinds close, switch the lights on.'),
    ('lock', 'locked', 'light', 'ha_set', {'action': 'turn_off'}, 'Leaving home',
     'When the front door locks, switch the lights off.'),
    ('lock', 'locked', 'plug', 'ha_set', {'action': 'turn_off'}, 'Leaving home, plugs off',
     'When the front door locks, switch the plug off.'),
    ('thermostat', 'off', 'fan', 'ha_set', {'action': 'turn_off'}, 'Heating off, fan off',
     'When the thermostat switches off, stop the fan too.'),
    ('light', 'off', 'media_player', 'ha_command', {'action': 'pause'}, 'Lights out',
     'When this light goes off, pause the media player.'),
)


def suggest_recipes(registry, learner, limit=12):
    """Cross-device features made only of capabilities this home has proven (verified runs)."""
    devices = registry.devices
    by_cat = {}
    for key, dev in devices.items():
        by_cat.setdefault(dev['category'], []).append(key)
    ideas = []
    for t_cat, t_state, a_cat, prim, params, title, why in RECIPES:
        action_name = params.get('action', prim)
        for t_key in by_cat.get(t_cat, []):
            seen = (learner.devices.get(t_key) or {}).get('states_seen', {})
            for a_key in by_cat.get(a_cat, []):
                if a_key == t_key:
                    continue
                proven = learner.proven(a_key, '%s:%s' % (prim, action_name)) or learner.proven(a_key, prim)
                if not proven:
                    continue
                ideas.append({'title': title, 'why': why,
                              'when': {'device': t_key, 'label': devices[t_key]['label'], 'state': t_state,
                                       'state_observed': t_state in seen},
                              'then': {'device': a_key, 'label': devices[a_key]['label'], 'primitive': prim, 'params': params},
                              'confidence': 'high' if t_state in seen else 'medium'})
    ideas.sort(key=lambda i: (i['confidence'] != 'high', i['title']))
    return ideas[:limit]
