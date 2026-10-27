"""Official Freebox OS app authorization and READ-ONLY LAN inventory.

Flow (Freebox OS API): POST login/authorize -> owner presses the button on the Freebox screen -> poll
login/authorize/<track_id> -> GET login (challenge) -> POST login/session with HMAC-SHA1(app_token, challenge).
Only GET endpoints are used after login. No configuration endpoint is ever called."""
import hashlib
import hmac
import json
import re
import threading
from urllib.request import Request, build_opener, ProxyHandler
from src.adapters.freebox import NoRedirect

APP_ID = 'fr.openbridge.devicefabric'
APP_NAME = 'OpenBridge Device Fabric'
APP_VERSION = '0.2'
BASE = 'http://mafreebox.freebox.fr'
READ_ONLY_PATHS = ('lan/browser/interfaces/', 'lan/browser/pub/', 'system/', 'connection/', 'connection/ftth/', 'wifi/config/', 'wifi/ap/')
TOKEN_NAME = 'freebox-app-token'


class FreeboxAuthError(RuntimeError):
    pass


def http(method, path, body=None, session=None):
    headers = {'Accept': 'application/json'}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); headers['Content-Type'] = 'application/json'
    if session:
        headers['X-Fbx-App-Auth'] = session
    req = Request(BASE + path, data=data, headers=headers, method=method)
    with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=6) as r:
        raw = r.read(2_000_001)
    if len(raw) > 2_000_000:
        raise FreeboxAuthError('Response too large')
    return json.loads(raw)


class FreeboxSession:
    def __init__(self, vault, api_major, transport=http, device_name='OpenBridge PC'):
        if not re.fullmatch(r'\d{1,2}', str(api_major)):
            raise ValueError('Invalid API version')
        self.vault, self.v, self.t, self.device_name = vault, f'/api/v{api_major}/', transport, device_name
        self.session = None
        self.permissions = {}
        self._lock = threading.Lock()

    def _ok(self, reply):
        if not isinstance(reply, dict) or reply.get('success') is not True:
            code = reply.get('error_code', 'unknown') if isinstance(reply, dict) else 'invalid'
            raise FreeboxAuthError(f'Freebox refused the request ({code})')
        return reply.get('result', {})

    def state(self):
        if not self.vault.available:
            return 'VAULT_UNAVAILABLE'
        return 'AUTHORIZED' if self.vault.get(TOKEN_NAME) else 'NOT_AUTHORIZED'

    def request_authorization(self):
        """Starts the official flow. The owner must accept on the Freebox front panel."""
        if not self.vault.available:
            raise FreeboxAuthError('No OS secret store; refusing to obtain a token that could not be protected')
        result = self._ok(self.t('POST', self.v + 'login/authorize/', {'app_id': APP_ID, 'app_name': APP_NAME,
                                  'app_version': APP_VERSION, 'device_name': self.device_name}))
        token, track = result.get('app_token'), result.get('track_id')
        if not isinstance(token, str) or not isinstance(track, int):
            raise FreeboxAuthError('Unexpected authorization response')
        self._pending = (token, track)
        return track

    def poll_authorization(self):
        token, track = self._pending
        status = self._ok(self.t('GET', f'{self.v}login/authorize/{track}'))
        state = status.get('status')
        if state == 'granted':
            self.vault.put(TOKEN_NAME, token)
        if state not in ('unknown', 'pending', 'timeout', 'granted', 'denied'):
            raise FreeboxAuthError('Unexpected authorization status')
        return state

    def open_session(self):
        token = self.vault.get(TOKEN_NAME)
        if not token:
            raise FreeboxAuthError('Not authorized yet')
        challenge = self._ok(self.t('GET', self.v + 'login/')).get('challenge')
        if not isinstance(challenge, str):
            raise FreeboxAuthError('No login challenge')
        password = hmac.new(token.encode(), challenge.encode(), hashlib.sha1).hexdigest()
        try:
            result = self._ok(self.t('POST', self.v + 'login/session/', {'app_id': APP_ID, 'password': password}))
        except FreeboxAuthError as error:
            if 'invalid_token' in str(error) or 'auth_required' in str(error):
                self.vault.delete(TOKEN_NAME)   # revoked on the box: forget it, require re-authorization
            raise
        self.session = result.get('session_token')
        self.permissions = {k: v for k, v in (result.get('permissions') or {}).items() if isinstance(v, bool)}
        if not isinstance(self.session, str):
            raise FreeboxAuthError('No session token')
        return self.permissions

    def get(self, path):
        if path not in READ_ONLY_PATHS:
            raise FreeboxAuthError('Path not on the read-only allowlist')
        with self._lock:
            if not self.session:
                self.open_session()
            try:
                return self._ok(self.t('GET', self.v + path, session=self.session))
            except FreeboxAuthError as error:
                if 'auth_required' not in str(error):
                    raise
                self.open_session()     # expired session: one renewal, no loop
                return self._ok(self.t('GET', self.v + path, session=self.session))

    def lan_hosts(self):
        out = []
        for host in (self.get('lan/browser/pub/') or [])[:1000]:
            if not isinstance(host, dict):
                continue
            l2 = host.get('l2ident') or {}
            ips = [c.get('addr') for c in host.get('l3connectivities') or [] if isinstance(c, dict) and c.get('af') == 'ipv4' and c.get('active')]
            out.append({'name': str(host.get('primary_name') or '')[:60], 'type': str(host.get('host_type') or 'unknown')[:30],
                        'vendor': str(host.get('vendor_name') or '')[:60], 'active': bool(host.get('active')),
                        'reachable': bool(host.get('reachable')), 'mac': l2.get('id') if l2.get('type') == 'mac_address' else None,
                        'ipv4': [i for i in ips if isinstance(i, str)][:4], 'last_activity': host.get('last_activity')})
        return out
