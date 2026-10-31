"""OpenBridge relay protocol v1 (PC side) and relay manager.

A relay (Android phone/TV companion, ESPHome proxy, ...) is enrolled once with a short pairing code shown on the relay;
both sides derive a per-relay key. Every command is HMAC-SHA256 signed, carries a nonce and an expiry, and names one
operation from a closed set. Scans are bounded (<= 15 s, <= 200 observations). Installing a companion grants nothing
by itself: the relay must report the Android permission as granted and the owner must have enabled the capability."""
import hashlib
import hmac
import json
import re
import secrets
import threading
import time

PROTOCOL = 'openbridge-relay/1'
OPERATIONS = ('discover_capabilities', 'start_discovery', 'stop_discovery', 'report_observations', 'get_status',
              'get_permissions', 'revoke_access', 'set_controls', 'get_requests', 'report_result',
              'get_commands', 'report_command', 'update_status')
MAX_CONTROLS, MAX_REQUESTS = 12, 16
CONTROL_KINDS = ('button', 'confirm', 'status', 'label')   # layout v2; a missing kind means 'button' (v1 devices)
MAX_STATUS_TEXT, MAX_LAYOUT_REVISION = 40, 100000
MAX_COMMANDS, MAX_COMMAND_TEXT, MAX_COMMAND_REPORT = 8, 500, 160
CONTROL_ID = re.compile(r'^[a-z0-9-]{4,40}$')
REQUEST_ID = re.compile(r'^[0-9a-f]{32}$')
CLIP_ID = re.compile(r'^[a-z0-9-]{1,32}$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
VOICE_MAX_BYTES = 512 * 1024   # 15 s of 16 kHz PCM16 mono is 480 000 bytes; margin, hard cap
VOICE_URL_SKEW = 120           # seconds of clock skew tolerated on a voice download URL
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
    if op == 'set_controls':
        cs = params.get('controls')
        if set(params) - {'controls', 'revision'} or not isinstance(cs, list) or len(cs) > MAX_CONTROLS or not all(
                isinstance(c, dict) and {'control_id', 'label'} <= set(c) <= {'control_id', 'label', 'kind', 'value'}
                and CONTROL_ID.match(str(c['control_id'])) and isinstance(c['label'], str) and 0 < len(c['label']) <= 40
                and c.get('kind', 'button') in CONTROL_KINDS
                and (c.get('value') is None or (isinstance(c['value'], str) and len(c['value']) <= MAX_STATUS_TEXT))
                for c in cs):
            raise RelayError('Controls must be at most 12 {control_id, label[, kind, value]} entries')
        rev = params.get('revision')
        if rev is not None and (not isinstance(rev, int) or isinstance(rev, bool) or not 1 <= rev <= MAX_LAYOUT_REVISION):
            raise RelayError('Layout revision must be an integer 1-100000')
    if op == 'update_status':
        vals = params.get('values')
        if set(params) != {'values'} or not isinstance(vals, dict) or not 0 < len(vals) <= MAX_CONTROLS or not all(
                CONTROL_ID.match(str(k)) and isinstance(v, str) and len(v) <= MAX_STATUS_TEXT for k, v in vals.items()):
            raise RelayError('Status update must map at most 12 control ids to short text')
    if op == 'report_result':
        if set(params) - {'request_id', 'state', 'text'} or not REQUEST_ID.match(str(params.get('request_id', ''))) or len(str(params.get('text', ''))) > 80:
            raise RelayError('Malformed result report')
    if op == 'report_command':
        if set(params) - {'request_id', 'status', 'text'} or not REQUEST_ID.match(str(params.get('request_id', ''))) \
                or params.get('status') not in ('resolved', 'needs_clarification', 'unsupported', 'escalation_required') \
                or not isinstance(params.get('text'), str) or len(params['text']) > MAX_COMMAND_REPORT:
            raise RelayError('Malformed command report')
    now = int(now if now is not None else time.time())
    msg = {'protocol': PROTOCOL, 'relay_id': relay_id, 'op': op, 'params': params, 'nonce': secrets.token_hex(12),
           'issued_at': now, 'expires_at': now + COMMAND_TTL}
    return {**msg, 'mac': sign(key, msg)}


MAX_NONCES = 512   # mirrors the Companion nonce-cache prune; bounds long-lived relay replay windows


def verify(key, message, seen_nonces, now=None):
    """Used by relays (and by the PC on relay replies). Rejects bad MAC, expiry, replay and unknown ops.

    seen_nonces is either a long-lived dict (nonce -> expires_at) that gives replay protection: a nonce is only
    forgotten after its message expired, and when the cache is full of live nonces new messages are refused, never
    admitted by evicting a live one; or None for a one-shot check of a single message (no replay tracking, e.g. a
    pairing reply). Other container types are rejected so no caller can rely on a count-evicting cache."""
    if seen_nonces is not None and not isinstance(seen_nonces, dict):
        raise TypeError('seen_nonces must be a dict nonce cache (nonce -> expires_at) or None for a one-shot check')
    now = time.time() if now is None else now
    msg = {k: v for k, v in message.items() if k != 'mac'}
    if not hmac.compare_digest(sign(key, msg), str(message.get('mac', ''))):
        raise RelayError('Bad signature')
    if msg.get('protocol') != PROTOCOL or msg.get('op') not in OPERATIONS + ('reply',):
        raise RelayError('Unknown protocol or operation')
    if not msg.get('issued_at', 0) - 5 <= now <= msg.get('expires_at', 0):
        raise RelayError('Expired command')
    if seen_nonces is None:             # one-shot check of a single message: nothing to remember
        return msg
    if msg['nonce'] in seen_nonces:
        raise RelayError('Replay')
    for n in [n for n, exp in seen_nonces.items() if not (isinstance(exp, (int, float)) and exp >= now)]:
        del seen_nonces[n]              # forget a nonce only once its message has expired
    if len(seen_nonces) >= MAX_NONCES:
        raise RelayError('Too many live commands; retry after they expire')   # never evict a live nonce
    seen_nonces[msg['nonce']] = msg.get('expires_at', now)
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


def applied_revision(report):
    """Layout revision the device says it rendered (device ACK), or None when absent/malformed."""
    v = report.get('applied_revision') if isinstance(report, dict) else None
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= MAX_LAYOUT_REVISION else None


def reported_full_control(report):
    """Standing owner consent the device reports (explicit on-device toggle). Strict bool, default False."""
    v = report.get('full_control') if isinstance(report, dict) else None
    return v if isinstance(v, bool) else False


def validate_requests(report, known_controls):
    """Requests from a relay are untrusted: only an id and the id of a control the owner authorized. The relay never
    supplies a skill, target or parameter; the PC takes those from the owner's grant."""
    reqs = report.get('requests')
    if not isinstance(reqs, list) or len(reqs) > MAX_REQUESTS:
        raise RelayError('Malformed request list')
    out = []
    for r in reqs:
        if not isinstance(r, dict) or not REQUEST_ID.match(str(r.get('request_id', ''))) or r.get('control_id') not in known_controls:
            continue                                # unknown or revoked control: dropped, never executed
        clean = {'request_id': r['request_id'], 'control_id': r['control_id']}
        if isinstance(r.get('pressed_at'), int) and not isinstance(r.get('pressed_at'), bool) and 0 < r['pressed_at'] < 10 ** 14:
            clean['pressed_at'] = r['pressed_at']                    # device time, milliseconds
        if isinstance(r.get('seq'), int) and not isinstance(r.get('seq'), bool) and 0 <= r['seq'] < 2 ** 53:
            clean['seq'] = r['seq']
        if r.get('gesture') in ('long_press', 'click', 'key', 'confirm'):
            clean['gesture'] = r['gesture']
        t = r.get('touch')
        if isinstance(t, dict):
            num = lambda v, hi: v if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= hi else None
            clean['touch'] = {'tool': num(t.get('tool'), 9), 'pressure': num(t.get('pressure'), 10), 'size': num(t.get('size'), 10),
                              'down_ms': num(t.get('down_ms'), 600000)}
        out.append(clean)
    return out


def validate_commands(report):
    """Typed NL commands from a relay are untrusted: bounded id, text, lang and quality only.
    Malformed entries are dropped; an oversize list is refused outright. The PC parses
    locally and never auto-approves or executes from this channel."""
    cmds = report.get('commands')
    if not isinstance(cmds, list) or len(cmds) > MAX_COMMANDS:
        raise RelayError('Malformed command list')
    out = []
    for c in cmds:
        if not isinstance(c, dict) or not REQUEST_ID.match(str(c.get('request_id', ''))):
            continue
        if c.get('lang') not in ('en', 'fr'):
            continue
        if c.get('quality') not in ('low', 'medium', 'high', 'auto'):
            continue
        if c.get('kind', 'text') == 'voice':
            # Voice clip announced by the relay; the PC downloads the raw PCM16 bytes over a
            # one-shot HMAC URL, checks size+sha256, transcribes locally, then parses as text.
            nbytes = c.get('bytes')
            if not CLIP_ID.match(str(c.get('clip_id', ''))) or not SHA256.match(str(c.get('sha256', ''))):
                continue
            if not isinstance(nbytes, int) or nbytes <= 0 or nbytes > VOICE_MAX_BYTES or nbytes % 2:
                continue
            out.append({'request_id': c['request_id'], 'kind': 'voice', 'clip_id': c['clip_id'],
                        'bytes': nbytes, 'sha256': c['sha256'], 'lang': c['lang'], 'quality': c['quality']})
            continue
        if c.get('kind', 'text') != 'text':
            continue
        text = c.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_COMMAND_TEXT:
            continue
        out.append({'request_id': c['request_id'], 'kind': 'text', 'text': text.strip(),
                    'lang': c['lang'], 'quality': c['quality']})
    return out


class RelayManager:
    """Tracks enrolled relays and picks one per request strictly by granted capability."""
    def __init__(self, transport):
        self.transport = transport            # callable(relay, message) -> reply dict, may raise OSError/TimeoutError
        self.relays = {}                      # relay_id -> {'key', 'device_key', 'capabilities', 'permissions', 'online', 'failures', 'busy'}
        self._lock = threading.Lock()

    def enroll(self, relay_id, key, device_key, declared):
        caps = {c for c in declared.get('capabilities', []) if c in ('ble_scan', 'remote_controls', 'command_submit')}
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


def _check_scope(base_url):
    import ipaddress
    from urllib.parse import urlsplit
    host = urlsplit(base_url).hostname
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise RelayError('Relay address must be an IP literal') from None
    if not (ip.is_loopback or ip.is_private) or ip.is_multicast:
        raise RelayError('Relay address outside the approved local scope')


def _opener():
    # No proxy, no redirects: the scope check guards the original URL, and a 302 must
    # never silently carry a signed message or a voice download off-scope (Sol audit).
    from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

    class _NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise RelayError('Relay redirected (refused, cross-origin not followed)')

    return build_opener(ProxyHandler({}), _NoRedirect)


def http_transport(base_url, timeout=25):
    """POST JSON to a relay. base_url must be loopback (adb forward) or a private LAN address in the approved scope."""
    from urllib.request import Request
    _check_scope(base_url)

    def send(_relay, message):
        data = json.dumps(message).encode()
        req = Request(base_url.rstrip('/') + '/ob', data=data, headers={'Content-Type': 'application/json'}, method='POST')
        from urllib.error import HTTPError
        try:
            with _opener().open(req, timeout=timeout) as r:
                raw = r.read(300_000)
        except HTTPError as error:
            raise RelayError('Relay refused: ' + error.read(200).decode('utf-8', 'replace')) from None
        reply = json.loads(raw)
        if 'error' in reply:
            raise RelayError('Relay refused: ' + str(reply['error'])[:80])
        return reply
    return send


def failover_transport(urls, lan_timeout=3, timeout=25):
    """POST JSON trying each relay URL in order. Transport errors (refused,
    reset, timeout) move to the next URL; protocol refusals (RelayError)
    propagate at once: a wrong key or a stale forward answering from another
    device must never silently reroute. LAN URLs fail fast (`lan_timeout`)
    so blackholed subnets (client isolation) fall back quickly; loopback
    (adb forward) keeps the full `timeout`. Malformed replies (HTTPException,
    bad JSON) propagate like RelayError: fail-closed, never rerouted."""
    from urllib.parse import urlsplit
    import ipaddress
    urls = list(urls or [])
    if not urls:
        raise RelayError('No relay URL')
    for u in urls:
        _check_scope(u)
    sends = []
    for u in urls:
        ip = ipaddress.ip_address(urlsplit(u).hostname)
        sends.append(http_transport(u, timeout=timeout if ip.is_loopback else lan_timeout))
    def send(_relay, message):
        last = None
        for s in sends:
            try:
                return s(_relay, message)
            except RelayError:
                raise
            except (OSError, TimeoutError) as e:
                last = e
        raise last
    return send


def voice_sig(key, clip_id, ts, nonce):
    """HMAC for a one-shot voice download URL. Mirrors the Companion's /voice check byte for byte."""
    return hmac.new(key, f'voice-v1|{clip_id}|{ts}|{nonce}'.encode(), hashlib.sha256).hexdigest()


def voice_url(base_url, key, clip_id, now=None):
    """Build a signed one-shot download URL for a voice clip announced via get_commands."""
    if not CLIP_ID.match(clip_id):
        raise RelayError('Bad clip id')
    ts = int(now if now is not None else time.time())
    nonce = secrets.token_hex(8)
    return '%s/voice?clip=%s&ts=%d&nonce=%s&sig=%s' % (
        base_url.rstrip('/'), clip_id, ts, nonce, voice_sig(key, clip_id, ts, nonce))


def fetch_voice(base_url, key, clip_id, expected_bytes, expected_sha256, timeout=25, relay_id=None, aead_version=None):
    """Download raw PCM16 mono 16 kHz bytes from a paired relay. Same local scope as http_transport.
    With aead1 negotiated the body must come back sealed (X-OB-Enc: aead1) and is authenticated before use."""
    _check_scope(base_url)
    if not isinstance(expected_bytes, int) or expected_bytes <= 0 or expected_bytes > VOICE_MAX_BYTES:
        raise RelayError('Bad voice size')
    if not SHA256.match(expected_sha256 or ''):
        raise RelayError('Bad voice hash')
    from urllib.request import Request
    from urllib.error import HTTPError
    try:
        req = Request(voice_url(base_url, key, clip_id), method='GET')
        with _opener().open(req, timeout=timeout) as r:
            sealed = r.headers.get('X-OB-Enc')
            raw = r.read(expected_bytes + 1 + (48 if aead_version else 0))
    except HTTPError as error:
        try:
            detail = error.read(200).decode('utf-8', 'replace')
        finally:
            error.close()
        raise RelayError('Relay refused voice: ' + detail) from None
    if aead_version:
        if sealed != aead_version:
            raise RelayError('Voice clip arrived unencrypted after aead1 was negotiated (refused)')
        from src.fabric import aead
        try:
            raw = aead.open_voice(key, relay_id, clip_id, raw)
        except aead.AeadError as e:
            raise RelayError('Voice clip rejected: %s' % e) from None
    if len(raw) != expected_bytes:
        raise RelayError('Voice clip size mismatch')
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise RelayError('Voice clip hash mismatch')
    return raw


def fetch_voice_urls(urls, key, clip_id, expected_bytes, expected_sha256, timeout=25, relay_id=None, aead_version=None, lan_timeout=3):
    """`fetch_voice` over ordered candidates: same failover rule as
    `failover_transport` (transport errors move on, refusals propagate)."""
    from urllib.parse import urlsplit
    import ipaddress
    urls = list(urls or [])
    if not urls:
        raise RelayError('No relay URL')
    last = None
    for u in urls:
        try:
            ip = ipaddress.ip_address(urlsplit(u).hostname or '')
            t = timeout if ip.is_loopback else min(timeout, lan_timeout)
        except ValueError:
            t = timeout  # fetch_voice reports the scope violation as RelayError
        try:
            return fetch_voice(u, key, clip_id, expected_bytes, expected_sha256, timeout=t, relay_id=relay_id, aead_version=aead_version)
        except RelayError:
            raise
        except (OSError, TimeoutError) as e:
            last = e
    raise last


def pair(send, code_reader):
    """Pairing: ask the relay to show a code, obtain it from the owner (code_reader), derive the key and prove it."""
    pc_nonce = secrets.token_hex(16)
    hello = send(None, {'op': 'pair_request', 'pc_nonce': pc_nonce})
    if hello.get('protocol') != PROTOCOL or not isinstance(hello.get('relay_nonce'), str):
        raise RelayError('Not an OpenBridge relay')
    key = derive_key(code_reader(), hello['relay_nonce'], pc_nonce)
    reply = send(None, command(key, hello['relay_id'], 'discover_capabilities'))
    declared = verify(key, reply, None).get('params', {})
    return hello['relay_id'], key, declared
