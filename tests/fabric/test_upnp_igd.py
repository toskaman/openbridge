"""Read-only UPnP-IGD adapter (SIMULATED_VERIFIED with a fake IGD; no residential gateway is touched in CI)."""
import unittest
from urllib.parse import urlsplit

from src.adapters import upnp_igd
from src.adapters.upnp_igd import IGDBlocked
from src.fabric.mdns import default_scope
from src.runtime import diagnostics

LOC = 'http://192.168.1.254:5678/rootDesc.xml'
DESC = b'''<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device>
<deviceType>urn:schemas-upnp-org:device:InternetGatewayDevice:1</deviceType><deviceList><device><deviceList><device>
<serviceList><service><serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType><controlURL>/ctl/IPConn</controlURL></service>
<service><serviceType>urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1</serviceType><controlURL>/ctl/CmnIfCfg</controlURL></service>
</serviceList></device></deviceList></device></deviceList></device></root>'''


def resp(action, fields):
    inner = ''.join(f'<{k}>{v}</{k}>' for k, v in fields.items())
    return (f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
            f'<u:{action}Response xmlns:u="x">{inner}</u:{action}Response></s:Body></s:Envelope>').encode()


class FakeIGD:
    def __init__(self, desc=DESC, ext='88.120.1.2', unsupported=()):
        self.desc, self.ext, self.unsupported, self.sent = desc, ext, unsupported, []

    def __call__(self, req, cap, timeout):
        self.sent.append((req.get_method(), req.full_url, req.headers.get('Soapaction')))
        if req.get_method() == 'GET':
            return self.desc
        action = req.headers['Soapaction'].strip('"').split('#')[1]
        if action in self.unsupported:
            return b'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault/></s:Body></s:Envelope>'
        return resp(action, {
            'GetStatusInfo': {'NewConnectionStatus': 'Connected', 'NewLastConnectionError': 'ERROR_NONE', 'NewUptime': '86400'},
            'GetExternalIPAddress': {'NewExternalIPAddress': self.ext},
            'GetConnectionTypeInfo': {'NewConnectionType': 'IP_Routed'},
            'GetCommonLinkProperties': {'NewWANAccessType': 'Ethernet', 'NewLayer1UpstreamMaxBitRate': '700000000',
                                        'NewLayer1DownstreamMaxBitRate': '1000000000', 'NewPhysicalLinkStatus': 'Up'}}[action])


class IGD(unittest.TestCase):
    def test_normalized_read_masks_external_ip(self):
        f = FakeIGD()
        r = upnp_igd.read(LOC, default_scope(), http=f)
        self.assertEqual(r['connection_status'], 'Connected')
        self.assertEqual(r['uptime_s'], 86400)
        self.assertEqual(r['max_bitrate_down_mbps'], 1000.0)
        self.assertEqual(r['external_ipv4'], 'present, public (masked)')
        self.assertNotIn('88.120', repr(r))
        actions = [s[2] for s in f.sent if s[2]]
        self.assertTrue(all(a.strip('"').split('#')[1] in upnp_igd.READ_ACTIONS for a in actions))

    def test_unsupported_fields_stay_unsupported(self):
        r = upnp_igd.read(LOC, default_scope(), http=FakeIGD(unsupported=('GetCommonLinkProperties', 'GetConnectionTypeInfo')))
        self.assertEqual(r['wan_access_type'], 'UNSUPPORTED')
        self.assertEqual(r['connection_type'], 'UNSUPPORTED')
        self.assertEqual(r['connection_status'], 'Connected')

    def test_write_actions_are_refused_before_sending(self):
        f = FakeIGD()
        svc = upnp_igd.services(LOC, default_scope(), http=f)
        n = len(f.sent)
        for a in upnp_igd.NEVER + ('Anything', 'SetDefaultConnectionService'):
            with self.subTest(action=a), self.assertRaises(IGDBlocked):
                upnp_igd.soap(a, svc['wan'], LOC, default_scope(), http=f)
        self.assertEqual(len(f.sent), n)

    def test_ssrf_xxe_and_size(self):
        cases = {
            'public location': ('http://8.8.8.8/desc.xml', DESC),
            'https scheme': ('https://192.168.1.254/desc.xml', DESC),
            'control on other host': (LOC, DESC.replace(b'/ctl/IPConn', b'http://192.168.1.10/ctl')),
            'control on metadata IP': (LOC, DESC.replace(b'/ctl/IPConn', b'http://169.254.169.254/latest')),
            'doctype': (LOC, b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><root>&x;</root>'),
            'oversized': (LOC, b'<root>' + b'a' * 70000 + b'</root>'),
        }
        for name, (loc, desc) in cases.items():
            with self.subTest(case=name), self.assertRaises(IGDBlocked):
                upnp_igd.services(loc, default_scope(), http=FakeIGD(desc=desc))

    def test_double_nat_and_down_findings(self):
        f = upnp_igd.read(LOC, default_scope(), http=FakeIGD(ext='192.168.0.2'))
        names = {x['name']: x for x in diagnostics.igd(f)}
        self.assertTrue(names['double_nat_likely']['value'])
        self.assertEqual(names['double_nat_likely']['kind'], 'INFERRED')
        f['connection_status'] = 'Disconnected'
        self.assertIn('internet_down', {x['name'] for x in diagnostics.igd(f)})

    def test_discovery_marks_igd_readable_and_read_facts_uses_it(self):
        import threading
        from types import SimpleNamespace
        from src.fabric.registry import Registry
        from src.fabric.discovery import ingest_ssdp
        from src.runtime.primitives import Executor
        reg = Registry()
        ingest_ssdp(reg, {'devices': [{'uuid': 'uuid:abc', 'ip': '192.168.1.254', 'location': LOC, 'types': ['urn:schemas-upnp-org:device:InternetGatewayDevice:1'],
                                       'description': {'udn': 'uuid:abc', 'friendly_name': 'Gateway', 'device_type': 'urn:schemas-upnp-org:device:InternetGatewayDevice:1'}}]}, b's')
        key, dev = next(iter(reg.devices.items()))
        self.assertEqual(dev['category'], 'router')
        snap = reg.snapshot()
        self.assertNotIn('192.168.1.254:5678', repr(snap['devices']))
        self.assertTrue(any(l['source'] == 'UPNP_IGD' and 'read' in l['grants'] for l in snap['links']))
        c = SimpleNamespace(fabric_registry=reg, fabric_snapshot=snap, igd_read=lambda loc, scope: upnp_igd.read(loc, scope, http=FakeIGD()))
        r = Executor(c).execute('read_facts', key, {})
        self.assertEqual(r['state'], 'VERIFIED', r)
        self.assertIn('igd_connection_status', {f['name'] for f in r['result']['facts']})


if __name__ == '__main__':
    unittest.main()
