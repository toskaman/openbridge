"""Local-network host guard, shared by every adapter and client.

One definition of "local enough for plain HTTP / direct pairing": loopback, private and
link-local IPs, the Tailscale/WireGuard mesh (100.64.0.0/10, *.ts.net — the mesh already
encrypts), localhost-style names and LAN suffixes (.local, .lan, .home.arpa). Anything else —
public IPs, public DNS names, URLs with credentials or odd characters — is refused.

Callers add their own extras (a vendor default name) and decide whether bare single-label
hostnames are acceptable: device adapters allow them (mDNS short names like `lamp`), URL
validators do not (a bare name could resolve through a search domain to the public internet).
"""
import ipaddress

TAILNET = ipaddress.ip_network('100.64.0.0/10')   # Tailscale / CGNAT range: reachable only inside the private mesh

LOCAL_NAMES = ('localhost', 'homeassistant')
LOCAL_SUFFIXES = ('.localhost', '.local', '.lan', '.home.arpa', '.ts.net')


def local_host(host, bare_names=False, extra_names=(), extra_suffixes=()):
    """True when host is clearly local. See module docstring for the exact rules."""
    h = (host or '').strip().lower().rstrip('.') if isinstance(host, str) else ''
    if not h or '/' in h or '\\' in h or '@' in h or ' ' in h:
        return False
    if h in LOCAL_NAMES or h in set(extra_names or ()):
        return True
    if h.endswith(LOCAL_SUFFIXES + tuple(extra_suffixes or ())):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        pass
    else:
        return ip.is_loopback or ip.is_private or ip.is_link_local \
            or (ip.version == 4 and ip in TAILNET)
    if not bare_names:
        return False
    return '.' not in h and h.replace('-', '').replace('_', '').isalnum()


def require_local(host, what='host', **kw):
    """local_host(), but raising ValueError with a readable reason instead of returning False."""
    if not local_host(host, **kw):
        raise ValueError('refusing non-local %s %r' % (what, host))
    return host
