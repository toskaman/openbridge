"""MQTT devices -> fabric devices. Identity = hashed (broker + family + device id); raw topics stay
off the snapshot and are used only by the primitives that act through the gateway."""
from src.fabric.contracts import Capability, DeviceObservation, Identifier, Link, now, opaque

EVIDENCE = 'MQTT gateway (Tasmota / Shelly Gen1 / Zigbee2MQTT conventions); emulator-validated against a loopback broker, real broker not yet tested'

CATEGORY = {'tasmota': 'plug', 'shelly': 'plug', 'z2m': 'light'}


def ingest_mqtt(registry, client, salt, seconds=5.0):
    from src.adapters import mqtt as M
    t = now()
    try:
        found = M.discover(client, seconds)
    except Exception as e:  # unreachable broker: reported, never fatal for discovery
        return {'status': 'UNAVAILABLE', 'detail': type(e).__name__}
    hub = registry.upsert([Identifier('mqtt_broker', opaque('mqtt_broker', '%s:%s' % (client.host, client.port), salt), True)],
                          category='hub', label='MQTT broker %s' % client.host,
                          observations=[DeviceObservation('devices', len(found), 'MQTT', 'LAN', t, True)])
    registry.link(Link('pc', hub, 'LAN', ('observe', 'read'), 'MQTT'))
    registry.capability(hub, Capability('mqtt_api', 'read', 'IMPLEMENTED_UNVERIFIED', 'MQTT', EVIDENCE))
    count, capped = 0, 0
    for d in found:
        dev = M.open_device(client, d)
        acts = sorted(dev.WRITABLE)
        try:
            key = registry.upsert([Identifier('mqtt_device', opaque('mqtt_device', '%s|%s|%s' % (
                client.host, d['family'], d.get('topic') or d.get('shelly_id') or d.get('name')), salt), True)],
                category=CATEGORY[d['family']], label=d['label'][:60],
                observations=[DeviceObservation('family', d['family'], 'MQTT', 'LAN', t, True)])
        except OverflowError:
            capped += 1       # registry full: skip new devices, keep merging the rest
            continue
        registry.devices[key]['mqtt'] = {k: v for k, v in d.items() if k != 'label'}   # kept off the snapshot
        registry.link(Link(hub, key, 'INVENTORY', ('observe', 'read', 'control'), 'MQTT'))
        registry.capability(key, Capability('mqtt_state', 'read', 'IMPLEMENTED_UNVERIFIED', 'MQTT', EVIDENCE))
        registry.capability(key, Capability('mqtt_control', 'write', 'IMPLEMENTED_UNVERIFIED', 'MQTT',
                                            'allowed: ' + ', '.join(acts) + '; consent per action, read back after'))
        count += 1
    return {'status': 'OK', 'devices': count, 'capped': capped}
