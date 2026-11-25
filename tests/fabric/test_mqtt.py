"""MQTT gateway: packet codec vectors, fake-broker round-trips, typed devices, discovery.

The fake broker below speaks just enough MQTT 3.1.1 to script the three device
families (Tasmota, Shelly Gen1, Zigbee2MQTT): retained-style answers on
SUBSCRIBE, state updates on command topics, PUBACKs and PINGRESPs.
"""
import json
import socket
import threading
import unittest
from unittest import mock

from src.adapters import mqtt as M
from src.fabric import mqtt_ingest as MI
from src.fabric.registry import Registry


class Codec(unittest.TestCase):
    def test_vectors(self):
        self.assertEqual(M.encode_connect('AB', 60).hex(), '100e00044d5154540402003c00024142')
        self.assertEqual(M.decode_connack(bytes.fromhex('0000')), 0)
        with self.assertRaises(M.MqttError):
            M.decode_connack(b'\x00')
        self.assertEqual(M.encode_subscribe(1, [('a/b', 0)]).hex(), '820800010003612f6200')
        self.assertEqual(M.encode_publish('a/b', b'hi').hex(), '30070003612f626869')
        self.assertEqual(M.encode_publish('a/b', b'hi', qos=1, pktid=7).hex(), '32090003612f6200076869')
        self.assertEqual(M.encode_publish('a/b', {'x': 1}).hex(), M.encode_publish('a/b', b'{"x": 1}').hex())
        self.assertEqual(M.encode_puback(7).hex(), '40020007')
        t, p, q, i = M.decode_publish(bytes.fromhex('0003612f6200076869'), 0x02)
        self.assertEqual((t, p, q, i), ('a/b', b'hi', 1, 7))
        with self.assertRaises(M.MqttError):
            M.decode_publish(b'\x00\x03a', 0x04)          # QoS 2 refused
        with self.assertRaises(M.MqttError):
            M.decode_publish(b'\x00', 0x00)               # truncated

    def test_remaining_length(self):
        for n, hx in ((0, '00'), (127, '7f'), (128, '8001'), (16383, 'ff7f'), (16384, '808001'),
                      (2097151, 'ffff7f'), (268435455, 'ffffff7f')):
            self.assertEqual(M._encode_remaining(n).hex(), hx)
            self.assertEqual(M._decode_remaining(bytes.fromhex(hx)), (n, len(hx) // 2))
        with self.assertRaises(M.MqttError):
            M._decode_remaining(bytes.fromhex('ffffffff7f'))
        with self.assertRaises(M.MqttBlocked):
            M._encode_remaining(268435456)

    def test_filter_match(self):
        self.assertTrue(M.filter_match('+/+', 'a/b'))
        self.assertTrue(M.filter_match('a/#', 'a/b/c'))
        self.assertTrue(M.filter_match('a/#', 'a'))
        self.assertTrue(M.filter_match('#', 'a/b'))
        self.assertFalse(M.filter_match('a/+', 'a'))
        self.assertFalse(M.filter_match('a/b', 'a/b/c'))
        self.assertFalse(M.filter_match('a/#/c', 'a/b/c'))


class FakeBroker:
    """Minimal scripted broker: 3 devices, retained-style answers, state updates on writes."""

    def __init__(self, connack=0, drop_writes=False, huge=False):
        self.connack, self.drop_writes, self.huge = connack, drop_writes, huge
        self.state = {'power': 'off', 'dimmer': 20, 'switch': 'off', 'watts': 0.0,
                      'zpower': 'off', 'zbright': 0}
        self.received = []
        self.subs = []          # (send_fn, filter)
        self._lock = threading.Lock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        threading.Thread(target=self._accept, daemon=True).start()

    def close(self):
        self._stop.set()
        try:
            socket.create_connection(('127.0.0.1', self.port), timeout=2).close()
        except OSError:
            pass
        self.sock.close()

    def _accept(self):
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _read_packet(self, fh):
        head = fh.read(1)
        if not head:
            return None, None, None
        ptype, flags = head[0] >> 4, head[0] & 0x0F
        n, mult = 0, 1
        for _ in range(4):
            b = fh.read(1)
            if not b:
                return None, None, None
            n += (b[0] & 0x7F) * mult
            mult *= 128
            if not b[0] & 0x80:
                break
        body = fh.read(n) if n else b''
        return ptype, flags, body

    def _send_pub(self, send, topic, payload, qos=0, pktid=0):
        send(M.encode_publish(topic, payload, qos, pktid))

    def _retained(self, send, filt):
        if M.filter_match(filt, 'tele/tasmota_plug/STATE'):
            self._send_pub(send, 'tele/tasmota_plug/STATE',
                           {'POWER': self.state['power'].upper(), 'Dimmer': self.state['dimmer']})
        if M.filter_match(filt, 'shellies/shelly1/relay/0'):
            self._send_pub(send, 'shellies/shelly1/relay/0', self.state['switch'])
            self._send_pub(send, 'shellies/shelly1/relay/0/power', str(self.state['watts']))
        if M.filter_match(filt, 'zigbee2mqtt/bulb'):
            self._send_pub(send, 'zigbee2mqtt/bulb', {'state': self.state['zpower'].upper(),
                                                     'brightness': self.state['zbright']})

    def _on_publish(self, send, topic, payload, qos, pktid):
        self.received.append((topic, payload))
        if qos:
            send(M.encode_puback(pktid))
        if self.drop_writes:
            return
        text = payload.decode('utf-8', 'replace')
        if topic == 'cmnd/tasmota_plug/Power':
            self.state['power'] = {'ON': 'on', 'OFF': 'off'}.get(text, 'on' if self.state['power'] == 'off' else 'off')
            self._fanout('stat/tasmota_plug/POWER', self.state['power'])
            self._fanout('stat/tasmota_plug/RESULT', {'POWER': self.state['power'].upper()})
        elif topic == 'cmnd/tasmota_plug/Dimmer':
            self.state['dimmer'] = max(0, min(100, int(text)))
            self._fanout('stat/tasmota_plug/RESULT', {'Dimmer': self.state['dimmer']})
        elif topic == 'shellies/shelly1/relay/0/command':
            self.state['switch'] = {'on': 'on', 'off': 'off'}.get(text, 'on' if self.state['switch'] == 'off' else 'off')
            self.state['watts'] = 42.5 if self.state['switch'] == 'on' else 0.0
            self._fanout('shellies/shelly1/relay/0', self.state['switch'])
            self._fanout('shellies/shelly1/relay/0/power', str(self.state['watts']))
        elif topic == 'zigbee2mqtt/bulb/set':
            doc = json.loads(text)
            if doc.get('state') == 'TOGGLE':
                self.state['zpower'] = 'off' if self.state['zpower'] == 'on' else 'on'
            elif doc.get('state') in ('ON', 'OFF'):
                self.state['zpower'] = doc['state'].lower()
            if 'brightness' in doc:
                self.state['zbright'] = max(0, min(254, int(doc['brightness'])))
            self._fanout('zigbee2mqtt/bulb', {'state': self.state['zpower'].upper(),
                                              'brightness': self.state['zbright']})

    def _fanout(self, topic, payload):
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        if isinstance(payload, str):
            payload = payload.encode()
        with self._lock:
            subs = list(self.subs)
        for send, filt in subs:
            if M.filter_match(filt, topic):
                try:
                    send(M.encode_publish(topic, payload))
                except OSError:
                    pass

    def _handle(self, conn):
        def send(data):
            conn.sendall(data)

        fh = conn.makefile('rb')
        try:
            ptype, _, _ = self._read_packet(fh)
            if ptype != 1:
                return
            send(b'\x20\x02\x00' + bytes([self.connack]))
            if self.connack:
                return
            while True:
                ptype, flags, body = self._read_packet(fh)
                if ptype is None:
                    return
                if ptype == 8:                                # SUBSCRIBE
                    pos, pktid = 2, int.from_bytes(body[:2], 'big')
                    while pos < len(body):
                        ln = int.from_bytes(body[pos:pos + 2], 'big')
                        filt = body[pos + 2:pos + 2 + ln].decode()
                        pos += 2 + ln + 1
                        with self._lock:
                            self.subs.append((send, filt))
                        self._retained(send, filt)
                        if self.huge:
                            send(M.encode_publish('big', b'x' * (M.MAX_PACKET + 8)))
                    send(b'\x90\x03' + body[:2] + b'\x00')
                elif ptype == 3:
                    topic, payload, qos, pktid = M.decode_publish(body, flags)
                    self._on_publish(send, topic, payload, qos, pktid)
                elif ptype == 12:
                    send(M.PINGRESP)
                elif ptype == 14:
                    return
        except (OSError, ValueError):
            pass
        finally:
            with self._lock:
                self.subs = [(s, f) for s, f in self.subs if s != send]
            try:
                conn.close()
            except OSError:
                pass


class ClientCase(unittest.TestCase):
    def test_connect_subscribe_publish(self):
        broker = FakeBroker()
        try:
            c = M.Client('127.0.0.1', broker.port)
            self.assertTrue(c.connect())
            c.subscribe('tele/+/STATE')
            c.spin(0.5)
            self.assertIsNotNone(c.cached('tele/tasmota_plug/STATE'))
            c.publish('cmnd/tasmota_plug/Power', 'ON', qos=1)
            self.assertIn(('cmnd/tasmota_plug/Power', b'ON'), broker.received)
            c.close()
        finally:
            broker.close()

    def test_non_local_broker_refused(self):
        with self.assertRaises(M.MqttBlocked):
            M.Client('8.8.8.8')

    def test_connack_refusal_and_closed_port(self):
        broker = FakeBroker(connack=4)
        try:
            with self.assertRaises(M.MqttError):
                M.Client('127.0.0.1', broker.port).connect()
        finally:
            broker.close()
        probe = socket.socket()
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()
        with self.assertRaises(M.MqttError):
            M.Client('127.0.0.1', port, timeout=1.0).connect()

    def test_oversize_packet_fails_closed(self):
        broker = FakeBroker(huge=True)
        try:
            c = M.Client('127.0.0.1', broker.port)
            c.connect()
            with self.assertRaises(M.MqttError):
                c.subscribe('big')
        finally:
            broker.close()

    def test_bad_filter_and_topic_refused(self):
        broker = FakeBroker()
        try:
            c = M.Client('127.0.0.1', broker.port)
            c.connect()
            with self.assertRaises(M.MqttBlocked):
                c.subscribe('a/#/c')
            with self.assertRaises(M.MqttBlocked):
                c.publish('a/+/c', 'x')
            c.close()
        finally:
            broker.close()


class Devices(unittest.TestCase):
    def setUp(self):
        self.broker = FakeBroker()
        self.client = M.Client('127.0.0.1', self.broker.port)
        self.client.connect()

    def tearDown(self):
        self.client.close()
        self.broker.close()

    def test_tasmota(self):
        d = M.TasmotaDevice(self.client, 'tasmota_plug')
        names = {f['name']: f['value'] for f in d.facts()}
        self.assertEqual((names['power'], names['brightness']), ('off', 20))
        r = d.set_reversible('power', 'on')
        self.assertEqual((r['before'], r['after'], r['verified']), ('off', 'on', True))
        r = d.set_reversible('brightness', 80)
        self.assertEqual((r['after'], r['verified']), (80, True))
        d.command('toggle')
        self.assertTrue(d.undo('power')['exact'])
        for name, value in (('firmware', 'x'), ('update', 'go'), ('brightness', 150)):
            with self.assertRaises(M.MqttBlocked):
                d.set_reversible(name, value)

    def test_shelly(self):
        d = M.ShellyRelay(self.client, 'shelly1')
        names = {f['name']: f['value'] for f in d.facts()}
        self.assertEqual((names['power'], names['watts']), ('off', 0.0))
        self.assertTrue(d.set_reversible('power', 'on')['verified'])
        self.assertEqual({f['name']: f['value'] for f in d.facts()}['watts'], 42.5)
        d.command('toggle')
        self.assertTrue(d.undo('power')['exact'])

    def test_zigbee2mqtt(self):
        d = M.Zigbee2MqttDevice(self.client, 'bulb')
        names = {f['name']: f['value'] for f in d.facts()}
        self.assertEqual((names['power'], names['brightness']), ('off', 0))
        self.assertTrue(d.set_reversible('power', 'on')['verified'])
        r = d.set_reversible('brightness', 50)
        self.assertEqual((r['after'], r['verified']), (50, True))
        d.command('toggle')
        self.assertTrue(d.undo('brightness')['exact'])

    def test_silent_device_never_reported_done(self):
        broker, client = FakeBroker(drop_writes=True), None
        try:
            client = M.Client('127.0.0.1', broker.port)
            client.connect()
            d = M.ShellyRelay(client, 'shelly1')
            with mock.patch.object(M, 'VERIFY_S', 0.6):
                self.assertFalse(d.set_reversible('power', 'on')['verified'])
        finally:
            if client:
                client.close()
            broker.close()

    def test_discovery_and_ingest(self):
        found = M.discover(self.client, seconds=1.0)
        self.assertEqual([(d['family'], d['label']) for d in found],
                         [('shelly', 'Shelly shelly1 relay 0'), ('tasmota', 'Tasmota tasmota_plug'),
                          ('z2m', 'bulb')])
        dev = M.open_device(self.client, found[0])
        self.assertIsInstance(dev, M.ShellyRelay)
        reg = Registry()
        from src.fabric import mqtt_ingest as MI2
        rep = MI2.ingest_mqtt(reg, self.client, b'salt', seconds=0.5)
        self.assertEqual(rep, {'status': 'OK', 'devices': 3, 'capped': 0})
        snap = json.dumps(reg.snapshot())
        for raw in ('tele/tasmota_plug/STATE', 'shellies/shelly1/relay/0/command', 'cmnd/',
                    'zigbee2mqtt/bulb/set'):
            self.assertNotIn(raw, snap)      # raw topics stay off the snapshot (labels may name devices)
        cats = sorted(d['category'] for d in reg.snapshot()['devices'])
        self.assertEqual(cats, ['hub', 'light', 'plug', 'plug'])

    def test_discovery_unavailable(self):
        self.client.close()
        reg = Registry()
        rep = MI.ingest_mqtt(reg, self.client, b'salt', seconds=0.2)
        self.assertEqual(rep['status'], 'UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
