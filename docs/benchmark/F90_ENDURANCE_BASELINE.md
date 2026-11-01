# F90 Endurance Baseline (Campaign One §3.5)

Long-session endurance of the simulated device fabric: repeated
discover / pair / dispatch / revoke cycles over controlled intervals,
with resource measurements and a graceful-shutdown drill after heavy use.

- Harness: `dev/f90_endurance.py` (`python -m dev.f90_endurance`)
- Tests: `tests/fabric/test_f90_endurance.py` (7 tests)
- Method: fully simulated wire (no network, BLE radio, or ADB). Registry +
  RelayManager are the real `src/fabric` code; relay endpoints are in-memory
  simulators that sign honest replies, plus a deterministic fault schedule
  (malformed reply, transport timeout) and periodic offline→re-enroll drills.
- Design: event-driven pacing (`Event.wait` deadlines), fixed worker pool on
  a bounded queue (backpressure counted, never spins), interruptible
  simulated latency, bounded joins at shutdown.

## Baseline run (2026-11-01, Windows, Python 3.14.4, seed 7)

Config: 360 cycles at 4/s, 4 workers, 120-device population, 8-relay pool.
Wall time **92.7 s** (budget: < ~3 min).

| Metric | Baseline | Notes / threshold |
|---|---|---|
| Cycles issued / shed | 360 / 0 | shed must stay 0 (no backpressure loss) |
| Ops total | 1128 (360 discover, 354 dispatch ok, 28 pair, 20 revoke, 360 journal, 6 flap) | exact per seed |
| Errors | 6 × RelayError (4 malformed, 2 timeout, all injected) | error_rate 0.0053; must stay < 0.05 and contain only injected classes |
| Dispatch latency p50 / p95 / max | 30.4 / 45.5 / 290 ms (n=354 ok) | max spike = dispatch queued behind an atomic flap (3 scans + PBKDF2 re-pair under one lock); p95 must stay < 250 ms |
| CPU process_time / avg | 16.2 s / 15.7% | ~17% of one core; avg must stay < 60% |
| RSS start → end (Δ) | 28.2 → 35.0 MB (+5.4) | ~15 KB/cycle of legitimate state (registry + journal rows); Δ must stay < 40 MB per 360-cycle session |
| Peak Python (tracemalloc) | 2.7 MB | must stay < 50 MB |
| Threads start / peak / end | 1 / 6 / 1 (Δ 0) | peak = main + 4 workers + sampler; Δ must be ≤ 0 |
| Sockets start / end (Δ) | 0 / 0 (0) | simulated wire opens none; Δ must be 0 |
| Queue max depth / pending | 1 / 0 | bounded queue (maxsize 8); pending must be 0 |
| Journal bytes / open | 71,574 B / 2 | ~200 B/cycle linear summary growth; no `.tmp` debris; temp dir removed |
| Fabric devices / links | 762 / 762 | far under the 2000-device cap; must stay < 1500 at this scale |
| Shutdown graceful / drain | true / 0.42 s | no hung workers, no live harness threads; drain must stay < 10 s |

## How to re-run

```bash
python -m dev.f90_endurance --duration 90 --rate 4 --workers 4 \
    --devices 120 --relays 8 --seed 7 --json-out endurance.json
python -m unittest tests.fabric.test_f90_endurance -v
```

Expected: exit 0, `graceful=True`, `shed=0`, `error_rate≈0.005`,
`threads.delta≤0`, `sockets.delta=0`, no `.tmp` debris.

## Findings

1. Registry growth is bounded and merge-dominated: 360 discovery rounds over
   a 120-device population plus fixed churn pools settle at 762 devices.
2. Journal grows linearly (~200 B/cycle, all CLOSED history rows) while open
   entries stay ≤ 5. A production long-run would want journal rotation;
   recorded here as future work, not a failure.
3. Dispatch p95 is stable (~45 ms); the max (~290 ms) is lock queueing behind
   the atomic flap drill, by design (atomicity keeps error totals
   deterministic). Not a tail-latency regression.
4. No thread, socket, queue, or temp-file leakage across the session.
