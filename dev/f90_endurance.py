"""F90 long-session endurance harness (Campaign One S3.5).

Repeatedly exercises the SIMULATED device fabric over controlled intervals and
measures resource behaviour: CPU, memory growth, thread count, socket count,
queue depth, journal size, dispatch latency and error rates. Ends with a
graceful-shutdown drill after heavy use.

Event-driven, bounded concurrency, no wasteful polling:
  - one scheduler thread paces cycle jobs with Event.wait(deadline) wakeups;
  - a fixed worker pool blocks on a bounded Queue (backpressure, never spins);
  - one sampler thread wakes on Event.wait(interval) and snapshots resources;
  - simulated transport latency waits on the stop Event so shutdown preempts it.

Simulated only: no network, no BLE radio, no ADB. The journal lives in a
temporary directory that is removed at shutdown. Deterministic per seed:
injected faults are a function of the cycle sequence number, not of thread
interleaving, so op/error totals reproduce exactly for a fixed seed.

Usage:
    python -m dev.f90_endurance [--duration 90] [--rate 4] [--workers 4]
                                [--devices 120] [--relays 8] [--seed 7]
                                [--json-out out.json]
"""
import argparse
import json
import os
import queue
import random
import secrets
import statistics
import sys
import tempfile
import threading
import time
import tracemalloc

from src.fabric import relay as R
from src.fabric.ble_local import normalize as ble_normalize
from src.fabric.discovery import ingest_ble, ingest_mdns
from src.fabric.registry import Registry
from src.fabric.session import KINDS, SessionJournal

try:
    import psutil
except Exception:  # optional: fall back to stdlib-only measurements
    psutil = None

SALT = b'f90-endurance-salt'
PAIR_CODE = '123456'
DECLARED = {'capabilities': ['ble_scan'],
            'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}}
JOURNAL_POOL = [('adb_network_connected', 'TV Salon', {'address': '192.168.1.21:5555'}),
                ('bluetooth_turned_on', 'Pixel 8', {'serial': 'emulator-5554'}),
                ('system_package_enabled', 'Pixel 8', {'serial': 'emulator-5554', 'package': 'com.example.app'}),
                ('freebox_app_authorized', 'Freebox', {'app_id': 'f90.endurance'}),
                ('companion_installed', 'Pixel 8', {'serial': 'emulator-5554'})]
SENTINEL = object()
SHUTDOWN_JOIN_S = 10.0


def _signed_reply(key, params):
    now = int(time.time())
    msg = {'protocol': R.PROTOCOL, 'op': 'reply', 'params': params,
           'nonce': secrets.token_hex(12), 'issued_at': now,
           'expires_at': now + R.COMMAND_TTL}
    return {**msg, 'mac': R.sign(key, msg)}


class SimRelay:
    """One simulated relay endpoint. Knows its id/nonce; pairs honestly."""

    def __init__(self, relay_id, rng):
        self.relay_id = relay_id
        self.relay_nonce = secrets.token_hex(16)
        self.pc_nonce = None
        self.key = None
        self.rng = rng

    def pair_hello(self, pc_nonce):
        self.pc_nonce = pc_nonce
        return {'protocol': R.PROTOCOL, 'relay_id': self.relay_id,
                'relay_nonce': self.relay_nonce}

    def pair_key(self):
        return R.derive_key(PAIR_CODE, self.relay_nonce, self.pc_nonce)

    def observations(self, seq):
        rng = random.Random(seq * 7919 + 13)
        return [{'address': 'C0:%02X:%02X:%02X:%02X:%02X' % tuple(rng.randrange(256) for _ in range(5)),
                 'name': 'SimBeacon-%d' % rng.randrange(50),
                 'rssi': rng.randrange(-90, -40),
                 'company_ids': [rng.choice([76, 117, 224, 343])],
                 'service_uuids': [],
                 'address_kind': 'static_random'} for _ in range(rng.randrange(3, 9))]


class Fabric:
    """Simulated fabric under test: registry + relay manager + journal."""

    def __init__(self, journal_path, n_relays, seed, stop=None):
        self.registry = Registry()
        self.journal = SessionJournal(path=journal_path)
        self.sims = {}
        self.manager = R.RelayManager(self.transport)
        self.lock = threading.RLock()  # serializes manager calls (eligible iterates)
        self.stop = stop or threading.Event()
        self._m = threading.Lock()  # guards ops/errors/latency/depth counters
        self.latency_ms = []
        self.errors = {}
        self.ops = {'discover': 0, 'dispatch': 0, 'pair': 0, 'revoke': 0,
                    'journal': 0, 'flap': 0}
        self.max_queue_depth = 0
        self.devices = 0
        self.links = 0
        base = random.Random(seed)
        for i in range(n_relays):
            self._add_sim('f90-relay-%02d' % i, base.randrange(1 << 30))

    def _add_sim(self, relay_id, seed):
        sim = SimRelay(relay_id, random.Random(seed))
        self.sims[relay_id] = sim
        return sim

    # -- simulated wire -------------------------------------------------
    def _latency(self, lo=0.001, hi=0.006):
        # Interruptible wait on the stop Event: shutdown preempts latency.
        self.stop.wait(random.Random().uniform(lo, hi))

    def _fault(self, seq):
        # Deterministic fault schedule from the cycle sequence number.
        if seq % 97 == 60:
            return 'malformed'
        if seq % 131 == 100:
            return 'timeout'
        return None

    def transport(self, relay, message):
        rid = message.get('relay_id')
        sim = self.sims.get(rid)
        self._latency()
        if sim is None:
            raise R.RelayError('Unknown simulated relay')
        op = message.get('op')
        if op == 'start_discovery':
            fault = getattr(threading.current_thread(), '_f90_fault', None)
            if fault == 'timeout':
                raise TimeoutError('sim link down')
            if fault == 'malformed':
                return {'bogus': 'unsigned'}
            seq = getattr(threading.current_thread(), '_f90_seq', 0)
            return _signed_reply(relay['key'], {'observations': sim.observations(seq)})
        if op in ('stop_discovery', 'revoke_access', 'get_status'):
            return _signed_reply(relay['key'], {})
        raise R.RelayError('Sim relay refuses op ' + str(op))

    def pair_send(self, _relay, message):
        self._latency()
        if message.get('op') == 'pair_request':
            sim = self.sims[message['_f90_target']]
            return sim.pair_hello(message['pc_nonce'])
        rid = message.get('relay_id')
        sim = self.sims[rid]
        R.verify(sim.pair_key(), message, None)  # device side checks the PC
        if message.get('op') != 'discover_capabilities':
            raise R.RelayError('Sim relay refuses op ' + str(message.get('op')))
        return _signed_reply(sim.pair_key(), dict(DECLARED))

    # -- cycle operations ------------------------------------------------
    def _pair_sender(self, relay_id):
        def send(relay, message):
            if message.get('op') == 'pair_request':
                # Hello is unsigned: tag the target. Signed commands pass
                # through byte-identical so the device-side MAC check holds.
                message = {**message, '_f90_target': relay_id}
            return self.pair_send(relay, message)

        return send

    def do_pair(self, relay_id):
        rid, key, declared = R.pair(self._pair_sender(relay_id), lambda: PAIR_CODE)
        with self.lock:
            self.manager.enroll(rid, key, 'dev-sim', declared)
        with self._m:
            self.ops['pair'] += 1
        return rid

    def do_revoke(self, relay_id):
        with self.lock:
            self.manager.revoke(relay_id)
        with self._m:
            self.ops['revoke'] += 1

    def do_churn(self, relay_id):
        # One atomic revoke+re-pair: concurrent dispatches never see a gap,
        # so error totals stay deterministic regardless of interleaving.
        with self.lock:
            self.manager.revoke(relay_id)
            rid, key, declared = R.pair(self._pair_sender(relay_id), lambda: PAIR_CODE)
            self.manager.enroll(rid, key, 'dev-sim', declared)
        with self._m:
            self.ops['revoke'] += 1
            self.ops['pair'] += 1

    def do_dispatch(self, relay_id, seq):
        thread = threading.current_thread()
        thread._f90_seq = seq
        thread._f90_fault = self._fault(seq)
        started = time.perf_counter()
        try:
            with self.lock:
                self.manager.scan(seconds=1, relay_id=relay_id)
        finally:
            thread._f90_fault = None
        with self._m:
            self.latency_ms.append((time.perf_counter() - started) * 1000.0)
            self.ops['dispatch'] += 1

    def do_discover(self, seq, population):
        rng = random.Random(seq)
        batch = rng.sample(population, min(12, len(population)))
        inst = [{'service': '_googlecast._tcp', 'instance': 'TV%d' % i,
                 'host': 'h%d.local' % i, 'port': 8009,
                 'addresses': ['192.168.%d.%d' % (i // 250, i % 250 + 1)],
                 'txt': {'id': 'id%d' % i, 'fn': 'TV %d' % i}, 'category': 'media'}
                for i in batch]
        # Two rotating newcomers per cycle from a fixed pool of 40: bounded churn.
        base = (seq * 2) % 40
        for i in (100000 + base, 100000 + base + 1):
            inst.append({'service': '_googlecast._tcp', 'instance': 'Guest%d' % i,
                         'host': 'g%d.local' % i, 'port': 8009,
                         'addresses': ['192.168.9.%d' % (i % 250 + 1)],
                         'txt': {'id': 'guest%d' % i, 'fn': 'Guest %d' % i},
                         'category': 'media'})
        ingest_mdns(self.registry, {'instances': inst}, SALT)
        ble = [ble_normalize('C0:AA:%02X:%02X:00:%02X' % (seq % 64, i, i), 'Beacon%d' % i,
                             -60 - (i % 20), {76: b'x'}, [], {})
               for i in range(8)]  # 512 distinct static beacons max: repeat and merge
        if seq % 4 == 0:  # sparse rotating private address: weak, never merges, stays rare
            ble.append(ble_normalize('41:00:00:00:%02X:%02X' % ((seq // 4) % 64, seq % 8), '', -70, {}, [], {}))
        ingest_ble(self.registry, {'devices': ble}, SALT)
        with self._m:
            self.ops['discover'] += 1

    def do_journal(self, seq):
        kind, label, target = JOURNAL_POOL[seq % len(JOURNAL_POOL)]
        assert kind in KINDS
        change_id = self.journal.record(kind, label, dict(target),
                                        before=3 if kind == 'system_package_enabled' else 'off',
                                        after='on')
        if seq % 2:
            self.journal.close(change_id, 'RESTORED', 'endurance drill')
        with self._m:
            self.ops['journal'] += 1

    def do_flap(self):
        """Force one relay offline (3 transport failures) then recover it."""
        rid = sorted(self.sims)[0]
        thread = threading.current_thread()
        with self.lock:  # atomic vs concurrent dispatches: no interleaving errors
            thread._f90_fault = 'timeout'
            try:
                for _ in range(3):
                    try:
                        self.manager.scan(seconds=1, relay_id=rid)
                    except R.RelayError:
                        pass
            finally:
                thread._f90_fault = None
            offline = not self.manager.relays[rid]['online']
            self.manager.revoke(rid)
            fresh, key, declared = R.pair(self._pair_sender(rid), lambda: PAIR_CODE)
            self.manager.enroll(fresh, key, 'dev-sim', declared)
            recovered = rid in self.manager.eligible('ble_scan')
        with self._m:
            self.ops['flap'] += 1
            self.ops['revoke'] += 1
            self.ops['pair'] += 1
        return offline and recovered

    def note_error(self, error):
        name = type(error).__name__
        with self._m:
            self.errors[name] = self.errors.get(name, 0) + 1

    def note_depth(self, depth):
        with self._m:
            if depth > self.max_queue_depth:
                self.max_queue_depth = depth


class Sampler(threading.Thread):
    """Wakes on stop.wait(interval); snapshots process resources. Daemon-free, joined."""

    def __init__(self, stop, journal_path, interval):
        super().__init__(name='f90-sampler', daemon=False)
        self.stop = stop
        self.journal_path = journal_path
        self.interval = interval
        self.samples = []
        self.proc = psutil.Process() if psutil else None
        if self.proc is not None:
            try:
                self.proc.cpu_percent()
            except Exception:
                pass

    def snapshot(self):
        sample = {'t': round(time.monotonic(), 2),
                  'threads': threading.active_count()}
        if self.proc is not None:
            try:
                sample['rss_mb'] = round(self.proc.memory_info().rss / 1e6, 1)
                sample['cpu_pct'] = self.proc.cpu_percent()
                conns = self.proc.net_connections(kind='inet')
                sample['sockets'] = len(conns)
            except Exception:
                pass
        try:
            sample['journal_bytes'] = os.path.getsize(self.journal_path)
        except OSError:
            sample['journal_bytes'] = 0
        return sample

    def run(self):
        while not self.stop.wait(self.interval):
            self.samples.append(self.snapshot())
        self.samples.append(self.snapshot())


def _worker(fabric, jobs, population, relay_ids):
    while True:
        job = jobs.get()  # blocks: no polling
        try:
            if job is SENTINEL:
                return
            seq = job
            try:
                fabric.do_discover(seq, population)
            except Exception as error:
                fabric.note_error(error)
            try:
                fabric.do_dispatch(relay_ids[seq % len(relay_ids)], seq)
            except Exception as error:
                fabric.note_error(error)
            try:
                fabric.do_journal(seq)
            except Exception as error:
                fabric.note_error(error)
            if seq % 25 == 24:  # revoke/re-pair churn on a rotating relay
                rid = relay_ids[(seq // 25) % len(relay_ids)]
                try:
                    fabric.do_churn(rid)
                except Exception as error:
                    fabric.note_error(error)
            if seq % 60 == 59:  # offline -> re-enroll recovery drill
                try:
                    if not fabric.do_flap():
                        fabric.note_error(AssertionError('flap recovery failed'))
                except Exception as error:
                    fabric.note_error(error)
        finally:
            jobs.task_done()


def run(*, cycles=None, duration=90.0, rate=4.0, workers=4, devices=120,
        relays=8, seed=7, sample_interval=2.0, stop=None):
    """Run the endurance session. Returns a JSON-serializable report dict.

    Give `cycles` for an exact deterministic count, else `duration * rate`
    cycles paced at `rate` per second. Wall time stays near cycles/rate.
    An external `stop` Event (e.g. SIGINT) ends issuing early; shutdown still
    drains gracefully and the report marks `issued < cycles`.
    """
    if cycles is None:
        cycles = max(1, int(duration * rate))
    t0 = time.monotonic()
    cpu0 = time.process_time()
    threads0 = threading.active_count()
    tracemalloc.start()
    tmp = tempfile.TemporaryDirectory(prefix='f90-endurance-')
    journal_path = os.path.join(tmp.name, 'session-changes.json')
    fabric = Fabric(journal_path, relays, seed, stop=stop)
    for rid in sorted(fabric.sims):
        fabric.do_pair(rid)  # enroll the whole pool through the real pair path
    population = list(range(devices))
    jobs = queue.Queue(maxsize=max(4, workers * 2))
    sampler = Sampler(fabric.stop, journal_path, sample_interval)
    sampler.snapshot0 = sampler.snapshot()
    sampler.start()
    pool = [threading.Thread(target=_worker, name='f90-worker-%d' % i,
                             args=(fabric, jobs, population, sorted(fabric.sims)),
                             daemon=True) for i in range(workers)]
    for thread in pool:
        thread.start()
    # Scheduler: event-driven pacing, backpressure counted, never spins.
    interval = 1.0 / rate
    deadline = time.monotonic()
    issued, shed = 0, 0
    for seq in range(cycles):
        deadline += interval
        if fabric.stop.wait(max(0.0, deadline - time.monotonic())):
            break  # external stop (SIGINT): fall through to graceful shutdown
        try:
            jobs.put(seq, timeout=interval * workers + 5.0)
            issued += 1
            fabric.note_depth(jobs.qsize())
        except queue.Full:
            shed += 1
    # Graceful shutdown drill after heavy use: drain, sentinel each worker,
    # bounded joins, then verify the process returned to baseline.
    drain0 = time.monotonic()
    sentinels_landed = 0
    for _ in pool:
        try:
            jobs.put(SENTINEL, timeout=SHUTDOWN_JOIN_S)
            sentinels_landed += 1
        except queue.Full:
            break
    for thread in pool:
        thread.join(timeout=SHUTDOWN_JOIN_S)
    workers_hung = [thread.name for thread in pool if thread.is_alive()]
    fabric.stop.set()
    sampler.join(timeout=SHUTDOWN_JOIN_S)
    pending = jobs.qsize()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    snap = fabric.registry.snapshot()
    fabric.devices, fabric.links = len(snap['devices']), len(snap['links'])
    journal_rows = fabric.journal.open_changes()
    try:
        journal_bytes = os.path.getsize(journal_path)
    except OSError:
        journal_bytes = 0
    debris = [name for name in os.listdir(tmp.name) if name.endswith('.tmp')]
    journal_dir = tmp.name
    tmp.cleanup()
    wall = time.monotonic() - t0
    lat = sorted(fabric.latency_ms)

    def pct(p):
        return round(lat[min(len(lat) - 1, int(p * len(lat)))] if lat else 0.0, 2)

    samples = sampler.samples
    rss = [s['rss_mb'] for s in samples if 'rss_mb' in s]
    cpu = [s['cpu_pct'] for s in samples if 'cpu_pct' in s]
    socks = [s['sockets'] for s in samples if 'sockets' in s]
    threads_peak = max([threads0] + [s['threads'] for s in samples])
    ops_total = sum(fabric.ops.values())
    err_total = sum(fabric.errors.values())
    live_f90 = [t.name for t in threading.enumerate()
                if t.is_alive() and t.name.startswith('f90-')]
    delta_threads = threading.active_count() - threads0
    # The harness must add no threads (delta <= 0: an unrelated outside thread
    # may legitimately exit mid-run) and leave none of its own behind.
    graceful = (not workers_hung and pending == 0 and not debris
                and sentinels_landed == len(pool)
                and not live_f90 and delta_threads <= 0)
    return {
        'config': {'cycles': cycles, 'issued': issued, 'shed': shed, 'rate': rate,
                   'workers': workers, 'devices': devices, 'relays': relays,
                   'seed': seed, 'wall_s': round(wall, 1)},
        'ops': dict(fabric.ops),
        'ops_total': ops_total,
        'errors': dict(fabric.errors),
        'error_total': err_total,
        'error_rate': round(err_total / ops_total, 4) if ops_total else 0.0,
        'latency_ms': {'n': len(lat), 'p50': pct(0.50), 'p95': pct(0.95),
                       'max': round(lat[-1], 2) if lat else 0.0},
        'cpu': {'process_time_s': round(time.process_time() - cpu0, 2),
                'avg_pct': round(sum(cpu) / len(cpu), 1) if cpu else None},
        'memory': {'rss_start_mb': sampler.snapshot0.get('rss_mb'),
                   'rss_end_mb': rss[-1] if rss else None,
                   'rss_delta_mb': round(rss[-1] - rss[0], 1) if len(rss) > 1 else 0.0,
                   'peak_python_mb': round(peak / 1e6, 1)},
        'threads': {'start': threads0, 'peak': threads_peak,
                    'end': threading.active_count(),
                    'delta': threading.active_count() - threads0},
        'sockets': {'start': socks[0] if socks else None,
                    'end': socks[-1] if socks else None,
                    'delta': (socks[-1] - socks[0]) if socks else None},
        'queue': {'max_depth': fabric.max_queue_depth, 'pending_at_shutdown': pending},
        'journal': {'bytes': journal_bytes, 'open_entries': len(journal_rows),
                    'tmp_debris': debris, 'dir_removed': not os.path.exists(journal_dir)},
        'fabric': {'devices': fabric.devices, 'links': fabric.links},
        'shutdown': {'graceful': graceful, 'drain_s': round(time.monotonic() - drain0, 2),
                     'workers_hung': workers_hung,
                     'harness_threads_live': live_f90},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='F90 long-session endurance harness')
    parser.add_argument('--duration', type=float, default=90.0)
    parser.add_argument('--cycles', type=int, default=None)
    parser.add_argument('--rate', type=float, default=4.0)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--devices', type=int, default=120)
    parser.add_argument('--relays', type=int, default=8)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--json-out', default=None)
    args = parser.parse_args(argv)
    import signal

    stop = threading.Event()

    def on_sigint(_signum, _frame):
        stop.set()  # scheduler + latency waits wake at once; shutdown stays graceful

    try:
        old = signal.signal(signal.SIGINT, on_sigint)
    except (ValueError, OSError):
        old = None
    try:
        report = run(cycles=args.cycles, duration=args.duration, rate=args.rate,
                     workers=args.workers, devices=args.devices,
                     relays=args.relays, seed=args.seed, stop=stop)
    finally:
        if old is not None:
            try:
                signal.signal(signal.SIGINT, old)
            except (ValueError, OSError):
                pass
    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, indent=1)
    print(json.dumps(report, indent=1))
    print('cycles=%(issued)d shed=%(shed)d wall=%(wall_s)ss graceful=%(graceful)s' % {
        'issued': report['config']['issued'], 'shed': report['config']['shed'],
        'wall_s': report['config']['wall_s'], 'graceful': report['shutdown']['graceful']})
    return 0 if report['shutdown']['graceful'] else 2


if __name__ == '__main__':
    sys.exit(main())




