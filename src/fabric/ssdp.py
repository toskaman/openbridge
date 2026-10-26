"""Bounded, read-only SSDP/UPnP discovery: one M-SEARCH to 239.255.255.250:1900 (TTL 1), parse replies, and optionally
fetch each device description XML once (GET only, private-scope LOCATION, size and time capped). Never calls SOAP actions."""
import socket
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from src.fabric.mdns import default_scope, in_scope, lan_interface_ip

GROUP = ('239.255.255.250', 1900)
MAX_REPLIES = 200
NS = '{urn:schemas-upnp-org:device-1-0}'


def search_message(st='ssdp:all', mx=2):
    return ('M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\n'
            f'MX: {mx}\r\nST: {st}\r\n\r\n').encode()


def parse_reply(data):
    lines = data.decode('utf-8', 'replace').split('\r\n')
    if not lines or not lines[0].startswith('HTTP/1.1 200'):
        raise ValueError('Not an SSDP response')
    headers = {}
    for line in lines[1:]:
        k, sep, v = line.partition(':')
        if sep and len(headers) < 30:
            headers[k.strip().lower()] = v.strip()[:300]
    if 'usn' not in headers or 'location' not in headers:
        raise ValueError('Incomplete SSDP response')
    return headers


def fetch_description(location, scope, timeout=2.0):
    parts = urlsplit(location)
    if parts.scheme != 'http' or not parts.hostname or not in_scope(parts.hostname, scope):
        return None
    req = Request(location, headers={'Accept': 'text/xml'}, method='GET')
    with build_opener(ProxyHandler({})).open(req, timeout=timeout) as r:
        raw = r.read(65537)
    if len(raw) > 65536 or b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:   # no DTD/entity expansion
        return None
    root = ET.fromstring(raw)
    dev = root.find(f'{NS}device')
    if dev is None:
        return None
    get = lambda tag: (dev.findtext(f'{NS}{tag}') or '').strip()[:80]
    return {'friendly_name': get('friendlyName'), 'manufacturer': get('manufacturer'), 'model': get('modelName'),
            'device_type': get('deviceType'), 'udn': get('UDN')}


def discover(timeout=3.0, scope=None, sock_factory=None, describe=True, fetch=fetch_description):
    scope = scope or default_scope()
    timeout = min(max(timeout, 0.5), 6.0)
    sock = sock_factory() if sock_factory else socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    replies, ignored, packets = {}, 0, 0
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        iface = None if sock_factory else lan_interface_ip(scope)
        if iface:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
        sock.bind((iface or '0.0.0.0', 0))
        sock.sendto(search_message(), GROUP)
        deadline = time.monotonic() + timeout
        resend_at = time.monotonic() + 0.6        # UDP may drop: one repeat, as commonly done for M-SEARCH
        while packets < MAX_REPLIES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if resend_at and time.monotonic() >= resend_at:
                sock.sendto(search_message(), GROUP); resend_at = None
            sock.settimeout(min(remaining, 0.6) if resend_at else remaining)
            try:
                data, (ip, _) = sock.recvfrom(4096)
            except socket.timeout:
                if resend_at:
                    continue
                break
            packets += 1
            if not in_scope(ip, scope):
                ignored += 1; continue
            try:
                h = parse_reply(data)
            except (ValueError, UnicodeError):
                continue
            uuid = h['usn'].split('::')[0][:80]
            # Embedded UPnP sub-devices share one description document: group by LOCATION (one physical device).
            entry = replies.setdefault(h['location'], {'uuid': uuid, 'ip': ip, 'location': h['location'], 'server': h.get('server', ''), 'types': set()})
            entry['types'].add(h.get('st', '')[:120])
    except OSError:
        return {'status': 'SSDP_UNAVAILABLE', 'devices': [], 'packets': packets, 'ignored_out_of_scope': ignored}
    finally:
        sock.close()
    devices = []
    for e in replies.values():
        e['types'] = sorted(t for t in e['types'] if t)
        if describe:
            try:
                e['description'] = fetch(e['location'], scope)
            except Exception:
                e['description'] = None
        devices.append(e)
    return {'status': 'OK', 'devices': devices, 'packets': packets, 'ignored_out_of_scope': ignored}
