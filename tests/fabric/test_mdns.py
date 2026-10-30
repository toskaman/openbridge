import socket
import struct
import unittest
from src.fabric import mdns
from src.fabric.mdns import encode_name, parse_packet, assemble, discover, build_query, PTR, SRV, TXT, A


def rr(name,rtype,rdata):return encode_name(name)+struct.pack('!HHIH',rtype,1,120,len(rdata))+rdata


def response(records):
    return struct.pack('!HHHHHH',0,0x8400,0,len(records),0,0)+b''.join(records)


def freebox_packet():
    inst='Freebox Server._fbx-api._tcp.local'
    return response([rr('_fbx-api._tcp.local',PTR,encode_name(inst)),
        rr(inst,SRV,struct.pack('!HHH',0,0,80)+encode_name('Freebox-Server.local')),
        rr(inst,TXT,b''.join(bytes([len(x)])+x for x in (b'api_version=12.1',b'api_base_url=/api/',b'device_type=FreeboxServer9,1',b'uid=SECRETUID'))),
        rr('Freebox-Server.local',A,socket.inet_aton('192.168.1.254'))])


def companion_packet():
    inst='OpenBridge-39f86439fbae._openbridge-relay._tcp.local'
    return response([rr('_openbridge-relay._tcp.local',PTR,encode_name(inst)),
        rr(inst,SRV,struct.pack('!HHH',0,0,47800)+encode_name('SM-L310.local')),
        rr(inst,TXT,b''.join(bytes([len(x)])+x for x in (b'relay=relay-39f86439fbae',b'proto=openbridge-relay/1',b'ver=12',b'form=watch',b'label=SM-L310'))),
        rr('SM-L310.local',A,socket.inet_aton('192.168.1.14'))])


class FakeSock:
    def __init__(self,packets):self.packets=list(packets);self.sent=[]
    def setsockopt(self,*a):pass
    def bind(self,a):pass
    def sendto(self,d,g):self.sent.append((d,g))
    def settimeout(self,t):pass
    def recvfrom(self,n):
        if not self.packets:raise socket.timeout()
        d,ip=self.packets.pop(0);return d,(ip,5353)
    def close(self):self.closed=True


class MdnsTests(unittest.TestCase):
    def test_parse_and_assemble_freebox(self):
        inst=assemble(parse_packet(freebox_packet()))
        self.assertEqual(len(inst),1);i=inst[0]
        self.assertEqual((i['service'],i['port'],i['addresses'],i['category']),('_fbx-api._tcp',80,['192.168.1.254'],'router'))
        self.assertEqual(i['txt']['api_version'],'12.1')

    def test_compression_pointer_and_malformed_packets(self):
        # name with backward pointer to offset 12
        body=encode_name('_hap._tcp.local')+struct.pack('!HHIH',PTR,1,120,4)+bytes([3])+b'abc'+b'\xc0\x0c'
        recs=parse_packet(struct.pack('!HHHHHH',0,0x8400,0,1,0,0)+body)
        self.assertEqual(recs[0][2],'abc._hap._tcp.local')
        for bad in (b'',b'\x00'*11,struct.pack('!HHHHHH',0,0,0,1,0,0)+b'\xc0\x20',  # forward pointer
                    struct.pack('!HHHHHH',0,0,0,900,0,0),struct.pack('!HHHHHH',0,0,0,1,0,0)+encode_name('a.local')+b'\x00\x01'):
            with self.assertRaises((ValueError,struct.error)):parse_packet(bad)

    def test_discover_is_bounded_scoped_and_survives_garbage(self):
        sock=FakeSock([(b'garbage','192.168.1.10'),(freebox_packet(),'192.168.1.254'),(freebox_packet(),'8.8.8.8')])
        out=discover(timeout=0.3,sock_factory=lambda:sock)
        self.assertEqual(out['status'],'OK');self.assertEqual(len(out['instances']),1)
        self.assertEqual(out['ignored_out_of_scope'],1);self.assertTrue(sock.closed)
        self.assertTrue(all(g==('224.0.0.251',5353) for _,g in sock.sent))

    def test_out_of_scope_addresses_in_records_are_dropped(self):
        import ipaddress
        sock=FakeSock([(freebox_packet(),'192.168.1.254')])
        out=discover(timeout=0.3,scope=[ipaddress.ip_network('10.0.0.0/8')],sock_factory=lambda:sock)
        self.assertEqual(out['instances'],[]);self.assertEqual(out['ignored_out_of_scope'],1)

    def test_socket_error_is_honest_status(self):
        class Broken(FakeSock):
            def bind(self,a):raise OSError('no network')
        self.assertEqual(discover(timeout=0.3,sock_factory=lambda:Broken([]))['status'],'MDNS_UNAVAILABLE')

    def test_companion_relay_assembles(self):
        inst=assemble(parse_packet(companion_packet()))
        self.assertEqual(len(inst),1);i=inst[0]
        self.assertEqual((i['service'],i['port'],i['addresses'],i['category']),('_openbridge-relay._tcp',47800,['192.168.1.14'],'companion'))
        self.assertEqual((i['txt']['relay'],i['txt']['form'],i['txt']['ver']),('relay-39f86439fbae','watch','12'))

    def test_discover_queries_companion_service(self):
        sock=FakeSock([])
        discover(timeout=0.2,sock_factory=lambda:sock)
        self.assertTrue(any(b'_openbridge-relay' in d for d,_ in sock.sent))

    def test_queries_request_unicast_replies(self):
        qclass=struct.unpack('!H',build_query(['_openbridge-relay._tcp.local'])[-2:])[0]
        self.assertEqual(qclass,0x8001)
