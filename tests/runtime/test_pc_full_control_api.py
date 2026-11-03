"""POST/GET /api/v2/pc/full-control: owner toggle with mandatory warning."""
import unittest
from types import SimpleNamespace

from src.fabric import pc_consent as PC
from src.fabric.contracts import Identifier
from src.fabric.registry import Registry
from src.runtime import api_v2


def srv(tmp):
    reg = Registry()
    key = reg.upsert([Identifier('windows_machine_guid', 'aa01bb02', True)],
                     category='computer', label='PC 1')
    return SimpleNamespace(fabric_registry=reg, fabric_snapshot=reg.snapshot(),
                           pc_consent=PC.PcConsentStore(tmp / 'pcfc.json')), key


class FullControlApi(unittest.TestCase):
    def test_get_reports_off_plus_warning(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            s, key = srv(Path(tmp))
            code, body = api_v2.get(s, '/api/v2/pc/full-control', 'device_key=' + key)
            self.assertEqual(code, 200)
            self.assertFalse(body['enabled'])
            self.assertIn('managed', body['warning'].lower())

    def test_post_enable_needs_confirm(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            s, key = srv(Path(tmp))
            code, _ = api_v2.post(s, '/api/v2/pc/full-control',
                                  {'device_key': key, 'enable': True})
            self.assertEqual(code, 400)
            code, body = api_v2.post(s, '/api/v2/pc/full-control',
                                     {'device_key': key, 'enable': True, 'confirm': True})
            self.assertEqual(code, 200)
            self.assertTrue(body['enabled'])

    def test_post_disable_needs_no_confirm(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            s, key = srv(Path(tmp))
            api_v2.post(s, '/api/v2/pc/full-control',
                        {'device_key': key, 'enable': True, 'confirm': True})
            code, body = api_v2.post(s, '/api/v2/pc/full-control',
                                     {'device_key': key, 'enable': False})
            self.assertEqual(code, 200)
            self.assertFalse(body['enabled'])

    def test_unknown_device_is_404(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            s, _ = srv(Path(tmp))
            code, _ = api_v2.post(s, '/api/v2/pc/full-control',
                                  {'device_key': 'nope', 'enable': True, 'confirm': True})
            self.assertEqual(code, 404)


if __name__ == '__main__':
    unittest.main()
