"""Wear OS dynamic capability manifest (V4-08).

A watch paired by the owner over ADB wireless debugging is described by what it actually reports, not by its model
name: `pm list features` (allowlisted feature names only) plus the same read-only diagnostics as other Android
devices. Each capability is `read`/`observe` only, carries the exact evidence that produced it, and is re-derived
on every read (a feature that disappears after an update disappears from the manifest). No health data is read:
sensor features are listed as *present*, never sampled.
"""
import hashlib
import json

FEATURE_CAPS = {   # android feature -> (capability, level, note)
    'android.hardware.type.watch': ('wear_os_device', 'observe', 'device declares itself a watch'),
    'android.hardware.bluetooth_le': ('ble_radio_present', 'observe', 'BLE radio present (no scan is started)'),
    'android.hardware.wifi': ('wifi_radio_present', 'observe', 'Wi-Fi radio present'),
    'android.hardware.location.gps': ('gps_present', 'observe', 'GPS present (location never read)'),
    'android.hardware.sensor.heartrate': ('heart_rate_sensor_present', 'observe', 'sensor present; health data never read'),
    'android.hardware.nfc': ('nfc_present', 'observe', 'NFC present'),
    'android.hardware.audio.output': ('speaker_present', 'observe', 'audio output present'),
    'android.hardware.microphone': ('microphone_present', 'observe', 'microphone present (never opened)'),
    'android.hardware.telephony': ('cellular_present', 'observe', 'cellular modem present'),
}
FINDING_CAPS = {   # diagnostics finding -> capability (read-only values OpenBridge can actually read)
    'battery_level': 'battery_read', 'battery_temperature': 'battery_temperature_read', 'storage_free': 'storage_read',
    'uptime': 'uptime_read', 'wifi': 'wifi_state_read', 'power_state': 'power_state_read', 'security_patch': 'security_patch_read',
}


def features(pm_output):
    out = set()
    for line in (pm_output or '').splitlines():
        name = line.strip().removeprefix('feature:').split('=')[0]
        if name in FEATURE_CAPS:
            out.add(name)
    return sorted(out)


def build(pm_output, facts, android_release=None):
    feats = features(pm_output)
    if 'android.hardware.type.watch' not in feats:
        return None
    caps = [{'capability': FEATURE_CAPS[f][0], 'level': FEATURE_CAPS[f][1], 'evidence': f'pm list features: {f}',
             'note': FEATURE_CAPS[f][2], 'status': 'OBSERVED'} for f in feats]
    names = {f['name'] for f in facts}
    caps += [{'capability': cap, 'level': 'read', 'evidence': f'finding {name} read in this pass', 'status': 'OBSERVED'}
             for name, cap in sorted(FINDING_CAPS.items()) if name in names]
    caps.append({'capability': 'control', 'level': 'write', 'status': 'BLOCKED', 'evidence': 'policy',
                 'note': 'no write primitive exists for watches'})
    manifest = {'version': 1, 'kind': 'wear_os_dynamic', 'android_release': android_release, 'capabilities': caps}
    manifest['sha256'] = hashlib.sha256(json.dumps(caps, sort_keys=True).encode()).hexdigest()
    return manifest
