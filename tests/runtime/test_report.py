import tempfile
import unittest

from src.runtime.primitives import Executor
from tests.runtime.test_primitives import ctx


class Report(unittest.TestCase):
    def test_report_redacted_and_honest(self):
        c, key = ctx(tempfile.mkdtemp())
        c.fabric_registry.devices[key]['label'] = 'Secret Phone Name'
        ex = Executor(c)
        r = ex.execute('diagnostic_report', 'fabric', {})
        self.assertEqual(r['state'], 'VERIFIED')
        md = r['result']['markdown']
        self.assertNotIn('Secret Phone Name', md)
        self.assertIn('phone 1', md)
        self.assertIn('| uptime | 1.0 h | OBSERVED |', md)
        c.android._handles = {}
        rep = ex.execute('diagnostic_report', 'fabric', {})['result']['report']
        self.assertEqual(rep['summary']['devices_unavailable'], 1)
        self.assertIn('DEVICE_UNAVAILABLE', rep['devices'][0]['errors'][0])
        named = ex.execute('diagnostic_report', 'fabric', {'redact': False})['result']['markdown']
        self.assertIn('Secret Phone Name', named)


if __name__ == '__main__':
    unittest.main()
