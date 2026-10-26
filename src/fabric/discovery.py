"""Discovery manager: runs bounded providers and feeds one registry. Discovery never implies permission to control."""
import os
import secrets
import time
from pathlib import Path
from src.fabric.contracts import DeviceObservation, Identifier, Capability, Link, opaque, mac_is_randomized, now
from src.fabric.registry import Registry
from src.fabric import mdns

MDNS_LABEL_KEYS = ('fn', 'md', 'box_model_name', 'manufacturer', 'model', 'name')


def install_salt(root=None):
    root = Path(root or os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'fabric-salt.bin'
    if not path.exists():
        path.write_bytes(secrets.token_bytes(32))
    return path.read_bytes()


def ingest_mdns(registry, result, salt):
    t = now()
    for inst in result.get('instances', []):
        txt, ids = inst.get('txt', {}), []
        if inst.get('host'):
            ids.append(Identifier('mdns_host', opaque('mdns_host', inst['host'].lower(), salt), True))
        if inst['service'] == '_googlecast._tcp' and txt.get('id'):
            ids.append(Identifier('cast_id', opaque('cast_id', txt['id'].lower(), salt), True))
        if inst['service'] == '_hap._tcp' and txt.get('id'):
            ids.append(Identifier('hap_id', opaque('hap_id', txt['id'].lower(), salt), True))
        mac = txt.get('bt') or txt.get('deviceid')
        if mac and len(mac) == 17 and not mac_is_randomized(mac):
            ids.append(Identifier('mac_global', opaque('mac_global', mac.lower(), salt), True))
        if inst['service'] == '_fbx-api._tcp' and txt.get('api_domain'):
            ids.append(Identifier('freebox_uid', opaque('freebox_uid', txt['api_domain'].lower(), salt), True))
        label = next((txt[k] for k in MDNS_LABEL_KEYS if txt.get(k)), inst['instance'])[:60]
        obs = []
        for k in ('md', 'box_model_name', 'manufacturer', 'api_version'):
            if txt.get(k):
                obs.append(DeviceObservation({'md': 'model', 'box_model_name': 'model'}.get(k, k), txt[k][:80], 'MDNS', 'LAN', t, False, 0.8))
        key = registry.upsert(ids, category=inst['category'], label=label, observations=obs,
                              weak=[('ip', a) for a in inst.get('addresses', [])])
        services = registry.devices[key].setdefault('mdns_services', set()); services.add(inst['service'])
        registry.observe(key, DeviceObservation('mdns_services', sorted(services), 'MDNS', 'LAN', t, False, 0.9))
        registry.link(Link('pc', key, 'LAN', ('observe',), 'MDNS:' + inst['service']))
        cap = {'_fbx-api._tcp': ('freebox_api', 'read', 'REAL_HARDWARE_VERIFIED'),
               '_androidtvremote2._tcp': ('tv_remote_protocol', 'observe', 'NOT_SUPPORTED'),
               '_adb-tls-connect._tcp': ('wireless_adb', 'observe', 'IMPLEMENTED_UNVERIFIED'),
               '_esphomelib._tcp': ('esphome_api', 'observe', 'NOT_SUPPORTED'),
               '_home-assistant._tcp': ('home_assistant_api', 'observe', 'NOT_SUPPORTED')}.get(inst['service'])
        if cap:
            registry.capability(key, Capability(cap[0], cap[1], cap[2], 'MDNS', inst['service']))


def ingest_android(registry, adapter, salt):
    inventory = adapter.discover()
    for device in inventory.get('devices', []):
        ident = adapter.stable_identifier(device['id'], salt) if device['state'] == 'device' else None
        ids = [Identifier('android_serial', ident, True)] if ident else []
        obs, category = [], 'android'
        if device['state'] == 'device':
            try:
                report = adapter.inspect(device['id'])
                obs = [DeviceObservation(e['key'], e['value'], 'ADB', device['transport'], e['observed_at'], True) for e in report['evidence']]
                facts = {e['key']: e['value'] for e in report['evidence']}
                category = 'tv' if facts.get('is_television') else 'phone'
            except ValueError:
                pass
        label = next((o.value for o in obs if o.key == 'model'), device['name'])
        key = registry.upsert(ids, category=category, label=str(label), observations=obs)
        grants = ('read', 'control') if device['state'] == 'device' else ('observe',)
        registry.link(Link('pc', key, device['transport'], grants, 'ADB:' + device['state']))
        registry.devices[key].setdefault('handles', {})[device['transport']] = device['id']
        if device['state'] == 'device':
            registry.capability(key, Capability('inspect', 'read', 'REAL_HARDWARE_VERIFIED', device['transport'], 'adb read-only allowlist'))
            registry.capability(key, Capability('optional_app_state', 'restore', 'REAL_HARDWARE_VERIFIED', device['transport'], 'consent-gated agent'))
            if any(o.key == 'bluetooth_le' and o.value for o in obs):
                registry.capability(key, Capability('ble_relay', 'observe', 'NOT_SUPPORTED', device['transport'], 'requires OpenBridge Companion'))
        else:
            registry.capability(key, Capability('inspect', 'read', 'BLOCKED', device['transport'], f'adb state {device["state"]}'))


def run(adapters, salt, providers=('mdns', 'android', 'freebox'), mdns_timeout=2.5, mdns_fn=mdns.discover):
    started = time.monotonic()
    registry, report = Registry(), {}
    if 'mdns' in providers:
        res = mdns_fn(mdns_timeout)
        report['mdns'] = {'status': res['status'], 'instances': len(res['instances']), 'packets': res['packets']}
        ingest_mdns(registry, res, salt)
    if 'android' in providers and adapters.get('android'):
        ingest_android(registry, adapters['android'], salt)
        report['android'] = {'status': 'OK'}
    if 'ble' in providers:
        from src.fabric import ble_local
        res = adapters.get('ble_scan', ble_local.scan)()
        report['ble'] = {'status': res['status'], 'devices': len(res['devices'])}
        ingest_ble(registry, res, salt)
    if 'freebox' in providers and adapters.get('freebox'):
        from src.fabric.freebox_ingest import ingest_freebox
        report['freebox'] = ingest_freebox(registry, adapters['freebox'], salt)
    snap = registry.snapshot()
    snap['providers'] = report
    snap['elapsed_ms'] = round((time.monotonic() - started) * 1000)
    snap['generated_at'] = now()
    return snap, registry


# Bluetooth SIG company identifiers (assigned numbers) for common manufacturers; used only for display labels.
BLE_COMPANIES = {6: 'Microsoft', 76: 'Apple', 89: 'Nordic Semiconductor', 117: 'Samsung', 135: 'Garmin', 224: 'Google', 301: 'Sony',
                 343: 'Xiaomi', 637: 'Huawei', 1177: 'OnePlus', 2949: 'Tile', 911: 'Xiaomi', 741: 'Bose', 87: 'Harman', 2312: 'Amazfit/Zepp'}


def ingest_ble(registry, result, salt, observer='pc', source='BLE:pc'):
    """BLE advertisers. Addresses are weak identity (private addresses rotate). Link grants 'observe' only."""
    t = now()
    for dev in result.get('devices', []):
        ids = []
        if dev['address_kind'] == 'static_random':
            ids.append(Identifier('ble_address', opaque('ble_address', dev['address'].lower(), salt), True))
        obs = [DeviceObservation('ble_rssi', dev['rssi'], source, 'BLE', t, True)] if dev['rssi'] is not None else []
        if dev['company_ids']:
            obs.append(DeviceObservation('ble_company_ids', dev['company_ids'], source, 'BLE', t, True))
        if dev['service_uuids']:
            obs.append(DeviceObservation('ble_services', dev['service_uuids'], source, 'BLE', t, True))
        company = next((BLE_COMPANIES[c] for c in dev['company_ids'] if c in BLE_COMPANIES), None)
        label = dev['name'] or (f'{company} device (BLE)' if company else 'BLE advertiser')
        key = registry.upsert(ids, category='ble', label=label, observations=obs,
                              weak=[('ble_addr', opaque('ble_address', dev['address'].lower(), salt))])
        registry.link(Link(observer, key, 'BLE', ('observe',), source))
