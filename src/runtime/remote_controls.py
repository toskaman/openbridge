"""B3: owner-authorized remote controls on paired Companions (e.g. a Galaxy Watch7 controlling the TV).

Trust model:
- The owner creates each control on the PC (CSRF + consent), choosing skill, target and exact params.
- The Companion only receives a control id and a label. A press sends back that id plus a fresh request id over the
  signed relay channel, which the PC polls; nothing listens on the PC for the device.
- The PC resolves the control to its owner-set skill, target and params, then routes it through B2. The actor is
  `relay:<relay_id>`, the invocation id is derived from the request id (a re-sent press is deduplicated), the
  binding covers the selected route, and the outcome is the Executor receipt.
- The standing grant plus one physical press on the paired device stands for consent to exactly one invocation.
- The verified outcome text is signed back to the device. Revoking a control or the relay stops new dispatch admissions. An already admitted operation may finish.

Delivery is at-most-once: get_requests drains the device queue. A press lost between drain and dispatch (e.g. PC
crash) is never retried automatically; the owner presses again. Failed or uncertain outcomes are never reissued.

Point-of-dispatch revalidation (Codex review of PR #54):
- Every control id embeds a grant generation, so a re-grant yields new ids and requests for old ids are dropped.
- Each grant is bound to the relay key fingerprint at grant time; re-pairing invalidates it.
- At dispatch, under the lock, the current grant generation, relay key and open state are rechecked.
- A request whose device timestamp is older or newer than REQUEST_TTL_S is EXPIRED (never executed).
- close() stops the poller and new dispatch admissions; an already admitted operation may finish.

Evidence chain: each history entry records request_id, the device's monotonic seq, pressed_at, gesture and coarse
touch info (tool type, pressure, size), invocation_id and transaction_id. That data is what isolates phantom touches
from a request loop (open defect: 2 taps -> 16 executions, 28 Oct).
"""
import hashlib
import json
import threading
import time

from src.fabric import relay as fabric_relay

POLL_S = 1.5
MAX_PER_POLL = 8
MIN_INTERVAL_S = 0.5              # per control: one invocation per half second at most
BURST, BURST_WINDOW_S = 3, 10.0   # more presses than this in the window: the control is suspended until re-granted
REQUEST_TTL_S = 30                # a press older (or further in the future, clock skew) than this is never executed


class RemoteControlError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _key_fp(key):
    return hashlib.sha256(b'openbridge-relay-key' + bytes(key)).hexdigest()[:16]


class RemoteControls:
    def __init__(self, server, clock=time.time):
        self.server, self.clock = server, clock
        self.grants = {}         # relay_id -> {control_id: {label, skill_id, target, params, generation, key_fp}}
        self.generation = 0
        self._grant_versions = {}   # latest accepted owner update per relay
        self._last = {}          # (relay_id, control_id) -> last invocation time
        self._recent = {}        # (relay_id, control_id) -> recent request times
        self.suspended = set()   # (relay_id, control_id) suspended after an unusual burst
        self.history = []        # bounded outcome log (no free text from the device)
        self.layouts = {}        # relay_id -> {revision, acked, display: {control_id: {kind, label, value, source}}}
        self._lock = threading.Lock()
        self._grant_send_lock = threading.Lock()  # order Companion updates through acknowledgement
        self._stop = threading.Event()
        self._thread = None
        self.closed = False

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
        if self.closed:
            raise RemoteControlError(503, 'Remote controls are shut down')
        if not isinstance(body, dict) or set(body) - {'relay_id', 'controls', 'consent'} or body.get('consent') is not True:
            raise RemoteControlError(400, 'relay_id, controls and consent: true are required')
        rid = body.get('relay_id')
        relay = self._relay(rid)
        items = body.get('controls')
        if not isinstance(items, list) or len(items) > fabric_relay.MAX_CONTROLS:
            raise RemoteControlError(400, f'At most {fabric_relay.MAX_CONTROLS} controls')
        with self._lock:
            self.generation += 1
            gen = self.generation
        fp = _key_fp(relay['key'])
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
            digest = hashlib.sha256(json.dumps([rid, skill, target, params, label], sort_keys=True).encode()).hexdigest()[:10]
            cid = f'ctl-{digest}-g{gen}'                 # a re-grant of the same definition gets a new id
            out[cid] = {'label': label, 'skill_id': skill, 'target': target, 'params': params, 'generation': gen, 'key_fp': fp}
        return self._install(rid, gen, fp, out)

    def set_manifest_controls(self, rid, specs, revision=None, display=()):
        """V4: controls bound to owner-approved Meta manifests (validated UIViewPlan). Owner path only.
        specs: [{label, manifest, grant, facts, inputs[, kind, widget_id]}] already compiled and grant-checked by the substrate;
        kind 'confirm' requires an on-device confirmation that the PC checks on every request.
        display: [{widget_id, kind: status|label, label[, source]}] never executes anything; a status shows the last
        outcome of its source widget. revision is the plan layout_version, acknowledged by the device."""
        if self.closed:
            raise RemoteControlError(503, 'Remote controls are shut down')
        relay = self._relay(rid)
        if len(specs) > fabric_relay.MAX_CONTROLS:
            raise RemoteControlError(400, f'At most {fabric_relay.MAX_CONTROLS} controls')
        with self._lock:
            self.generation += 1
            gen = self.generation
        if len(specs) + len(display) > fabric_relay.MAX_CONTROLS:
            raise RemoteControlError(400, f'At most {fabric_relay.MAX_CONTROLS} widgets')
        fp, out, by_widget = _key_fp(relay['key']), {}, {}
        for s in specs:
            digest = hashlib.sha256(json.dumps([rid, s['manifest_hash'], s['inputs'], s['label']], sort_keys=True).encode()).hexdigest()[:10]
            cid = f'ctl-{digest}-g{gen}'
            out[cid] = {'kind': 'manifest', 'ui_kind': s.get('kind', 'button'), 'label': s['label'], 'skill_id': s['manifest']['capability_id'],
                        'target': None, 'params': s['inputs'], 'manifest': s['manifest'], 'grant': s['grant'], 'facts': s['facts'],
                        'manifest_hash': s['manifest_hash'], 'generation': gen, 'key_fp': fp}
            if s.get('widget_id'):
                by_widget[s['widget_id']] = cid
        shown = {}
        for d in display:
            digest = hashlib.sha256(json.dumps([rid, d['widget_id'], d['label']], sort_keys=True).encode()).hexdigest()[:10]
            shown[f'ui-{digest}-g{gen}'] = {'kind': d['kind'], 'label': d['label'], 'value': '' if d['kind'] == 'status' else None,
                                            'source': by_widget.get(d.get('source'))}
        return self._install(rid, gen, fp, out, shown, revision)

    def _install(self, rid, gen, fp, out, shown=None, revision=None):
        with self._lock:                                 # owner-update order survives delayed network replies
            if self.closed:
                raise RemoteControlError(503, 'Remote controls are shut down')
            superseded = self._grant_versions.get(rid, 0) > gen
            if not superseded:
                self._grant_versions[rid] = gen
                self.grants.pop(rid, None)
                self.suspended = {k for k in self.suspended if k[0] != rid}
                self._recent = {k: v for k, v in self._recent.items() if k[0] != rid}
        if superseded:
            return self.state()
        with self._grant_send_lock:
            with self._lock:
                superseded = self.closed or self._grant_versions.get(rid) != gen
            if superseded:
                return self.state()
            items = []
            for k, v in out.items():
                c = {'control_id': k, 'label': v['label']}
                if v.get('ui_kind', 'button') != 'button':
                    c['kind'] = v['ui_kind']
                items.append(c)
            for k, v in (shown or {}).items():
                c = {'control_id': k, 'label': v['label'], 'kind': v['kind']}
                if v['value'] is not None:
                    c['value'] = v['value']
                items.append(c)
            params = {'controls': items}
            if revision is not None:
                params['revision'] = revision
            self._send(rid, 'set_controls', params)
            with self._lock:
                current_relay = self.server.relays.relays.get(rid)
                if out and not self.closed and self._grant_versions.get(rid) == gen and current_relay and _key_fp(current_relay['key']) == fp:
                    self.grants[rid] = out
                if not self.closed and self._grant_versions.get(rid) == gen:
                    if shown or revision is not None:
                        self.layouts[rid] = {'revision': revision, 'acked': None, 'display': dict(shown or {})}
                    else:
                        self.layouts.pop(rid, None)
        self._ex().emit('remote_controls', relay_id=rid, count=len(out), generation=gen)
        self._ensure_thread()
        return self.state()

    def state(self):
        with self._lock:
            return {'controls': [{'relay_id': rid, 'control_id': cid, **{k: v for k, v in g.items() if k not in ('key_fp', 'grant', 'facts', 'manifest')}}
                                 for rid, cs in self.grants.items() for cid, g in cs.items()],
                    'history': list(self.history[-20:]), 'suspended': sorted(f'{a}/{b}' for a, b in self.suspended),
                    'layouts': {rid: {'revision': l['revision'], 'acked': l['acked'],
                                      'display': [{'control_id': k, **v} for k, v in l['display'].items()]}
                                for rid, l in self.layouts.items()},
                    'closed': self.closed}

    def close(self):
        """Server shutdown: stop the poller, forget grants; any in-flight poll dispatches nothing."""
        with self._lock:
            self.closed = True
            self.grants.clear()
            self.layouts.clear()
        self._stop.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(POLL_S * 4)

    # ---------- device side ----------
    def _ex(self):
        from src.runtime.api_v2 import executor
        return executor(self.server)

    def _ensure_thread(self):
        with self._lock:
            if self.closed or not self.grants or (self._thread is not None and self._thread.is_alive()):
                return
            self._thread = threading.Thread(target=self._loop, name='openbridge-remote-controls', daemon=True)
            self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            with self._lock:
                if not self.grants:
                    self._thread = None
                    return
            try:
                self.poll_once()
            except Exception:
                pass
            self._stop.wait(POLL_S)

    def _current_grant(self, rid, cid):
        """Point-of-dispatch revalidation (call with the lock held)."""
        if self.closed:
            return None
        g = (self.grants.get(rid) or {}).get(cid)
        r = self.server.relays.relays.get(rid)
        if g is None or r is None or _key_fp(r['key']) != g['key_fp']:
            return None
        return g

    def poll_once(self):
        with self._lock:
            if self.closed:
                return 0
            relays = {rid: set(cs) for rid, cs in self.grants.items()}
            for rid, l in self.layouts.items():          # display-only layouts are polled until the device acknowledges them
                if rid not in relays and l['revision'] is not None and l['acked'] != l['revision']:
                    relays[rid] = set()
        done = 0
        for rid, known in relays.items():
            r = self.server.relays.relays.get(rid)
            if r is None:                                   # relay revoked: its controls die with it
                with self._lock:
                    self.grants.pop(rid, None)
                continue
            if not r.get('online') or r.get('busy'):
                continue
            try:
                reply = self._send(rid, 'get_requests')
                reqs = fabric_relay.validate_requests(reply, known)
            except fabric_relay.RelayError:
                continue
            ack = fabric_relay.applied_revision(reply)
            if ack is not None:
                with self._lock:
                    if rid in self.layouts:
                        self.layouts[rid]['acked'] = ack
            for req in reqs[:MAX_PER_POLL - done]:
                self.process(rid, req)
                done += 1
        return done

    def process(self, rid, req):
        from src.runtime.api_v2 import router
        from src.runtime.routing import RouteError
        actor = f'relay:{rid}'
        key = (rid, req['control_id'])
        now = self.clock()
        entry = {'at': now, 'relay_id': rid, 'control_id': req['control_id'], 'request_id': req['request_id'],
                 'seq': req.get('seq'), 'pressed_at': req.get('pressed_at'), 'gesture': req.get('gesture'), 'touch': req.get('touch'),
                 'skill_id': None, 'invocation_id': None, 'transaction_id': None}
        with self._lock:
            grant = self._current_grant(rid, req['control_id'])
        if grant is None:
            outcome, text = 'REVOKED', 'This control is no longer authorized'
        else:
            entry['skill_id'] = grant['skill_id']
            pressed = req.get('pressed_at')
            recent = [x for x in self._recent.get(key, []) if now - x < BURST_WINDOW_S] + [now]
            self._recent[key] = recent
            if key not in self.suspended and len(recent) > BURST:
                self.suspended.add(key)
                self._ex().emit('remote_control_suspended', relay_id=rid, control_id=req['control_id'], presses=len(recent))
            if not isinstance(pressed, int) or abs(now - pressed / 1000) > REQUEST_TTL_S:
                outcome, text = 'EXPIRED', f"{grant['label']}: request too old; press again"
            elif key in self.suspended:
                outcome, text = 'SUSPENDED', f"{grant['label']}: paused (unusual repeated presses); re-enable on the PC"
            elif (actor, 'inv-' + req['request_id']) in router(self.server).completed:
                outcome, text = 'DUPLICATE', f"{grant['label']}: already done"     # a re-sent press: never dispatched twice
            elif now - self._last.get(key, 0) < MIN_INTERVAL_S:
                outcome, text = 'BLOCKED', 'Too fast; press again'
            elif grant.get('ui_kind') == 'confirm' and req.get('gesture') != 'confirm':
                outcome, text = 'BLOCKED', f"{grant['label']}: confirm on the device first"
            else:
                outcome, text = self._dispatch(rid, req, grant, actor, entry)
                self._last[key] = now
        entry['state'] = outcome
        with self._lock:
            self.history.append(entry)
            del self.history[:-100]
        self._update_status(rid, req['control_id'], outcome, now)
        ev = {k: v for k, v in entry.items() if k not in ('at', 'touch', 'seq')}
        self._ex().emit('remote_request', device_seq=entry['seq'], **ev)
        if not self.closed:
            try:
                self._send(rid, 'report_result', {'request_id': req['request_id'], 'state': outcome, 'text': text[:80]})
            except fabric_relay.RelayError:
                pass
        return entry

    def _update_status(self, rid, cid, outcome, now):
        """Status widgets show the last outcome of their source control. Sent as update_status, which never resets
        pending device requests (a full set_controls would)."""
        with self._lock:
            l = self.layouts.get(rid)
            targets = [k for k, v in (l or {}).get('display', {}).items() if v['kind'] == 'status' and v['source'] == cid]
            if not targets:
                return
            word = {'VERIFIED': 'done, verified', 'EXECUTED': 'done', 'REVOKED': 'not authorized'}.get(outcome, outcome.lower().replace('_', ' '))
            value = (word + ' ' + time.strftime('%H:%M', time.localtime(now)))[:fabric_relay.MAX_STATUS_TEXT]
            for k in targets:
                l['display'][k]['value'] = value
        if not self.closed:
            try:
                self._send(rid, 'update_status', {'values': {k: value for k in targets}})
            except fabric_relay.RelayError:
                pass

    def _dispatch(self, rid, req, grant, actor, entry):
        if grant.get('kind') == 'manifest':
            return self._dispatch_manifest(rid, req, grant, entry)
        from src.runtime.api_v2 import router
        from src.runtime.routing import RouteError
        rt = router(self.server)
        try:
            doc = rt.skill_routes(grant['skill_id'], grant['target'])
            if not doc['selected_route_id']:
                reasons = sorted({r['reason'] for r in doc['routes'] if r['reason']}) or ['no route']
                raise RouteError(409, 'NO_ROUTE', 'Unavailable: ' + ', '.join(reasons).replace('_', ' '))
            inv_id = 'inv-' + req['request_id']
            lease = rt.arm({'skill_id': grant['skill_id'], 'target': grant['target'], 'route_id': doc['selected_route_id'],
                            'params': grant['params'], 'consent': True}, actor=actor, invocation_id=inv_id)
            body = {k: lease[k] for k in ('invocation_id', 'route_id', 'lease_id', 'graph_revision')}
            body.update(skill_id=grant['skill_id'], params=grant['params'], consent=True)
            if grant['target']:
                body['target'] = grant['target']
            with self._lock:                         # last revalidation right before the device is touched
                if self._current_grant(rid, req['control_id']) is not grant:
                    return 'REVOKED', 'This control is no longer authorized'
            entry['invocation_id'] = inv_id
            rc = rt.invoke(body, actor=actor)
            entry['transaction_id'] = rc.get('transaction_id')
            outcome = rc.get('state', 'FAILED')
            text = f"{grant['label']}: " + {'VERIFIED': 'done, verified', 'EXECUTED': 'done', 'REVERTED': 'restored'}.get(outcome, outcome.lower().replace('_', ' '))
            after = rc.get('after')
            if outcome == 'VERIFIED' and isinstance(after, int):
                text += f' ({after})'
            return outcome, text
        except RouteError as e:
            return 'BLOCKED', f"{grant['label']}: {e}"[:80]

    def _dispatch_manifest(self, rid, req, grant, entry):
        """V4 path: the press runs an owner-approved Meta manifest through the substrate kernel (grant re-verified,
        facts and permissions re-checked before each step, receipt signed). operation_id derives from the request id."""
        from src.runtime.api_v2 import substrate
        from src.substrate.kernel import SubstrateError
        s = substrate(self.server)
        op = 'op-' + req['request_id']
        if op in s.operations:
            return 'DUPLICATE', f"{grant['label']}: already done"
        with self._lock:
            if self._current_grant(rid, req['control_id']) is not grant:
                return 'REVOKED', 'This control is no longer authorized'
        try:
            rec = s.invoke(grant['manifest'], grant['grant'], grant['facts'],
                           {'operation_id': op, 'principal': 'relay', 'manifest_hash': grant['manifest_hash'], 'grant_id': grant['grant']['grant_id'],
                            'inputs': grant['params'], 'trace_id': 'rc-' + req['request_id'][:20]})
        except SubstrateError as e:
            return 'BLOCKED', f"{grant['label']}: {e.code.lower().replace('_', ' ')}"[:80]
        entry['invocation_id'] = op
        entry['transaction_id'] = next((st['transaction_id'] for st in reversed(rec['steps']) if st['transaction_id']), None)
        text = f"{grant['label']}: " + {'VERIFIED': 'done, verified', 'EXECUTED': 'done'}.get(rec['status'], rec['status'].lower())
        return rec['status'], text
