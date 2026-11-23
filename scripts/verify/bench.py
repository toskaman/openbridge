"""Micro-benchmarks with absolute ceilings (standard library only).

Measures the hot paths that must stay instant on a modest PC, and fails when
one exceeds its ceiling (a gross regression or an asphyxiated machine, not a
5% wobble: ceilings sit ~10x above a typical laptop so CI stays green across
runners).

    python scripts/verify/bench.py              # measure and check ceilings
    python scripts/verify/bench.py --save       # also write bench-baseline.json (git-ignored)
    python scripts/verify/bench.py --compare    # fail when 3x slower than the saved baseline

CI runs the plain form (see .github/workflows/verify.yml, job "bench").
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

BASELINE = ROOT / 'bench-baseline.json'

# name -> (repeats, ceiling seconds for the whole batch)
PLAN = {'skill_validate': (200, 5.0),
        'pack_validate_all': (20, 10.0),
        'cpace_handshake': (1, 10.0),
        'x25519_op': (3, 10.0),
        'skill_match': (200, 5.0),
        'library_run': (20, 10.0)}


def bench_skill_validate(n):
    from src.runtime import skill_library as SL
    recipe = {'name': 'Bench', 'description': '',
              'trigger': {'kind': 'state', 'device': 'dev_tv', 'state': 'playing'},
              'steps': [{'device': 'dev_lamp', 'primitive': 'ha_set',
                         'params': {'action': 'set_brightness', 'value': 20}}]}
    for _ in range(n):
        SL.validate(recipe)
        SL.fingerprint(recipe)


def bench_pack_validate_all(n):
    from src.runtime import skill_packs as SP
    packs = SP.available()
    assert packs, 'no pinned packs found'
    devices = {'tv1': {'category': 'media_player', 'label': 'TV'},
               'rb1': {'category': 'robot', 'label': 'Robot'},
               'lt1': {'category': 'light', 'label': 'Lamp'},
               'pl1': {'category': 'plug', 'label': 'Plug'},
               'th1': {'category': 'thermostat', 'label': 'Heat'},
               'cv1': {'category': 'cover', 'label': 'Blind'},
               'lk1': {'category': 'lock', 'label': 'Lock'}}
    for _ in range(n):
        for p in packs:
            SP.validate(p)
            mapping, _, _ = SP.auto_map(p, devices)
            if len(mapping) == len(p['roles']):
                SP.resolve(p, devices, mapping)


def bench_cpace_handshake(n):
    from src.fabric import cpace as C
    for _ in range(n):
        g = C.generator(b'654321', b'bench-relay', bytes(range(64)))
        ya, Ya = C.share(g)
        yb, Yb = C.share(g)
        assert C.isk(ya, Yb, bytes(range(64)), Ya, Yb) == C.isk(yb, Ya, bytes(range(64)), Ya, Yb)


def bench_x25519_op(n):
    from src.fabric.cpace import x25519
    k, u = bytes(range(32)), bytes([9] + [0] * 31)
    for _ in range(n):
        x25519(k, u)


def bench_skill_match(n):
    from src.runtime import skills as S
    for q in ('allume la lampe', 'dim the lights', 'start vacuum', 'verrouille la porte',
              'suggest ideas', 'volume up tv', 'ouvre les volets', 'undo'):
        for _ in range(max(1, n // 8)):
            S.match(q)


class _Ex:
    def execute(self, primitive, device, params, consent=False):
        return {'state': 'VERIFIED', 'verified': True, 'errors': [], 'transaction_id': 'tx-bench'}


def bench_library_run(n):
    from src.runtime.skill_library import Library
    lib = Library(_Ex(), persist=False)
    r = lib.add({'name': 'Bench', 'description': '',
                 'trigger': {'kind': 'manual'},
                 'steps': [{'device': 'd1', 'primitive': 'ha_set', 'params': {'action': 'turn_on'}},
                           {'device': 'd2', 'primitive': 'ha_set', 'params': {'action': 'turn_off'}}]})
    lib.approve(r['id'])
    for _ in range(n):
        out = lib.run(r['id'], actor='bench')
        assert out['result'] == 'done', out


BENCHES = {'skill_validate': bench_skill_validate, 'pack_validate_all': bench_pack_validate_all,
           'cpace_handshake': bench_cpace_handshake, 'x25519_op': bench_x25519_op,
           'skill_match': bench_skill_match, 'library_run': bench_library_run}


def run():
    results = {}
    for name, (repeats, ceiling) in PLAN.items():
        t0 = time.perf_counter()
        BENCHES[name](repeats)
        dt = time.perf_counter() - t0
        results[name] = {'repeats': repeats, 'seconds': round(dt, 3),
                         'per_op_ms': round(dt / repeats * 1000, 3), 'ceiling': ceiling,
                         'ok': dt <= ceiling}
    return results


def main(argv):
    results = run()
    for name, r in results.items():
        print('%-20s %7.3fs / %4d ops (%8.3f ms/op) ceiling %5.1fs  %s'
              % (name, r['seconds'], r['repeats'], r['per_op_ms'], r['ceiling'],
                 'OK' if r['ok'] else 'OVER CEILING'))
    failed = [n for n, r in results.items() if not r['ok']]
    if '--save' in argv:
        BASELINE.write_text(json.dumps({'results': results}, indent=1), encoding='utf-8')
        print('baseline saved to %s' % BASELINE.name)
    if '--compare' in argv:
        if not BASELINE.exists():
            print('no baseline file; run with --save first')
            return 2
        base = json.loads(BASELINE.read_text(encoding='utf-8'))['results']
        for name, r in results.items():
            old = base.get(name, {}).get('seconds')
            if old and r['seconds'] > max(0.5, 3 * old):
                print('%s regressed: %.3fs vs baseline %.3fs' % (name, r['seconds'], old))
                failed.append(name + ' (vs baseline)')
    if failed:
        print('BENCH FAILED: %s' % ', '.join(failed))
        return 1
    print('BENCH OK (%d measures within ceiling)' % len(results))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
