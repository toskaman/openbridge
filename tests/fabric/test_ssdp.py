import ipaddress, socket, unittest
from src.fabric import ssdp
from src.fabric.discovery import ingest_ssdp
from src.fabric.registry import Registry

REPLY=b'HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=1800\r\nLOCATION: http://192.168.1.24:49152/desc.xml\r\nSERVER: Linux UPnP/1.0\r\nST: urn:schemas-upnp-org:device:MediaRenderer:1\r\nUSN: uuid:abc-123::urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n'


class Sock:
    def __init__(s,p):s.p=list(p);s.sent=[]
    def setsockopt(s,*a):pass
    def bind(s,a):pass
    def sendto(s,d,g):s.sent.append((d,g))
    def settimeout(s,t):pass
    def recvfrom(s,n):
        if not s.p:raise socket.timeout()
        d,ip=s.p.pop(0);return d,(ip,1900)
    def close(s):s.closed=True


class SsdpTests(unittest.TestCase):
    def test_parse_and_bounds(self):
        self.assertEqual(ssdp.parse_reply(REPLY)['usn'][:8],'uuid:abc')
        for bad in (b'NOTIFY * HTTP/1.1\r\n\r\n',b'HTTP/1.1 200 OK\r\nST: x\r\n\r\n'):
            with self.assertRaises(ValueError):ssdp.parse_reply(bad)
        self.assertIn(b'MX: 2',ssdp.search_message())

    def test_discover_dedups_scopes_and_survives_garbage(self):
        s=Sock([(REPLY,'192.168.1.24'),(REPLY.replace(b'USN: uuid:abc-123',b'USN: uuid:embedded-456'),'192.168.1.24'),(b'junk','192.168.1.5'),(REPLY,'8.8.8.8')])
        out=ssdp.discover(1,sock_factory=lambda:s,fetch=lambda loc,sc:{'friendly_name':'Living TV','manufacturer':'LG','model':'webOS','device_type':'urn:schemas-upnp-org:device:MediaRenderer:1','udn':'uuid:abc-123'})
        self.assertEqual(len(out['devices']),1);self.assertEqual(out['ignored_out_of_scope'],1);self.assertTrue(s.closed)
        self.assertEqual(s.sent[0][1],('239.255.255.250',1900))
        r=Registry();ingest_ssdp(r,out,b's');d=r.snapshot()['devices'][0]
        self.assertEqual((d['category'],d['label']),('media','Living TV'));self.assertEqual(r.snapshot()['links'][0]['grants'],['observe'])

    def test_description_fetch_refuses_out_of_scope_and_dtd(self):
        self.assertIsNone(ssdp.fetch_description('http://8.8.8.8/x.xml',ssdp.default_scope()))
        self.assertIsNone(ssdp.fetch_description('https://192.168.1.2/x.xml',ssdp.default_scope()))
