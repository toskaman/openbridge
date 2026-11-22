"""Device links: devices talk to each other. "When <device> becomes <state>, do <action> on <other device>."

A link is a standing instruction the owner approves once, for that exact pair, state and action. It never widens:
- the action is a typed primitive run through the same Executor as the app (schema, policy, read-back, receipt);
- the owner's approval is recorded on the link; an unapproved or disabled link never fires;
- loop guards: a link fires on the state *change* only (edge, not level), has a cooldown, a per-hour cap, and an
  action caused by a link cannot itself trigger another link within the guard window (no chains, no ping-pong);
- every firing, refusal and skip is logged with its receipt.

The engine is passive: call tick(states) with the current states (from discovery, Home Assistant, a watcher...).
"""
import json
import os
import secrets
import threading
import time
from pathlib import Path

ALLOWED_PRIMITIVES = ('ha_set', 'ha_command', 'tuya_command', 'tv_wake', 'tv_sleep')
DEFAULT_COOLDOWN_S = 30
DEFAULT_MAX_PER_HOUR = 20
CHAIN_GUARD_S = 10


class LinkError(ValueError):
    pass


def default_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'device_links.json'


class Links:
    def __init__(self, executor, path=None, persist=True, clock=time.time, learner=None):
        self.ex, self.clock, self.learner = executor, clock, learner
        self.path = Path(path) if path else default_path()
        self.persist = persist
        self._lock = threading.Lock()
        self.links, self.log = {}, []
        self._last_state, self._caused = {}, {}
        if persist:
            try:
                self.links = json.loads(self.path.read_text(encoding='utf-8')).get('links', {})
            except (OSError, ValueError):
                self.links = {}

    def _save(self):
        if self.persist:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'version': 1, 'links': self.links}, indent=1), encoding='utf-8')
            os.replace(tmp, self.path)

    # ---------- owner side ----------
    def add(self, when_device, when_state, then_device, primitive, params, title='', cooldown_s=DEFAULT_COOLDOWN_S,
            max_per_hour=DEFAULT_MAX_PER_HOUR):
        if primitive not in ALLOWED_PRIMITIVES:
            raise LinkError('links can only run: ' + ', '.join(ALLOWED_PRIMITIVES))
        if when_device == then_device:
            raise LinkError('a link connects two different devices')
        if not isinstance(when_state, str) or not 0 < len(when_state) <= 40:
            raise LinkError('trigger state must be a short state name, e.g. playing, locked, cleaning')
        if not isinstance(params, dict) or len(params) > 4:
            raise LinkError('params must be a small object')
        if not (5 <= int(cooldown_s) <= 86400) or not (1 <= int(max_per_hour) <= 120):
            raise LinkError('cooldown 5 s..1 day, at most 120 runs per hour')
        lid = 'link-' + secrets.token_hex(4)
        self.links[lid] = {'id': lid, 'title': str(title)[:60], 'when': {'device': when_device, 'state': when_state},
                           'then': {'device': then_device, 'primitive': primitive, 'params': params},
                           'approved': False, 'enabled': True, 'cooldown_s': int(cooldown_s), 'max_per_hour': int(max_per_hour),
                           'fired': []}
        self._save()
        return self.links[lid]

    def approve(self, lid):
        """The owner's one-time approval for exactly this link (pair, state, action, params)."""
        self._get(lid)['approved'] = True
        self._save()
        return self.links[lid]

    def disable(self, lid):
        self._get(lid)['enabled'] = False
        self._save()

    def remove(self, lid):
        self._get(lid)
        self.links.pop(lid)
        self._save()

    def _get(self, lid):
        if lid not in self.links:
            raise LinkError('unknown link')
        return self.links[lid]

    # ---------- engine ----------
    def tick(self, states):
        """states: {device_key: state}. Fires approved links on state changes. Returns the events of this tick."""
        now = self.clock()
        events = []
        with self._lock:
            changed = {k: v for k, v in states.items() if self._last_state.get(k) != v}
            first = not self._last_state
            self._last_state.update(states)
        if first:
            return events          # the first snapshot is a baseline, never a trigger
        for lid, link in list(self.links.items()):
            w = link['when']
            if changed.get(w['device']) != w['state']:
                continue
            ev = {'link': lid, 'at': now, 'trigger': w}
            if not link['enabled']:
                ev['result'] = 'SKIPPED_DISABLED'
            elif not link['approved']:
                ev['result'] = 'SKIPPED_NOT_APPROVED'
            elif now - self._caused.get(w['device'], -1e9) < CHAIN_GUARD_S:
                ev['result'] = 'SKIPPED_CHAIN_GUARD'
            elif link['fired'] and now - link['fired'][-1] < link['cooldown_s']:
                ev['result'] = 'SKIPPED_COOLDOWN'
            elif sum(1 for t in link['fired'] if now - t < 3600) >= link['max_per_hour']:
                ev['result'] = 'SKIPPED_HOURLY_CAP'
            else:
                t = link['then']
                r = self.ex.execute(t['primitive'], t['device'], t['params'], consent=True)
                link['fired'] = (link['fired'] + [now])[-200:]
                self._caused[t['device']] = now
                ev.update(result=r['state'], verified=r['verified'], transaction_id=r['transaction_id'], errors=r['errors'][:2])
                if self.learner is not None:
                    self.learner.observe_receipt(r, action='%s:%s' % (t['primitive'], t['params'].get('action', '')))
            events.append(ev)
        self.log = (self.log + events)[-500:]
        if events:
            self._save()
        return events
