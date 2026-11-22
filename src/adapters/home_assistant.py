"""Home Assistant bridge: one link gives OpenBridge the lights, plugs, thermostats, media players, covers, locks and
robots that the owner's Home Assistant already knows, including Matter, Zigbee and Thread devices paired there.

Transport: the official Home Assistant REST API (GET /api/states, POST /api/services/<domain>/<service>) with a
long-lived access token created by the owner in their Home Assistant profile. The token is read from the OS vault
(``openbridge ha connect --store-token``) or from an environment variable; it is never written to disk in clear,
never logged and never returned by any API.

Safety, on top of OpenBridge's consent gate:
- Only allowlisted actions per entity domain exist; there is no free-form service call.
- Some actions are refused by policy whatever the consent: unlocking a lock, opening a garage door or a gate,
  disarming an alarm. Cameras, people and device trackers are not even listed (privacy).
- After every call the entity is read back; a result is ``verified`` only when its state matches.
- Reversible changes (on/off, brightness, volume, target temperature) record the previous value for an exact Undo.

Status: verified on a real Home Assistant instance with its demo devices (docs/evidence/home-assistant-real-instance-22nov.md);
physical devices through Home Assistant not yet tested.
"""
import ipaddress
import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, quote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

SECRET_NAME = 'home-assistant-token'
DEFAULT_TOKEN_ENV = 'OPENBRIDGE_HA_TOKEN'
MAX_BYTES = 4 * 1024 * 1024
MAX_ENTITIES = 300
TIMEOUT_S = 6
ENTITY_ID = re.compile(r'[a-z_]{2,32}\.[a-z0-9_]{1,96}')
_sleep = time.sleep

# domain -> OpenBridge device category (kept distinct from native adapters: Tuya uses 'vacuum', Android TVs 'tv').
CATEGORY = {'light': 'light', 'switch': 'plug', 'fan': 'fan', 'climate': 'thermostat', 'media_player': 'media_player',
            'cover': 'cover', 'lock': 'lock', 'vacuum': 'robot', 'sensor': 'sensor', 'binary_sensor': 'sensor',
            'alarm_control_panel': 'alarm'}
# Never listed: their state is personal data (images, whereabouts) and OpenBridge has no action for them.
EXCLUDED = ('camera', 'person', 'device_tracker', 'zone', 'image', 'calendar', 'conversation', 'tts', 'stt', 'notify')

# action -> (domain, service, kind). kind: 'onoff' (exact undo), 'value' (exact undo), 'momentary' (irreversible)
ACTIONS = {
    'light': {'turn_on': ('turn_on', 'onoff'), 'turn_off': ('turn_off', 'onoff'), 'set_brightness': ('turn_on', 'value')},
    'switch': {'turn_on': ('turn_on', 'onoff'), 'turn_off': ('turn_off', 'onoff')},
    'fan': {'turn_on': ('turn_on', 'onoff'), 'turn_off': ('turn_off', 'onoff')},
    'media_player': {'turn_on': ('turn_on', 'onoff'), 'turn_off': ('turn_off', 'onoff'), 'set_volume': ('volume_set', 'value'),
                     'play': ('media_play', 'momentary'), 'pause': ('media_pause', 'momentary')},
    'climate': {'set_temperature': ('set_temperature', 'value')},
    'cover': {'open': ('open_cover', 'momentary'), 'close': ('close_cover', 'momentary'), 'stop': ('stop_cover', 'momentary')},
    'lock': {'lock': ('lock', 'momentary')},
    'vacuum': {'start': ('start', 'momentary'), 'pause': ('pause', 'momentary'), 'return_to_base': ('return_to_base', 'momentary')},
}
ALL_ACTIONS = sorted({a for d in ACTIONS.values() for a in d})
# Refused by policy, with the reason shown to the owner.
POLICY = {('lock', 'unlock'): 'OpenBridge never unlocks a door.',
          ('lock', 'open'): 'OpenBridge never opens a lock.',
          ('alarm_control_panel', '*'): 'Alarm systems are read-only in OpenBridge.',
          ('cover', 'garage'): 'Garage doors and gates are never moved by OpenBridge.'}
SENSITIVE_COVERS = ('garage', 'gate', 'door')
TEMP_RANGE = (7.0, 30.0)
EXPECT = {'turn_on': lambda s, a, v: s.get('state') not in ('off', 'unavailable', 'unknown'),
          'turn_off': lambda s, a, v: s.get('state') == 'off',
          'set_brightness': lambda s, a, v: s.get('state') == 'on' and abs(round((s.get('attributes', {}).get('brightness') or 0) * 100 / 255) - v) <= 2,
          'set_volume': lambda s, a, v: abs(float(s.get('attributes', {}).get('volume_level') or -1) - v / 100.0) <= 0.02,
          'set_temperature': lambda s, a, v: abs(float(s.get('attributes', {}).get('temperature') or -99) - v) < 0.05,
          'play': lambda s, a, v: s.get('state') == 'playing', 'pause': lambda s, a, v: s.get('state') == 'paused',
          'open': lambda s, a, v: s.get('state') == 'open', 'close': lambda s, a, v: s.get('state') == 'closed',
          'stop': lambda s, a, v: s.get('state') in ('open', 'closed', 'stopped'),
          'lock': lambda s, a, v: s.get('state') == 'locked',
          'start': lambda s, a, v: s.get('state') == 'cleaning', 'return_to_base': lambda s, a, v: s.get('state') in ('returning', 'docked')}
# States that mean "the device acted but has not finished": reported as executed, not verified.
MOVING = {'open': ('opening',), 'close': ('closing',), 'lock': ('locking',), 'start': ('cleaning',)}


class HABlocked(PermissionError):
    """Refused before anything was sent (policy, allowlist, configuration)."""


class HAError(OSError):
    """Home Assistant could not be reached or answered unexpectedly."""


def config_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'home_assistant.json'


def _host_is_private(host):
    if host in ('localhost', 'homeassistant') or host.endswith(('.localhost', '.local', '.lan', '.home.arpa')):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def validate_url(url):
    """http only on this PC or the local network; anything else must be https. No credentials in the URL."""
    if not isinstance(url, str) or len(url) > 200:
        raise HABlocked('Home Assistant URL missing or too long')
    u = urlsplit(url.strip())
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise HABlocked('Home Assistant URL must look like http://homeassistant.local:8123')
    if u.scheme == 'http' and not _host_is_private(u.hostname):
        raise HABlocked('plain http is only allowed on the local network; use https')
    return '%s://%s' % (u.scheme, u.netloc)


def load_config(path=None):
    p = Path(path or config_path())
    try:
        doc = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    try:
        url = validate_url(doc.get('url', ''))
    except HABlocked:
        return None
    env = doc.get('token_env') or DEFAULT_TOKEN_ENV
    if not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,63}', env):
        env = DEFAULT_TOKEN_ENV
    return {'url': url, 'token_env': env}


def save_config(url, token_env=None, path=None):
    clean = {'url': validate_url(url), 'token_env': token_env or DEFAULT_TOKEN_ENV}
    if not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,63}', clean['token_env']):
        raise HABlocked('token variable name must be like OPENBRIDGE_HA_TOKEN')
    p = Path(path or config_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(clean, indent=1), encoding='utf-8')
    return clean


def resolve_token(config, vault=None):
    if vault is None:
        from src.fabric.credential_vault import Vault
        vault = Vault()
    token = None
    try:
        token = vault.get(SECRET_NAME)
    except Exception:
        token = None
    return token or os.environ.get(config.get('token_env') or DEFAULT_TOKEN_ENV) or None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise HAError('Home Assistant answered with a redirect; refused')


def _http(method, url, token, body=None, timeout=TIMEOUT_S):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                                                           'Accept': 'application/json'})
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(req, timeout=timeout) as resp:
            raw = resp.read(MAX_BYTES + 1)
    except HTTPError as e:
        e.close()
        if e.code in (401, 403):
            raise HABlocked('Home Assistant refused the token (create a long-lived access token in your HA profile)') from None
        if e.code == 404:
            raise HAError('not found on Home Assistant') from None
        raise HAError('Home Assistant answered HTTP %d' % e.code) from None
    except URLError as e:
        raise HAError('Home Assistant unreachable: %s' % str(e.reason)[:80]) from None
    if len(raw) > MAX_BYTES:
        raise HAError('Home Assistant response too large')
    try:
        return json.loads(raw.decode('utf-8')) if raw else None
    except ValueError:
        raise HAError('Home Assistant answered something that is not JSON') from None


def domain_of(entity_id):
    return entity_id.split('.', 1)[0]


def actions_for(state):
    """Allowlisted actions for one entity, after policy (sensitive covers have none)."""
    domain = domain_of(state['entity_id'])
    acts = dict(ACTIONS.get(domain, {}))
    attrs = state.get('attributes') or {}
    if domain == 'cover' and attrs.get('device_class') in SENSITIVE_COVERS:
        return {}
    if domain == 'light' and not any(m in (attrs.get('supported_color_modes') or ['brightness']) for m in
                                     ('brightness', 'color_temp', 'hs', 'xy', 'rgb', 'rgbw', 'rgbww', 'white')):
        acts.pop('set_brightness', None)
    return acts


def policy_refusal(domain, action, state=None):
    if (domain, action) in POLICY:
        return POLICY[(domain, action)]
    if (domain, '*') in POLICY:
        return POLICY[(domain, '*')]
    if domain == 'cover' and ((state or {}).get('attributes') or {}).get('device_class') in SENSITIVE_COVERS:
        return POLICY[('cover', 'garage')]
    return None


class HomeAssistant:
    def __init__(self, url, token, http=_http, poll_s=0.5, verify_s=6.0):
        if not token:
            raise HABlocked('No Home Assistant token: run `openbridge ha connect --url ... --store-token`')
        self.url, self._token, self._http = validate_url(url), token, http
        self.poll_s, self.verify_s = poll_s, verify_s
        self._before = {}

    @classmethod
    def from_config(cls, config=None, vault=None, **kw):
        config = config or load_config()
        if not config:
            raise HABlocked('Home Assistant not connected: run `openbridge ha connect --url ...`')
        return cls(config['url'], resolve_token(config, vault), **kw)

    def _get(self, path):
        return self._http('GET', self.url + path, self._token)

    def ping(self):
        r = self._get('/api/')
        if not isinstance(r, dict) or 'message' not in r:
            raise HAError('this does not look like a Home Assistant API')
        return {'ok': True, 'message': str(r['message'])[:80]}

    def states(self):
        rows = self._get('/api/states')
        if not isinstance(rows, list):
            raise HAError('unexpected /api/states answer')
        out = []
        for s in rows:
            eid = s.get('entity_id') if isinstance(s, dict) else None
            if not isinstance(eid, str) or not ENTITY_ID.fullmatch(eid):
                continue
            if domain_of(eid) in EXCLUDED or domain_of(eid) not in CATEGORY:
                continue
            out.append(s)
            if len(out) >= MAX_ENTITIES:
                break
        return out

    def state(self, entity_id):
        if not ENTITY_ID.fullmatch(entity_id or ''):
            raise HABlocked('invalid entity id')
        s = self._get('/api/states/' + quote(entity_id, safe='._'))
        if not isinstance(s, dict) or s.get('entity_id') != entity_id:
            raise HAError('unexpected state answer')
        return s

    def facts(self, entity_id):
        s = self.state(entity_id)
        attrs = s.get('attributes') or {}
        out = [{'name': 'state', 'value': s.get('state'), 'unit': ''}]
        for k, unit in (('brightness', '/255'), ('volume_level', ''), ('temperature', '°'), ('current_temperature', '°'),
                        ('current_position', '%'), ('battery_level', '%'), ('unit_of_measurement', ''), ('device_class', '')):
            if k in attrs and isinstance(attrs[k], (int, float, str)) and not isinstance(attrs[k], bool):
                out.append({'name': k, 'value': attrs[k], 'unit': unit})
        return out

    def _service_data(self, domain, action, value, state):
        data = {'entity_id': state['entity_id']}
        if action == 'set_brightness':
            if not isinstance(value, (int, float)) or not 1 <= value <= 100:
                raise HABlocked('brightness must be between 1 and 100 %')
            data['brightness_pct'] = int(value)
        elif action == 'set_volume':
            if not isinstance(value, (int, float)) or not 0 <= value <= 100:
                raise HABlocked('volume must be between 0 and 100')
            data['volume_level'] = round(value / 100.0, 2)
        elif action == 'set_temperature':
            lo = max(TEMP_RANGE[0], float((state.get('attributes') or {}).get('min_temp', TEMP_RANGE[0])))
            hi = min(TEMP_RANGE[1], float((state.get('attributes') or {}).get('max_temp', TEMP_RANGE[1])))
            if not isinstance(value, (int, float)) or not lo <= value <= hi:
                raise HABlocked('temperature must be between %g and %g' % (lo, hi))
            data['temperature'] = round(float(value), 1)
        elif value is not None:
            raise HABlocked('this action takes no value')
        return data

    def _snapshot(self, action, state):
        attrs = state.get('attributes') or {}
        if action in ('turn_on', 'turn_off'):
            return {'kind': 'onoff', 'state': state.get('state')}
        if action == 'set_brightness':
            return {'kind': 'brightness', 'state': state.get('state'),
                    'pct': round((attrs.get('brightness') or 0) * 100 / 255) if state.get('state') == 'on' else None}
        if action == 'set_volume':
            return {'kind': 'volume', 'pct': round(float(attrs.get('volume_level') or 0) * 100)}
        if action == 'set_temperature' and isinstance(attrs.get('temperature'), (int, float)):
            return {'kind': 'temperature', 'value': attrs.get('temperature')}
        return None

    def _wait(self, entity_id, ok, moving=()):
        deadline = time.monotonic() + self.verify_s
        last = None
        while True:
            last = self.state(entity_id)
            if ok(last):
                return last, True
            if time.monotonic() >= deadline:
                return last, (None if last.get('state') in moving else False)
            _sleep(self.poll_s)

    def act(self, entity_id, action, value=None):
        """One allowlisted action, then an independent read-back. Raises HABlocked before sending if not allowed."""
        domain = domain_of(entity_id or '')
        refusal = policy_refusal(domain, action)
        if refusal:
            raise HABlocked(refusal)
        before = self.state(entity_id)
        refusal = policy_refusal(domain, action, before)
        if refusal:
            raise HABlocked(refusal)
        allowed = actions_for(before)
        if action not in allowed:
            raise HABlocked('%s is not an allowed action for %s' % (action, domain))
        if before.get('state') == 'unavailable':
            raise HABlocked('the device is unavailable in Home Assistant')
        service, kind = allowed[action]
        if kind != 'momentary' and entity_id in self._before:
            raise HABlocked('this device has a pending Undo; undo it before changing it again')
        data = self._service_data(domain, action, value, before)
        snap = self._snapshot(action, before)
        self._http('POST', '%s/api/services/%s/%s' % (self.url, domain, service), self._token, data)
        after, verified = self._wait(entity_id, lambda s: EXPECT[action](s, action, value), MOVING.get(action, ()))
        if verified and snap is not None:
            self._before[entity_id] = (domain, snap)
        return {'entity': entity_id, 'action': action, 'value': value, 'before': before.get('state'), 'after': after.get('state'),
                'verified': verified, 'reversible': snap is not None}

    def undo(self, entity_id):
        if entity_id not in self._before:
            raise HABlocked('nothing to undo for this device')
        domain, snap = self._before[entity_id]
        k = snap['kind']
        if k == 'onoff' or (k == 'brightness' and snap['state'] != 'on'):
            target = snap['state']
            service = 'turn_on' if target == 'on' else 'turn_off'
            self._http('POST', '%s/api/services/%s/%s' % (self.url, domain, service), self._token, {'entity_id': entity_id})
            ok = lambda s: s.get('state') == target
        elif k == 'brightness':
            self._http('POST', '%s/api/services/light/turn_on' % self.url, self._token, {'entity_id': entity_id, 'brightness_pct': snap['pct']})
            ok = lambda s: EXPECT['set_brightness'](s, None, snap['pct'])
        elif k == 'volume':
            self._http('POST', '%s/api/services/media_player/volume_set' % self.url, self._token,
                       {'entity_id': entity_id, 'volume_level': round(snap['pct'] / 100.0, 2)})
            ok = lambda s: EXPECT['set_volume'](s, None, snap['pct'])
        else:
            self._http('POST', '%s/api/services/climate/set_temperature' % self.url, self._token,
                       {'entity_id': entity_id, 'temperature': snap['value']})
            ok = lambda s: EXPECT['set_temperature'](s, None, float(snap['value']))
        after, exact = self._wait(entity_id, ok)
        if exact:
            self._before.pop(entity_id, None)
        return {'entity': entity_id, 'restored': after.get('state'), 'exact': bool(exact)}
