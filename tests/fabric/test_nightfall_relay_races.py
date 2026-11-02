import threading
import unittest

from src.fabric.relay import RelayError, RelayManager, command, sign, verify


def _bad_time_reply(key, nonce):
    msg = command(key, 'r1', 'get_status')
    msg['op'] = 'reply'
    msg['nonce'] = nonce
    msg['issued_at'] = 'not-a-number'
    msg['expires_at'] = 'also-not-a-number'
    body = {k: v for k, v in msg.items() if k != 'mac'}
    body['mac'] = sign(key, body)
    return body


class TimestampRobustnessTests(unittest.TestCase):
    def test_verify_rejects_non_numeric_timestamps_as_relay_error(self):
        key = b'x' * 32
        with self.assertRaises(RelayError):
            verify(key, _bad_time_reply(key, 'n1'), {})

    def test_scan_surfaces_bad_timestamps_as_relay_error(self):
        key = b'x' * 32
        bad = _bad_time_reply(key, 'n2')
        m = RelayManager(transport=lambda relay, msg: dict(bad))
        m.enroll('r1', key, 'dev', {'capabilities': ['ble_scan'],
                                    'permissions': {'BLUETOOTH_SCAN': True,
                                                    'owner_enabled': True}})
        with self.assertRaises(RelayError):
            m.scan(seconds=1)


class SameNonceRaceTests(unittest.TestCase):
    def test_concurrent_same_nonce_accepted_at_most_once(self):
        # B-08 residual probe: verify() has no lock between the replay
        # check and the insert. Hammer one valid nonce from 32 threads
        # behind a barrier; more than one accept is a double-accept.
        # Bounded: 200 rounds, no sleeps, ~seconds.
        key = b'x' * 32
        double_accepts = 0
        for rnd in range(200):
            msg = command(key, 'r1', 'get_status')
            msg['nonce'] = 'race-%d' % rnd
            body = {k: v for k, v in msg.items() if k != 'mac'}
            body['mac'] = sign(key, body)
            seen = {}
            # Widen the check-to-insert window: a near-full cache makes
            # the prune loop do real work between the two.
            for i in range(500):
                seen['pad-%d' % i] = 4102444800.0
            barrier = threading.Barrier(32)
            accepted = []
            lock = threading.Lock()

            def worker():
                barrier.wait()
                try:
                    verify(key, dict(body), seen)
                except RelayError:
                    return
                with lock:
                    accepted.append(1)

            threads = [threading.Thread(target=worker) for _ in range(32)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            if len(accepted) > 1:
                double_accepts += 1
        self.assertEqual(double_accepts, 0,
                         'same nonce double-accepted in %d/200 rounds'
                         % double_accepts)


if __name__ == '__main__':
    unittest.main(verbosity=2)
