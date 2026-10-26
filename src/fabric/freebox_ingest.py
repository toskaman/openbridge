"""Freebox into the graph: public identity always; authenticated LAN inventory only with an official app token.
A host seen by the Freebox is linked Freebox -> host with grant 'observe' only: not reachable or controllable from the PC."""
from src.fabric.contracts import DeviceObservation, Identifier, Capability, Link, opaque, mac_is_randomized, now
from src.adapters.freebox_auth import FreeboxAuthError

CATEGORY = {'smartphone': 'phone', 'tablet': 'phone', 'television': 'tv', 'multimedia_device': 'media', 'workstation': 'computer',
            'laptop': 'computer', 'printer': 'printer', 'nas': 'nas', 'freebox_player': 'tv', 'freebox_hd': 'tv',
            'networking_device': 'network', 'ip_camera': 'iot', 'iot': 'iot', 'car': 'iot', 'other': 'unknown'}


def ingest_freebox(registry, adapters, salt):
    public, session = adapters.get('public'), adapters.get('session')
    t = now()
    inv = public.discover() if public else {'status': 'GATEWAY_UNAVAILABLE', 'devices': []}
    if not inv['devices']:
        return {'status': inv['status']}
    facts = inv['devices'][0]['facts']
    # Merge with the mDNS view of the same box through its api_domain-derived id when available.
    box = None
    for key, dev in registry.devices.items():
        if any(i.kind == 'freebox_uid' for i in dev['identifiers']):
            box = key
    obs = [DeviceObservation(k, v, 'FREEBOX_API', 'LAN', t, True) for k, v in facts.items()]
    if box is None:
        box = registry.upsert([], category='router', label='Freebox', observations=obs)
    else:
        for o in obs:
            registry.observe(box, o)
    from src.fabric.contracts import Link as _L
    registry.link(_L('pc', box, 'LAN', ('read',), 'FREEBOX_API:public'))
    report = {'status': 'PUBLIC_ONLY', 'lan_hosts': 0}
    if session is None:
        registry.capability(box, Capability('lan_inventory', 'read', 'BLOCKED', 'FREEBOX_API', 'app authorization required'))
        return report
    state = session.state()
    report['authorization'] = state
    if state != 'AUTHORIZED':
        registry.capability(box, Capability('lan_inventory', 'read', 'BLOCKED', 'FREEBOX_API', state.lower()))
        return report
    try:
        hosts = session.lan_hosts()
    except (FreeboxAuthError, OSError, ValueError) as error:
        registry.capability(box, Capability('lan_inventory', 'read', 'BLOCKED', 'FREEBOX_API', str(error)[:80]))
        report['status'] = 'AUTH_ERROR'
        return report
    registry.capability(box, Capability('lan_inventory', 'read', 'REAL_HARDWARE_VERIFIED', 'FREEBOX_API', 'GET lan/browser/pub/'))
    for capability in ('router_settings', 'wifi_settings', 'dhcp', 'firewall'):
        registry.capability(box, Capability(capability, 'write', 'BLOCKED', 'FREEBOX_API', 'read-only by policy: no independent recovery path'))
    for host in hosts:
        ids = []
        if host['mac'] and not mac_is_randomized(host['mac']):
            ids.append(Identifier('mac_global', opaque('mac_global', host['mac'].lower(), salt), True))
        hobs = [DeviceObservation('lan_active', host['active'], 'FREEBOX_API', 'INVENTORY', t, False),
                DeviceObservation('host_type', host['type'], 'FREEBOX_API', 'INVENTORY', t, False)]
        if host['vendor']:
            hobs.append(DeviceObservation('manufacturer', host['vendor'], 'FREEBOX_API', 'INVENTORY', t, False, 0.6))
        if host['mac'] and mac_is_randomized(host['mac']):
            hobs.append(DeviceObservation('randomized_mac', True, 'FREEBOX_API', 'INVENTORY', t, True))
        key = registry.upsert(ids, category=CATEGORY.get(host['type'], 'unknown'), label=host['name'] or host['vendor'] or 'LAN host',
                              observations=hobs, weak=[('ip', ip) for ip in host['ipv4']] + ([('name', host['name'].lower())] if host['name'] else []))
        registry.link(_L(box, key, 'INVENTORY', ('observe',), 'FREEBOX_API:lan'))
    report.update(status='AUTHENTICATED', lan_hosts=len(hosts))
    return report
