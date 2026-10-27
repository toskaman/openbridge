"""Capability engine: turns graph evidence into CapabilityDescriptors with six independent states.
Nothing is inferred upward: a capability is controllable/reversible only when an adapter verified that path."""
from datetime import datetime, timezone
from src.runtime.contract import CapabilityDescriptor, CapabilityPermission, ReversibilityClass

UNAVAILABLE = ('BLOCKED', 'UNSUPPORTED', 'NOT_SUPPORTED')

# Known adapter capabilities -> (readable, controllable, reversibility, operations, parameters, limitations)
KNOWN = {
    'inspect': (True, False, ReversibilityClass.NONE, ('read_facts',), {}, ()),
    'optional_app_state': (True, True, ReversibilityClass.EXACT, ('android_optional_app_state', 'undo_transaction'),
                           {'package': {'type': 'string', 'enum': 'allowlisted optional apps installed on the device'},
                            'target': {'type': 'string', 'enum': ['disabled-user']}},
                           ('Android user 0 only', 'allowlisted optional apps only', 'owner consent per change')),
    'ble_relay': (True, True, ReversibilityClass.SESSION_CLEANUP, ('relay_ble_scan', 'relay_revoke'),
                  {'seconds': {'type': 'integer', 'minimum': 1, 'maximum': 15}},
                  ('Companion must be open in the foreground', 'advertisements only, never connects')),
    'lan_inventory': (True, False, ReversibilityClass.NONE, ('read_facts',), {}, ('read-only Freebox API',)),
    'freebox_api': (True, False, ReversibilityClass.NONE, ('read_facts',), {}, ('public endpoints',)),
}


def _age(ts):
    try:
        return max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()))
    except (TypeError, ValueError):
        return -1


def describe(snapshot, relay_permissions=None):
    """snapshot: registry snapshot. relay_permissions: {device_key: {'BLUETOOTH_SCAN': bool, 'owner_enabled': bool}}."""
    relay_permissions = relay_permissions or {}
    links = {}
    for l in snapshot['links']:
        links.setdefault(l['child'], []).append(l)
    out = []
    for d in snapshot['devices']:
        dlinks = links.get(d['key'], [])
        grants = {g for l in dlinks for g in l['grants']}
        transport = dlinks[0]['transport'] if dlinks else 'NONE'
        fresh = _age(d.get('last_seen'))
        out.append(CapabilityDescriptor(
            capability_id=f"{d['key']}:presence", device_key=d['key'], name='presence', transport=transport,
            discovered=True, observed=bool(dlinks), readable='read' in grants or 'control' in grants,
            controllable=False, reversible=False, verified='REAL_HARDWARE_VERIFIED' if dlinks else 'IMPLEMENTED_UNVERIFIED',
            permissions=(), parameters={}, operations=('read_facts',) if ('read' in grants or 'control' in grants) else (),
            source=', '.join(sorted({l['source'] for l in dlinks}))[:120], freshness_s=fresh,
            limitations=() if dlinks else ('no current link',)))
        for c in d['capabilities']:
            known = KNOWN.get(c['name'])
            status = c['status'] if c['status'] != 'NOT_SUPPORTED' else 'UNSUPPORTED'
            available = status not in UNAVAILABLE and known is not None
            readable, controllable, rev, ops, params, lim = known if known else (False, False, ReversibilityClass.NONE, (), {}, ())
            perms = ()
            if c['name'] == 'ble_relay':
                p = relay_permissions.get(d['key'], {})
                perms = (CapabilityPermission('android.permission.BLUETOOTH_SCAN', bool(p.get('BLUETOOTH_SCAN')), 'android_dialog'),
                         CapabilityPermission('pairing', bool(p), 'pairing_code'))
                if available and not all(x.granted for x in perms):
                    available = False; lim = lim + ('missing permission or not paired',)
            if c['name'] == 'optional_app_state':
                perms = (CapabilityPermission('owner_consent', False, 'consent'),)   # granted per transaction only
            if c['level'] == 'write' and status == 'BLOCKED':
                lim = lim + (c.get('evidence') or 'blocked by policy',)
            out.append(CapabilityDescriptor(
                capability_id=f"{d['key']}:{c['name']}", device_key=d['key'], name=c['name'], transport=c.get('via', transport),
                discovered=True, observed=bool(dlinks), readable=available and readable,
                controllable=available and controllable, reversible=available and controllable and rev in (ReversibilityClass.EXACT, ReversibilityClass.SESSION_CLEANUP),
                verified=status if status in ('REAL_HARDWARE_VERIFIED', 'INTEGRATION_VERIFIED', 'SIMULATED_VERIFIED', 'IMPLEMENTED_UNVERIFIED', 'BLOCKED', 'UNSUPPORTED') else 'IMPLEMENTED_UNVERIFIED',
                permissions=perms, parameters=params if available else {}, operations=ops if available else (),
                source=c.get('via', ''), freshness_s=fresh, limitations=tuple(lim) + (() if available else (f'unavailable: {status}',)),
                reversibility=(rev if available else ReversibilityClass.NONE).value))
    return out


def check_invariants(desc):
    """Contract rules every descriptor must satisfy (used by tests for all adapters)."""
    errors = []
    if desc.observed and not desc.discovered: errors.append('observed without discovered')
    if desc.reversible and not desc.controllable: errors.append('reversible without controllable')
    if desc.verified in ('BLOCKED', 'UNSUPPORTED') and (desc.controllable or desc.readable or desc.operations):
        errors.append('unavailable capability exposes operations')
    if desc.controllable and not desc.operations: errors.append('controllable without operations')
    if desc.reversibility == 'IRREVERSIBLE' and desc.controllable: errors.append('irreversible must stay blocked')
    return errors
