"""Hardware proof for the read-only UPnP-IGD adapter: one bounded SSDP search, then the allowlisted queries on each
gateway that advertises a WAN service. Prints a sanitized receipt (no address, no UDN). Run on the home LAN:
    python -m dev.igd_read
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone

from src.adapters import upnp_igd
from src.fabric import ssdp
from src.fabric.mdns import default_scope


def main():
    res = ssdp.discover(timeout=3.0, describe=False)
    out = {'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'ssdp_status': res['status'], 'gateways': []}
    for d in res['devices']:
        if not any('InternetGatewayDevice' in t or 'WANIPConnection' in t or 'WANPPPConnection' in t for t in d['types']):
            continue
        try:
            r = upnp_igd.read(d['location'], default_scope())
            out['gateways'].append({'gateway': 'gateway-' + hashlib.sha256(d['uuid'].encode()).hexdigest()[:6], **r})
        except Exception as e:
            out['gateways'].append({'error': type(e).__name__})
    try:
        out['commit'] = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
    except OSError:
        pass
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
