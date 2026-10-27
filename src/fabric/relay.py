"""OpenBridge relay protocol v1 (PC side) and relay manager.

A relay (Android phone/TV companion, ESPHome proxy, ...) is enrolled once with a short pairing code shown on the relay;
both sides derive a per-relay key. Every command is HMAC-SHA256 signed, carries a nonce and an expiry, and names one
operation from a closed set. Scans are bounded (<= 15 s, <= 200 observations). Installing a companion grants nothing
by itself: the relay must report the Android permission as granted and the owner must have enabled the capability."""
import hashlib
import hmac
import json
import secrets
import threading
import time

PROTOCOL = 'openbridge-relay/1'
OPERATIONS = ('discover_capabilities', 'start_discovery', 'stop_discovery', 'report_observations', 'get_status',
              'get_permissions', 'revoke_access')
MAX_SCAN_SECONDS = 15
MAX_OBSERVATIONS = 200
COMMAND_TTL = 30


class RelayError(RuntimeError):
    pass


def derive_key(pairing_code, relay_nonce, pc_nonce):
    if not (isinstance(pairing_code, str) and pairing_code.isdigit() and len(pairing_code) == 6):
        raise RelayError('Pairing code must be the 6 digits shown on the relay')
    return hashlib.pbkdf2_hmac('sha256', pairing_code.encode(), (relay_nonce + pc_nonce).encode(), 200_000)


def sign(key, message):
    body = json.dumps(message, sort_keys=True, separators=(',', ':')).encode()
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def command(key, relay_id, op, params=None, now=None):
    if op not in OPERATIONS:
        raise RelayError('Unknown relay operation')
    params = dict(params or {})
    if op == 'start_discovery':
        seconds = params.get('seconds', 8)
        if params.get('radio') != 'ble' or not isinstance(seconds, (int, float)) or not 1 <= seconds <= MAX_SCAN_SECONDS:
            raise RelayError('Only bounded BLE discovery (1-15 s) is allowed')
    now = int(now if now is not None else time.time())
    msg = {'protocol': PROTOCOL, 'relay_id': relay_id, 'op': op, 'params': params, 'nonce': secrets.token_hex(12),
           'issued_at': now, 'expires_at': now + COMMAND_TTL}
    return {**msg, 'mac': sign(key, msg)}


MAX_NONCES = 512   # mirrors the Companion nonce-cache prune; bounds long-lived relay replay windows


def verify(key, message, seen_nonces, now=None):
    """Used by relays (and by the PC on relay replies). Rejects bad MAC, expiry, replay and unknown ops."""
    now = time.time() if now is None else now
    msg = {k: v for k, v in message.items() if k != 'mac'}
    if not hmac.compare_digest(sign(key, msg), str(message.get('mac', ''))):
        raise RelayError('Bad signature')
    if msg.get('protocol') != PROTOCOL or msg.get('op') not in OPERATIONS + ('reply',):
        raise RelayError('Unknown protocol or operation')
    if not msg.get('issued_at', 0) - 5 <= now <= msg.get('expires_at', 0):
        raise RelayError('Expired command')
    if msg['nonce'] in seen_nonces:
        raise RelayError('Replay')
    if isinstance(seen_nonces, dict):   # long-lived: nonce -> expires_at; forget a nonce only once its message has expired
        for n in [n for n, exp in seen_nonces.items() if not (isinstance(exp, (int, float)) and exp >= now)]:
            del seen_nonces[n]
        if len(seen_nonces) >= MAX_NONCES:
            raise RelayError('Too many live commands; retry after they expire')   # never evict a live nonce
        seen_nonces[msg['nonce']] = msg.get('expires_at', now)
    else:                               # ephemeral caller-owned set
        seen_nonces.add(msg['nonce'])
        while len(seen_nonces) > MAX_NONCES:
            seen_nonces.pop()
    return msg


def validate_report(report):
    """Relay replies are untrusted data: strict shape, bounded size, no free text beyond short names."""
    obs = report.get('observations')
    if not isinstance(obs, list) or len(obs) > MAX_OBSERVATIONS:
        raise RelayError('Malformed observation list')
    clean = []
    for o in obs:
        if not isinstance(o, dict) or not isinstance(o.get('address'), str) or len(o['address']) > 40:
            raise RelayError('Malformed observation')
        rssi = o.get('rssi')
        clean.append({'address': o['address'], 'name': str(o.get('name') or '')[:60],
                      'rssi': rssi if isinstance(rssi, int) and -127 <= rssi <= 20 else None,
                      'company_ids': [c for c in (o.get('company_ids') or []) if isinstance(c, int) and 0 <= c < 65536][:8],
                      'service_uuids': [str(u)[:40] for u in (o.get('service_uuids') or [])][:12],
                      'service_data_uuids': [], 'address_kind': str(o.get('address_kind') or 'unknown')[:24]})
    return clean


class RelayManager:
    """Tracks enrolled relays and picks one per request strictly by granted capability."""
    def __init__(self, transport):
        self.transport = transport            # callable(relay, message) -> reply dict, may raise OSError/TimeoutError
        self.relays = {}                      # relay_id -> {'key', 'device_key', 'capabilities', 'permissions', 'online', 'failures', 'busy'}
        self._lock = threading.Lock()

    def enroll(self, relay_id, key, device_key, declared):
        caps = {c for c in declared.get('capabilities', []) if c in ('ble_scan',)}
        self.relays[relay_id] = {'key': key, 'device_key': device_key, 'capabilities': caps,
                                 'permissions': dict(declared.get('permissions', {})), 'online': True, 'failures': 0,
                                 'busy': False, 'battery_powered': bool(declared.get('battery_powered')), 'seen': {}}

    def eligible(self, capability):
        out = []
        for rid, r in self.relays.items():
            permitted = capability == 'ble_scan' and r['permissions'].get('BLUETOOTH_SCAN') is True and r['permissions'].get('owner_enabled') is True
            if capability in r['capabilities'] and permitted and r['online'] and not r['busy']:
                out.append(rid)
        # Prefer mains-powered relays, then fewer recent failures.
        return sorted(out, key=lambda rid: (self.relays[rid]['battery_powered'], self.relays[rid]['failures'], rid))

    def scan(self, seconds=8, relay_id=None):
        candidates = [relay_id] if relay_id else self.eligible('ble_scan')
        if relay_id and relay_id not in self.eligible('ble_scan'):
            raise RelayError('Relay lacks permission, is offline or busy')
        if not candidates:
            raise RelayError('No authorized relay can scan BLE')
        rid = candidates[0]; relay = self.relays[rid]
        with self._lock:
            if relay['busy']:
                raise RelayError('Relay busy')
            relay['busy'] = True
        try:
            start = command(relay['key'], rid, 'start_discovery', {'radio': 'ble', 'seconds': min(seconds, MAX_SCAN_SECONDS)})
            reply = self.transport(relay, start)
            msg = verify(relay['key'], reply, relay['seen'])
            observations = validate_report(msg.get('params', {}))
            relay['failures'] = 0
            return rid, observations
        except (OSError, TimeoutError) as error:
            relay['failures'] += 1
            if relay['failures'] >= 3:
                relay['online'] = False
            raise RelayError(f'Relay unreachable: {type(error).__name__}') from None
        finally:
            try:
                self.transport(relay, command(relay['key'], rid, 'stop_discovery'))
            except Exception:
                pass
            relay['busy'] = False

    def revoke(self, relay_id):
        relay = self.relays.pop(relay_id, None)
        if relay:
            try:
                self.transport(relay, command(relay['key'], relay_id, 'revoke_access'))
            except Exception:
                pass        # local key is gone regardless: relay can no longer be commanded


def http_transport(base_url, timeout=25):
    """POST JSON to a relay. base_url must be loopback (adb forward) or a private LAN address in the approved scope."""
    import ipaddress
    from urllib.parse import urlsplit
    from urllib.request import Request, build_opener, ProxyHandler
    host = urlsplit(base_url).hostname
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise RelayError('Relay address must be an IP literal') from None
    if not (ip.is_loopback or ip.is_private) or ip.is_multicast:
        raise RelayError('Relay address outside the approved local scope')

    def send(_relay, message):
        data = json.dumps(message).encode()
        req = Request(base_url.rstrip('/') + '/ob', data=data, headers={'Content-Type': 'application/json'}, method='POST')
        from urllib.error import HTTPError
        try:
            with build_opener(ProxyHandler({})).open(req, timeout=timeout) as r:
                raw = r.read(300_000)
        except HTTPError as error:
            raise RelayError('Relay refused: ' + error.read(200).decode('utf-8', 'replace')) from None
        reply = json.loads(raw)
        if 'error' in reply:
            raise RelayError('Relay refused: ' + str(reply['error'])[:80])
        return reply
    return send


def pair(send, code_reader):
    """Pairing: ask the relay to show a code, obtain it from the owner (code_reader), derive the key and prove it."""
    pc_nonce = secrets.token_hex(16)
    hello = send(None, {'op': 'pair_request', 'pc_nonce': pc_nonce})
    if hello.get('protocol') != PROTOCOL or not isinstance(hello.get('relay_nonce'), str):
        raise RelayError('Not an OpenBridge relay')
    key = derive_key(code_reader(), hello['relay_nonce'], pc_nonce)
    reply = send(None, command(key, hello['relay_id'], 'discover_capabilities'))
    declared = verify(key, reply, set()).get('params', {})
    return hello['relay_id'], key, declared
