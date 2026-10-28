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
        for k in ('md', 'box_model_name', 'manufacturer', 'api_version', 'model'):
            if txt.get(k) and not (k == 'model' and inst['service'] not in ('_device-info._tcp', '_airplay._tcp', '_companion-link._tcp')):
                obs.append(DeviceObservation({'md': 'model', 'box_model_name': 'model'}.get(k, k), txt[k][:80], 'MDNS', 'LAN', t, False, 0.8))
        key = registry.upsert(ids, category=inst['category'], label=label, observations=obs,
                              weak=[('ip', a) for a in inst.get('addresses', [])])
        services = registry.devices[key].setdefault('mdns_services', set()); services.add(inst['service'])
        if inst.get('port') and any('.' in a for a in inst.get('addresses', [])):
            # Kept off the snapshot; used only by the local onboarding view (e.g. the ADB pairing port).
            registry.devices[key].setdefault('endpoints', {})[inst['service']] = (next(a for a in inst['addresses'] if '.' in a), int(inst['port']))
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
        bt = adapter.bluetooth_identifier(device['id'], salt) if device['state'] == 'device' and hasattr(adapter, 'bluetooth_identifier') else None
        if bt:
            ids.append(Identifier('mac_global', bt, True))
        obs, category = [], 'android'
        if device['state'] == 'device':
            try:
                report = adapter.inspect(device['id'])
                obs = [DeviceObservation(e['key'], e['value'], 'ADB', device['transport'], e['observed_at'], True) for e in report['evidence']]
                facts = {e['key']: e['value'] for e in report['evidence']}
                category = 'tv' if facts.get('is_television') else 'watch' if facts.get('is_watch') else 'phone'
            except ValueError:
                pass
        label = next((o.value for o in obs if o.key == 'model'), device['name'])
        serial_ip = next((k.split(':')[0] for k, v in getattr(adapter, '_handles', {}).items() if v == device['id'] and ':' in k), None)
        key = registry.upsert(ids, category=category, label=str(label), observations=obs, weak=[('ip', serial_ip)] if serial_ip else [])
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


def run(adapters, salt, providers=('mdns', 'ssdp', 'android', 'freebox'), mdns_timeout=2.5, mdns_fn=mdns.discover):
    started = time.monotonic()
    registry, report = Registry(), {}
    if 'mdns' in providers:
        res = mdns_fn(mdns_timeout)
        report['mdns'] = {'status': res['status'], 'instances': len(res['instances']), 'packets': res['packets']}
        ingest_mdns(registry, res, salt)
    if 'android' in providers and adapters.get('android'):
        ingest_android(registry, adapters['android'], salt)
        report['android'] = {'status': 'OK'}
    if 'ssdp' in providers:
        from src.fabric import ssdp
        res = adapters.get('ssdp_discover', ssdp.discover)()
        report['ssdp'] = {'status': res['status'], 'devices': len(res['devices'])}
        ingest_ssdp(registry, res, salt)
    if 'ble' in providers:
        from src.fabric import ble_local
        res = adapters.get('ble_scan', ble_local.scan)()
        report['ble'] = {'status': res['status'], 'devices': len(res['devices'])}
        ingest_ble(registry, res, salt)
    if 'windows' in providers and adapters.get('windows'):
        report['windows'] = ingest_windows(registry, adapters['windows'], salt)
    if 'tuya' in providers and adapters.get('tuya'):
        report['tuya'] = ingest_tuya(registry, adapters['tuya'], salt)
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


UPNP_CATEGORY = (('MediaRenderer', 'media'), ('InternetGatewayDevice', 'router'), ('MediaServer', 'nas'), ('Printer', 'printer'),
                 ('dial', 'tv'), ('Basic', 'iot'))


def ingest_ssdp(registry, result, salt):
    """UPnP devices: the UDN is a stable strong identifier; IP is weak. Observe-only links; no SOAP control is ever used."""
    t = now()
    for d in result.get('devices', []):
        desc = d.get('description') or {}
        ids = [Identifier('upnp_udn', opaque('upnp_udn', (desc.get('udn') or d['uuid']).lower(), salt), True)]
        joined = ' '.join(d['types'] + [desc.get('device_type', '')])
        category = next((c for key, c in UPNP_CATEGORY if key.lower() in joined.lower()), 'unknown')
        obs = [DeviceObservation('upnp_types', d['types'][:6], 'SSDP', 'LAN', t, False, 0.8)]
        for k in ('manufacturer', 'model'):
            if desc.get(k):
                obs.append(DeviceObservation(k, desc[k], 'SSDP', 'LAN', t, False, 0.8))
        key = registry.upsert(ids, category=category, label=desc.get('friendly_name') or desc.get('model') or 'UPnP device',
                              observations=obs, weak=[('ip', d['ip'])])
        registry.link(Link('pc', key, 'LAN', ('observe',), 'SSDP'))
        if category == 'router':
            registry.capability(key, Capability('upnp_igd_control', 'write', 'BLOCKED', 'SSDP', 'port mapping and every write action refused'))
            if any('InternetGatewayDevice' in t or 'WANIPConnection' in t or 'WANPPPConnection' in t for t in d['types'] + [desc.get('device_type', '')]):
                # Kept off the snapshot (the URL contains an address); used only by read_facts.
                registry.devices[key]['igd_location'] = d['location']
                registry.capability(key, Capability('igd_status', 'read', 'IMPLEMENTED_UNVERIFIED', 'UPNP_IGD',
                                                    'allowlisted read-only IGD queries; external IP masked'))
                registry.link(Link('pc', key, 'LAN', ('observe', 'read'), 'UPNP_IGD'))


def ingest_tuya(registry, vacuum, salt):
    """Owner-linked Tuya vacuum (official IoT project key). Strong identity = Tuya device id (hashed)."""
    t = now()
    try:
        facts = vacuum.facts()
    except Exception as e:
        return {'status': 'UNAVAILABLE', 'detail': type(e).__name__}
    ids = [Identifier('tuya_device_id', opaque('tuya_device_id', vacuum.device_id, salt), True)]
    obs = [DeviceObservation(f['name'], f['value'], 'TUYA_LOCAL', 'LAN', t, True) for f in facts]
    key = registry.upsert(ids, category='vacuum', label='Robot vacuum (Tuya)', observations=obs, weak=[('ip', vacuum.ip)])
    registry.link(Link('pc', key, 'LAN', ('observe', 'read', 'control'), 'TUYA_LOCAL'))
    registry.capability(key, Capability('tuya_status', 'read', 'IMPLEMENTED_UNVERIFIED', 'TUYA_LOCAL', 'local protocol 3.4, owner-linked key'))
    registry.capability(key, Capability('tuya_setting', 'write', 'IMPLEMENTED_UNVERIFIED', 'TUYA_LOCAL', 'suction / volume, exact Undo'))
    registry.capability(key, Capability('robot_control', 'write', 'IMPLEMENTED_UNVERIFIED', 'TUYA_LOCAL', 'start, pause, dock, moves (auto-stop), seek, dust, resets: irreversible, consent per command'))
    return {'status': 'OK', 'devices': 1}


def ingest_windows(registry, bridge, salt):
    """One authenticated BridgeWindows agent -> one 'computer' device with a strong machine identity."""
    if not bridge.connected():
        return {'status': 'NO_AGENT'}
    try:
        ident = bridge.identity(salt)
        diag = bridge.call('sys.diag')
    except ValueError as e:
        return {'status': 'UNAVAILABLE', 'detail': str(e)[:80]}
    if not ident:
        return {'status': 'NO_IDENTITY'}
    t = now()
    obs = [DeviceObservation(k, diag[k], 'WINDOWS_AGENT', 'LAN', t, True) for k in ('os_build', 'architecture', 'cpu_cores') if k in diag]
    key = registry.upsert([Identifier('windows_machine_guid', ident, True)], category='computer', label='Windows PC (agent)',
                          observations=obs, weak=[('ip', bridge.peer_ip)] if bridge.peer_ip else [])
    registry.link(Link('pc', key, 'LAN', ('observe', 'read'), 'WINDOWS_AGENT'))
    registry.devices[key].setdefault('handles', {})['WINDOWS_AGENT'] = 'windows-agent'
    registry.capability(key, Capability('windows_diagnostics', 'read', 'REAL_HARDWARE_VERIFIED', 'WINDOWS_AGENT', 'allowlisted read methods only'))
    for cap in ('run_command', 'file_write', 'registry_write', 'input_injection', 'agent_update'):
        registry.capability(key, Capability(cap, 'write', 'BLOCKED', 'WINDOWS_AGENT', 'not exposed: no bounded inverse'))
    return {'status': 'OK', 'agent_version': bridge.hello.get('version')}
