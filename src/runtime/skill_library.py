"""Skill library: new features created by the AI (or suggested, or written by the owner), saved as model-free recipes.

The AI is needed once, to turn a sentence ("when the TV starts playing, dim the living room to 20 %") into a recipe.
After the owner approves it, the recipe runs forever with no AI model at all: on this PC, from a button on a paired
device, on a schedule, or when another device changes state. It can be exported to a file and imported elsewhere.

A recipe is data, never code: a trigger and 1 to 8 typed steps on known devices.

  {'id', 'name', 'description',
   'origin':  {'kind': 'ai' | 'suggestion' | 'owner' | 'import' | 'pack', 'model': str | None, 'request': str | None},
   'trigger': {'kind': 'manual'}
            | {'kind': 'state', 'device': key, 'state': 'playing'}             (edge: fires on the change only)
            | {'kind': 'time',  'at': 'HH:MM', 'days': [0..6]}                  (0 = Monday, local time)
   'steps':   [{'device': key, 'primitive': 'ha_set', 'params': {...}}, ...],
   'approved': None | {'at': epoch, 'fingerprint': sha256 of the canonical trigger + steps},
   'enabled', 'created_at', 'runs': [...]}

Safety, the same as everything else in OpenBridge:
- Steps can only use the primitives in ALLOWED_PRIMITIVES (no free-form command, no PC job, no file transfer).
- Every step goes through the Executor: schema, policy refusals, consent, read-back, receipt. The library adds no power.
- Approval covers this exact recipe: any change to the trigger or the steps voids it (fingerprint mismatch).
- A run stops at the first step that is not VERIFIED; later steps are not attempted.
- Automatic triggers have a cooldown, an hourly cap and a chain guard (a device a recipe just changed cannot
  trigger another recipe for CHAIN_GUARD_S seconds), like device links.
- An imported recipe is never approved, whatever its origin; a bundle signed by this install is reported as trusted,
  any other bundle as foreign.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

FORMAT = 'openbridge-skills/1'
ALLOWED_PRIMITIVES = ('read_facts', 'ha_set', 'ha_command', 'ha_undo', 'tuya_command', 'tuya_setting', 'tv_wake',
                      'tv_sleep', 'device_action', 'pc_open_url', 'pc_wallpaper', 'retro_command')
MAX_STEPS = 8
MAX_RECIPES = 500
DEFAULT_COOLDOWN_S = 30
MAX_PER_HOUR = 20
CHAIN_GUARD_S = 10
KEY = re.compile(r'^[A-Za-z0-9_.:-]{1,64}$')
HHMM = re.compile(r'^([01][0-9]|2[0-3]):[0-5][0-9]$')


class SkillError(ValueError):
    pass


def default_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'skill_library.json'


def canonical(recipe):
    """What the owner approves: the trigger and the steps, nothing else."""
    return json.dumps({'trigger': recipe['trigger'], 'steps': recipe['steps']}, sort_keys=True, separators=(',', ':'))


def fingerprint(recipe):
    return hashlib.sha256(canonical(recipe).encode()).hexdigest()


def validate(recipe):
    """Shape check of a recipe proposal. Raises SkillError with a reason a person can read."""
    if not isinstance(recipe, dict):
        raise SkillError('a skill is an object')
    name = recipe.get('name')
    if not isinstance(name, str) or not 0 < len(name.strip()) <= 60:
        raise SkillError('a skill needs a short name (1-60 characters)')
    if not isinstance(recipe.get('description', ''), str) or len(recipe.get('description', '')) > 300:
        raise SkillError('description: at most 300 characters')
    t = recipe.get('trigger')
    if not isinstance(t, dict) or t.get('kind') not in ('manual', 'state', 'time'):
        raise SkillError('trigger must be manual, state or time')
    if t['kind'] == 'manual' and set(t) != {'kind'}:
        raise SkillError('a manual trigger has no other field')
    if t['kind'] == 'state':
        if set(t) != {'kind', 'device', 'state'} or not KEY.match(str(t['device'])) \
                or not isinstance(t['state'], str) or not 0 < len(t['state']) <= 40:
            raise SkillError('a state trigger is {device, state}, e.g. the TV becoming "playing"')
    if t['kind'] == 'time':
        days = t.get('days')
        if set(t) != {'kind', 'at', 'days'} or not HHMM.match(str(t['at'])) or not isinstance(days, list) \
                or not 0 < len(days) <= 7 or len(set(days)) != len(days) \
                or not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in days):
            raise SkillError('a time trigger is {at: "HH:MM", days: [0..6]} (0 = Monday)')
    steps = recipe.get('steps')
    if not isinstance(steps, list) or not 0 < len(steps) <= MAX_STEPS:
        raise SkillError('a skill has 1 to %d steps' % MAX_STEPS)
    for i, s in enumerate(steps):
        if not isinstance(s, dict) or set(s) != {'device', 'primitive', 'params'}:
            raise SkillError('step %d must be {device, primitive, params}' % (i + 1))
        if s['primitive'] not in ALLOWED_PRIMITIVES:
            raise SkillError('step %d: %s is not allowed in a skill' % (i + 1, s['primitive']))
        if not KEY.match(str(s['device'])):
            raise SkillError('step %d: unknown device reference' % (i + 1))
        if not isinstance(s['params'], dict) or len(json.dumps(s['params'])) > 400:
            raise SkillError('step %d: params must be a small object' % (i + 1))
    if t['kind'] == 'state' and any(s['device'] == t['device'] for s in steps):
        raise SkillError('a state-triggered skill cannot act on its own trigger device (it would loop)')
    return recipe


class Library:
    def __init__(self, executor=None, path=None, persist=True, clock=time.time, key=None, learner=None):
        self.ex, self.clock, self.learner = executor, clock, learner
        self.path = Path(path) if path else default_path()
        self.persist = persist
        self._lock = threading.RLock()
        self.recipes, self.log = {}, []
        self._last_state, self._caused, self._fired_time = {}, {}, {}
        self._key = key
        if persist:
            try:
                doc = json.loads(self.path.read_text(encoding='utf-8'))
                self.recipes = doc.get('recipes', {}) if doc.get('version') == 1 else {}
                self._key = self._key or (bytes.fromhex(doc['key']) if isinstance(doc.get('key'), str) else None)
            except (OSError, ValueError, KeyError):
                self.recipes = {}
        if self._key is None:
            self._key = secrets.token_bytes(32)      # this install's signing key for exported bundles

    def _save(self):
        if self.persist:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'version': 1, 'key': self._key.hex(), 'recipes': self.recipes}, indent=1),
                           encoding='utf-8')
            os.replace(tmp, self.path)

    # ---------- create ----------
    def add(self, proposal, origin_kind='owner', model=None, request=None):
        """Save a proposal (from the AI, a suggestion or the owner). It is NOT approved: it cannot run yet."""
        if origin_kind not in ('ai', 'suggestion', 'owner', 'import', 'pack'):
            raise SkillError('unknown origin')
        validate(proposal)
        with self._lock:
            if len(self.recipes) >= MAX_RECIPES:
                raise SkillError('the library is full (%d skills)' % MAX_RECIPES)
            sid = 'skill-' + secrets.token_hex(4)
            self.recipes[sid] = {
                'id': sid, 'name': proposal['name'].strip(), 'description': proposal.get('description', ''),
                'origin': {'kind': origin_kind, 'model': model, 'request': (request or None) and str(request)[:300]},
                'trigger': json.loads(json.dumps(proposal['trigger'])),
                'steps': json.loads(json.dumps(proposal['steps'])),
                'approved': None, 'enabled': True, 'created_at': self.clock(), 'runs': []}
            self._save()
            return self.recipes[sid]

    def from_suggestion(self, idea):
        """A `create suggest` idea ({title, when: {device, state}, then: {device, action, value?}}) -> saved proposal."""
        when, then = idea['when'], idea['then']
        params = {'action': then['action']}
        if then.get('value') is not None:
            params['value'] = then['value']
        prim = 'ha_set' if then['action'] in ('turn_on', 'turn_off', 'set_brightness', 'set_volume',
                                              'set_temperature') else 'ha_command'
        return self.add({'name': idea.get('title') or 'Suggested link', 'description': idea.get('why', '')[:300],
                         'trigger': {'kind': 'state', 'device': when['device'], 'state': when['state']},
                         'steps': [{'device': then['device'], 'primitive': prim, 'params': params}]}, 'suggestion')

    # ---------- owner decisions ----------
    def _get(self, sid):
        if sid not in self.recipes:
            raise SkillError('unknown skill')
        return self.recipes[sid]

    def approve(self, sid):
        """The owner's approval for exactly this recipe. Editing it later voids the approval."""
        with self._lock:
            r = self._get(sid)
            r['approved'] = {'at': self.clock(), 'fingerprint': fingerprint(r)}
            self._save()
            return r

    def is_approved(self, r):
        a = r.get('approved')
        return bool(a) and hmac.compare_digest(str(a.get('fingerprint', '')), fingerprint(r))

    def set_enabled(self, sid, enabled):
        with self._lock:
            self._get(sid)['enabled'] = bool(enabled)
            self._save()

    def remove(self, sid):
        with self._lock:
            self._get(sid)
            self.recipes.pop(sid)
            self._save()

    # ---------- run (no AI model involved) ----------
    def run(self, sid, actor='owner'):
        """Run an approved recipe now. Stops at the first step that is not VERIFIED."""
        with self._lock:
            r = self._get(sid)
            if not r['enabled']:
                return self._record(r, 'blocked', [], 'disabled', actor)
            if not self.is_approved(r):
                return self._record(r, 'blocked', [], 'not approved (or changed since approval)', actor)
            if self.ex is None:
                raise SkillError('no executor: skills run inside OpenBridge')
            receipts = []
            for step in r['steps']:
                rc = self.ex.execute(step['primitive'], step['device'], step['params'], consent=True)
                receipts.append({'device': step['device'], 'primitive': step['primitive'], 'state': rc['state'],
                                 'verified': rc['verified'], 'transaction_id': rc.get('transaction_id'),
                                 'errors': list(rc.get('errors') or [])[:2]})
                self._caused[step['device']] = self.clock()
                if self.learner is not None:
                    self.learner.observe_receipt(rc, action='%s:%s' % (step['primitive'], step['params'].get('action', '')))
                if not rc['verified']:
                    break
            n_ok = sum(1 for x in receipts if x['verified'])
            result = 'done' if n_ok == len(r['steps']) else ('partial' if n_ok else 'failed')
            return self._record(r, result, receipts, None, actor)

    def _record(self, r, result, receipts, reason, actor):
        entry = {'at': self.clock(), 'result': result, 'actor': actor, 'steps': receipts}
        if reason:
            entry['reason'] = reason
        r['runs'] = (r['runs'] + [entry])[-50:]
        self.log = (self.log + [dict(entry, skill=r['id'])])[-500:]
        self._save()
        return dict(entry, skill=r['id'])

    # ---------- automatic triggers ----------
    def _automatic_ok(self, r, now):
        recent = [x['at'] for x in r['runs'] if x['actor'] != 'owner' and x['result'] != 'blocked']
        if recent and now - recent[-1] < DEFAULT_COOLDOWN_S:
            return 'cooldown'
        if sum(1 for t in recent if now - t < 3600) >= MAX_PER_HOUR:
            return 'hourly cap'
        return None

    def tick(self, states):
        """states: {device_key: state}. Runs approved state-triggered recipes on state changes (edges only)."""
        now = self.clock()
        with self._lock:
            changed = {k: v for k, v in states.items() if self._last_state.get(k) != v}
            first = not self._last_state
            self._last_state.update(states)
            if first:
                return []                     # the first snapshot is a baseline, never a trigger
            out = []
            for r in list(self.recipes.values()):
                t = r['trigger']
                if t['kind'] != 'state' or changed.get(t['device']) != t['state']:
                    continue
                if now - self._caused.get(t['device'], -1e9) < CHAIN_GUARD_S:
                    out.append(self._record(r, 'blocked', [], 'chain guard', 'trigger'))
                    continue
                why = self._automatic_ok(r, now)
                out.append(self._record(r, 'blocked', [], why, 'trigger') if why else self.run(r['id'], actor='trigger'))
            return out

    def due(self, local_time=None):
        """Approved time-triggered recipes due now (call once a minute). local_time: time.struct_time."""
        lt = local_time or time.localtime(self.clock())
        hhmm, day = '%02d:%02d' % (lt.tm_hour, lt.tm_min), lt.tm_wday
        stamp = '%04d-%02d-%02d %s' % (lt.tm_year, lt.tm_mon, lt.tm_mday, hhmm)
        with self._lock:
            ids = [r['id'] for r in self.recipes.values() if r['trigger']['kind'] == 'time'
                   and r['trigger']['at'] == hhmm and day in r['trigger']['days'] and self._fired_time.get(r['id']) != stamp]
            for sid in ids:
                self._fired_time[sid] = stamp     # at most once per scheduled minute
            return ids

    def run_due(self, local_time=None):
        return [self.run(sid, actor='schedule') for sid in self.due(local_time)]

    # ---------- share ----------
    def export(self, ids=None, registry=None):
        """A portable, signed bundle. Approvals are never exported. registry: device descriptions for remapping."""
        with self._lock:
            chosen = [self._get(i) for i in ids] if ids else list(self.recipes.values())
            skills = [{k: json.loads(json.dumps(r[k])) for k in ('name', 'description', 'origin', 'trigger', 'steps')}
                      for r in chosen]
        devices = {}
        for s in skills:
            keys = [st['device'] for st in s['steps']] + ([s['trigger']['device']] if s['trigger']['kind'] == 'state' else [])
            for k in keys:
                d = (getattr(registry, 'devices', {}) or {}).get(k) if registry is not None else None
                devices[k] = {'category': (d or {}).get('category'), 'label': (d or {}).get('label')}
        body = {'format': FORMAT, 'exported_at': int(self.clock()), 'skills': skills, 'devices': devices}
        body['signature'] = hmac.new(self._key, json.dumps(body, sort_keys=True, separators=(',', ':')).encode(),
                                     hashlib.sha256).hexdigest()
        return body

    def import_bundle(self, bundle, device_map=None):
        """Import a bundle. Every imported skill starts unapproved. device_map: {key in bundle: key here}.

        Returns {'trusted': bool, 'imported': [ids], 'unmapped_devices': [...] }. A skill whose devices are not
        known here can still be imported; it simply cannot run until the owner maps them and approves it."""
        if not isinstance(bundle, dict) or bundle.get('format') != FORMAT or not isinstance(bundle.get('skills'), list):
            raise SkillError('not an OpenBridge skills file')
        body = {k: v for k, v in bundle.items() if k != 'signature'}
        expected = hmac.new(self._key, json.dumps(body, sort_keys=True, separators=(',', ':')).encode(),
                            hashlib.sha256).hexdigest()
        trusted = hmac.compare_digest(expected, str(bundle.get('signature', '')))
        mapping = dict(device_map or {})
        imported, unmapped = [], set()
        for s in bundle['skills'][:MAX_RECIPES]:
            s = json.loads(json.dumps(s))
            for st in s.get('steps', []):
                st['device'] = mapping.get(st['device'], st['device'])
            if isinstance(s.get('trigger'), dict) and s['trigger'].get('kind') == 'state':
                s['trigger']['device'] = mapping.get(s['trigger']['device'], s['trigger']['device'])
            origin = s.get('origin') or {}
            r = self.add(s, 'import', model=origin.get('model'), request=origin.get('request'))
            imported.append(r['id'])
            for k in [st['device'] for st in r['steps']] + ([r['trigger']['device']] if r['trigger']['kind'] == 'state' else []):
                if k not in mapping.values() and k in (bundle.get('devices') or {}):
                    unmapped.add(k)
        return {'trusted': trusted, 'imported': imported, 'unmapped_devices': sorted(unmapped)}

    # ---------- views ----------
    def summary(self):
        return [{'id': r['id'], 'name': r['name'], 'trigger': r['trigger']['kind'], 'steps': len(r['steps']),
                 'approved': self.is_approved(r), 'enabled': r['enabled'], 'origin': r['origin']['kind'],
                 'runs': len(r['runs']), 'last': (r['runs'][-1]['result'] if r['runs'] else None)}
                for r in self.recipes.values()]

    def buttons(self):
        """Approved manual recipes, as {control_id, label} pairs a paired device can show as buttons."""
        return [{'control_id': 'skill-%s' % r['id'][6:], 'label': r['name'][:40]} for r in self.recipes.values()
                if r['trigger']['kind'] == 'manual' and r['enabled'] and self.is_approved(r)]
