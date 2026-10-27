"""Privacy-preserving payload preparation for any optional Meta cloud request (V4-05).

This is data minimisation, not anonymity: device categories, counts and timing can still be informative, and
the README must say so. Identifiers are replaced by per-request aliases (stable inside one payload, different
next time), sensitive keys are dropped, free text is scanned. `prepare` returns the exact bytes that would be
sent plus a field-level diff, so the owner can review them before consenting. Fails closed: if the final
leak scan finds anything, there is no payload."""
import hashlib
import ipaddress
import json
import re
import secrets

DROP_KEYS = {'ssid', 'key', 'password', 'passphrase', 'token', 'secret', 'serial', 'serialno', 'imei', 'mac',
             'hostname', 'host', 'address', 'ip', 'ipv4', 'ipv6', 'email', 'phone', 'account', 'user', 'username',
             'owner', 'location', 'latitude', 'longitude', 'url', 'handles', 'identifiers', 'label', 'name'}
PATTERNS = [
    ('mac', re.compile(r'\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b')),
    ('email', re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b')),
    ('url', re.compile(r'\b(?:https?|ftp|adb)://\S+', re.I)),
    ('ipv4', re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?\b')),
    ('ipv6', re.compile(r'(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?:%\w+)?(?![\w:])')),
    ('phone', re.compile(r'(?<!\w)\+?\d[\d .-]{8,}\d(?!\w)')),
    ('uuid', re.compile(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b')),
    ('opaque_id', re.compile(r'\b(?:dev|android_serial|windows_machine_guid|mac_global|ble_address|upnp_udn)[-:][0-9a-f]{8,}\b')),
    ('long_hex', re.compile(r'\b[0-9a-fA-F]{16,}\b')),
    ('wifi_qr', re.compile(r'WIFI:[^\s]*', re.I)),
    ('ssid', re.compile(r'\b(?:Freebox|Livebox|SFR|Bbox|NETGEAR|TP-Link|FRITZ!Box|Vodafone|eduroam|DIRECT)[-_ ][\w-]{2,}\b', re.I)),
    ('hostname', re.compile(r'\b[\w-]+\.(?:local|lan|home|internal|box)\b', re.I)),
    ('android_name', re.compile(r"\b\w+(?:'s| de) (?:Galaxy|Pixel|iPhone|Phone|TV|Watch|PC|Redmi|Xiaomi)\b", re.I)),
    ('owner_name', re.compile(r"\b(?:Galaxy|Pixel|iPhone|Phone|TV|Watch|PC|Redmi|Xiaomi|Tablette|T\u00e9l\u00e9phone|Montre)\s+(?:de |d')[A-Z\u00c0-\u00dd][\w-]+")),
]


class LeakDetected(ValueError):
    pass


def _ipv4_ok(m):
    try:
        ipaddress.ip_address(m.split(':')[0])
        return True
    except ValueError:
        return False


def _ipv6_ok(m):
    try:
        ipaddress.IPv6Address(m.split('%')[0])
        return sum(1 for g in m.split('%')[0].split(':') if g) >= 2     # '::' alone is noise, not an address
    except ValueError:
        return False


VALID = {'ipv4': _ipv4_ok, 'ipv6': _ipv6_ok, 'phone': lambda m: not re.fullmatch(r'\d{4}-\d{2}-\d{2}', m)}


def scan(text):
    """Return [(kind, match)] of identifier-like strings still present in text."""
    hits = []
    for kind, rx in PATTERNS:
        for m in rx.findall(text):
            if kind in VALID and not VALID[kind](m):
                continue
            hits.append((kind, m))
    return hits


class Redactor:
    def __init__(self):
        self.salt = secrets.token_bytes(16)       # new per request: aliases are not linkable across requests
        self.aliases = {}
        self.diff = []

    def alias(self, kind, value):
        k = (kind, value)
        if k not in self.aliases:
            self.aliases[k] = f'{kind}_{hashlib.sha256(self.salt + value.encode()).hexdigest()[:6]}'
        return self.aliases[k]

    def text(self, s, path):
        out = s
        for kind, rx in PATTERNS:
            def sub(m, kind=kind):
                v = m.group(0)
                if kind in VALID and not VALID[kind](v):
                    return v
                self.diff.append({'path': path, 'action': 'aliased', 'kind': kind})
                return '<' + self.alias(kind, v) + '>'
            out = rx.sub(sub, out)
        return out[:500]

    def walk(self, obj, path='$'):
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if str(k).lower() in DROP_KEYS:
                    self.diff.append({'path': f'{path}.{k}', 'action': 'dropped', 'kind': 'sensitive_key'})
                    continue
                out[k] = self.walk(v, f'{path}.{k}')
            return out
        if isinstance(obj, list):
            return [self.walk(v, f'{path}[{i}]') for i, v in enumerate(obj[:200])]
        if isinstance(obj, str):
            return self.text(obj, path)
        return obj


def prepare(obj):
    """-> {'payload': bytes, 'diff': [...], 'stats': {...}}. Raises LeakDetected if anything survives."""
    r = Redactor()
    red = r.walk(obj)
    payload = json.dumps(red, separators=(',', ':'), sort_keys=True, ensure_ascii=False)
    left = [h for h in scan(payload) if not h[1].startswith(tuple(f'{k}_' for k, _ in PATTERNS))]
    if left:
        raise LeakDetected(f'{len(left)} identifier-like value(s) survived redaction ({sorted({k for k, _ in left})})')
    return {'payload': payload.encode(), 'diff': r.diff,
            'stats': {'bytes': len(payload.encode()), 'dropped': sum(d['action'] == 'dropped' for d in r.diff),
                      'aliased': sum(d['action'] == 'aliased' for d in r.diff),
                      'sha256': hashlib.sha256(payload.encode()).hexdigest()}}
