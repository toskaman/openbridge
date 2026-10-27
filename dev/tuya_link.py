"""Link the owner's Tuya vacuum through the OFFICIAL Tuya IoT Cloud project (no key extraction).

Reads the owner's project credentials (api_key/api_secret/region) and device id from a file the owner points to,
asks Tuya's cloud API for the device's local key (the same call `python -m tinytuya wizard` makes), and stores
{device_id, ip, local_key, version} in %LOCALAPPDATA%/OpenBridge/tuya.json. Nothing is printed except a masked check.
    python -m dev.tuya_link --config "E:\\PROJECT PET RIFT\\Tuya\\config.json"
"""
import argparse
import json
import os
from pathlib import Path


def main():
    a = argparse.ArgumentParser(); a.add_argument('--config', required=True); a = a.parse_args()
    c = json.loads(Path(a.config).read_text(encoding='utf-8'))
    import tinytuya
    cloud = c['cloud']
    key, source = None, None
    try:
        cl = tinytuya.Cloud(apiRegion=cloud.get('region', 'eu'), apiKey=cloud['api_key'], apiSecret=cloud['api_secret'])
        r = cl.cloudrequest('/v1.0/devices/' + c['device_id'])
        if isinstance(r, dict) and r.get('success') and len((r.get('result') or {}).get('local_key', '')) == 16:
            key, source = r['result']['local_key'], 'Tuya IoT Cloud project (official, live)'
        else:
            print('Tuya cloud:', (r or {}).get('msg') if isinstance(r, dict) else r)
    except Exception as e:
        print('Tuya cloud unreachable:', type(e).__name__)
    if key is None and isinstance(c.get('local_key'), str) and len(c['local_key']) == 16:
        # Key the owner already saved from the same Tuya IoT project; the local handshake below proves it is right.
        key, source = c['local_key'], "owner's saved Tuya IoT project config (cloud not used)"
    if key is None:
        raise SystemExit('No local key: renew the free IoT Core subscription of your Tuya project, then retry.')
    dev = {'key': key}
    out = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'tuya.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'device_id': c['device_id'], 'ip': c['ip_address'], 'local_key': dev['key'],
                               'version': str(c.get('protocol_version', '3.4')), 'source': source}))
    d = tinytuya.Device(c['device_id'], c['ip_address'], key, version=float(c.get('protocol_version', '3.4')))
    d.set_socketTimeout(4)
    st = d.status()
    ok = isinstance(st, dict) and 'dps' in st
    print(f"Linked {c['device_id'][:4]}… source: {source} -> {out}; local handshake: {'OK, ' + str(len(st['dps'])) + ' DPs' if ok else st}")
    if not ok:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
