"""Multi-device diagnosis: deterministic, evidence-based statements about what the fabric can and cannot do.
No AI decides here. Every statement lists the evidence it rests on; INFERRED statements say so."""
from src.runtime.diagnostics import finding


def diagnose(snapshot, relay_routes=(), executor_recovery=None):
    out = []
    prov = (snapshot or {}).get('providers', {})
    devices = (snapshot or {}).get('devices', [])
    if not snapshot:
        return [finding('graph', 'empty', source='no discovery yet', level='warning')]
    for name, rep in sorted(prov.items()):
        out.append(finding(f'provider_{name}', rep.get('status', 'OK'), source='discovery report'))
    ble = prov.get('ble', {})
    pc_ble = ble.get('status') == 'OK'
    if ble and not pc_ble:
        out.append(finding('pc_bluetooth', 'unavailable', source='provider_ble', level='info'))
    relay_capable = [d for d in devices if any(c['name'] == 'ble_relay' for c in d.get('capabilities', []))]
    proven = [d for d in relay_capable if any(c['name'] == 'ble_relay' and c['status'] == 'REAL_HARDWARE_VERIFIED' for c in d['capabilities'])]
    out.append(finding('ble_relay_candidates', len(relay_capable), source='capabilities ble_relay'))
    if not pc_ble and relay_capable:
        out.append(finding('ble_via_relay_possible', True, '', 'pc_bluetooth + ble_relay_candidates', True,
                           f'PC has no usable Bluetooth; {len(relay_capable)} Android device(s) with BLE can relay '
                           f'({len(proven)} already proven)', 'info'))
    if not pc_ble and not relay_capable:
        out.append(finding('ble_unreachable', True, '', 'pc_bluetooth + ble_relay_candidates', True,
                           'no local adapter and no relay-capable device: BLE devices cannot be observed', 'warning'))
    stale = [r for r in relay_routes if r.get('status') in ('STALE', 'OFFLINE')]
    if stale:
        out.append(finding('relay_routes_degraded', len(stale), '', 'route status', True, 'relay offline or no fresh scan', 'warning'))
    blocked = [(d['label'], c['name']) for d in devices for c in d.get('capabilities', []) if c['status'] == 'BLOCKED']
    if blocked:
        out.append(finding('blocked_capabilities', len(blocked), source='capabilities status=BLOCKED', level='warning'))
    dups = (snapshot or {}).get('possible_duplicates', [])
    if dups:
        out.append(finding('possible_duplicates', len(dups), '', 'weak identifier overlap', True,
                           'same IP/name/BLE hint without a strong identifier; not merged', 'info'))
    controllable = [d for d in devices if any(c['level'] in ('write', 'restore') and c['status'] == 'REAL_HARDWARE_VERIFIED' for c in d.get('capabilities', []))]
    out.append(finding('devices_with_verified_reversible_control', len(controllable), source='capabilities'))
    if executor_recovery and executor_recovery.get('pending_transactions'):
        out.append(finding('unverified_transactions', len(executor_recovery['pending_transactions']), '', 'executor recovery', True,
                           'actions ended without verification; inspect before further changes', 'warning'))
    return out
