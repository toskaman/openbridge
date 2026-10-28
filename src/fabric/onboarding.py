"""Connect-a-device view: which phones, tablets, watches and other hardware are visible, what model they appear to
be, and the simplest honest way to bring each one into OpenBridge.

Inputs are only what bounded discovery already produced (mDNS/DNS-SD, ADB, Freebox inventory, BLE via relays).
Nothing here probes the network. Each candidate lists ordered onboarding methods with a status:
  READY        the method can be started from the UI now (e.g. the phone is showing its pairing screen)
  NEEDS_STEP   one owner action on the device is required first (instructions included)
  CONNECTED    already linked; nothing to do
  UNAVAILABLE  honestly not possible here (reason included), e.g. there is no iOS Companion app
Model names come from the device itself (ADB getprop, mDNS TXT) or the gateway inventory; vendor-only guesses
from Bluetooth company identifiers are marked weak.
"""
import re

APPLE_PREFIX = (('iPhone', 'phone'), ('iPad', 'tablet'), ('Watch', 'watch'), ('AppleTV', 'tv'), ('Mac', 'computer'), ('iMac', 'computer'))
PHONE_BLE = {76: 'Apple', 117: 'Samsung', 224: 'Google', 343: 'Xiaomi', 911: 'Xiaomi', 637: 'Huawei', 1177: 'OnePlus'}


def _val(reg, key, name):
    o = reg.best_value(key, name)
    return None if o is None else o.value


def _methods_android(dev, linked, pairing, companion_ready, kind):
    usb = {'id': 'adb_usb', 'title': 'USB cable', 'status': 'CONNECTED' if linked.get('USB') else 'NEEDS_STEP',
           'steps': ['Settings → About phone → tap "Build number" 7 times', 'Settings → Developer options → USB debugging: on',
                     'Plug the cable into this PC and accept "Allow USB debugging" on the phone'],
           'detail': 'Most complete control. Some vendors (e.g. Xiaomi MIUI) also need "USB debugging (Security settings)" to allow taps and settings.'}
    wifi = {'id': 'adb_wifi', 'title': 'Wi-Fi pairing (Android 11+, Wear OS)',
            'status': 'CONNECTED' if linked.get('WIFI') else 'READY' if pairing else 'NEEDS_STEP',
            'steps': ['Developer options → Wireless debugging: on', 'Tap "Pair device with pairing code"',
                      'Type the 6-digit code here' + ('' if pairing else ' together with the IP:port shown under the code')],
            'pairing_address': f'{pairing[0]}:{pairing[1]}' if pairing else None,
            'detail': 'No cable. The phone shows a 6-digit code; OpenBridge runs the official adb pairing with it.'}
    comp = {'id': 'companion_apk', 'title': 'OpenBridge Companion app (Android)',
            'status': 'UNAVAILABLE' if not companion_ready else 'READY' if (linked.get('USB') or linked.get('WIFI')) else 'NEEDS_STEP',
            'steps': ['Install from this PC once the phone is linked (USB or Wi-Fi)', 'or open the LAN download link on the phone and accept Android\'s install prompt'],
            'detail': 'Adds Bluetooth relay for this PC. Android always asks the owner before installing; OpenBridge cannot install silently.',
            'reason': None if companion_ready else 'Companion APK not built on this PC (python -m dev.build_companion)'}
    if kind == 'watch':
        return [wifi, usb | {'status': 'UNAVAILABLE', 'reason': 'watches have no USB data port'}]
    return [usb, wifi, comp]


def _methods_apple(model):
    return [{'id': 'companion_ios', 'title': 'OpenBridge Companion for iOS', 'status': 'UNAVAILABLE',
             'reason': 'No iOS Companion app exists yet (planned). iOS allows no ADB-like debugging bridge.', 'steps': [],
             'detail': f'{model or "Apple device"} stays observe-only: OpenBridge can show it is on the network, not control it.'}]


def candidates(snapshot, registry, companion_ready=False):
    if not snapshot or registry is None:
        return []
    out = []
    links = {}
    for l in snapshot.get('links', []):
        links.setdefault(l['child'], []).append(l)
    for d in snapshot['devices']:
        key, cat = d['key'], d['category']
        dev = registry.devices.get(key, {})
        svcs = set(dev.get('mdns_services') or ())
        model = _val(registry, key, 'model')
        vendor = _val(registry, key, 'manufacturer') or _val(registry, key, 'vendor')
        handles = dev.get('handles', {})
        linked = {'USB': 'USB' in handles, 'WIFI': 'WIFI' in handles}
        ep = dev.get('endpoints') or {}
        pairing = ep.get('_adb-tls-pairing._tcp')
        kind, confidence, evidence, apple = None, 'strong', [], False
        if cat in ('phone', 'watch', 'android', 'tv') and (linked['USB'] or linked['WIFI']):
            kind, evidence = ('watch' if cat == 'watch' else 'tv' if cat == 'tv' else 'phone'), ['ADB link (model read from the device)']
        elif svcs & {'_adb-tls-pairing._tcp', '_adb-tls-connect._tcp'}:
            kind, evidence = 'phone', ['Android wireless debugging is on (mDNS)']
        elif cat == 'apple' or svcs & {'_apple-mobdev2._tcp', '_companion-link._tcp'}:
            m = str(model or '')
            kind, apple = next((k for p, k in APPLE_PREFIX if m.startswith(p)), 'apple'), True
            evidence = ['Apple device services on the LAN (mDNS)'] + ([f'model identifier {m}'] if m else [])
        elif cat == 'phone':
            kind, evidence = 'phone', ['reported as a phone/tablet by the gateway inventory']
        elif cat == 'ble':
            cids = _val(registry, key, 'ble_company_ids') or []
            v = next((PHONE_BLE[c] for c in cids if c in PHONE_BLE), None)
            if v:
                kind, confidence, vendor, evidence = 'phone_maybe', 'weak', v, [f'Bluetooth advertiser from {v} (could be a phone, watch, earbuds…)']
        if not kind:
            continue
        if apple:
            methods = _methods_apple(model)
        elif kind in ('phone', 'watch', 'tv'):
            methods = _methods_android(dev, linked, pairing, companion_ready, kind)
        elif kind == 'phone_maybe':
            methods = [{'id': 'identify', 'title': 'Identify it', 'status': 'NEEDS_STEP', 'steps': ['If it is your Android phone, turn on Wireless debugging and run discovery again'],
                        'detail': 'Bluetooth advertisements alone cannot prove what this device is.'}]
        else:
            methods = _methods_apple(model)
        state = 'CONNECTED' if any(m['status'] == 'CONNECTED' for m in methods) else 'READY' if any(m['status'] == 'READY' for m in methods) else 'ACTION_NEEDED' if kind != 'phone_maybe' else 'IDENTIFY'
        out.append({'device_key': key, 'label': d['label'], 'kind': kind, 'category': cat, 'model': model, 'vendor': vendor,
                    'platform': 'ios/apple' if apple else 'android' if kind in ('phone', 'watch', 'tv') else 'unknown', 'confidence': confidence, 'evidence': evidence, 'state': state, 'methods': methods})
    order = {'READY': 0, 'ACTION_NEEDED': 1, 'IDENTIFY': 2, 'CONNECTED': 3}
    return sorted(out, key=lambda c: (order.get(c['state'], 9), c['kind'], c['label']))
