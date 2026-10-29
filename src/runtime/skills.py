"""Command Center P0: executable skill registry.

Every skill the NL layer may propose must be registered here with a validated
contract. Verification honesty rule: 'verified_physical' requires a cited
receipt artifact inspected in-repo; README-claimed-but-unreinspected stays
'claimed'; anything else is 'simulation_only' or 'unavailable'. The executor
must refuse unknown and unavailable skills; the model cannot bypass this table.
"""
from src.runtime.routing import SKILLS as B2_SKILLS

REGISTRY_VERSION = 1
VERIFICATION = ('verified_physical', 'claimed', 'simulation_only', 'unavailable')
PROVENANCE = ('builtin', 'meta_discovered', 'meta_composed', 'meta_generated')

_FIELDS = {'skill_id', 'version', 'display_name', 'description', 'capability_id',
           'targets', 'permissions', 'risk_level', 'idempotent',
           'verification', 'verification_ref', 'provenance', 'primitive_id',
           'param_names', 'params', 'keywords'}


def _b2(skill_id, display_name, capability_id, targets, risk_level,
        verification, verification_ref, keywords):
    b2 = B2_SKILLS[skill_id]
    return {'skill_id': skill_id, 'version': 1, 'display_name': display_name,
            'description': b2['plain'], 'capability_id': capability_id,
            'targets': targets, 'permissions': ['route:' + skill_id],
            'risk_level': risk_level, 'idempotent': b2['idempotent'],
            'verification': verification, 'verification_ref': verification_ref,
            'provenance': 'builtin', 'primitive_id': 'b2:' + skill_id,
            'param_names': ('seconds', 'value', 'direction'),
            'params': {}, 'keywords': keywords}


def _tuya(skill_id, display_name, command, risk_level, keywords):
    return {'skill_id': skill_id, 'version': 1, 'display_name': display_name,
            'description': 'Tuya robot vacuum typed command: ' + command,
            'capability_id': 'vacuum.clean', 'targets': ['vacuum'],
            'permissions': ['tuya:command'], 'risk_level': risk_level,
            'idempotent': False, 'verification': 'claimed',
            'verification_ref': 'README (Tuya vacuum control claimed, not re-verified this session)',
            'provenance': 'builtin', 'primitive_id': 'tuya_command',
            'param_names': (), 'params': {'command': command},
            'keywords': keywords}


_REGISTRY = {}
for _c in (
    _b2('ble_scan_room', 'Scan nearby Bluetooth', 'ble.scan', ['relay'],
        'low', 'verified_physical',
        'docs/release/failover-evidence/partial-two-relay-run.json',
        ('bluetooth', 'ble', 'scan', 'nearby', 'devices')),
    _b2('device_facts', 'Read device facts', 'device.facts', ['any'],
        'low', 'claimed', 'README (read path, not re-verified this session)',
        ('facts', 'info', 'device', 'status')),
    _b2('tv_volume_set', 'Set TV volume (exact)', 'tv.volume', ['tv'],
        'low', 'claimed', 'docs/release/WATCH_CONTROL_ACCEPTANCE.md (published with limitations)',
        ('tv', 'volume', 'set', 'television')),
    _b2('tv_volume_step', 'TV volume step', 'tv.volume', ['tv'],
        'low', 'claimed', 'docs/release/WATCH_CONTROL_ACCEPTANCE.md (published with limitations)',
        ('tv', 'volume', 'up', 'down', 'television')),
    _tuya('vacuum.start', 'Start vacuum cleaning', 'start', 'high',
          ('vacuum', 'start', 'clean', 'aspirateur', 'demarrer', 'demarrer le menage')),
    _tuya('vacuum.pause', 'Pause vacuum', 'pause', 'medium',
          ('vacuum', 'pause', 'stop', 'aspirateur', 'pause')),
    _tuya('vacuum.dock', 'Send vacuum to dock', 'dock', 'medium',
          ('vacuum', 'dock', 'charge', 'base', 'aspirateur', 'recharger')),
    _tuya('vacuum.seek', 'Find the vacuum (beep)', 'seek', 'low',
          ('vacuum', 'seek', 'find', 'beep', 'where', 'aspirateur', 'trouver', 'bip', 'ou')),
    _tuya('vacuum.empty_dust', 'Empty the dustbin', 'empty_dust', 'medium',
          ('vacuum', 'empty', 'dust', 'dustbin', 'aspirateur', 'vider', 'poussiere')),
    {'skill_id': 'fabric.status', 'version': 1, 'display_name': 'Summarize fabric state',
     'description': 'Count devices by category and relays by online state (read-only, no hardware calls)',
     'capability_id': 'fabric.status', 'targets': ['fabric'],
     'permissions': [], 'risk_level': 'low', 'idempotent': True,
     'verification': 'claimed',
     'verification_ref': 'unit + sandbox + live approve/execute READ proof (this branch)',
     'provenance': 'meta_generated', 'primitive_id': 'fabric_status',
     'param_names': (), 'params': {},
     'keywords': ('fabric', 'status', 'how many', 'devices', 'online', 'count', 'summary',
                  'combien', 'appareils', 'etat', 'resume')},
):
    _REGISTRY[_c['skill_id']] = _c
del _c


class SkillError(ValueError):
    pass


def validate_contract(c):
    if not isinstance(c, dict):
        return ['$: must be an object']
    errs = [f'$.{k}: unexpected field' for k in c if k not in _FIELDS]
    for k in _FIELDS:
        if k not in c:
            errs.append(f'$.{k}: required')
    if c.get('verification') not in VERIFICATION:
        errs.append(f'$.verification: must be one of {VERIFICATION}')
    if c.get('verification') == 'verified_physical' and not c.get('verification_ref'):
        errs.append('$.verification_ref: required for verified_physical')
    if c.get('provenance') not in PROVENANCE:
        errs.append(f'$.provenance: must be one of {PROVENANCE}')
    if c.get('risk_level') not in ('low', 'medium', 'high'):
        errs.append('$.risk_level: must be low|medium|high')
    if not isinstance(c.get('idempotent'), bool):
        errs.append('$.idempotent: must be boolean')
    return errs


def get(skill_id):
    return _REGISTRY.get(skill_id)


def all_skills():
    return list(_REGISTRY.values())


def match(keyword):
    kw = (keyword or '').strip().lower()
    if not kw:
        return []
    out = []
    for c in _REGISTRY.values():
        hay = ' '.join([c['skill_id'], c['display_name'], c['description'], *c['keywords']]).lower()
        if kw in hay:
            out.append(c)
    return out


def resolve(skill_id, params):
    c = _REGISTRY.get(skill_id)
    if c is None:
        raise SkillError(f'unknown skill: {skill_id}')
    if c['verification'] == 'unavailable':
        raise SkillError(f'skill unavailable: {skill_id}')
    if not isinstance(params, dict) or any(k not in c['param_names'] for k in params):
        raise SkillError(f'invalid params for {skill_id}: only {c["param_names"]}')
    return {'skill_id': skill_id, 'primitive_id': c['primitive_id'],
            'params': {**c['params'], **params}, 'risk_level': c['risk_level'],
            'verification': c['verification']}
