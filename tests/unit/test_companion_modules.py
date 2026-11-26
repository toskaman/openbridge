"""Optional Companion modules (the Oracle): parsing of typed/spoken toggles, relay op bounds, PC-side switch."""
import unittest

from src.fabric import relay as R
from src.runtime import companion_modules as M


class ToggleParsing(unittest.TestCase):
    def test_french_and_english(self):
        self.assertEqual(M.parse_toggle("désactive l'Oracle"), ('oracle', False))
        self.assertEqual(M.parse_toggle('Active le module Oracle'), ('oracle', True))
        self.assertEqual(M.parse_toggle('Enlève l\u2019oracle'), ('oracle', False))
        self.assertEqual(M.parse_toggle('turn on the oracle'), ('oracle', True))
        self.assertEqual(M.parse_toggle('hide the Oracle'), ('oracle', False))
        self.assertEqual(M.parse_toggle('Active Loracle.'), ('oracle', True))
        self.assertEqual(M.parse_toggle('désactive les oracles'), ('oracle', False))

    def test_other_orders_are_not_toggles(self):
        for t in ('baisse le son de la télé', 'what is the oracle of delphi', 'oracle', '', 'active le salon', 'enlève la musique'):
            self.assertIsNone(M.parse_toggle(t), t)


class RelayOp(unittest.TestCase):
    def test_set_modules_bounds(self):
        key = b'k' * 32
        R.command(key, 'relay-abc', 'set_modules', {'oracle': False})
        for bad in ({}, {'oracle': 'no'}, {'camera': True}, {'oracle': 1}):
            with self.assertRaises(R.RelayError):
                R.command(key, 'relay-abc', 'set_modules', bad)

    def test_glasses_ops_bounds(self):
        key = b'k' * 32
        R.command(key, 'relay-abc', 'glasses_connect', {'seconds': 8, 'name_hint': 'ENGO', 'address': 'C0:06:46:0A:D7:B4'})
        R.command(key, 'relay-abc', 'glasses_write', {'chunks': ['/wA=']})
        R.command(key, 'relay-abc', 'glasses_events', {'wait_ms': 800})
        for op, bad in (('glasses_connect', {'seconds': 99}), ('glasses_connect', {'address': 'nope'}),
                        ('glasses_write', {'chunks': []}), ('glasses_write', {'chunks': ['A' * 1000]}),
                        ('glasses_write', {'chunks': ['not base64!']}), ('glasses_events', {'wait_ms': 5000}),
                        ('glasses_disconnect', {'x': 1})):
            with self.assertRaises(R.RelayError, msg=(op, bad)):
                R.command(key, 'relay-abc', op, bad)


class _Server:
    def __init__(self, reply):
        self.relays = type('Relays', (), {'relays': {'relay-abc': {'online': True}}})()
        self.reply, self.sent = reply, []


class SetModule(unittest.TestCase):
    def setUp(self):
        self._orig = M._send

    def tearDown(self):
        M._send = self._orig

    def test_confirmed_change(self):
        srv = _Server({'modules': {'oracle': False}})
        M._send = lambda server, rid, op, params=None: server.sent.append((rid, op, params)) or server.reply
        self.assertEqual(M.set_module(srv, 'relay-abc', 'oracle', False),
                         {'relay_id': 'relay-abc', 'module': 'oracle', 'enabled': False})
        self.assertEqual(srv.sent, [('relay-abc', 'set_modules', {'oracle': False})])

    def test_old_companion_is_reported(self):
        srv = _Server({})
        M._send = lambda server, rid, op, params=None: server.reply
        with self.assertRaises(R.RelayError):
            M.set_module(srv, 'relay-abc', 'oracle', True)

    def test_unknown_module_or_screen(self):
        srv = _Server({})
        with self.assertRaises(ValueError):
            M.set_module(srv, 'relay-abc', 'camera', True)
        with self.assertRaises(ValueError):
            M.set_module(srv, 'relay-zzz', 'oracle', True)


class PhoneLinkBatching(unittest.TestCase):
    def test_writes_go_out_in_bounded_batches_and_gestures_come_back(self):
        import base64
        import time
        from src.glasses.hub import PhoneLink
        sent, gestures = [], []

        def send(op, params):
            if op == 'glasses_connect':
                return {'state': 'READY', 'mtu': 247, 'address': 'C0:06:46:0A:D7:B4'}
            if op == 'glasses_write':
                sent.append([base64.b64decode(c) for c in params['chunks']])
                return {'state': 'READY', 'accepted': len(params['chunks']), 'events': [{'t': 'gesture'}]}
            if op == 'glasses_events':
                time.sleep(0.05)
                return {'state': 'READY', 'events': []}
            return {'state': 'IDLE'}
        link = PhoneLink(lambda: gestures.append(1), send, takeover=True)
        try:
            link.write(bytes(range(256)) * 40)               # 10 240 bytes
            for _ in range(100):
                if sum(len(c) for b in sent for c in b) >= 10240:
                    break
                time.sleep(0.02)
        finally:
            link.close()
        self.assertEqual(b''.join(c for b in sent for c in b), bytes(range(256)) * 40)
        self.assertTrue(all(len(c) <= 244 for b in sent for c in b))
        self.assertTrue(all(sum(len(c) for c in b) <= PhoneLink.BATCH_BYTES for b in sent))
        self.assertTrue(gestures)


if __name__ == '__main__':
    unittest.main()
