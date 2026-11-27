"""MQTT gateway: Tasmota, Shelly Gen1 and Zigbee2MQTT devices over a local broker.

Transport: an MQTT 3.1.1 subset over TCP (CONNECT / SUBSCRIBE / PUBLISH QoS 0-1 / PING),
LAN-only broker with optional username/password. No TLS (documented LAN-only, like the
v4 BridgeWindows link), no QoS 2, no retained-store serving. The client is synchronous and
poll-based (no threads): typed devices poll-verify every write against the state topics.

Conventions (each covered by loopback tests against a fake broker):
- Tasmota: `tele/<t>/STATE` ({"POWER": "ON", "Dimmer": 80}), `stat/<t>/POWER`,
  `stat/<t>/RESULT`, writes to `cmnd/<t>/Power|Dimmer`. Update/Reset/Config have no
  transport path and are refused by policy.
- Shelly Gen1: `shellies/<id>/relay/<n>` with `<n>/command` for writes, `<n>/power` watts.
- Zigbee2MQTT: `zigbee2mqtt/<name>` JSON state, writes to `zigbee2mqtt/<name>/set`.

Discovery subscribes to `tele/+/STATE`, `shellies/+/relay/+` and `zigbee2mqtt/+` for a bounded
time; see `discover()` and `src/fabric/mqtt_ingest.py`. Status: emulator (fake-broker) only.
"""
import json
import socket
import time

MAX_PACKET = 256 * 1024
MAX_TOPIC = 256
MAX_CACHE = 512
CONNECT_TIMEOUT = 5.0


class MqttError(OSError):
    pass


class MqttBlocked(PermissionError):
    """Refused before anything was sent (policy, bad host, bad topic)."""


def _encode_str(s):
    raw = s.encode('utf-8')
    if len(raw) > 0xFFFF:
        raise MqttBlocked('MQTT string too long')
    return len(raw).to_bytes(2, 'big') + raw


def _encode_remaining(n):
    if not 0 <= n <= 268435455:
        raise MqttBlocked('MQTT length out of range')
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _decode_remaining(buf, pos=0):
    n, mult, i = 0, 1, pos
    for _ in range(4):
        if i >= len(buf):
            raise MqttError('truncated remaining length')
        b = buf[i]
        i += 1
        n += (b & 0x7F) * mult
        mult *= 128
        if not b & 0x80:
            return n, i
    raise MqttError('overlong remaining length')


def _packet(ptype, flags, body):
    return bytes([(ptype << 4) | flags]) + _encode_remaining(len(body)) + body


def encode_connect(client_id, keepalive=30, username=None, password=None, clean=True):
    flags = (0x80 if username is not None else 0) | (0x40 if password is not None else 0) \
        | (0x02 if clean else 0)
    body = _encode_str('MQTT') + bytes([4, flags]) + int(keepalive).to_bytes(2, 'big') \
        + _encode_str(client_id)
    if username is not None:
        body += _encode_str(username)
    if password is not None:
        body += _encode_str(password)
    return _packet(1, 0, body)


def decode_connack(body):
    if len(body) != 2:
        raise MqttError('bad CONNACK')
    return body[1]


CONNACK_REASONS = {1: 'unacceptable protocol version', 2: 'client id rejected',
                   3: 'broker unavailable', 4: 'bad username or password', 5: 'not authorized'}


def encode_subscribe(pktid, topics):
    body = int(pktid).to_bytes(2, 'big')
    for filt, qos in topics:
        body += _encode_str(filt) + bytes([qos])
    return _packet(8, 0x02, body)


def encode_publish(topic, payload, qos=0, pktid=0, retain=False):
    if qos not in (0, 1):
        raise MqttBlocked('only QoS 0-1 supported')
    if isinstance(payload, dict):
        payload = json.dumps(payload)
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    body = _encode_str(topic)
    if qos:
        body += int(pktid or 1).to_bytes(2, 'big')
    return _packet(3, (qos << 1) | (1 if retain else 0), body + bytes(payload))


def encode_puback(pktid):
    return _packet(4, 0, int(pktid).to_bytes(2, 'big'))


PINGREQ, PINGRESP, DISCONNECT = b'\xc0\x00', b'\xd0\x00', b'\xe0\x00'


def decode_publish(body, flags):
    """(topic, payload bytes, qos, pktid). QoS 2 is refused (never negotiated)."""
    qos = (flags & 0x06) >> 1
    if qos == 2:
        raise MqttError('QoS 2 not supported')
    if len(body) < 2:
        raise MqttError('truncated PUBLISH')
    ln = int.from_bytes(body[:2], 'big')
    if len(body) < 2 + ln + (2 if qos else 0):
        raise MqttError('truncated PUBLISH')
    topic = body[2:2 + ln].decode('utf-8', 'replace')
    pos = 2 + ln
    pktid = 0
    if qos:
        pktid = int.from_bytes(body[pos:pos + 2], 'big')
        pos += 2
    return topic, bytes(body[pos:]), qos, pktid


def filter_match(filt, topic):
    """MQTT wildcard match (+ single level, # multi level, only as last level)."""
    fp, tp = filt.split('/'), topic.split('/')
    for i, f in enumerate(fp):
        if f == '#':
            return i == len(fp) - 1
        if i >= len(tp):
            return False
        if f != '+' and f != tp[i]:
            return False
    return len(fp) == len(tp)


def _check_topic(topic):
    if not isinstance(topic, str) or not topic or len(topic) > MAX_TOPIC or '+' in topic or '#' in topic \
            or any(ord(c) < 32 for c in topic):
        raise MqttBlocked('bad publish topic %r' % (topic,))
    return topic


class Client:
    """Synchronous poll-based MQTT client (no threads). Call poll()/spin() to receive."""

    def __init__(self, host, port=1883, username=None, password=None, client_id=None, keepalive=30,
                 timeout=CONNECT_TIMEOUT, clock=time.monotonic):
        from src.fabric import netguard
        if not netguard.local_host(host):
            raise MqttBlocked('refusing non-local MQTT broker %r' % (host,))
        self.host, self.port = host, int(port)
        self.username, self.password = username, password
        self.client_id = client_id or 'openbridge-%d' % (int(clock() * 1000) % 100000)
        self.keepalive, self.timeout, self.clock = keepalive, timeout, clock
        self.sock, self._buf = None, bytearray()
        self.subs = {}            # filter -> qos
        self.cache = {}           # topic -> (payload bytes, monotonic ts)
        self._pktid = 0
        self._puback = {}         # pktid -> Event-less flag set
        self._pending_subs = {}   # pktid -> filter (SUBACK tracking)
        self._last_io = clock()

    def _next_id(self):
        self._pktid = (self._pktid % 0xFFFF) + 1
        return self._pktid

    def connect(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            self.sock.settimeout(self.timeout)
            self._send(encode_connect(self.client_id, self.keepalive, self.username, self.password))
            ptype, _, body = self._read_packet()
        except (OSError, ValueError) as e:
            self.close()
            raise MqttError('MQTT connect to %s:%d failed: %s' % (self.host, self.port, e)) from None
        if ptype != 2:
            self.close()
            raise MqttError('expected CONNACK, got packet %d' % ptype)
        code = decode_connack(body)
        if code:
            self.close()
            raise MqttError('broker refused: %s' % CONNACK_REASONS.get(code, code))
        for filt, qos in self.subs.items():
            self._resub(filt, qos)
        return True

    def _resub(self, filt, qos):
        pid = self._next_id()
        self._pending_subs[pid] = filt
        self._send(encode_subscribe(pid, [(filt, qos)]))

    def close(self):
        s, self.sock = self.sock, None
        if s is not None:
            try:
                s.sendall(DISCONNECT)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass

    def _send(self, data):
        if self.sock is None:
            raise MqttError('not connected')
        try:
            self.sock.sendall(data)
        except OSError as e:
            raise MqttError('send failed: %s' % e) from None
        self._last_io = self.clock()

    def _fill(self, want, deadline):
        while len(self._buf) < want:
            if self.clock() >= deadline:
                raise MqttError('read timeout')
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                raise MqttError('read timeout') from None
            except OSError as e:
                raise MqttError('connection lost: %s' % e) from None
            if not chunk:
                raise MqttError('broker closed the connection')
            self._buf += chunk
            if len(self._buf) > MAX_PACKET + 5:
                raise MqttError('packet too large')
            self._last_io = self.clock()

    def _read_packet(self, timeout=None):
        if self.sock is None:
            raise MqttError('not connected')
        deadline = self.clock() + (self.timeout if timeout is None else timeout)
        self._fill(2, deadline)
        ptype, flags = self._buf[0] >> 4, self._buf[0] & 0x0F
        # Remaining length may straddle reads: parse incrementally (at most 4 bytes).
        for _ in range(3):
            try:
                ln, hlen = _decode_remaining(bytes(self._buf[1:5]), 0)
                break
            except MqttError:
                self._fill(len(self._buf) + 1, deadline)
        else:
            raise MqttError('bad remaining length')
        self._fill(1 + hlen + ln, deadline)
        body = bytes(self._buf[1 + hlen:1 + hlen + ln])
        del self._buf[:1 + hlen + ln]
        return ptype, flags, body

    def subscribe(self, filt, qos=0):
        if not isinstance(filt, str) or not filt or '#' in filt[:-1] or len(filt) > MAX_TOPIC:
            raise MqttBlocked('bad subscribe filter %r' % (filt,))
        self.subs[filt] = qos
        if self.sock is not None:
            self._resub(filt, qos)
            self.poll(timeout=0.3)          # drain the SUBACK; the broker applies the sub

    def publish(self, topic, payload, qos=0, timeout=5.0):
        _check_topic(topic)
        pktid = self._next_id() if qos else 0
        self._send(encode_publish(topic, payload, qos, pktid))
        if qos:
            self._puback[pktid] = False
            end = self.clock() + timeout
            while not self._puback.get(pktid):
                if self.clock() >= end:
                    raise MqttError('PUBACK timeout')
                self.poll(timeout=0.2)

    def poll(self, timeout=0.2):
        """Process incoming packets for up to timeout seconds. Returns [(topic, payload)]."""
        if self.sock is None:
            raise MqttError('not connected')
        if self.keepalive and self.clock() - self._last_io > self.keepalive:
            self._send(PINGREQ)
        end, out = self.clock() + timeout, []
        while True:
            self.sock.settimeout(max(0.05, end - self.clock()))
            try:
                ptype, flags, body = self._read_packet(timeout=max(0.05, end - self.clock()))
            except MqttError as e:
                if 'timeout' in str(e).lower():
                    return out
                raise
            if ptype == 3:
                topic, payload, qos, pktid = decode_publish(body, flags)
                if qos == 1:
                    self._send(encode_puback(pktid))
                self.cache[topic] = (payload, self.clock())
                while len(self.cache) > MAX_CACHE:
                    self.cache.pop(next(iter(self.cache)))
                out.append((topic, payload))
            elif ptype == 9:                            # SUBACK
                if len(body) >= 2:
                    pid = int.from_bytes(body[:2], 'big')
                    filt = self._pending_subs.pop(pid, None)
                    if any(c == 0x80 for c in body[2:]):
                        raise MqttError('broker refused subscription %r' % (filt,))
            elif ptype == 4 and len(body) == 2:
                self._puback[int.from_bytes(body, 'big')] = True
            elif ptype == 13:
                pass                                    # PINGRESP
            if self.clock() >= end:
                return out

    def spin(self, seconds):
        """Poll for a while (discovery). Returns [(topic, payload)] seen."""
        out, end = [], self.clock() + seconds
        while self.clock() < end:
            out += self.poll(timeout=max(0.1, end - self.clock()))
        return out

    def cached(self, topic, max_age=30.0):
        """Last payload for a topic, or None when absent or stale."""
        hit = self.cache.get(topic)
        if hit is None or self.clock() - hit[1] > max_age:
            return None
        return hit[0]


# ---------- typed devices (kit-shaped: READ / WRITABLE / COMMANDS / POLICY) ----------

POLICY = {('firmware', '*'): 'Firmware is never changed by OpenBridge.',
          ('update', '*'): 'OTA updates are never triggered by OpenBridge.',
          ('reset', '*'): 'OpenBridge never resets a device.',
          ('configuration', '*'): 'Device configuration is never changed by OpenBridge.'}

VERIFY_S = 6.0


def _json(payload):
    try:
        doc = json.loads(bytes(payload).decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def _onoff(text):
    s = (text or '').strip().lower()
    if s in ('on', 'true', '1'):
        return 'on'
    if s in ('off', 'false', '0'):
        return 'off'
    return None


class _Device:
    READ, WRITABLE, COMMANDS = {}, {}, {}

    def __init__(self, client):
        self.client = client
        self._before = {}
        self._subbed = False

    def _ensure_subs(self):
        raise NotImplementedError

    def _read_state(self):
        raise NotImplementedError

    def _write(self, name, value):
        raise NotImplementedError

    def _run_command(self, name, value):
        raise NotImplementedError

    def facts(self):
        self._ensure_subs()
        state = self._read_state()
        return [{'name': k, 'value': state[k], 'unit': unit} for k, unit in self.READ.items() if k in state]

    def _refusal(self, name, value):
        return POLICY.get((name, value)) or POLICY.get((name, '*'))

    def set_reversible(self, name, value):
        reason = self._refusal(name, value)
        if reason:
            raise MqttBlocked(reason)
        if name not in self.WRITABLE or value not in self.WRITABLE[name]:
            raise MqttBlocked('%s=%r is not an allowed setting' % (name, value))
        if name in self._before:
            raise MqttBlocked('this setting has a pending Undo; undo it before changing it again')
        self._ensure_subs()
        before = self._read_state()
        if name not in before:
            raise MqttBlocked('the device does not report %s' % name)
        self._write(name, value)
        after = self._await(name, value)
        verified = after == value
        if verified:
            self._before[name] = before[name]
        return {'setting': name, 'before': before[name], 'after': after, 'verified': verified, 'reversible': True}

    def _await(self, name, value, timeout=None):
        end = self.client.clock() + (VERIFY_S if timeout is None else timeout)
        while self.client.clock() < end:
            self.client.poll(timeout=0.2)
            if self._read_state().get(name) == value:
                return value
        return self._read_state().get(name)

    def undo(self, name):
        if name not in self._before:
            raise MqttBlocked('nothing to undo for %s' % name)
        target = self._before[name]
        self._write(name, target)
        now = self._await(name, target)
        if now == target:
            self._before.pop(name)
        return {'setting': name, 'restored': now, 'exact': now == target}

    def command(self, name, value=None):
        reason = self._refusal(name, value)
        if reason:
            raise MqttBlocked(reason)
        if name not in self.COMMANDS or (self.COMMANDS[name] is None and value is not None) \
                or (self.COMMANDS[name] is not None and value not in self.COMMANDS[name]):
            raise MqttBlocked('%s is not an allowed command' % name)
        self._ensure_subs()
        self._run_command(name, value)
        return {'command': name, 'value': value, 'verified': None, 'reversible': False}


class TasmotaDevice(_Device):
    """Tasmota plug or dimmer: tele/<t>/STATE + stat/<t>/# reads, cmnd/<t>/# writes."""

    READ = {'power': '', 'brightness': '%'}
    WRITABLE = {'power': ('on', 'off'), 'brightness': tuple(range(0, 101))}
    COMMANDS = {'toggle': None}

    def __init__(self, client, topic):
        super().__init__(client)
        if not topic or '/' in topic or '+' in topic or '#' in topic or len(topic) > 64:
            raise MqttBlocked('bad Tasmota topic %r' % (topic,))
        self.topic = topic

    def _ensure_subs(self):
        if not self._subbed:
            self.client.subscribe('tele/%s/STATE' % self.topic)
            self.client.subscribe('stat/%s/POWER' % self.topic)
            self.client.subscribe('stat/%s/RESULT' % self.topic)
            self._subbed = True

    def _read_state(self):
        self.client.poll(timeout=0.3)
        state = {}
        power = self.client.cached('stat/%s/POWER' % self.topic)
        if power is not None:
            onoff = _onoff(power.decode('utf-8', 'replace'))
            if onoff:
                state['power'] = onoff
        result = self.client.cached('stat/%s/RESULT' % self.topic)
        doc = _json(result) if result is not None else None
        if doc:
            onoff = _onoff(str(doc.get('POWER', '')))
            if onoff:
                state['power'] = onoff
            if 'Dimmer' in doc:
                try:
                    state['brightness'] = max(0, min(100, int(doc['Dimmer'])))
                except (TypeError, ValueError):
                    pass
        tele = self.client.cached('tele/%s/STATE' % self.topic)
        doc = _json(tele) if tele is not None else None
        if doc:
            state.setdefault('power', _onoff(str(doc.get('POWER', ''))) or state.get('power'))
            if 'Dimmer' in doc and 'brightness' not in state:
                try:
                    state['brightness'] = max(0, min(100, int(doc['Dimmer'])))
                except (TypeError, ValueError):
                    pass
            state = {k: v for k, v in state.items() if v is not None}
        return state

    def _write(self, name, value):
        if name == 'power':
            self.client.publish('cmnd/%s/Power' % self.topic, 'ON' if value == 'on' else 'OFF', qos=1)
        elif name == 'brightness':
            self.client.publish('cmnd/%s/Dimmer' % self.topic, str(value), qos=1)

    def _run_command(self, name, value):
        self.client.publish('cmnd/%s/Power' % self.topic, 'TOGGLE', qos=1)


class ShellyRelay(_Device):
    """Shelly Gen1 relay (+ watts on plugs/meters): shellies/<id>/..."""

    READ = {'power': '', 'watts': 'W'}
    WRITABLE = {'power': ('on', 'off')}
    COMMANDS = {'toggle': None}

    def __init__(self, client, shelly_id, index=0):
        super().__init__(client)
        if not shelly_id or '/' in shelly_id or len(shelly_id) > 64:
            raise MqttBlocked('bad Shelly id %r' % (shelly_id,))
        self.sid, self.index = shelly_id, int(index)

    def _ensure_subs(self):
        if not self._subbed:
            self.client.subscribe('shellies/%s/relay/%d' % (self.sid, self.index))
            self.client.subscribe('shellies/%s/relay/%d/power' % (self.sid, self.index))
            self._subbed = True

    def _read_state(self):
        self.client.poll(timeout=0.3)
        state = {}
        power = self.client.cached('shellies/%s/relay/%d' % (self.sid, self.index))
        if power is not None:
            onoff = _onoff(power.decode('utf-8', 'replace'))
            if onoff:
                state['power'] = onoff
        watts = self.client.cached('shellies/%s/relay/%d/power' % (self.sid, self.index))
        if watts is not None:
            try:
                state['watts'] = round(float(watts.decode('utf-8', 'replace')), 1)
            except ValueError:
                pass
        return state

    def _write(self, name, value):
        self.client.publish('shellies/%s/relay/%d/command' % (self.sid, self.index),
                            'on' if value == 'on' else 'off', qos=1)

    def _run_command(self, name, value):
        self.client.publish('shellies/%s/relay/%d/command' % (self.sid, self.index), 'toggle', qos=1)


class Zigbee2MqttDevice(_Device):
    """Zigbee2MQTT light/plug: zigbee2mqtt/<name> JSON state, .../set writes (brightness 0-254)."""

    READ = {'power': '', 'brightness': '%'}
    WRITABLE = {'power': ('on', 'off'), 'brightness': tuple(range(0, 101))}
    COMMANDS = {'toggle': None}

    def __init__(self, client, name):
        super().__init__(client)
        if not name or '/' in name or '+' in name or '#' in name or len(name) > 64:
            raise MqttBlocked('bad Zigbee2MQTT name %r' % (name,))
        self.name = name

    def _ensure_subs(self):
        if not self._subbed:
            self.client.subscribe('zigbee2mqtt/%s' % self.name)
            self._subbed = True

    def _read_state(self):
        self.client.poll(timeout=0.3)
        state = {}
        raw = self.client.cached('zigbee2mqtt/%s' % self.name)
        doc = _json(raw) if raw is not None else None
        if not doc:
            return state
        onoff = _onoff(str(doc.get('state', '')))
        if onoff:
            state['power'] = onoff
        if 'brightness' in doc:
            try:
                state['brightness'] = max(0, min(100, int(round(float(doc['brightness']) * 100 / 254))))
            except (TypeError, ValueError):
                pass
        return state

    def _write(self, name, value):
        if name == 'power':
            self.client.publish('zigbee2mqtt/%s/set' % self.name,
                                {'state': 'ON' if value == 'on' else 'OFF'}, qos=1)
        elif name == 'brightness':
            self.client.publish('zigbee2mqtt/%s/set' % self.name,
                                {'state': 'ON', 'brightness': max(0, min(254, int(round(value * 254 / 100))))}, qos=1)

    def _run_command(self, name, value):
        self.client.publish('zigbee2mqtt/%s/set' % self.name, {'state': 'TOGGLE'}, qos=1)


# ---------- discovery ----------

PATTERNS = ('tele/+/STATE', 'shellies/+/relay/+', 'zigbee2mqtt/+')


def discover(client, seconds=5.0):
    """Bounded discovery: subscribes to the three conventions, returns device descriptors.

    Each: {family: 'tasmota' | 'shelly' | 'z2m', key, label, ...ids}. Bridge/availability/set
    topics are ignored; nothing is published. Only topics observed during this
    call are reported (older cache entries are ignored).
    """
    t0 = client.clock()
    for p in PATTERNS:
        client.subscribe(p)
    client.spin(seconds)
    seen = {}
    for topic, (_payload, ts) in client.cache.items():
        if ts < t0:
            continue
        if not any(filter_match(p, topic) for p in PATTERNS):
            continue
        parts = topic.split('/')
        if topic.startswith('tele/') and topic.endswith('/STATE') and len(parts) == 3:
            seen.setdefault(('tasmota', parts[1]), {'family': 'tasmota', 'topic': parts[1],
                                                   'label': 'Tasmota %s' % parts[1]})
        elif topic.startswith('shellies/') and len(parts) == 4 and parts[2] == 'relay' and parts[3].isdigit():
            seen.setdefault(('shelly', parts[1], parts[3]),
                            {'family': 'shelly', 'shelly_id': parts[1], 'index': int(parts[3]),
                             'label': 'Shelly %s relay %s' % (parts[1], parts[3])})
        elif topic.startswith('zigbee2mqtt/') and len(parts) == 2 and parts[1] not in ('bridge',):
            seen.setdefault(('z2m', parts[1]), {'family': 'z2m', 'name': parts[1], 'label': parts[1]})
    return sorted(seen.values(), key=lambda d: (d['family'], d['label']))


def open_device(client, descriptor):
    """A typed device from a discover() descriptor."""
    fam = descriptor.get('family')
    if fam == 'tasmota':
        return TasmotaDevice(client, descriptor['topic'])
    if fam == 'shelly':
        return ShellyRelay(client, descriptor['shelly_id'], descriptor.get('index', 0))
    if fam == 'z2m':
        return Zigbee2MqttDevice(client, descriptor['name'])
    raise MqttBlocked('unknown MQTT family %r' % (fam,))
