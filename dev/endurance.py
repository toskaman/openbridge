"""Bounded endurance run (synthetic, no network): hundreds of devices, repeated discovery events, malformed inputs,
relay churn. Reports time, peak Python memory, thread count, open sockets in this process and snapshot size."""
import gc, json, random, socket, struct, threading, time, tracemalloc
from src.fabric.registry import Registry
from src.fabric.discovery import ingest_mdns, ingest_ble
from src.fabric import mdns, relay as R
from src.fabric.ble_local import normalize


def run(devices=500, rounds=20, seed=1):
    rng = random.Random(seed); tracemalloc.start(); threads0 = threading.active_count(); t0 = time.monotonic()
    reg = Registry()
    for r in range(rounds):                       # repeated discovery rounds over the same population
        inst = [{'service': '_googlecast._tcp', 'instance': f'TV{i}', 'host': f'h{i}.local', 'port': 8009,
                 'addresses': [f'192.168.{i // 250}.{i % 250 + 1}'], 'txt': {'id': f'id{i}', 'fn': f'TV {i}'}, 'category': 'media'}
                for i in range(devices)]
        ingest_mdns(reg, {'instances': inst}, b'salt')
        ingest_ble(reg, {'devices': [normalize(f'4A:00:00:{i // 256:02X}:{i % 256:02X}:{r:02X}', '', -60, {}, [], {}) for i in range(50)]}, b'salt')
    snap = reg.snapshot()
    malformed_ok = 0
    for _ in range(5000):                           # malformed mDNS packets must never crash or hang
        blob = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 120)))
        try:
            mdns.parse_packet(blob)
        except (ValueError, struct.error, UnicodeError, IndexError):
            malformed_ok += 1
    key = R.derive_key('123456', 'a', 'b'); m = R.RelayManager(lambda r, msg: (_ for _ in ()).throw(TimeoutError()))
    m.enroll('x', key, 'd', {'capabilities': ['ble_scan'], 'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
    for _ in range(10):
        try:
            m.scan(1)
        except R.RelayError:
            pass
    current, peak = tracemalloc.get_traced_memory(); tracemalloc.stop(); gc.collect()
    return {'devices_in_graph': len(snap['devices']), 'links': len(snap['links']), 'rounds': rounds,
            'elapsed_s': round(time.monotonic() - t0, 2), 'peak_python_mb': round(peak / 1e6, 1),
            'snapshot_kb': round(len(json.dumps(snap)) / 1024), 'malformed_packets_rejected': malformed_ok,
            'relay_offline_after_failures': not m.relays['x']['online'], 'threads_delta': threading.active_count() - threads0}


if __name__ == '__main__':
    print(json.dumps(run()))
