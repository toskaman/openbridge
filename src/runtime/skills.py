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


HA_REF = 'docs/evidence/device-learning-soak-22nov.md (real Home Assistant, demo devices, read-back verified)'


def _home(skill_id, display_name, description, primitive_id, action, targets, param_names, risk_level, keywords):
    """Home Assistant devices (lights, plugs, fans, heating, speakers, blinds, locks) through the typed gate."""
    return {'skill_id': skill_id, 'version': 1, 'display_name': display_name, 'description': description,
            'capability_id': 'home.' + (action or 'undo'), 'targets': targets, 'permissions': ['ha:' + (action or 'undo')],
            'risk_level': risk_level, 'idempotent': action not in ('play', 'pause', 'open', 'close', 'next', 'previous'),
            'verification': 'claimed', 'verification_ref': HA_REF, 'provenance': 'builtin',
            'primitive_id': primitive_id, 'param_names': param_names,
            'params': {'action': action} if action else {}, 'keywords': keywords}


_HOME = (
    _home('home.turn_on', 'Switch a device on', 'Switch on a light, plug, fan, speaker or appliance', 'ha_set', 'turn_on',
          ['light', 'plug', 'fan', 'media_player', 'appliance'], (), 'low',
          ('turn on', 'switch on', 'allume', 'light', 'lamp', 'plug', 'lumiere', 'lampe', 'prise')),
    _home('home.turn_off', 'Switch a device off', 'Switch off a light, plug, fan, speaker or appliance', 'ha_set', 'turn_off',
          ['light', 'plug', 'fan', 'media_player', 'appliance'], (), 'low',
          ('turn off', 'switch off', 'eteins', 'coupe', 'light', 'lamp', 'plug', 'lumiere', 'lampe', 'prise')),
    _home('home.set_brightness', 'Set light brightness', 'Set a light to a brightness percentage (value 1-100)', 'ha_set',
          'set_brightness', ['light'], ('value',), 'low', ('brightness', 'dim', 'luminosite', 'tamise', 'percent')),
    _home('home.set_temperature', 'Set heating temperature', 'Set a thermostat, heater or AC target temperature in C (value 7-30)',
          'ha_set', 'set_temperature', ['thermostat'], ('value',), 'medium',
          ('temperature', 'heating', 'thermostat', 'chauffage', 'degres', 'radiateur', 'clim')),
    _home('home.set_color_temp', 'Set light colour temperature', 'Set a light to warm/cool white in kelvin (value 2000-6500)',
          'ha_set', 'set_color_temp', ['light'], ('value',), 'low',
          ('kelvin', 'kelvins', 'warm', 'cool', 'warm white', 'cool white', 'blanc chaud', 'blanc froid',
           'lumiere chaude', 'lumiere froide')),
    _home('home.set_color', 'Set light colour', 'Set a light to a hue in degrees (value 0-360, full saturation)',
          'ha_set', 'set_color', ['light'], ('value',), 'low',
          ('color', 'colour', 'red', 'green', 'blue', 'yellow', 'purple', 'pink', 'orange', 'hue',
           'couleur', 'rouge', 'vert', 'bleu', 'jaune', 'violet', 'rose', 'teinte')),
    _home('home.fan_speed', 'Set fan speed', 'Set a fan to a speed percentage (value 0-100)',
          'ha_set', 'set_speed', ['fan'], ('value',), 'low',
          ('fan', 'speed', 'fan speed', 'ventilateur', 'ventilo', 'vitesse', 'slow', 'fast', 'breeze')),
    _home('home.set_mode', 'Set thermostat mode', 'Set a thermostat, heater or AC mode (mode: off, heat, cool, auto, dry, fan_only)',
          'ha_set', 'set_mode', ['thermostat'], ('mode',), 'medium',
          ('mode', 'heat mode', 'cool mode', 'auto mode', 'dry mode', 'hvac', 'mode chaud', 'mode froid',
           'climatisation', 'heating mode', 'cooling mode')),
    _home('home.media_play', 'Play media', 'Resume or start playback on a speaker or media player (not the TV volume)',
          'ha_command', 'play', ['media_player'], (), 'low', ('play', 'resume', 'music', 'lecture', 'musique', 'reprends')),
    _home('home.media_pause', 'Pause media', 'Pause playback on a speaker or media player', 'ha_command', 'pause',
          ['media_player'], (), 'low', ('pause', 'music', 'musique', 'speaker', 'enceinte')),
    _home('home.media_volume', 'Set speaker volume', 'Set a speaker or media player volume (value 0-100); TV volume uses tv_volume_set',
          'ha_set', 'set_volume', ['media_player'], ('value',), 'low', ('speaker', 'enceinte', 'volume', 'sonos', 'soundbar')),
    _home('home.media_next', 'Next track', 'Skip to the next track on a speaker or media player',
          'ha_command', 'next', ['media_player'], (), 'low',
          ('next', 'song', 'chanson', 'suivant', 'chanson suivante', 'piste suivante', 'morceau suivant', 'skip')),
    _home('home.media_previous', 'Previous track', 'Go back one track on a speaker or media player',
          'ha_command', 'previous', ['media_player'], (), 'low',
          ('previous', 'song', 'chanson', 'precedent', 'chanson precedente', 'piste precedente', 'morceau precedent')),
    _home('home.media_mute', 'Mute or unmute', 'Mute (value 1) or unmute (value 0) a speaker or media player',
          'ha_set', 'set_mute', ['media_player'], ('value',), 'low',
          ('mute', 'muted', 'unmute', 'muet', 'sourdine', 'silence', 'speaker', 'enceinte')),
    _home('home.cover_open', 'Open blinds', 'Open blinds, shutters or curtains (never a garage door or gate)', 'ha_command',
          'open', ['cover'], (), 'medium', ('open', 'blinds', 'shutters', 'curtains', 'ouvre', 'volets', 'stores', 'rideaux')),
    _home('home.cover_close', 'Close blinds', 'Close blinds, shutters or curtains (never a garage door or gate)', 'ha_command',
          'close', ['cover'], (), 'medium', ('close', 'blinds', 'shutters', 'curtains', 'ferme', 'volets', 'stores', 'rideaux')),
    _home('home.cover_stop', 'Stop blinds', 'Stop blinds, shutters or curtains mid-travel (never a garage door or gate)',
          'ha_command', 'stop', ['cover'], (), 'medium',
          ('stop', 'stoppe', 'stopper', 'halt', 'blinds', 'blind', 'shutters', 'curtains',
           'volets', 'volet', 'stores', 'rideaux')),
    _home('home.lock', 'Lock a door', 'Lock a door lock (OpenBridge never unlocks)', 'ha_command', 'lock', ['lock'], (), 'medium',
          ('lock', 'verrouille', 'ferme a cle', 'door', 'porte')),
    _home('home.vacuum_start', 'Start the robot vacuum', 'Start cleaning on a robot vacuum known to Home Assistant',
          'ha_command', 'start', ['robot'], (), 'high',
          ('robot vacuum', 'robot', 'cleaning robot', 'robot cleaner', 'robot aspirateur', 'aspirateur robot',
           'le robot', 'robovac')),
    _home('home.vacuum_dock', 'Send the robot vacuum home', 'Send a robot vacuum known to Home Assistant back to its dock',
          'ha_command', 'return_to_base', ['robot'], (), 'medium',
          ('dock the robot', 'robot dock', 'robot back to base', 'robot base', 'robot home', 'rentrer le robot',
           'robot a sa base', 'le robot a charger', 'robovac dock', 'robot')),
    _home('home.vacuum_pause', 'Pause the robot vacuum', 'Pause a robot vacuum known to Home Assistant',
          'ha_command', 'pause', ['robot'], (), 'medium',
          ('pause the robot', 'robot pause', 'pause robot', 'hold the robot', 'robot hold',
           'mets le robot en pause', 'robot en pause', 'pause le robot', 'robovac pause', 'robot')),
    _home('home.undo', 'Undo the last change', 'Put a device back exactly as it was before the last change', 'ha_undo', None,
          ['any'], (), 'low', ('undo', 'annule', 'revert', 'remets comme avant', 'put it back')),
    {'skill_id': 'links.create', 'version': 1, 'display_name': 'Create a device link',
     'description': ('Create a new automation: WHEN device 1 reaches when_state THEN device 2 does then_action (optional value). '
                     'targets = [trigger device, target device]. Inactive until the owner approves it.'),
     'capability_id': 'links.create', 'targets': ['any'], 'permissions': ['links:propose'], 'risk_level': 'medium',
     'idempotent': False, 'verification': 'claimed',
     'verification_ref': 'docs/evidence/device-learning-soak-22nov.md (link fired once, verified)',
     'provenance': 'builtin', 'primitive_id': 'links.propose', 'param_names': ('when_state', 'then_action', 'value'),
     'params': {}, 'keywords': ('when', 'whenever', 'quand', 'lorsque', 'automation', 'automatise', 'link', 'each time', 'chaque fois')},
    {'skill_id': 'create.suggest', 'version': 1, 'display_name': 'Suggest new features',
     'description': 'Suggest new cross-device features built from what the devices have proven they can do (read-only)',
     'capability_id': 'create.suggest', 'targets': ['fabric'], 'permissions': [], 'risk_level': 'low', 'idempotent': True,
     'verification': 'claimed', 'verification_ref': 'docs/evidence/device-learning-soak-22nov.md (10 suggestions)',
     'provenance': 'builtin', 'primitive_id': 'create_suggest', 'param_names': (), 'params': {},
     'keywords': ('suggest', 'ideas', 'idees', 'propose', 'feature', 'fonctionnalite', 'together', 'ensemble')},
    {'skill_id': 'learn.report', 'version': 1, 'display_name': 'What OpenBridge learned',
     'description': 'Report what OpenBridge learned about each device: reliable actions, success rate, latency (read-only)',
     'capability_id': 'learn.report', 'targets': ['fabric'], 'permissions': [], 'risk_level': 'low', 'idempotent': True,
     'verification': 'claimed', 'verification_ref': 'docs/evidence/device-learning-soak-22nov.md (87 proven actions)',
     'provenance': 'builtin', 'primitive_id': 'learn_report', 'param_names': (), 'params': {},
     'keywords': ('learned', 'appris', 'reliable', 'fiable', 'reliability', 'fiabilite')},
)

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
    {'skill_id': 'app_launch', 'version': 1,
     'display_name': 'Launch app on Android device',
     'description': B2_SKILLS['app_launch']['plain'],
     'capability_id': 'android.app', 'targets': ['tv'],
     'permissions': ['route:app_launch'], 'risk_level': 'low',
     'idempotent': B2_SKILLS['app_launch']['idempotent'],
     'verification': 'claimed',
     'verification_ref': ('unit-covered (router dispatches youtube.tv to '
                          'launch_app; unknown packages rejected pre-send); '
                          'no physical receipt inspected'),
     'provenance': 'builtin', 'primitive_id': 'b2:app_launch',
     'param_names': ('package',), 'params': {},
     'keywords': ('youtube', 'launch', 'open', 'app', 'lance', 'lancer',
                  'ouvrir', 'ouvre')},
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
) + _HOME:
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
