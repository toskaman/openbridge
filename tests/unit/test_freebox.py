import unittest
from src.adapters.freebox import FreeboxAdapter


class FreeboxTests(unittest.TestCase):
    def test_only_public_discovery_fields_are_returned(self):
        adapter=FreeboxAdapter(fetch=lambda: {'device_name':'Private home name','device_type':'FreeboxServer7,1',
            'api_version':'16.1','api_base_url':'/api/','uid':'PRIVATE_UUID','api_domain':'PRIVATE_DOMAIN'})
        result=adapter.discover()
        self.assertEqual(result['status'],'READY')
        self.assertNotIn('PRIVATE',str(result))
        self.assertNotIn('Private home',str(result))
        self.assertFalse(result['devices'][0]['simulated'])
        report=adapter.inspect('freebox-local')
        self.assertEqual(report['source'],'FREEBOX_DISCOVERY')
        self.assertEqual(report['status'],'READ_ONLY')

    def test_malformed_data_never_claims_a_device(self):
        for value in ([],{}, {'api_version':'999','device_type':'FreeboxServer7,1'},
                      {'api_version':'16.1','device_type':'unexpected'},
                      {'api_version':'16.1','device_type':'FreeboxServer7,1','api_base_url':'https://other/' }):
            result=FreeboxAdapter(fetch=lambda:value).discover()
            self.assertEqual(result['status'],'GATEWAY_UNAVAILABLE')
            self.assertEqual(result['devices'],[])

    def test_failed_gateway_does_not_return_demo_or_private_error(self):
        def fail():
            raise OSError('PRIVATE_ADDRESS')
        adapter=FreeboxAdapter(fetch=fail)
        result=adapter.discover()
        self.assertNotIn('PRIVATE',str(result))
        with self.assertRaises(ValueError):
            adapter.inspect('freebox-local')

    def test_arbitrary_handle_rejected(self):
        with self.assertRaises(ValueError):
            FreeboxAdapter(fetch=lambda:{}).inspect('http://other')
