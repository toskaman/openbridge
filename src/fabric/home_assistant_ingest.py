"""Home Assistant entities -> fabric devices. Identity = hashed (instance URL + entity id); the entity id itself is kept
off the snapshot (like the IGD location) and used only by the primitives that act through the bridge."""
from src.fabric.contracts import Capability, DeviceObservation, Identifier, Link, now, opaque

EVIDENCE = 'Home Assistant REST API; verified on a real Home Assistant with demo devices, physical devices not yet tested'


def ingest_home_assistant(registry, ha, salt):
    from src.adapters.home_assistant import CATEGORY, actions_for, domain_of
    t = now()
    try:
        states = ha.states()
    except Exception as e:  # unreachable, refused token: reported, never fatal for discovery
        return {'status': 'UNAVAILABLE', 'detail': type(e).__name__}
    hub = registry.upsert([Identifier('ha_instance', opaque('ha_instance', ha.url, salt), True)], category='hub',
                          label='Home Assistant', observations=[DeviceObservation('entities', len(states), 'HOME_ASSISTANT', 'LAN', t, True)])
    registry.link(Link('pc', hub, 'LAN', ('observe', 'read'), 'HOME_ASSISTANT'))
    registry.capability(hub, Capability('home_assistant_api', 'read', 'IMPLEMENTED_UNVERIFIED', 'HOME_ASSISTANT', EVIDENCE))
    count = 0
    for s in states:
        eid = s['entity_id']
        domain, attrs = domain_of(eid), s.get('attributes') or {}
        acts = actions_for(s)
        label = str(attrs.get('friendly_name') or eid.split('.', 1)[1].replace('_', ' '))[:60]
        obs = [DeviceObservation('state', str(s.get('state'))[:40], 'HOME_ASSISTANT', 'LAN', t, True),
               DeviceObservation('ha_domain', domain, 'HOME_ASSISTANT', 'LAN', t, True)]
        if attrs.get('device_class'):
            obs.append(DeviceObservation('device_class', str(attrs['device_class'])[:40], 'HOME_ASSISTANT', 'LAN', t, True))
        key = registry.upsert([Identifier('ha_entity', opaque('ha_entity', ha.url + '|' + eid, salt), True)],
                              category=CATEGORY[domain], label=label, observations=obs)
        registry.devices[key]['ha_entity'] = eid          # kept off the snapshot
        registry.link(Link(hub, key, 'INVENTORY', ('observe', 'read', 'control') if acts else ('observe', 'read'), 'HOME_ASSISTANT'))
        registry.capability(key, Capability('ha_state', 'read', 'IMPLEMENTED_UNVERIFIED', 'HOME_ASSISTANT', EVIDENCE))
        if acts:
            registry.capability(key, Capability('ha_control', 'write', 'IMPLEMENTED_UNVERIFIED', 'HOME_ASSISTANT',
                                                'allowed: ' + ', '.join(sorted(acts)) + '; consent per action, read back after'))
        elif domain in ('cover', 'lock', 'alarm_control_panel'):
            registry.capability(key, Capability('ha_control', 'write', 'BLOCKED', 'HOME_ASSISTANT', 'refused by policy (physical access)'))
        count += 1
    return {'status': 'OK', 'devices': count}
