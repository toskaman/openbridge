"""Campaign Two §4.9 reproducible oracle: portable dashboard bundles.

Simulated only (synthetic registry/relays + FakeCompanion, which mirrors
RelayServer.java). No hardware, no model, no network.

Usage: python -m dev.f90_innov_oracle
Exit 0 + JSON receipt on success; exit 1 + JSON failure otherwise.

Checks:
 1. Golden bundle digest is byte-stable (export determinism, pinned value).
 2. Cross-PC round trip: PC-A exports a live panel; PC-B (fresh registry, so
    all device keys differ) imports it with an explicit target remap and the
    Companion shows the same labels bound to PC-B's keys.
 3. Refusals: tampered bundle, unknown skill, exec skill (pc_run), unmapped
    target hint, missing consent — each refused with no install.
"""
import copy
import json
import sys

GOLDEN_CONTROLS = [
    {'label': 'Volume +', 'skill_id': 'tv_volume_step', 'target': 'hint-tv',
     'params': {'direction': 'up'}},
    {'label': 'Volume -', 'skill_id': 'tv_volume_step', 'target': 'hint-tv',
     'params': {'direction': 'down'}},
    {'label': 'Find robots', 'skill_id': 'ble_scan_room', 'params': {'seconds': 5}},
]
GOLDEN_DIGEST = 'f1cf0a280a1492a9d51994bc997f8cb86202f668fe8ecd70852e5f797260d8cf'

from src.runtime import dashboard_port as P  # noqa: E402
from src.runtime import dashboards as D  # noqa: E402
from src.runtime.api_v2 import remote_controls  # noqa: E402
from src.runtime.state_store import StateStore  # noqa: E402
from tests.runtime.test_remote_controls import FakeCompanion, KEY  # noqa: E402
from tests.runtime.test_routing import Clock, world  # noqa: E402

out = {'oracle': 'f90-innov-dashboard-port', 'checks': {}}


def check(name, fn):
    try:
        out['checks'][name] = fn()
    except Exception as e:  # noqa: BLE001 - oracle reports, never raises
        out['checks'][name] = 'FAILED: %s: %s' % (type(e).__name__, str(e)[:200])


def make_pc():
    clock = Clock()
    server, keys = world(clock)
    companion = FakeCompanion()
    companion.clock = clock
    server.relays.enroll('r-watch', KEY, 'h-ph-1',
                         {'capabilities': ['remote_controls'], 'permissions': {}})
    server.relays.relays['r-watch']['send'] = companion
    rc = remote_controls(server)
    rc.clock = clock
    rc._ensure_thread = lambda: None
    return server, keys, rc, companion


def t_golden():
    b1 = P.export_bundle(name='golden-panel', controls=copy.deepcopy(GOLDEN_CONTROLS))
    b2 = P.export_bundle(name='golden-panel', controls=copy.deepcopy(GOLDEN_CONTROLS))
    assert b1 == b2, 'export is not deterministic'
    assert b1['integrity']['digest'] == GOLDEN_DIGEST, \
        'golden digest moved: %s' % b1['integrity']['digest']
    assert P.verify_bundle(b1) == GOLDEN_DIGEST
    return {'digest': GOLDEN_DIGEST, 'controls': len(b1['controls'])}


def t_round_trip():
    srv_a, keys_a, rc_a, comp_a = make_pc()
    D.create(rc_a, 'r-watch', 'tv', keys_a['tv'])
    before = [c['label'] for c in comp_a.controls]
    store_a = D.DashStore(StateStore.for_server(srv_a))
    store_a.save('r-watch', 'tv-evening', D.defs(rc_a, 'r-watch'))
    bundle = P.export_bundle(store=store_a, name='tv-evening')
    # PC-B: a fresh world; every device key differs (uuid4), like a real 2nd PC.
    srv_b, keys_b, rc_b, comp_b = make_pc()
    assert keys_b['tv'] != keys_a['tv'], 'worlds unexpectedly share keys'
    plan = P.dry_run(bundle, target=keys_b['tv'])
    assert [c['label'] for c in plan['controls']] == before
    assert all(c.get('target', keys_b['tv']) == keys_b['tv']
               for c in plan['controls'] if c['skill_id'] != 'ble_scan_room')
    receipt = P.import_bundle(rc_b, 'r-watch', bundle, target=keys_b['tv'], consent=True)
    after = [c['label'] for c in comp_b.controls]
    assert after == before, '%r != %r' % (after, before)
    live_targets = {c['target'] for c in rc_b.grants['r-watch'].values()}
    assert live_targets == {keys_b['tv']}, live_targets
    return {'labels': after, 'installed': receipt['installed'],
            'digest': receipt['bundle_digest']}


def _expect_refusal(fn):
    try:
        fn()
    except P.PortError as e:
        return str(e)[:120]
    raise AssertionError('expected PortError, install path ran')


def t_refusals():
    bundle = P.export_bundle(name='golden-panel', controls=copy.deepcopy(GOLDEN_CONTROLS))
    res = {}
    tampered = copy.deepcopy(bundle)
    tampered['controls'][0]['label'] = 'Volume MAXXXX'
    res['tamper'] = _expect_refusal(lambda: P.verify_bundle(tampered))
    res['consent'] = _expect_refusal(
        lambda: P.import_bundle(None, 'r-x', bundle, target='k', consent=False))
    res['unmapped'] = _expect_refusal(lambda: P.dry_run(bundle))
    evil = copy.deepcopy(GOLDEN_CONTROLS)
    evil[0]['skill_id'] = 'nope_not_a_skill'
    try:
        P.export_bundle(name='evil', controls=evil)
        raise AssertionError('unknown skill exported')
    except P.PortError as e:
        res['unknown_skill'] = str(e)[:120]
    pc = copy.deepcopy(GOLDEN_CONTROLS)
    pc[0] = {'label': 'Run', 'skill_id': 'pc_run', 'target': 'hint-pc', 'params': {'command': 'x'}}
    try:
        P.export_bundle(name='pc', controls=pc)
        raise AssertionError('pc_run exported')
    except P.PortError as e:
        res['exec_skill'] = str(e)[:120]
    return res


check('golden_digest_stable', t_golden)
check('cross_pc_round_trip', t_round_trip)
check('refusals', t_refusals)

failed = [k for k, v in out['checks'].items() if isinstance(v, str) and v.startswith('FAILED')]
out['outcome'] = 'FAILED' if failed else 'PASS'
print(json.dumps(out, indent=2, sort_keys=True))
sys.exit(1 if failed else 0)
