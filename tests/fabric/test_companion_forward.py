"""Companion port forwards: one local port per device (two relays must coexist). Fake adb runner, no device."""
import unittest
from types import SimpleNamespace

from src.adapters.android import AndroidAdapter


class Forward(unittest.TestCase):
    def test_each_device_gets_its_own_stable_port(self):
        state = {'next': 50001, 'list': []}
        def run(args, **kw):
            a = args[1:]
            if a == ['forward', '--list']:
                return SimpleNamespace(returncode=0, stdout='\n'.join(state['list']))
            if a[0] == '-s' and a[2:] == ['forward', 'tcp:0', 'tcp:47800']:
                p = state['next']; state['next'] += 1
                state['list'].append(f'{a[1]} tcp:{p} tcp:47800')
                return SimpleNamespace(returncode=0, stdout=f'{p}\n')
            return SimpleNamespace(returncode=0, stdout='')
        ad = AndroidAdapter(executable='adb', runner=run)
        ad._handles = {'tv-serial': 'h-tv', 'phone-serial': 'h-ph'}
        tv, ph = ad.forward_companion('h-tv'), ad.forward_companion('h-ph')
        self.assertNotEqual(tv, ph)
        self.assertEqual(ad.forward_companion('h-tv'), tv)             # stable while the forward exists
        state['list'] = [l for l in state['list'] if not l.startswith('tv-serial')]
        self.assertNotEqual(ad.forward_companion('h-tv'), tv)          # re-allocated after adb dropped it
        with self.assertRaises(ValueError):
            ad.forward_companion('h-unknown')


if __name__ == '__main__':
    unittest.main()
