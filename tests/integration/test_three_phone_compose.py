"""Scenario G composition: one app_launch per phone, none silently dropped.

'Open Play Store on all three phones' composes to 3 allowed steps with
3 distinct device keys, and to_workflow preserves all 3. If one phone
has no live link, its step is refused and to_workflow aborts loudly
instead of running a partial fan-out silently.
"""
import unittest

from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.runtime import composer as C
from src.runtime.api_v2 import router
from tests.runtime.test_routing import Clock, world


def add_phone(reg, tag, live=True):
    k = reg.upsert([Identifier('android_serial', 'ph-' + tag, True)],
                   category='phone', label='Phone ' + tag,
                   observations=[DeviceObservation(
                       'model', 'Phone ' + tag, 'ADB', 'USB', now(), True)])
    if live:
        reg.devices[k]['handles'] = {'USB': 'h-ph-' + tag}
        reg.link(Link('pc', k, 'USB', ('observe', 'read', 'control'),
                      'ADB:device'))
    return k


def devices_for(server, keys):
    snap = server.fabric_snapshot['devices']
    return [{'key': d['key'], 'label': d['label'], 'category': d['category'],
             'handles': d.get('handles', {})} for d in snap
            if d['key'] in keys]


class ThreePhoneCompose(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, keys = world(self.clock)
        reg = self.server.fabric_registry
        self.phones = [add_phone(reg, t) for t in ('a', 'b', 'c')]
        self.server.fabric_snapshot = reg.snapshot()

    def _proposal(self, labels):
        return C.proposal_from_doc({'steps': [
            {'skill_id': 'app_launch', 'target': label,
             'params': {'package': 'com.android.vending'},
             'needs': [], 'on_fail': 'fail'} for label in labels]})

    def test_three_phones_three_steps(self):
        labels = ['Phone a', 'Phone b', 'Phone c']
        composed = C.compose(self._proposal(labels),
                             devices_for(self.server, self.phones),
                             router(self.server))
        self.assertEqual((composed['allowed'], composed['refused']), (3, 0))
        keys = [s['device_key'] for s in composed['steps']]
        self.assertEqual(len(set(keys)), 3)
        body = C.to_workflow(composed)
        self.assertEqual(len(body['steps']), 3)
        self.assertEqual(sorted(s['skill_id'] for s in body['steps']),
                         ['app_launch'] * 3)

    def test_offline_phone_aborts_loudly(self):
        reg = self.server.fabric_registry
        dead = add_phone(reg, 'dead', live=False)
        self.server.fabric_snapshot = reg.snapshot()
        labels = ['Phone a', 'Phone b', 'Phone dead']
        composed = C.compose(
            self._proposal(labels),
            devices_for(self.server, self.phones[:2] + [dead]),
            router(self.server))
        self.assertEqual((composed['allowed'], composed['refused']), (2, 1))
        with self.assertRaises(C.ComposerError):
            C.to_workflow(composed)


if __name__ == '__main__':
    unittest.main()
