"""§7 multi-device orchestration: dependency-aware workflow runtime.

A workflow is a DAG of steps dispatched through the REAL Router
(skill_routes -> arm -> invoke), never a parallel command system. Steps in
one level run in parallel; levels run in order. Conditions, approvals,
timeouts, cancellation, partial failure and durable per-step receipts are
all first-class. Retrying a workflow id never dispatches twice: step
invocation ids are deterministic (wf-<workflow>-<step>) and terminal
records are returned as-is.
"""
import concurrent.futures
import copy
import re
import threading
import time
from datetime import datetime, timezone

MAX_STEPS = 32
MAX_WORKERS = 4
DEFAULT_TIMEOUT_S = 120
MAX_JOURNAL = 32
TERMINAL = ('done', 'partial', 'failed', 'cancelled')

_ID = re.compile(r'[A-Za-z0-9_-]{1,64}')

# §14: one in-process lock per workflow id. Concurrent run/approve/cancel for
# the same id serialize; the store stays the source of truth (terminal records
# short-circuit inside the lock), so lock churn can never double-dispatch.
_RUN_LOCKS = {}
_RUN_LOCKS_GUARD = threading.Lock()


def _lock_for(workflow_id):
    with _RUN_LOCKS_GUARD:
        return _RUN_LOCKS.setdefault(workflow_id, threading.Lock())


def _release_lock(workflow_id, store):
    with _RUN_LOCKS_GUARD:
        try:
            terminal = (store.get(workflow_id) or {}).get('status') in TERMINAL
        except Exception:
            terminal = False
        if terminal:
            _RUN_LOCKS.pop(workflow_id, None)


class WorkflowError(ValueError):
    pass


def _iso(ts=None):
    return datetime.fromtimestamp(ts if ts is not None else time.time(),
                                  timezone.utc).isoformat()


def _resolve_path(doc, path):
    cur = doc
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(path)
        cur = cur[part]
    return cur


def _refs_in(node, found):
    if isinstance(node, dict):
        if set(node) == {'$ref'} and isinstance(node['$ref'], str):
            found.append(node['$ref'])
        else:
            for v in node.values():
                _refs_in(v, found)
    elif isinstance(node, list):
        for v in node:
            _refs_in(v, found)


def validate_workflow(body):
    """Validate a workflow body into {levels, steps}. Raises WorkflowError."""
    from src.runtime.routing import SKILLS
    if not isinstance(body, dict):
        raise WorkflowError('workflow body must be an object')
    if body.get('consent') is not True:
        raise WorkflowError('consent: true is required to run a workflow')
    raw = body.get('steps')
    if not isinstance(raw, list) or not raw or len(raw) > MAX_STEPS:
        raise WorkflowError(f'steps must be 1..{MAX_STEPS} items')
    steps = {}
    for s in raw:
        if not isinstance(s, dict):
            raise WorkflowError('each step must be an object')
        sid = s.get('id')
        if not isinstance(sid, str) or not _ID.fullmatch(sid) or sid in steps:
            raise WorkflowError(f'invalid or duplicate step id {sid!r}')
        skill = s.get('skill_id')
        if skill not in SKILLS:
            raise WorkflowError(f'unknown skill {skill!r}')
        target = s.get('target')
        if not isinstance(target, str) or not target or len(target) > 64:
            raise WorkflowError(f'invalid target for step {sid!r}')
        if SKILLS[skill]['targeted'] == (target == 'fabric'):
            raise WorkflowError(
                f"step {sid!r}: untargeted skills take target 'fabric', targeted skills take a device key")
        params = s.get('params') or {}
        if not isinstance(params, dict):
            raise WorkflowError(f'invalid params for step {sid!r}')
        needs = s.get('needs') or []
        if not isinstance(needs, list) or any(n == sid or not isinstance(n, str) for n in needs):
            raise WorkflowError(f'invalid needs for step {sid!r}')
        when = s.get('when')
        if when is not None and (not isinstance(when, dict) or
                                 not isinstance(when.get('step'), str) or
                                 not isinstance(when.get('path'), str) or
                                 'equals' not in when):
            raise WorkflowError(f'invalid when for step {sid!r}')
        timeout = s.get('timeout_s', DEFAULT_TIMEOUT_S)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) \
                or not 0 < timeout <= 600:
            raise WorkflowError(f'invalid timeout_s for step {sid!r}')
        on_fail = s.get('on_fail', 'fail')
        if on_fail not in ('fail', 'continue'):
            raise WorkflowError(f'invalid on_fail for step {sid!r}')
        steps[sid] = {'id': sid, 'skill_id': skill, 'target': target,
                      'params': copy.deepcopy(params), 'needs': list(needs),
                      'when': copy.deepcopy(when) if when else None,
                      'approval': s.get('approval') is True,
                      'timeout_s': timeout, 'on_fail': on_fail}
    for sid, s in steps.items():
        for n in s['needs']:
            if n not in steps:
                raise WorkflowError(f'step {sid!r} needs unknown step {n!r}')
    # Kahn topological levels (input order kept inside a level).
    done, levels, order = set(), [], {}
    remaining = {sid: set(s['needs']) for sid, s in steps.items()}
    while remaining:
        ready = [sid for sid in steps if sid in remaining and remaining[sid] <= done]
        if not ready:
            raise WorkflowError('dependency cycle detected')
        for sid in ready:
            order[sid] = len(levels)
            del remaining[sid]
        done.update(ready)
        levels.append([steps[sid] for sid in ready])
    # Refs and conditions may only point backwards in topological order.
    for sid, s in steps.items():
        refs = []
        _refs_in(s['params'], refs)
        for r in refs:
            head = r.split('.')[0]
            if head not in steps or order[head] >= order[sid]:
                raise WorkflowError(f'step {sid!r} has invalid $ref {r!r}')
        if s['when'] is not None:
            w = s['when']['step']
            if w not in steps or order[w] >= order[sid]:
                raise WorkflowError(f'step {sid!r} has invalid when.step {w!r}')
    return {'levels': levels, 'steps': steps}


class MemoryStore:
    def __init__(self):
        self._d = {}
        self._lock = threading.Lock()

    def get(self, workflow_id):
        with self._lock:
            return copy.deepcopy(self._d.get(workflow_id))

    def save(self, record):
        with self._lock:
            self._d[record['workflow_id']] = copy.deepcopy(record)


class StateStoreJournal:
    """Durable journal: records live under the state file's 'workflows' key."""

    def __init__(self, state_store):
        self._s = state_store

    def get(self, workflow_id):
        try:
            d = self._s.load()
        except Exception:
            return None
        rec = (d.get('workflows') or {}).get(workflow_id)
        return copy.deepcopy(rec) if rec else None

    def save(self, record):
        def change(d):
            wfs = d.setdefault('workflows', {})
            wfs[record['workflow_id']] = copy.deepcopy(record)
            while len(wfs) > MAX_JOURNAL:
                victim = next((k for k in wfs if wfs[k].get('status') in TERMINAL), None)
                if victim is None:
                    break
                del wfs[victim]
        self._s._mutate(change)


def _substitute(params, receipts):
    def one(node):
        if isinstance(node, dict):
            if set(node) == {'$ref'}:
                head, _, path = node['$ref'].partition('.')
                return _resolve_path(receipts[head], path)
            return {k: one(v) for k, v in node.items()}
        if isinstance(node, list):
            return [one(v) for v in node]
        return node
    return one(copy.deepcopy(params))


def _dispatch(router, step, invocation_id, receipts, actor):
    params = _substitute(step['params'], receipts)
    doc = router.skill_routes(step['skill_id'], step['target'])
    route_id = doc['selected_route_id']
    arm = router.arm({'skill_id': step['skill_id'], 'target': step['target'],
                      'params': params, 'route_id': route_id, 'consent': True},
                     actor=actor, invocation_id=invocation_id)
    return router.invoke({'invocation_id': invocation_id,
                          'skill_id': step['skill_id'], 'target': step['target'],
                          'route_id': route_id, 'lease_id': arm['lease_id'],
                          'graph_revision': arm['graph_revision'],
                          'params': params, 'consent': True}, actor=actor)


def _drive(record, spec, router, store, actor):
    states = {s['id']: s for s in record['steps']}
    receipts = {s['id']: s['receipt'] for s in record['steps'] if s.get('receipt')}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for level in spec['levels']:
            if record.get('cancel_requested'):
                record['status'] = 'cancelled'
                break
            # Steps whose needs are all EXECUTED are runnable; anything
            # under a failed/denied/skipped need is SKIPPED, never dropped silently.
            runnable, waiting = [], []
            for step in level:
                st = states[step['id']]
                if st['state'] != 'QUEUED':
                    continue
                needs = [states[n]['state'] for n in step['needs']]
                if any(n in ('FAILED', 'TIMEOUT', 'DENIED', 'SKIPPED') for n in needs):
                    st['state'] = 'SKIPPED'
                    st['note'] = 'a prerequisite did not execute'
                elif step['approval'] and not st.get('approved'):
                    st['state'] = 'WAITING'
                    waiting.append(step)
                else:
                    runnable.append(step)
            futs = {}
            for step in runnable:
                if _when_holds(step, states, receipts):
                    st = states[step['id']]
                    futs[pool.submit(_run_step, router, step, record, receipts,
                                     actor)] = step
                else:
                    states[step['id']]['state'] = 'SKIPPED'
                    states[step['id']]['note'] = 'when condition was false'
            for fut, step in futs.items():
                st = states[step['id']]
                try:
                    receipt = fut.result(timeout=step['timeout_s'])
                except concurrent.futures.TimeoutError:
                    fut.cancel()
                    st['state'] = 'TIMEOUT'
                    st['note'] = f'no result after {step["timeout_s"]}s'
                except Exception as e:  # noqa: BLE001 - step failure is data
                    st['state'] = 'FAILED'
                    st['note'] = f'{type(e).__name__}: {e}'[:300]
                else:
                    rstate = receipt.get('state')
                    if rstate in ('EXECUTED', 'VERIFIED', 'REVERTED'):
                        st['state'] = 'EXECUTED'
                    elif rstate == 'EXECUTED_UNVERIFIED':
                        # Ran but verification is pending: ordering follows the
                        # completed action (dependents run), the workflow verdict
                        # caps at 'partial' until the owner reviews.
                        st['state'] = 'UNVERIFIED'
                    elif rstate in ('TIMEOUT', 'UNKNOWN_TIMEOUT'):
                        st['state'] = 'TIMEOUT'
                    else:
                        st['state'] = 'FAILED'
                    st['receipt'] = receipt
                    receipts[step['id']] = receipt
                    if st['state'] in ('FAILED', 'TIMEOUT'):
                        st['note'] = '; '.join(receipt.get('errors', ()))[:300] or rstate
            store.save(record)
            if waiting:
                record['status'] = 'waiting_approval'
                store.save(record)
                return record
            if record.get('cancel_requested'):
                record['status'] = 'cancelled'
                break
    if record['status'] not in TERMINAL:
        record['status'] = _finalize(states, spec)
        record['finished_at'] = _iso()
    store.save(record)
    return record


def _when_holds(step, states, receipts):
    if step['when'] is None:
        return True
    try:
        return _resolve_path(receipts[step['when']['step']], step['when']['path']) == step['when']['equals']
    except (KeyError, TypeError):
        return False


def invocation_id(workflow_id, step_id):
    """Deterministic Router invocation id (B2 contract: inv- + 32 hex)."""
    import hashlib
    return 'inv-' + hashlib.sha256(f'{workflow_id}\0{step_id}'.encode()).hexdigest()[:32]


def _run_step(router, step, record, receipts, actor):
    return _dispatch(router, step, invocation_id(record['workflow_id'], step['id']), receipts, actor)


def _finalize(states, spec):
    bad = [s for s in states.values() if s['state'] in ('FAILED', 'TIMEOUT', 'DENIED')]
    if any(s['state'] == 'DENIED' for s in states.values()):
        return 'failed'
    if not bad:
        if any(s['state'] == 'UNVERIFIED' for s in states.values()):
            return 'partial'
        return 'done'
    by_id = spec['steps']
    if all(by_id[s['id']]['on_fail'] == 'continue' for s in bad):
        return 'partial'
    return 'failed'


def run(body, router, store, workflow_id, actor='owner'):
    if not isinstance(workflow_id, str) or not _ID.fullmatch(workflow_id):
        raise WorkflowError('invalid workflow id')
    spec = validate_workflow(body)
    lock = _lock_for(workflow_id)
    with lock:
        existing = store.get(workflow_id)
        if existing is not None:
            return existing  # terminal or waiting: never dispatch twice
        record = {'workflow_id': workflow_id, 'status': 'running',
                  'name': body.get('name', '')[:120],
                  'steps': [{'id': s['id'], 'state': 'QUEUED'} for lvl in spec['levels'] for s in lvl],
                  'spec': spec, 'created_at': _iso()}
        store.save(record)
        try:
            return _drive(record, spec, router, store, actor)
        finally:
            _release_lock(workflow_id, store)


def approve(workflow_id, step_id, allow, router, store, actor='owner'):
    with _lock_for(workflow_id):
        record = store.get(workflow_id)
        if record is None or record['status'] != 'waiting_approval':
            raise WorkflowError('workflow is not waiting for approval')
        if record.get('cancel_requested'):
            raise WorkflowError('workflow was cancelled')
        states = {s['id']: s for s in record['steps']}
        if step_id not in states or states[step_id]['state'] != 'WAITING':
            raise WorkflowError('step is not waiting for approval')
        if allow is not True:
            states[step_id]['state'] = 'DENIED'
            record['status'] = 'failed'
            record['finished_at'] = _iso()
            # Dependents of a denied step are SKIPPED, never silently dropped.
            spec = record['spec']
            for lvl in spec['levels']:
                for s in lvl:
                    if states[s['id']]['state'] == 'QUEUED' and \
                            any(states[n]['state'] in ('FAILED', 'TIMEOUT', 'DENIED', 'SKIPPED') for n in s['needs']):
                        states[s['id']]['state'] = 'SKIPPED'
                        states[s['id']]['note'] = 'a prerequisite did not execute'
            store.save(record)
            _release_lock(workflow_id, store)
            return record
        states[step_id]['approved'] = True
        states[step_id]['state'] = 'QUEUED'
        record['status'] = 'running'
        store.save(record)
        try:
            return _drive(record, record['spec'], router, store, actor)
        finally:
            _release_lock(workflow_id, store)


def cancel(workflow_id, store):
    with _lock_for(workflow_id):
        record = store.get(workflow_id)
        if record is None or record['status'] in TERMINAL:
            raise WorkflowError('workflow is not active')
        record['cancel_requested'] = True
        record['status'] = 'cancelled'
        record['finished_at'] = _iso()
        store.save(record)
        return record
