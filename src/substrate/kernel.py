"""V4 trust kernel: compile model-authored manifests, bind owner approvals, execute through prebuilt primitives.

Pipeline (11_META_NATIVE_V4/03_ADAPTER_FACTORY_POLICY.md):
  CandidateManifest (origin=meta_generated) -> compile() [schema, known primitives, typed args, permissions,
  fresh signed facts, target identity, static bounds, injection checks] -> owner grant bound to the manifest hash,
  device fingerprints, permissions, uses and expiry (HMAC with a server-only key: a model cannot mint one) ->
  invoke() [grant re-verified, facts and permissions re-checked just before each step, dispatch through the existing
  Executor with its locks/consent/receipts, no retry after an uncertain outcome] -> signed Receipt.
Unknown, hypothetical or owner-only primitives -> REJECTED_UNSUPPORTED_PRIMITIVE + EngineeringPrimitiveRequest.
"""
import copy
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from src.runtime.route_contract import schema_errors
from src.substrate.registry import BACKEND, NATIVE_PRIMITIVE_REGISTRY

CONTRACT = json.loads((Path(__file__).with_name('v4_contract.schema.json')).read_text(encoding='utf-8'))
CONTRACT_VERSION = 'obv4.1'
GRANT_RANK = {'observe': 0, 'read': 1, 'control': 2}
MAX_TOTAL_DISPATCHES = 20
BAD_TEXT = re.compile(r'[\x00-\x1f\x7f]|\$\(|`|\{\{|\}\}|<script|javascript:|\$\{', re.I)


class SubstrateError(Exception):
    def __init__(self, code, message, status=400, extra=None):
        super().__init__(message)
        self.code, self.status, self.extra = code, status, extra or {}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def manifest_hash(m):
    return 'sha256:' + hashlib.sha256(canonical(m).encode()).hexdigest()


def iso(t):
    return datetime.fromtimestamp(int(t), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def epoch(ts):
    return datetime.fromisoformat(str(ts).replace('Z', '+00:00')).timestamp()


def validate(doc_type, doc):
    return schema_errors(doc, CONTRACT['$defs'][doc_type], '$', CONTRACT)


class Substrate:
    def __init__(self, server, clock=time.time, key=None):
        self.server, self.clock = server, clock
        self._key = key or secrets.token_bytes(32)        # never leaves the process; not exposed to model tools
        self._lock = threading.Lock()
        self.grant_uses = {}                              # grant_id -> uses
        self.revoked = set()
        self.receipts = []                                # bounded signed receipts
        self.operations = set()                           # operation ids already used (no replay)

    # ---------- identity and facts ----------
    def _sign(self, kind, obj):
        return hmac.new(self._key, (kind + '|' + canonical(obj)).encode(), hashlib.sha256).hexdigest()

    def _devices(self):
        snap = getattr(self.server, 'fabric_snapshot', None) or {'devices': [], 'links': []}
        return snap

    def fingerprint(self, key):
        reg = getattr(self.server, 'fabric_registry', None)
        dev = reg.devices.get(key, {}) if reg else {}
        strong = sorted(f'{i.kind}:{i.value}' for i in dev.get('identifiers', ()) if getattr(i, 'strong', False))
        anchor = strong[0] if strong else f'key:{key}'
        return 'fp-' + hmac.new(self._key, ('fp|' + anchor).encode(), hashlib.sha256).hexdigest()[:16]

    def device_by_fp(self, fp):
        for d in self._devices()['devices']:
            if self.fingerprint(d['key']) == fp:
                return d
        return None

    def facts(self, device_key):
        """Signed, timestamped facts for one device (EvidenceBundle). Values are short scalars; no credentials."""
        d = next((x for x in self._devices()['devices'] if x['key'] == device_key), None)
        if d is None:
            raise SubstrateError('UNKNOWN_DEVICE', 'Device not in the current graph', 404)
        fp, out = self.fingerprint(device_key), []
        rows = [('category', d['category'], 'REGISTRY', None, True)]
        for name, f in sorted((d.get('facts') or {}).items()):
            v = f.get('value')
            if isinstance(v, (str, int, float, bool)) or v is None:
                src = (f.get('sources') or ['UNKNOWN'])[0].split(':')[0][:24] or 'UNKNOWN'
                rows.append((re.sub(r'[^a-z0-9_.-]', '_', name.lower())[:63], v if not isinstance(v, str) else v[:200], src, f.get('observed_at'), bool(f.get('verified'))))
        for name, v, src, obs, ver in rows:
            if not re.fullmatch(r'[A-Z_]{2,24}', src):
                src = 'UNKNOWN'
            fact = {'fact_id': 'f-' + hashlib.sha256(f'{fp}|{name}'.encode()).hexdigest()[:16], 'device_fingerprint': fp, 'name': name if re.fullmatch(r'[a-z][a-z0-9_.-]{0,63}', name) else 'field_' + hashlib.sha256(name.encode()).hexdigest()[:8],
                    'value': v, 'source': src, 'observed_at': iso(epoch(obs) if obs else self.clock()), 'verified': ver}
            fact['signature'] = self._sign('fact', fact)
            out.append(fact)
        return out

    def _check_fact(self, fact, fp, max_age):
        body = {k: v for k, v in fact.items() if k != 'signature'}
        if validate('Fact', fact) or not hmac.compare_digest(self._sign('fact', body), str(fact.get('signature', ''))):
            return 'FORGED_FACT'
        if fact['device_fingerprint'] != fp:
            return 'FACT_OTHER_DEVICE'
        if self.clock() - epoch(fact['observed_at']) > max_age:
            return 'STALE_FACT'
        current = {f['fact_id']: f for f in self.facts(self.device_by_fp(fp)['key'])}
        cur = current.get(fact['fact_id'])
        if cur is None or cur['value'] != fact['value']:
            return 'FACT_CHANGED'
        return None

    # ---------- compiler ----------
    def _text_ok(self, v):
        return not (isinstance(v, str) and BAD_TEXT.search(v))

    def _epr(self, pid, reason, platform='any'):
        desc = NATIVE_PRIMITIVE_REGISTRY.get(pid)
        req = {'request_id': 'epr-' + hashlib.sha256(f'{pid}|{reason}'.encode()).hexdigest()[:16], 'requested_primitive': pid if re.fullmatch(r'[a-z][a-z0-9_.-]{0,63}', str(pid)) else 'invalid.primitive',
               'platform': desc['platform'] if desc else platform, 'reason': reason, 'evidence_refs': [],
               'least_permission_design': (desc['test_oracle'] if desc else 'to be designed by the substrate owner')[:200],
               'blockers': (desc['constraints'] if desc else ['no platform API identified'])[:8], 'test_plan': 'fail-first contract tests + one owner-supervised hardware check',
               'status': 'OPEN'}
        return req

    def compile(self, manifest, facts=(), inputs=None, for_dispatch=False):
        """Return {'manifest_hash', 'plan', 'permissions', 'device_key', 'effects'} or raise SubstrateError."""
        errs = validate('CandidateManifest', manifest)
        if errs:
            raise SubstrateError('SCHEMA', errs[0])
        m = manifest
        if self.clock() > epoch(m['expires_at']):
            raise SubstrateError('MANIFEST_EXPIRED', 'Manifest expired')
        def strings(o):
            if isinstance(o, str):
                yield o
            elif isinstance(o, dict):
                for k, v in o.items():
                    yield str(k)
                    yield from strings(v)
            elif isinstance(o, list):
                for v in o:
                    yield from strings(v)
        for v in strings([m['title'], m['steps'], m['inputs'], m['capability_id']]):
            if not self._text_ok(v):
                raise SubstrateError('INJECTION', 'Control characters or template/script markers are not allowed')
        dev = self.device_by_fp(m['target']['device_fingerprint'])
        if dev is None:
            raise SubstrateError('UNKNOWN_TARGET', 'Target fingerprint is not a device in the current graph (forged or swapped)', 409)
        if dev['category'] != m['target']['category']:
            raise SubstrateError('TARGET_MISMATCH', 'Target category does not match the device', 409)
        # facts: every required fact must be supplied, signed by this server, fresh, for this device, unchanged
        by_id = {f.get('fact_id'): f for f in facts if isinstance(f, dict)}
        for fid in m['facts_required']:
            if fid not in by_id:
                raise SubstrateError('MISSING_FACT', f'{fid} not supplied')
            why = self._check_fact(by_id[fid], m['target']['device_fingerprint'], m['max_fact_age_s'])
            if why:
                raise SubstrateError(why, f'{fid}: {why.lower()}', 409)
        # inputs: a closed, typed set
        if not isinstance(m['inputs'], dict) or len(m['inputs']) > 8:
            raise SubstrateError('INPUTS', 'At most 8 typed inputs')
        for name, sch in m['inputs'].items():
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', name) or not isinstance(sch, dict) or sch.get('type') not in ('integer', 'string', 'boolean') \
                    or set(sch) - {'type', 'minimum', 'maximum', 'maxLength', 'enum'}:
                raise SubstrateError('INPUTS', f'input {name!r} must be integer/string/boolean with bounds or enum')
            if sch['type'] == 'string' and 'enum' not in sch and sch.get('maxLength', 1000) > 100:
                raise SubstrateError('INPUTS', f'string input {name!r} needs maxLength <= 100 or an enum')
        from src.runtime.primitives import validate as strict, PrimitiveError
        plan, perms, total, effects, seen = [], set(), 0, set(), set()
        for st in m['steps']:
            pid = st['primitive_id']
            if st['step_id'] in seen:
                raise SubstrateError('DUPLICATE_STEP', st['step_id'])
            seen.add(st['step_id'])
            desc = NATIVE_PRIMITIVE_REGISTRY.get(pid)
            reason = None if desc else 'UNKNOWN_PRIMITIVE'
            if desc and not desc['manifest_allowed']:
                reason = 'NOT_MANIFEST_ALLOWED'
            elif desc and desc['status'] == 'BLOCKED':
                reason = 'PRIMITIVE_BLOCKED'
            elif desc and desc['status'] == 'HYPOTHESIS':
                reason = 'PRIMITIVE_HYPOTHESIS'
            if reason:
                raise SubstrateError('REJECTED_UNSUPPORTED_PRIMITIVE', f'{pid}: {reason}', 422, {'engineering_request': self._epr(pid, reason)})
            backend = BACKEND[pid]
            if backend[2] is not None and dev['category'] not in backend[2]:
                raise SubstrateError('PRIMITIVE_NOT_FOR_DEVICE', f'{pid} does not apply to a {dev["category"]}', 422)
            reps = st.get('repeat', 1)
            if reps > 1 and desc['idempotency'] != 'IDEMPOTENT' and desc['side_effect_class'] == 'IRREVERSIBLE' and reps > 3:
                raise SubstrateError('UNBOUNDED_EFFECT', f'{pid}: at most 3 repetitions of an irreversible step')
            total += reps
            # resolve args: literal, {"$input": n} or {"$fact": id}
            resolved = {}
            for k, v in st['args'].items():
                if isinstance(v, dict):
                    if set(v) == {'$input'} and v['$input'] in m['inputs']:
                        if inputs is not None:
                            if v['$input'] not in inputs:
                                raise SubstrateError('MISSING_INPUT', v['$input'])
                            try:
                                strict(m['inputs'][v['$input']], inputs[v['$input']], v['$input'])
                            except PrimitiveError as e:
                                raise SubstrateError('INVALID_INPUT', str(e)) from None
                            resolved[k] = inputs[v['$input']]
                        else:
                            resolved[k] = None
                    elif set(v) == {'$fact'} and v['$fact'] in m['facts_required']:
                        resolved[k] = by_id[v['$fact']]['value']
                    else:
                        raise SubstrateError('BAD_REFERENCE', f'{st["step_id"]}.{k}: only declared $input or required $fact references')
                else:
                    resolved[k] = v
            if inputs is not None or all(v is not None for v in resolved.values()):
                try:
                    strict(desc['input_schema'], resolved, f'{st["step_id"]}')
                except PrimitiveError as e:
                    raise SubstrateError('INVALID_ARGS', str(e)) from None
            else:   # dry compile: check structure with inputs stubbed
                for k in resolved:
                    if k not in desc['input_schema'].get('properties', {}):
                        raise SubstrateError('INVALID_ARGS', f'{st["step_id"]}: unexpected argument {k!r}')
            perms |= set(desc['required_permissions'])
            effects.add(desc['side_effect_class'])
            plan.append({'step_id': st['step_id'], 'primitive_id': pid, 'args': resolved, 'repeat': reps, 'on_uncertain': st['on_uncertain'],
                         'side_effect_class': desc['side_effect_class'], 'idempotency': desc['idempotency']})
        if total > MAX_TOTAL_DISPATCHES:
            raise SubstrateError('UNBOUNDED_EFFECT', f'{total} dispatches > {MAX_TOTAL_DISPATCHES}')
        if not perms <= set(m['permissions_requested']):
            raise SubstrateError('UNDECLARED_PERMISSION', f'steps need {sorted(perms)}; manifest declares {sorted(m["permissions_requested"])}')
        # the device link must actually grant what the steps need (no privilege expansion)
        links = [l for l in self._devices()['links'] if l['child'] == dev['key'] and l['parent'] == 'pc']
        have = max((GRANT_RANK.get(g, -1) for l in links for g in l['grants']), default=-1)
        need = max((GRANT_RANK[p] for p in perms), default=-1)
        if need > have:
            raise SubstrateError('PRIVILEGE_ESCALATION', f'device link grants {have}, steps need {need}', 403)
        return {'manifest_hash': manifest_hash(m), 'plan': plan, 'permissions': sorted(perms), 'device_key': dev['key'],
                'effects': sorted(effects), 'origin': m['origin'], 'dispatches': total}

    # ---------- owner approval ----------
    def issue_grant(self, manifest, facts, consent, max_uses=1, ttl_s=900):
        """Called only from the owner HTTP path (CSRF + Origin). Compiles the manifest itself before signing."""
        if consent is not True:
            raise SubstrateError('CONSENT_REQUIRED', 'consent: true is required')
        if not isinstance(max_uses, int) or not 1 <= max_uses <= 100 or not isinstance(ttl_s, int) or not 30 <= ttl_s <= 86400:
            raise SubstrateError('BAD_GRANT', 'max_uses 1-100, ttl_s 30-86400')
        c = self.compile(manifest, facts)
        now = self.clock()
        g = {'grant_id': 'g-' + secrets.token_hex(8), 'principal': 'owner', 'manifest_hash': c['manifest_hash'],
             'device_fingerprints': [manifest['target']['device_fingerprint']], 'permissions': c['permissions'], 'max_uses': max_uses,
             'issued_at': iso(now), 'expires_at': iso(min(now + ttl_s, epoch(manifest['expires_at'])))}
        g['signature'] = self._sign('grant', g)
        return g, c

    def revoke(self, grant_id):
        with self._lock:
            self.revoked.add(grant_id)

    def _check_grant(self, grant, mhash, fp, perms):
        if not isinstance(grant, dict) or validate('Grant', grant):
            raise SubstrateError('GRANT_INVALID', 'Malformed grant', 403)
        body = {k: v for k, v in grant.items() if k != 'signature'}
        if not hmac.compare_digest(self._sign('grant', body), grant['signature']):
            raise SubstrateError('GRANT_FORGED', 'Grant signature invalid (not issued by the owner path)', 403)
        if grant['grant_id'] in self.revoked:
            raise SubstrateError('GRANT_REVOKED', 'Grant revoked', 403)
        if self.clock() > epoch(grant['expires_at']):
            raise SubstrateError('GRANT_EXPIRED', 'Grant expired', 403)
        if grant['manifest_hash'] != mhash:
            raise SubstrateError('GRANT_OTHER_MANIFEST', 'Grant is for a different manifest version', 403)
        if fp not in grant['device_fingerprints']:
            raise SubstrateError('GRANT_OTHER_DEVICE', 'Grant does not cover this device', 403)
        if not set(perms) <= set(grant['permissions']):
            raise SubstrateError('GRANT_SCOPE', 'Grant does not cover the permissions needed', 403)
        if self.grant_uses.get(grant['grant_id'], 0) >= grant['max_uses']:
            raise SubstrateError('GRANT_USED', 'Grant uses exhausted', 403)

    # ---------- execution ----------
    def _ex(self):
        from src.runtime.api_v2 import executor
        return executor(self.server)

    def invoke(self, manifest, grant, facts, request):
        """Owner (or relay) invocation of an approved manifest. Every check is redone right before dispatch."""
        errs = validate('InvokeRequest', request)
        if errs:
            raise SubstrateError('SCHEMA', errs[0])
        with self._lock:
            if request['operation_id'] in self.operations:
                raise SubstrateError('OPERATION_REPLAY', 'operation_id already used', 409)
        c = self.compile(manifest, facts, request['inputs'], for_dispatch=True)
        if c['manifest_hash'] != request['manifest_hash']:
            raise SubstrateError('HASH_MISMATCH', 'Request hash does not match the manifest', 409)
        fp = manifest['target']['device_fingerprint']
        with self._lock:
            self._check_grant(grant, c['manifest_hash'], fp, c['permissions'])
            if grant['grant_id'] != request['grant_id']:
                raise SubstrateError('GRANT_MISMATCH', 'grant_id differs from the request', 409)
            self.grant_uses[grant['grant_id']] = self.grant_uses.get(grant['grant_id'], 0) + 1
            self.operations.add(request['operation_id'])
        started, steps, status, error = self.clock(), [], 'VERIFIED', None
        ex = self._ex()
        for st in c['plan']:
            exe, build, _cats = BACKEND[st['primitive_id']]
            for attempt in range(1, st['repeat'] + 1):
                # re-check freshness/permissions/target identity just before touching the device
                try:
                    self.compile(manifest, facts, request['inputs'], for_dispatch=True)
                    if grant['grant_id'] in self.revoked or self.clock() > epoch(grant['expires_at']):
                        raise SubstrateError('GRANT_REVOKED', 'grant revoked or expired during the operation', 403)
                except SubstrateError as e:
                    status, error = 'BLOCKED', f'{e.code}: {e}'
                    break
                r = ex.execute(exe, c['device_key'], build(st['args']), consent=True)
                state = r.get('state', 'FAILED')
                steps.append({'step_id': st['step_id'], 'primitive_id': st['primitive_id'], 'attempt': attempt,
                              'transaction_id': r.get('transaction_id'), 'status': state})
                if state in ('VERIFIED', 'REVERTED'):
                    continue
                if state == 'EXECUTED':
                    if status == 'VERIFIED':
                        status = 'EXECUTED'          # done but not independently verified
                    continue
                if state == 'BLOCKED':
                    status, error = 'BLOCKED', '; '.join(r.get('errors') or [])[:200]
                else:                                 # FAILED / PARTIAL / UNKNOWN_TIMEOUT: never retried
                    status, error = ('INCONCLUSIVE' if st['on_uncertain'] == 'INCONCLUSIVE' or state == 'UNKNOWN_TIMEOUT' else 'FAILED'), '; '.join(r.get('errors') or [])[:200]
                break
            if status in ('BLOCKED', 'FAILED', 'INCONCLUSIVE'):
                break
        rec = {'operation_id': request['operation_id'], 'manifest_hash': c['manifest_hash'], 'origin': manifest['origin'], 'device_fingerprint': fp,
               'status': status, 'steps': steps, 'error': error, 'started_at': iso(started), 'finished_at': iso(self.clock())}
        rec['signature'] = self._sign('receipt', rec)
        with self._lock:
            self.receipts.append(rec)
            del self.receipts[:-200]
        self._ex().emit('manifest_receipt', operation_id=rec['operation_id'], manifest_hash=rec['manifest_hash'], status=status, origin=rec['origin'])
        return rec

    def verify_receipt(self, rec):
        body = {k: v for k, v in rec.items() if k != 'signature'}
        return hmac.compare_digest(self._sign('receipt', body), str(rec.get('signature', '')))

    # ---------- Meta-generated UI ----------
    def relay_fingerprint(self, rid):
        r = self.server.relays.relays.get(rid)
        reg = getattr(self.server, 'fabric_registry', None)
        if r is None or reg is None:
            return None
        key = next((k for k, d in reg.devices.items() if r['device_key'] in d.get('handles', {}).values()), None)
        return self.fingerprint(key) if key else None

    def install_ui_plan(self, body):
        """Owner path. A validated UIViewPlan becomes Companion controls; each button runs one approved manifest."""
        from src.runtime.api_v2 import remote_controls
        if not isinstance(body, dict) or set(body) - {'relay_id', 'plan', 'bindings', 'consent'} or body.get('consent') is not True:
            raise SubstrateError('CONSENT_REQUIRED', 'relay_id, plan, bindings and consent: true are required')
        plan, bindings = body.get('plan'), body.get('bindings') or {}
        errs = validate('UIViewPlan', plan) if isinstance(plan, dict) else ['plan must be an object']
        if errs:
            raise SubstrateError('SCHEMA', errs[0])
        if manifest_hash({k: v for k, v in plan.items() if k != 'plan_hash'}) != plan['plan_hash']:
            raise SubstrateError('PLAN_HASH', 'plan_hash does not match the plan')
        rid = body.get('relay_id')
        if self.relay_fingerprint(rid) != plan['target_device']:
            raise SubstrateError('UI_TARGET', 'The plan targets another device than this relay', 409)
        specs = []
        for w in plan['widgets']:
            if not self._text_ok(w['label']) or not self._text_ok(w['permission_label']):
                raise SubstrateError('INJECTION', 'Widget text contains control or script markers')
            if w['kind'] == 'label':
                if w['binding'] is not None:
                    raise SubstrateError('UI_BINDING', 'A label cannot be bound to an action')
                continue
            b = w['binding']
            if b is None:
                raise SubstrateError('UI_BINDING', f'button {w["widget_id"]} has no binding')
            bound = bindings.get(b['manifest_hash'])
            if not isinstance(bound, dict) or manifest_hash(bound.get('manifest')) != b['manifest_hash']:
                raise SubstrateError('UI_BINDING', f'button {w["widget_id"]}: manifest not supplied or hash differs')
            c = self.compile(bound['manifest'], bound.get('facts') or [], b['inputs'])
            self._check_grant(bound.get('grant'), c['manifest_hash'], bound['manifest']['target']['device_fingerprint'], c['permissions'])
            specs.append({'label': w['label'], 'manifest': bound['manifest'], 'grant': bound['grant'], 'facts': bound.get('facts') or [],
                          'manifest_hash': c['manifest_hash'], 'inputs': b['inputs']})
        from src.runtime.remote_controls import RemoteControlError
        from src.fabric.relay import RelayError
        try:
            state = remote_controls(self.server).set_manifest_controls(rid, specs)
        except RemoteControlError as e:
            raise SubstrateError('UI_INSTALL', str(e), e.status) from None
        except RelayError as e:
            raise SubstrateError('UI_INSTALL', f'Companion unreachable: {e}', 409) from None
        self._ex().emit('ui_plan_installed', relay_id=rid, plan_hash=plan['plan_hash'], layout_version=plan['layout_version'], buttons=len(specs))
        return {'plan_hash': plan['plan_hash'], 'installed': [c['control_id'] for c in state['controls'] if c.get('relay_id') == rid]}
