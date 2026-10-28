"""B3: owner-authorized remote controls on paired Companions (e.g. a Galaxy Watch7 controlling the TV).

Trust model:
- The owner creates each control on the PC (CSRF + consent), choosing skill, target and exact params.
- The Companion only receives a control id and a label. A press sends back that id plus a fresh request id over the
  signed relay channel, which the PC polls; nothing listens on the PC for the device.
- The PC resolves the control to its owner-set skill, target and params, then routes it through B2. The actor is
  `relay:<relay_id>`, the invocation id is derived from the request id (a re-sent press is deduplicated), the
  binding covers the selected route, and the outcome is the Executor receipt.
- The standing grant plus one physical press on the paired device stands for consent to exactly one invocation.
- The verified outcome text is signed back to the device. Revoking a control or the relay stops it immediately.
"""
import hashlib
import json
import threading
import time

from src.fabric import relay as fabric_relay

POLL_S = 1.5
MAX_PER_POLL = 8
MIN_INTERVAL_S = 0.5           # per control: one invocation per half second at most
BURST, BURST_WINDOW_S = 3, 10.0   # more presses than this in the window: the control is suspended until re-granted


class RemoteControlError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class RemoteControls:
    def __init__(self, server, clock=time.time):
        self.server, self.clock = server, clock
        self.grants = {}         # relay_id -> {control_id: {label, skill_id, target, params}}
        self._last = {}          # (relay_id, control_id) -> last invocation time
        self._recent = {}        # (relay_id, control_id) -> recent request times
        self.suspended = set()   # (relay_id, control_id) suspended after an unusual burst (hardware run 28 Oct)
        self.history = []        # bounded outcome log (no free text from the device)
        self._lock = threading.Lock()
        self._thread = None

    # ---------- owner side ----------
    def _relay(self, rid):
        r = self.server.relays.relays.get(rid)
        if r is None:
            raise RemoteControlError(404, 'Unknown relay; pair the Companion first')
        if 'remote_controls' not in r.get('capabilities', ()):
            raise RemoteControlError(409, 'This Companion version has no remote controls; install the current Companion')
        return r

    def _send(self, rid, op, params=None):
        r = self.server.relays.relays[rid]
        msg = fabric_relay.command(r['key'], rid, op, params)
        try:
            return fabric_relay.verify(r['key'], r['send'](r, msg), r['seen']).get('params', {})
        except (OSError, TimeoutError) as error:
            r['online'] = False
            raise fabric_relay.RelayError(f'Relay unreachable: {type(error).__name__}') from None

    def set_controls(self, body):
        from src.runtime.api_v2 import router
        from src.runtime.routing import SKILLS, RouteError
        if not isinstance(body, dict) or set(body) - {'relay_id', 'controls', 'consent'} or body.get('consent') is not True:
            raise RemoteControlError(400, 'relay_id, controls and consent: true are required')
        rid = body.get('relay_id')
        self._relay(rid)
        items = body.get('controls')
        if not isinstance(items, list) or len(items) > fabric_relay.MAX_CONTROLS:
            raise RemoteControlError(400, f'At most {fabric_relay.MAX_CONTROLS} controls')
        out = {}
        for c in items:
            if not isinstance(c, dict) or set(c) - {'label', 'skill_id', 'target', 'params'}:
                raise RemoteControlError(400, 'Each control is {label, skill_id, target?, params}')
            label, skill, target, params = c.get('label'), c.get('skill_id'), c.get('target'), c.get('params') or {}
            if not isinstance(label, str) or not 0 < len(label) <= 40:
                raise RemoteControlError(400, 'Label must be 1-40 characters')
            if skill not in SKILLS:
                raise RemoteControlError(400, 'Unknown skill')
            if SKILLS[skill]['targeted'] and not isinstance(target, str):
                raise RemoteControlError(400, 'This skill needs a target device')
            try:
                router(self.server)._validate_input(skill, params)
            except RouteError as e:
                raise RemoteControlError(400, str(e)) from None
            cid = 'ctl-' + hashlib.sha256(json.dumps([rid, skill, target, params, label], sort_keys=True).encode()).hexdigest()[:12]
            out[cid] = {'label': label, 'skill_id': skill, 'target': target, 'params': params}
        self._send(rid, 'set_controls', {'controls': [{'control_id': k, 'label': v['label']} for k, v in out.items()]})
        with self._lock:
            self.suspended = {k for k in self.suspended if k[0] != rid}      # an explicit re-grant re-enables
            self._recent = {k: v for k, v in self._recent.items() if k[0] != rid}
            if out:
                self.grants[rid] = out
            else:
                self.grants.pop(rid, None)
        self._ex().emit('remote_controls', relay_id=rid, count=len(out))
        self._ensure_thread()
        return self.state()

    def state(self):
        with self._lock:
            return {'controls': [{'relay_id': rid, 'control_id': cid, **g} for rid, cs in self.grants.items() for cid, g in cs.items()],
                    'history': list(self.history[-20:]), 'suspended': sorted(f'{a}/{b}' for a, b in self.suspended)}

    # ---------- device side ----------
    def _ex(self):
        from src.runtime.api_v2 import executor
        return executor(self.server)

    def _ensure_thread(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name='openbridge-remote-controls', daemon=True)
            self._thread.start()

    def _loop(self):
        while True:
            with self._lock:
                if not self.grants:
                    self._thread = None
                    return
            try:
                self.poll_once()
            except Exception:
                pass
            time.sleep(POLL_S)

    def poll_once(self):
        with self._lock:
            grants = {rid: dict(cs) for rid, cs in self.grants.items()}
        done = 0
        for rid, controls in grants.items():
            r = self.server.relays.relays.get(rid)
            if r is None:                                   # relay revoked: its controls die with it
                with self._lock:
                    self.grants.pop(rid, None)
                continue
            if not r.get('online') or r.get('busy'):
                continue
            try:
                reqs = fabric_relay.validate_requests(self._send(rid, 'get_requests'), set(controls))
            except fabric_relay.RelayError:
                continue
            for req in reqs[:MAX_PER_POLL - done]:
                self.process(rid, controls[req['control_id']], req)
                done += 1
        return done

    def process(self, rid, grant, req):
        from src.runtime.api_v2 import router
        from src.runtime.routing import RouteError
        actor = f'relay:{rid}'
        key = (rid, req['control_id'])
        now = self.clock()
        recent = [x for x in self._recent.get(key, []) if now - x < BURST_WINDOW_S] + [now]
        self._recent[key] = recent
        if key not in self.suspended and len(recent) > BURST:
            self.suspended.add(key)
            self._ex().emit('remote_control_suspended', relay_id=rid, control_id=req['control_id'], presses=len(recent))
        if key in self.suspended:
            outcome, text = 'SUSPENDED', f"{grant['label']}: paused (unusual repeated presses); re-enable on the PC"
        elif (actor, 'inv-' + req['request_id']) in router(self.server).completed:
            outcome, text = 'DUPLICATE', f"{grant['label']}: already done"     # a re-sent press: never dispatched twice
        elif now - self._last.get(key, 0) < MIN_INTERVAL_S:
            outcome, text = 'BLOCKED', 'Too fast; press again'
        else:
            self._last[key] = now
            rt = router(self.server)
            try:
                doc = rt.skill_routes(grant['skill_id'], grant['target'])
                if not doc['selected_route_id']:
                    reasons = sorted({r['reason'] for r in doc['routes'] if r['reason']}) or ['no route']
                    raise RouteError(409, 'NO_ROUTE', 'Unavailable: ' + ', '.join(reasons).replace('_', ' '))
                lease = rt.arm({'skill_id': grant['skill_id'], 'target': grant['target'], 'route_id': doc['selected_route_id'],
                                'params': grant['params'], 'consent': True}, actor=actor, invocation_id='inv-' + req['request_id'])
                body = {k: lease[k] for k in ('invocation_id', 'route_id', 'lease_id', 'graph_revision')}
                body.update(skill_id=grant['skill_id'], params=grant['params'], consent=True)
                if grant['target']:
                    body['target'] = grant['target']
                rc = rt.invoke(body, actor=actor)
                outcome = rc.get('state', 'FAILED')
                text = f"{grant['label']}: " + {'VERIFIED': 'done, verified', 'EXECUTED': 'done', 'REVERTED': 'restored'}.get(outcome, outcome.lower().replace('_', ' '))
                after = rc.get('after')
                if outcome == 'VERIFIED' and isinstance(after, int):
                    text += f' ({after})'
            except RouteError as e:
                outcome, text = 'BLOCKED', f"{grant['label']}: {e}"[:80]
        entry = {'at': now, 'relay_id': rid, 'control_id': req['control_id'], 'request_id': req['request_id'], 'skill_id': grant['skill_id'], 'state': outcome}
        with self._lock:
            self.history.append(entry)
            del self.history[:-100]
        self._ex().emit('remote_request', **{k: v for k, v in entry.items() if k != 'at'})
        try:
            self._send(rid, 'report_result', {'request_id': req['request_id'], 'state': outcome, 'text': text[:80]})
        except fabric_relay.RelayError:
            pass
        return entry
