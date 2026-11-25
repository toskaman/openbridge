"""MQTT CLI against the loopback fake broker (no real broker in CI)."""
import unittest
from argparse import Namespace

from src import cli
from tests.fabric.test_mqtt import FakeBroker


def base(**kw):
    args = dict(host='127.0.0.1', port=None, user=None, password_env=None, seconds=1.0,
                family='tasmota', id='tasmota_plug', index=0, action='power', value='on', consent='ALLOW')
    args.update(kw)
    return Namespace(**args)


class MqttCli(unittest.TestCase):
    def setUp(self):
        self.broker = FakeBroker()
        self.addCleanup(self.broker.close)

    def test_discover(self):
        out = cli.cmd_mqtt_discover(base(port=self.broker.port))
        self.assertEqual(out['count'], 3)
        self.assertEqual({d['family'] for d in out['devices']}, {'tasmota', 'shelly', 'z2m'})

    def test_do_power_and_undo_shape(self):
        out = cli.cmd_mqtt_do(base(port=self.broker.port))
        self.assertEqual((out['setting'], out['before'], out['after'], out['verified']),
                         ('power', 'off', 'on', True))

    def test_do_brightness_and_toggle(self):
        out = cli.cmd_mqtt_do(base(port=self.broker.port, action='brightness', value='80'))
        self.assertEqual((out['after'], out['verified']), (80, True))
        out = cli.cmd_mqtt_do(base(port=self.broker.port, action='toggle', value=None))
        self.assertIsNone(out['verified'])

    def test_do_shelly(self):
        out = cli.cmd_mqtt_do(base(port=self.broker.port, family='shelly', id='shelly1'))
        self.assertTrue(out['verified'])

    def test_consent_required(self):
        with self.assertRaises(cli.CliError) as e:
            cli.cmd_mqtt_do(base(port=self.broker.port, consent=None))
        self.assertEqual(e.exception.code, 'CONSENT_REQUIRED')

    def test_bad_inputs(self):
        with self.assertRaises(cli.CliError) as e:
            cli.cmd_mqtt_do(base(port=self.broker.port, family='hue', id='x'))
        self.assertEqual(e.exception.code, 'MQTT_UNKNOWN_FAMILY')
        with self.assertRaises(cli.CliError) as e:
            cli.cmd_mqtt_do(base(port=self.broker.port, action='explode'))
        self.assertEqual(e.exception.code, 'MQTT_REFUSED')
        with self.assertRaises(cli.CliError) as e:
            cli.cmd_mqtt_discover(base(host='8.8.8.8'))
        self.assertEqual(e.exception.code, 'MQTT_BAD_HOST')
        with self.assertRaises(cli.CliError) as e:
            cli.cmd_mqtt_discover(base(port=self.broker.port, password_env='OB_TEST_MISSING_PW_XYZ'))
        self.assertEqual(e.exception.code, 'MQTT_NO_PASSWORD')

    def test_unavailable_broker(self):
        import socket
        probe = socket.socket()
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()
        with self.assertRaises(cli.CliError) as e:
            cli.cmd_mqtt_discover(base(port=port))
        self.assertEqual(e.exception.code, 'MQTT_UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
