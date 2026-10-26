"""Bounded passive BLE advertisement scan on this PC (optional dependency: bleak). Never connects or pairs.
BLE only: Bluetooth Classic inquiry is not implemented (no reliable cross-OS API in this stack)."""
import asyncio

MAX_SECONDS = 10.0
MAX_DEVICES = 300


def available():
    try:
        import bleak  # noqa: F401
        return True
    except Exception:
        return False


def address_kind(addr):
    """Top two bits of a BLE random address: 11 static (stable until power cycle), 01 resolvable private (rotates)."""
    try:
        top = int(addr.split(':')[0], 16) >> 6
    except (ValueError, IndexError):
        return 'unknown'
    return {3: 'static_random', 1: 'resolvable_private', 0: 'non_resolvable_or_public', 2: 'reserved'}[top]


def normalize(address, name, rssi, manufacturer_data, service_uuids, service_data):
    return {'address': str(address)[:40], 'name': (name or '')[:60], 'rssi': rssi if isinstance(rssi, int) else None,
            'company_ids': sorted(int(k) for k in (manufacturer_data or {}) if isinstance(k, int))[:8],
            'service_uuids': sorted(str(u).lower() for u in (service_uuids or []))[:12],
            'service_data_uuids': sorted(str(u).lower() for u in (service_data or {}))[:8],
            'address_kind': address_kind(str(address))}


def scan(seconds=5.0, scanner=None):
    seconds = min(max(seconds, 1.0), MAX_SECONDS)
    if scanner is None:
        if not available():
            return {'status': 'NOT_SUPPORTED', 'reason': 'bleak not installed', 'devices': []}
        from bleak import BleakScanner

        async def run():
            found = await BleakScanner.discover(timeout=seconds, return_adv=True)
            return [normalize(d.address, adv.local_name or d.name, adv.rssi, adv.manufacturer_data, adv.service_uuids, adv.service_data)
                    for d, adv in found.values()]
        scanner = run
    try:
        devices = asyncio.run(asyncio.wait_for(scanner(), seconds + 5))
    except asyncio.TimeoutError:
        return {'status': 'TIMEOUT', 'devices': []}
    except Exception as error:   # adapter off, permission denied, no radio
        return {'status': 'BLE_UNAVAILABLE', 'reason': type(error).__name__, 'devices': []}
    return {'status': 'OK', 'devices': devices[:MAX_DEVICES], 'seconds': seconds}
