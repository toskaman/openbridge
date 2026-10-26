"""Bounded, read-only mDNS / DNS-SD discovery (RFC 6762/6763) using only the standard library.

Queries are sent once per service type to the link-local group 224.0.0.251:5353 from an ephemeral port
(legacy unicast replies, RFC 6762 §6.7). No connection is made to any discovered device. Responders outside the
approved scope are ignored. Hard limits on time, packets, bytes and records."""
import ipaddress
import random
import socket
import struct
import time

GROUP = ('224.0.0.251', 5353)
SERVICE_TYPES = ('_fbx-api._tcp', '_googlecast._tcp', '_androidtvremote2._tcp', '_adb-tls-connect._tcp',
                 '_adb-tls-pairing._tcp', '_home-assistant._tcp', '_esphomelib._tcp', '_hap._tcp', '_matter._tcp',
                 '_matterc._udp', '_ipp._tcp', '_smb._tcp', '_workstation._tcp', '_airplay._tcp', '_raop._tcp',
                 '_spotify-connect._tcp', '_device-info._tcp', '_http._tcp')
CATEGORY = {'_fbx-api._tcp': 'router', '_googlecast._tcp': 'media', '_androidtvremote2._tcp': 'tv',
            '_adb-tls-connect._tcp': 'android', '_adb-tls-pairing._tcp': 'android', '_home-assistant._tcp': 'hub',
            '_esphomelib._tcp': 'iot', '_hap._tcp': 'iot', '_matter._tcp': 'iot', '_matterc._udp': 'iot',
            '_ipp._tcp': 'printer', '_smb._tcp': 'nas', '_workstation._tcp': 'computer', '_airplay._tcp': 'media',
            '_raop._tcp': 'media', '_spotify-connect._tcp': 'media'}
MAX_PACKETS = 400
MAX_RECORDS = 4000
A, PTR, TXT, AAAA, SRV = 1, 12, 16, 28, 33


def default_scope():
    return [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16')]


def encode_name(name):
    out = b''
    for label in name.rstrip('.').split('.'):
        raw = label.encode()
        if not 0 < len(raw) < 64:
            raise ValueError('Invalid DNS label')
        out += bytes([len(raw)]) + raw
    return out + b'\0'


def build_query(names, qid=0):
    body = b''.join(encode_name(n) + struct.pack('!HH', PTR, 1) for n in names)
    return struct.pack('!HHHHHH', qid, 0, len(names), 0, 0, 0) + body


def read_name(data, offset, depth=0):
    labels = []
    jumped = None
    while True:
        if depth > 20 or offset >= len(data):
            raise ValueError('Malformed name')
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(data):
                raise ValueError('Malformed pointer')
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if pointer >= offset:
                raise ValueError('Forward pointer')
            suffix, _ = read_name(data, pointer, depth + 1)
            labels.append(suffix)
            offset += 2
            jumped = True
            break
        if length > 63 or offset + 1 + length > len(data):
            raise ValueError('Malformed label')
        labels.append(data[offset + 1:offset + 1 + length].decode('utf-8', 'replace'))
        offset += 1 + length
    return '.'.join(l for l in labels if l), offset


def parse_packet(data):
    """Return a list of (name, type, value) records. Raises ValueError on malformed packets."""
    if len(data) < 12:
        raise ValueError('Short packet')
    _, flags, qd, an, ns, ar = struct.unpack('!HHHHHH', data[:12])
    if qd + an + ns + ar > 300:
        raise ValueError('Too many records')
    offset = 12
    for _ in range(qd):
        _, offset = read_name(data, offset)
        offset += 4
    records = []
    for _ in range(an + ns + ar):
        name, offset = read_name(data, offset)
        if offset + 10 > len(data):
            raise ValueError('Truncated record')
        rtype, _, _, rdlen = struct.unpack('!HHIH', data[offset:offset + 10])
        offset += 10
        rdata_start, end = offset, offset + rdlen
        if end > len(data):
            raise ValueError('Truncated rdata')
        if rtype == PTR:
            value, _ = read_name(data, rdata_start)
        elif rtype == SRV and rdlen >= 7:
            _, _, port = struct.unpack('!HHH', data[rdata_start:rdata_start + 6])
            target, _ = read_name(data, rdata_start + 6)
            value = (target, port)
        elif rtype == TXT:
            items, i = {}, rdata_start
            while i < end:
                n = data[i]; chunk = data[i + 1:i + 1 + n].decode('utf-8', 'replace'); i += 1 + n
                if chunk:
                    k, _, v = chunk.partition('=')
                    if len(items) < 40:
                        items[k[:40]] = v[:200]
            value = items
        elif rtype == A and rdlen == 4:
            value = socket.inet_ntoa(data[rdata_start:end])
        elif rtype == AAAA and rdlen == 16:
            value = socket.inet_ntop(socket.AF_INET6, data[rdata_start:end])
        else:
            value = None
        offset = end
        if value is not None:
            records.append((name.lower(), rtype, value))
    return records


def assemble(records):
    """Group DNS-SD records into service instances."""
    ptr, srv, txt, addr = {}, {}, {}, {}
    for name, rtype, value in records:
        if rtype == PTR and not name.startswith('_services.'):
            ptr.setdefault(name, set()).add(value.lower())
        elif rtype == SRV:
            srv[name] = value
        elif rtype == TXT:
            txt[name] = value
        elif rtype in (A, AAAA):
            addr.setdefault(name, set()).add(value)
    out = []
    for service, instances in ptr.items():
        stype = service.removesuffix('.local')
        for inst in sorted(instances):
            target, port = srv.get(inst, (None, None))
            out.append({'service': stype, 'instance': inst.removesuffix('.' + service), 'host': target, 'port': port,
                        'addresses': sorted(addr.get((target or '').lower(), ())), 'txt': txt.get(inst, {}),
                        'category': CATEGORY.get(stype, 'unknown')})
    return out


def in_scope(ip, scope):
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in net for net in scope if net.version == address.version)


def lan_interface_ip(scope):
    """Local IPv4 of the default-route interface, if it is inside the approved scope (no packet is sent)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(('192.0.2.1', 9))      # TEST-NET-1: routing lookup only
        ip = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    return ip if in_scope(ip, scope) else None


def discover(timeout=2.5, scope=None, services=SERVICE_TYPES, sock_factory=None, interface_ip=None):
    """One bounded browse. Returns {'status','instances','ignored_out_of_scope','packets'}."""
    scope = scope or default_scope()
    timeout = min(max(timeout, 0.2), 6.0)
    sock = sock_factory() if sock_factory else socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    records, packets, ignored = [], 0, set()
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)   # link-local only
        iface = interface_ip if interface_ip is not None else (None if sock_factory else lan_interface_ip(scope))
        if iface:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
        sock.bind((iface or '0.0.0.0', 0))
        names = [s + '.local' for s in services]
        for i in range(0, len(names), 8):
            sock.sendto(build_query(names[i:i + 8], random.randrange(1, 65535)), GROUP)
        deadline = time.monotonic() + timeout
        while packets < MAX_PACKETS and len(records) < MAX_RECORDS:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                data, (ip, _) = sock.recvfrom(9000)
            except socket.timeout:
                break
            packets += 1
            if not in_scope(ip, scope):
                ignored.add(ip)
                continue
            try:
                records.extend(parse_packet(data))
            except (ValueError, struct.error, UnicodeError, IndexError):
                continue    # malformed packets are dropped, never fatal
    except OSError:
        return {'status': 'MDNS_UNAVAILABLE', 'instances': [], 'ignored_out_of_scope': 0, 'packets': packets}
    finally:
        sock.close()
    instances = [i for i in assemble(records) if not i['addresses'] or all(in_scope(a, scope) for a in i['addresses'] if ':' not in a)]
    return {'status': 'OK', 'instances': instances, 'ignored_out_of_scope': len(ignored), 'packets': packets}
