"""Read-only UPnP Internet Gateway Device adapter (generic "ISP Router API (e.g., Freebox OS / UPnP-IGD)").

Scope: only on a gateway that SSDP already found and whose description advertises a WAN connection service.
Only the allowlisted query actions below can be sent; anything else (AddPortMapping, DeletePortMapping,
SetConnectionType, ForceTermination, RequestConnection, ...) is refused before any byte is sent. UPnP-IGD is
not a Wi-Fi diagnostic API: it never provides client lists, channels or DHCP leases, and nothing here infers them.

SSRF/XXE controls: description and control URLs must be http, private-scope and on the SAME host as the SSDP
LOCATION; no proxy, no redirects; responses are capped (64 KiB description, 16 KiB SOAP) and parsed with
DTD/entity declarations rejected. The external IPv4 is never returned in clear: only whether it is public/private.
"""
import ipaddress
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

from src.fabric.mdns import in_scope

NS_DEV = '{urn:schemas-upnp-org:device-1-0}'
WAN_SERVICES = ('urn:schemas-upnp-org:service:WANIPConnection:2', 'urn:schemas-upnp-org:service:WANIPConnection:1',
                'urn:schemas-upnp-org:service:WANPPPConnection:1')
COMMON = 'urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1'
READ_ACTIONS = {  # action -> service family
    'GetStatusInfo': 'wan', 'GetExternalIPAddress': 'wan', 'GetConnectionTypeInfo': 'wan',
    'GetCommonLinkProperties': 'common', 'GetTotalBytesReceived': 'common', 'GetTotalBytesSent': 'common'}
NEVER = ('AddPortMapping', 'AddAnyPortMapping', 'DeletePortMapping', 'DeletePortMappingRange', 'SetConnectionType',
         'ForceTermination', 'RequestConnection', 'RequestTermination', 'SetAutoDisconnectTime', 'SetIdleDisconnectTime',
         'SetWarnDisconnectDelay', 'GetGenericPortMappingEntry', 'GetSpecificPortMappingEntry', 'GetListOfPortMappings')
MAX_DESC, MAX_SOAP = 65536, 16384


class IGDBlocked(PermissionError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _safe_url(url, location, scope):
    p, base = urlsplit(url), urlsplit(location)
    if p.scheme != 'http' or not p.hostname or p.hostname != base.hostname or not in_scope(p.hostname, scope):
        raise IGDBlocked('URL outside the gateway that answered SSDP')
    return url


def _parse(raw, cap):
    if len(raw) > cap:
        raise IGDBlocked('response too large')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise IGDBlocked('DTD/entity declarations refused')
    return ET.fromstring(raw)


def _http(req, cap, timeout):
    with build_opener(ProxyHandler({}), _NoRedirect()).open(req, timeout=timeout) as r:
        ctype = (r.headers.get('Content-Type') or '').lower()
        if 'xml' not in ctype:
            raise IGDBlocked('unexpected content type')
        return r.read(cap + 1)


def services(location, scope, timeout=2.0, http=_http):
    """-> {'wan': (service_type, control_url) | None, 'common': (...) | None, 'device_type': str}"""
    _safe_url(location, location, scope)
    root = _parse(http(Request(location, headers={'Accept': 'text/xml'}, method='GET'), MAX_DESC, timeout), MAX_DESC)
    found = {'wan': None, 'common': None, 'device_type': (root.findtext(f'.//{NS_DEV}deviceType') or '')[:120]}
    for svc in root.iter(f'{NS_DEV}service'):
        st = (svc.findtext(f'{NS_DEV}serviceType') or '').strip()
        ctl = (svc.findtext(f'{NS_DEV}controlURL') or '').strip()
        if not ctl:
            continue
        url = _safe_url(urljoin(location, ctl), location, scope)
        if st in WAN_SERVICES and (found['wan'] is None or WAN_SERVICES.index(st) < WAN_SERVICES.index(found['wan'][0])):
            found['wan'] = (st, url)
        elif st == COMMON:
            found['common'] = (st, url)
    return found


def soap(action, service, location, scope, timeout=2.0, http=_http):
    if action in NEVER or action not in READ_ACTIONS:
        raise IGDBlocked(f'{action} is not an allowlisted read-only IGD query')
    st, url = service
    _safe_url(url, location, scope)
    body = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action} xmlns:u="{st}"/></s:Body></s:Envelope>').encode()
    req = Request(url, data=body, method='POST', headers={'Content-Type': 'text/xml; charset="utf-8"',
                                                          'SOAPAction': f'"{st}#{action}"'})
    root = _parse(http(req, MAX_SOAP, timeout), MAX_SOAP)
    resp = next((el for el in root.iter() if el.tag.endswith(action + 'Response')), None)
    if resp is None:
        raise IGDBlocked('no response element (fault or unsupported)')
    return {child.tag.split('}')[-1]: (child.text or '').strip()[:64] for child in resp}


def _mask_ip(v):
    try:
        ip = ipaddress.IPv4Address(v)
    except ValueError:
        return 'UNSUPPORTED' if not v else 'invalid'
    return 'present, private (double NAT likely)' if ip.is_private else ('none' if ip.is_unspecified else 'present, public (masked)')


def read(location, scope, timeout=2.0, http=_http):
    """Normalized facade. Unsupported fields are 'UNSUPPORTED', never inferred."""
    svc = services(location, scope, timeout, http)
    out = {'gateway_device_type': svc['device_type'] or 'UNSUPPORTED', 'connection_status': 'UNSUPPORTED',
           'uptime_s': 'UNSUPPORTED', 'last_connection_error': 'UNSUPPORTED', 'external_ipv4': 'UNSUPPORTED',
           'connection_type': 'UNSUPPORTED', 'wan_access_type': 'UNSUPPORTED', 'link_status': 'UNSUPPORTED',
           'max_bitrate_down_mbps': 'UNSUPPORTED', 'max_bitrate_up_mbps': 'UNSUPPORTED', 'calls': []}
    def call(action, fam):
        if svc[fam] is None:
            return None
        try:
            r = soap(action, svc[fam], location, scope, timeout, http)
            out['calls'].append({'action': action, 'ok': True})
            return r
        except Exception as e:  # one unsupported query must not hide the others
            out['calls'].append({'action': action, 'ok': False, 'error': type(e).__name__})
            return None
    s = call('GetStatusInfo', 'wan')
    if s:
        out['connection_status'] = s.get('NewConnectionStatus') or 'UNSUPPORTED'
        out['last_connection_error'] = s.get('NewLastConnectionError') or 'UNSUPPORTED'
        if (s.get('NewUptime') or '').isdigit():
            out['uptime_s'] = int(s['NewUptime'])
    e = call('GetExternalIPAddress', 'wan')
    if e:
        out['external_ipv4'] = _mask_ip(e.get('NewExternalIPAddress', ''))
    t = call('GetConnectionTypeInfo', 'wan')
    if t and t.get('NewConnectionType'):
        out['connection_type'] = t['NewConnectionType']
    c = call('GetCommonLinkProperties', 'common')
    if c:
        out['wan_access_type'] = c.get('NewWANAccessType') or 'UNSUPPORTED'
        out['link_status'] = c.get('NewPhysicalLinkStatus') or 'UNSUPPORTED'
        for k, n in (('NewLayer1DownstreamMaxBitRate', 'max_bitrate_down_mbps'), ('NewLayer1UpstreamMaxBitRate', 'max_bitrate_up_mbps')):
            if (c.get(k) or '').isdigit():
                out[n] = round(int(c[k]) / 1e6, 1)
    return out
