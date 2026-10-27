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
    devs = tinytuya.Cloud(apiRegion=cloud.get('region', 'eu'), apiKey=cloud['api_key'], apiSecret=cloud['api_secret']).getdevices()
    dev = next((d for d in devs or [] if isinstance(d, dict) and d.get('id') == c['device_id']), None)
    if not dev or len(dev.get('key', '')) != 16:
        raise SystemExit('Device not found in your Tuya IoT project (link the Tuya Smart account in iot.tuya.com first).')
    out = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'tuya.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'device_id': c['device_id'], 'ip': c['ip_address'], 'local_key': dev['key'],
                               'version': str(c.get('protocol_version', '3.4')), 'source': 'Tuya IoT Cloud project (official)'}))
    print(f"Linked {c['device_id'][:4]}… key ****{dev['key'][-2:]} (matches local config: {dev['key'] == c.get('local_key')}) -> {out}")


if __name__ == '__main__':
    main()
