"""Multi-device workflows over the V4 trust kernel (Claude substrate; Meta authors the plan).

A Workflow is a small DAG of nodes; each node runs ONE already-approved single-device manifest through
`Substrate.invoke`, so every per-step check (facts, permissions, target identity, grant, revocation) still applies.
On top of that, the owner signs the WHOLE workflow (its canonical hash) once, so a model cannot reorder, add or drop
nodes after approval.

Execution: independent nodes run in parallel (bounded), dependents start only after all their dependencies
EXECUTED/VERIFIED. A failed, blocked or inconclusive node is never retried; its transitive dependents are SKIPPED and
independent branches continue. Cancellation stops nodes that have not started (a running physical step is not
interrupted). The signed workflow receipt lists every node with its status and its manifest receipt.
"""
import hashlib
import hmac
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait

from src.substrate.kernel import SubstrateError, epoch, iso, manifest_hash

WORKFLOW_VERSION = 'obv4.1-wf'
MAX_NODES, MAX_PARALLEL = 16, 4
ID = re.compile(r'^[a-z][a-z0-9_.-]{0,63}$')
KEYS = {'workflow_version', 'workflow_id', 'title', 'origin', 'model_run', 'nodes', 'max_parallel'}
NODE_KEYS = {'node_id', 'manifest_hash', 'depends_on'}
OK = ('VERIFIED', 'EXECUTED')


def validate_workflow(wf):
    """Static checks; returns nodes in a deterministic topological order. Raises SubstrateError."""
    def bad(msg):
        raise SubstrateError('WORKFLOW_SCHEMA', msg)
    if not isinstance(wf, dict) or set(wf) != KEYS:
        bad('workflow keys must be exactly %s' % sorted(KEYS))
    if wf['workflow_version'] != WORKFLOW_VERSION or not ID.match(str(wf['workflow_id'])):
        bad('workflow_version/workflow_id')
    if not isinstance(wf['title'], str) or not 1 <= len(wf['title']) <= 80:
        bad('title 1-80 chars')
    if wf['origin'] != 'meta_generated':
        bad('origin must be meta_generated')
    mr = wf['model_run']
    if not isinstance(mr, dict) or set(mr) != {'provider', 'model', 'run_id'} or mr['provider'] != 'meta':
        bad('model_run must name a Meta run')
    mp = wf['max_parallel']
    if not isinstance(mp, int) or isinstance(mp, bool) or not 1 <= mp <= MAX_PARALLEL:
        bad('max_parallel 1-%d' % MAX_PARALLEL)
    nodes = wf['nodes']
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        bad('1-%d nodes' % MAX_NODES)
    ids = []
    for n in nodes:
        if not isinstance(n, dict) or set(n) != NODE_KEYS or not ID.match(str(n['node_id'])):
            bad('node keys must be exactly %s' % sorted(NODE_KEYS))
        if not isinstance(n['manifest_hash'], str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', n['manifest_hash']):
            bad('node %s manifest_hash' % n['node_id'])
        if not isinstance(n['depends_on'], list) or len(set(n['depends_on'])) != len(n['depends_on']):
            bad('node %s depends_on' % n['node_id'])
        ids.append(n['node_id'])
    if len(set(ids)) != len(ids):
        bad('node ids must be unique')
    by_id = {n['node_id']: n for n in nodes}
    for n in nodes:
        for d in n['depends_on']:
            if d not in by_id or d == n['node_id']:
                bad('node %s depends on unknown or itself: %s' % (n['node_id'], d))
    order, done = [], set()
    while len(order) < len(nodes):                       # Kahn, deterministic by node order
        ready = [n for n in nodes if n['node_id'] not in done and set(n['depends_on']) <= done]
        if not ready:
            raise SubstrateError('WORKFLOW_CYCLE', 'dependency cycle')
        for n in ready:
            order.append(n); done.add(n['node_id'])
    return order


def node_operation_id(workflow_op, node_id):
    return 'op-' + hashlib.sha256(('wf|%s|%s' % (workflow_op, node_id)).encode()).hexdigest()[:32]


class Workflows:
    """Owner-approved workflow grants and their execution. One instance per Substrate."""

    def __init__(self, substrate):
        self.s = substrate
        self._lock = threading.Lock()
        self.used = set()                 # workflow grant ids already consumed
        self.revoked = set()
        self.operations = set()           # workflow operation ids (no replay)
        self.receipts = []

    def _sign(self, kind, obj):
        return self.s._sign(kind, obj)

    def _check_bindings(self, wf, bindings):
        if not isinstance(bindings, dict):
            raise SubstrateError('WORKFLOW_BINDING', 'bindings must map manifest_hash -> {manifest, grant, facts}')
        for n in wf['nodes']:
            b = bindings.get(n['manifest_hash'])
            if not isinstance(b, dict) or manifest_hash(b.get('manifest')) != n['manifest_hash']:
                raise SubstrateError('WORKFLOW_BINDING', 'node %s: manifest missing or hash differs' % n['node_id'])
            c = self.s.compile(b['manifest'], b.get('facts') or [])
            self.s._check_grant(b.get('grant'), c['manifest_hash'], b['manifest']['target']['device_fingerprint'], c['permissions'])

    def issue_grant(self, wf, bindings, consent, ttl_s=900):
        """Owner path only (CSRF + Origin at the HTTP layer). Signs the exact workflow; one use."""
        if consent is not True:
            raise SubstrateError('CONSENT_REQUIRED', 'consent: true is required')
        if not isinstance(ttl_s, int) or not 30 <= ttl_s <= 86400:
            raise SubstrateError('BAD_GRANT', 'ttl_s 30-86400')
        validate_workflow(wf)
        if not self.s._text_ok(wf['title']):
            raise SubstrateError('INJECTION', 'title contains control or script markers')
        self._check_bindings(wf, bindings)
        now = self.s.clock()
        g = {'wgrant_id': 'wg-' + secrets.token_hex(8), 'workflow_hash': manifest_hash(wf), 'principal': 'owner',
             'issued_at': iso(now), 'expires_at': iso(now + ttl_s)}
        g['signature'] = self._sign('wgrant', g)
        return g

    def revoke(self, wgrant_id):
        with self._lock:
            self.revoked.add(wgrant_id)

    def _check_wgrant(self, wf, g):
        if not isinstance(g, dict) or set(g) != {'wgrant_id', 'workflow_hash', 'principal', 'issued_at', 'expires_at', 'signature'}:
            raise SubstrateError('WGRANT_INVALID', 'malformed workflow grant', 403)
        body = {k: v for k, v in g.items() if k != 'signature'}
        if not hmac.compare_digest(self._sign('wgrant', body), str(g['signature'])):
            raise SubstrateError('WGRANT_FORGED', 'workflow grant not issued by the owner path', 403)
        if g['workflow_hash'] != manifest_hash(wf):
            raise SubstrateError('WGRANT_OTHER_WORKFLOW', 'workflow changed after approval', 403)
        if g['wgrant_id'] in self.revoked:
            raise SubstrateError('WGRANT_REVOKED', 'workflow grant revoked', 403)
        if self.s.clock() > epoch(g['expires_at']):
            raise SubstrateError('WGRANT_EXPIRED', 'workflow grant expired', 403)
        if g['wgrant_id'] in self.used:
            raise SubstrateError('WGRANT_USED', 'workflow grant already used', 403)

    def run(self, wf, wgrant, bindings, operation_id, cancel=None, principal='owner'):
        if not isinstance(operation_id, str) or not re.fullmatch(r'op-[0-9a-f]{32}', operation_id):
            raise SubstrateError('SCHEMA', 'operation_id must be op- + 32 hex')
        order = validate_workflow(wf)
        with self._lock:                                  # replay + grant consumption in one critical section
            if operation_id in self.operations:
                raise SubstrateError('OPERATION_REPLAY', 'workflow operation already executed', 409)
            self._check_wgrant(wf, wgrant)
            self._check_bindings(wf, bindings)
            self.operations.add(operation_id)
            self.used.add(wgrant['wgrant_id'])
        cancel = cancel or threading.Event()
        started = self.s.clock()
        status = {n['node_id']: 'PENDING' for n in order}
        detail = {}
        deps = {n['node_id']: set(n['depends_on']) for n in order}
        by_id = {n['node_id']: n for n in order}

        def run_node(nid):
            n = by_id[nid]
            b = bindings[n['manifest_hash']]
            req = {'operation_id': node_operation_id(operation_id, nid), 'principal': principal, 'manifest_hash': n['manifest_hash'],
                   'grant_id': b['grant']['grant_id'], 'inputs': b.get('inputs') or {}, 'trace_id': ('wf-' + nid)[:40] + '-' + operation_id[3:9]}
            try:
                rec = self.s.invoke(b['manifest'], b['grant'], b.get('facts') or [], req)
                return nid, rec['status'], {'receipt': rec}
            except SubstrateError as e:
                return nid, 'BLOCKED', {'error': '%s: %s' % (e.code, str(e)[:160])}
            except Exception as e:  # noqa: BLE001 - unknown outcome: reported, never retried
                return nid, 'INCONCLUSIVE', {'error': type(e).__name__}

        def skip_dependents():
            changed = True
            while changed:
                changed = False
                for nid in status:
                    if status[nid] == 'PENDING' and any(status[d] not in OK + ('PENDING', 'RUNNING') for d in deps[nid]):
                        bad = [d for d in deps[nid] if status[d] not in OK + ('PENDING', 'RUNNING')]
                        status[nid] = 'SKIPPED'; detail[nid] = {'reason': 'dependency %s %s' % (bad[0], status[bad[0]])}
                        changed = True

        with ThreadPoolExecutor(max_workers=wf['max_parallel'], thread_name_prefix='wf') as pool:
            running = {}
            while True:
                skip_dependents()
                if cancel.is_set():
                    for nid in status:
                        if status[nid] == 'PENDING':
                            status[nid] = 'CANCELLED'
                ready = [nid for nid in status if status[nid] == 'PENDING' and all(status[d] in OK for d in deps[nid])]
                for nid in ready[:max(0, wf['max_parallel'] - len(running))]:
                    status[nid] = 'RUNNING'
                    running[pool.submit(run_node, nid)] = nid
                if not running:
                    break
                finished, _ = wait(list(running), return_when=FIRST_COMPLETED)
                for f in finished:
                    nid, st, info = f.result()
                    running.pop(f)
                    status[nid], detail[nid] = st, info
        ok = [k for k, v in status.items() if v in OK]
        overall = ('COMPLETED' if len(ok) == len(status) else 'CANCELLED' if cancel.is_set() and len(ok) < len(status)
                   else 'PARTIAL' if ok else 'FAILED')
        rec = {'operation_id': operation_id, 'workflow_hash': manifest_hash(wf), 'workflow_id': wf['workflow_id'],
               'wgrant_id': wgrant['wgrant_id'], 'status': overall,
               'nodes': [{'node_id': n['node_id'], 'status': status[n['node_id']],
                          'operation_id': node_operation_id(operation_id, n['node_id']),
                          'receipt_signature': (detail.get(n['node_id'], {}).get('receipt') or {}).get('signature'),
                          'error': detail.get(n['node_id'], {}).get('error') or detail.get(n['node_id'], {}).get('reason')}
                         for n in order],
               'started_at': iso(started), 'finished_at': iso(self.s.clock())}
        rec['signature'] = self._sign('wf-receipt', rec)
        with self._lock:
            self.receipts.append(rec)
            del self.receipts[:-100]
        return rec

    def verify_receipt(self, rec):
        body = {k: v for k, v in rec.items() if k != 'signature'}
        return hmac.compare_digest(self._sign('wf-receipt', body), str(rec.get('signature', '')))
