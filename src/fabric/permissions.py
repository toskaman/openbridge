"""§10 permission center: catalog, verify parsers, live states, intents.

Every entry maps an OS-level permission to its OpenBridge effect, what breaks
without it, a read-only verify path (adb shell), and the system screen or
command that grants it. States are measured, never guessed: a failed check
yields 'unknown', and permissions the companion does not declare are labeled
so, with their observable state still reported when the OS exposes it.
"""
import re

COMPANION_PKG = 'fr.openbridge.companion'
SHELL_PKG = 'com.android.shell'


class PermissionsError(ValueError):
    pass

CATALOG = [
    {'id': 'bluetooth_scan', 'os': 'android', 'title': 'Nearby devices (BLE scan)',
     'applies_to': 'companion', 'declared': True, 'min_sdk': 31,
     'why': 'Companion BLE scanning for relay discovery (scan only, neverForLocation).',
     'breaks': ['BLE relay discovery', 'watch/phone proximity features'],
     'verify': {'method': 'appops', 'op': 'BLUETOOTH_SCAN',
                'argv': ['appops', 'get', '{pkg}', 'BLUETOOTH_SCAN']},
     'intent': {'action': 'android.settings.BLUETOOTH_SETTINGS'},
     'grant': None,
     'steps': ['Open Bluetooth settings', 'Enable Bluetooth', 'Return here and tap Recheck']},
    {'id': 'bluetooth_connect', 'os': 'android', 'title': 'Bluetooth connect',
     'applies_to': 'companion', 'declared': True, 'min_sdk': 31,
     'why': 'Lets the companion show the system Turn-on-Bluetooth dialog when the owner asks.',
     'breaks': ['in-app Bluetooth enable prompt'],
     'verify': {'method': 'appops', 'op': 'BLUETOOTH_CONNECT',
                'argv': ['appops', 'get', '{pkg}', 'BLUETOOTH_CONNECT']},
     'intent': {'action': 'android.settings.BLUETOOTH_SETTINGS'},
     'grant': None,
     'steps': ['Open Bluetooth settings', 'Enable Bluetooth', 'Return here and tap Recheck']},
    {'id': 'fine_location', 'os': 'android', 'title': 'Precise location (Android ≤30)',
     'applies_to': 'companion', 'declared': True, 'min_sdk': None,
     'why': 'Declared with maxSdk 30: on Android ≤30, BLE and Wi-Fi scans require it. On 31+ the companion cannot request it.',
     'breaks': ['BLE scans on Android ≤30', 'Wi-Fi scan lists on Android ≤30'],
     'verify': {'method': 'appops', 'op': 'FINE_LOCATION',
                'argv': ['appops', 'get', '{pkg}', 'FINE_LOCATION']},
     'intent': {'action': 'android.settings.APPLICATION_DETAILS_SETTINGS', 'data': True},
     'grant': None,
     'steps': ['Open the app info page', 'Permissions', 'Allow location', 'Return here and tap Recheck']},
    {'id': 'record_audio', 'os': 'android', 'title': 'Microphone (voice input)',
     'applies_to': 'companion', 'declared': True, 'min_sdk': None,
     'why': 'The owner taps Speak, Android transcribes, the text lands in the reviewed field.',
     'breaks': ['companion voice input'],
     'verify': {'method': 'appops', 'op': 'RECORD_AUDIO',
                'argv': ['appops', 'get', '{pkg}', 'RECORD_AUDIO']},
     'intent': {'action': 'android.settings.APPLICATION_DETAILS_SETTINGS', 'data': True},
     'grant': None,
     'steps': ['Open the app info page', 'Permissions', 'Allow microphone', 'Return here and tap Recheck']},
    {'id': 'post_notifications', 'os': 'android', 'title': 'Notifications',
     'applies_to': 'companion', 'declared': False, 'min_sdk': 33,
     'why': 'Undeclared: the companion cannot post notifications at all.',
     'breaks': ['companion status notifications'],
     'verify': {'method': 'appops', 'op': 'POST_NOTIFICATION',
                'argv': ['appops', 'get', '{pkg}', 'POST_NOTIFICATION']},
     'intent': {'action': 'android.settings.APP_NOTIFICATION_SETTINGS', 'data': True},
     'grant': None,
     'steps': ['Needs a companion update declaring POST_NOTIFICATIONS', 'Then allow on the app info page']},
    {'id': 'nearby_wifi', 'os': 'android', 'title': 'Nearby Wi-Fi devices',
     'applies_to': 'companion', 'declared': False, 'min_sdk': 33,
     'why': 'Undeclared: the companion cannot list Wi-Fi networks directly.',
     'breaks': ['in-app Wi-Fi network lists'],
     'verify': {'method': 'appops', 'op': 'NEARBY_WIFI_DEVICES',
                'argv': ['appops', 'get', '{pkg}', 'NEARBY_WIFI_DEVICES']},
     'intent': {'action': 'android.settings.APPLICATION_DETAILS_SETTINGS', 'data': True},
     'grant': None,
     'steps': ['Needs a companion update declaring NEARBY_WIFI_DEVICES', 'Then allow on the app info page']},
    {'id': 'overlay', 'os': 'android', 'title': 'Draw over other apps',
     'applies_to': 'companion', 'declared': False, 'min_sdk': None,
     'why': 'Undeclared: no floating controls over other apps.',
     'breaks': ['floating controls'],
     'verify': {'method': 'appops', 'op': 'SYSTEM_ALERT_WINDOW',
                'argv': ['appops', 'get', '{pkg}', 'SYSTEM_ALERT_WINDOW']},
     'intent': {'action': 'android.settings.action.MANAGE_OVERLAY_PERMISSION', 'data': True},
     'grant': None,
     'steps': ['Needs a companion update declaring SYSTEM_ALERT_WINDOW', 'Then allow on the overlay screen']},
    {'id': 'accessibility', 'os': 'android', 'title': 'Accessibility service',
     'applies_to': 'companion', 'declared': False, 'min_sdk': None,
     'why': 'Undeclared: the companion exposes no accessibility service.',
     'breaks': ['UI automation reads (not implemented)'],
     'verify': {'method': 'setting', 'key': 'enabled_accessibility_services',
                'argv': ['settings', 'get', 'secure', 'enabled_accessibility_services']},
     'intent': {'action': 'android.settings.ACCESSIBILITY_SETTINGS'},
     'grant': None,
     'steps': ['Needs a companion update with an accessibility service', 'Then enable it in Accessibility settings']},
    {'id': 'device_admin', 'os': 'android', 'title': 'Device admin',
     'applies_to': 'companion', 'declared': False, 'min_sdk': None,
     'why': 'Undeclared: the companion is not a device admin.',
     'breaks': ['remote lock/wipe (not implemented)'],
     'verify': {'method': 'admin', 'argv': ['dumpsys', 'device_policy']},
     'intent': {'action': 'android.app.action.ADD_DEVICE_ADMIN'},
     'grant': None,
     'steps': ['Needs a companion update with a DeviceAdminReceiver', 'Then activate it when prompted']},
    {'id': 'battery_opt_out', 'os': 'android', 'title': 'Ignore battery optimizations',
     'applies_to': 'companion', 'declared': False, 'min_sdk': None,
     'why': 'The companion can be dozed: long-lived relay scans and the background link may drop.',
     'breaks': ['long-lived relay scans', 'background companion link'],
     'verify': {'method': 'whitelist', 'argv': ['dumpsys', 'deviceidle', 'whitelist']},
     'intent': {'action': 'android.settings.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS', 'data': True},
     'grant': None,
     'steps': ['Open the battery optimization screen', 'Allow the companion to run unrestricted',
               'Return here and tap Recheck']},
    {'id': 'exact_alarm', 'os': 'android', 'title': 'Exact alarms',
     'applies_to': 'companion', 'declared': False, 'min_sdk': 31,
     'why': 'Undeclared: the companion cannot schedule exact alarms.',
     'breaks': ['precisely timed automations'],
     'verify': {'method': 'appops', 'op': 'SCHEDULE_EXACT_ALARM',
                'argv': ['appops', 'get', '{pkg}', 'SCHEDULE_EXACT_ALARM']},
     'intent': {'action': 'android.settings.REQUEST_SCHEDULE_EXACT_ALARM', 'data': True},
     'grant': None,
     'steps': ['Needs a companion update declaring SCHEDULE_EXACT_ALARM', 'Then allow on the alarms screen']},
    {'id': 'media_projection', 'os': 'android', 'title': 'Screen capture consent',
     'applies_to': 'companion', 'declared': False, 'min_sdk': None,
     'why': 'Granted per session inside the app; Android exposes no static state to read.',
     'breaks': ['companion screen sharing'],
     'verify': {'method': 'interactive'},
     'intent': None,
     'grant': None,
     'steps': ['Start sharing inside the companion app', 'Accept the system consent dialog each session']},
    {'id': 'write_secure_settings', 'os': 'android', 'title': 'Secure settings (adb shell)',
     'applies_to': 'shell', 'declared': True, 'min_sdk': None,
     'why': 'Lets PC-driven automation write secure/global settings over adb.',
     'breaks': ['secure/global settings writes from the PC'],
     'verify': {'method': 'permgrant', 'perm': 'android.permission.WRITE_SECURE_SETTINGS',
                'argv': ['dumpsys', 'package', 'com.android.shell']},
     'intent': None,
     'grant': {'method': 'adb-pm-grant',
               'argv': ['pm', 'grant', 'com.android.shell', 'android.permission.WRITE_SECURE_SETTINGS']},
     'steps': ['Tap Grant (runs one documented adb command with your consent)', 'State is rechecked immediately']},
]

CAPABILITY_MAP = {
    'bluetooth_scan': ['ble', 'relay', 'bluetooth'],
    'bluetooth_connect': ['bluetooth'],
    'fine_location': ['location'],
    'record_audio': ['voice', 'speak', 'microphone'],
    'post_notifications': ['notif'],
    'nearby_wifi': ['wifi'],
    'overlay': ['overlay', 'float'],
    'accessibility': ['accessibility', 'automation'],
    'device_admin': ['admin', 'lock', 'wipe'],
    'battery_opt_out': ['relay', 'background'],
    'exact_alarm': ['alarm', 'schedule'],
    'media_projection': ['screen', 'capture', 'project'],
    'write_secure_settings': ['secure', 'setting'],
}


def parse_appops(text, op):
    m = re.search(r'^%s:\s*(\w+)' % re.escape(op or ''), text or '', re.M)
    if not m:
        return None
    return {'allow': 'granted', 'deny': 'denied', 'ignore': 'denied',
            'foreground': 'granted', 'default': 'default'}.get(m[1].lower())


def parse_whitelist(text, pkg):
    if not (text or '').strip():
        return None
    return bool(re.search(r'(^|,)\s*%s\s*(,|$)' % re.escape(pkg), text, re.M))


def parse_perm_grant(text, perm):
    m = re.search(r'^%s:\s*granted=(true|false)\s*$' % re.escape(perm or ''), text or '', re.M)
    if not m:
        m = re.search(r'%s:\s*granted=(true|false)' % re.escape(perm or ''), text or '')
    if not m:
        return None
    return m[1] == 'true'


def parse_setting_contains(text, pkg):
    if not (text or '').strip():
        return None
    return pkg in text


def parse_device_admin(text, pkg):
    if not (text or '').strip():
        return None
    return pkg in text


def parse_resolve(text):
    if not (text or '').strip():
        return None
    return any('/' in line for line in text.splitlines())


def intent_command(entry, package):
    intent = entry.get('intent')
    if not intent:
        return None
    cmd = ['am', 'start', '-a', intent['action']]
    if intent.get('data'):
        cmd += ['-d', 'package:' + package]
    return cmd


def grant_command(entry, package):
    grant = entry.get('grant')
    if not grant:
        return None
    return [a.replace('{pkg}', package) for a in grant['argv']]


def _verify_entry(run, entry, package, sdk):
    v = entry['verify']
    if entry.get('min_sdk') and sdk is not None and sdk < entry['min_sdk']:
        return {'id': entry['id'], 'state': 'na', 'method': v['method'],
                'declared': entry['declared'],
                'detail': 'needs Android %d+' % entry['min_sdk']}
    if v['method'] == 'interactive':
        return {'id': entry['id'], 'state': 'session', 'method': 'interactive',
                'declared': entry['declared'],
                'detail': 'granted per session inside the app; no static state'}
    argv = [a.replace('{pkg}', package) for a in v['argv']]
    try:
        text = run(*argv)
    except Exception as err:
        return {'id': entry['id'], 'state': 'unknown', 'method': v['method'],
                'declared': entry['declared'], 'detail': 'verify failed: %s' % err}
    snippet = ((text or '').strip().splitlines() or [''])[0][:120]
    if v['method'] == 'appops':
        r = parse_appops(text, v['op'])
        state = r if r in ('granted', 'denied', 'default') else 'unknown'
    elif v['method'] == 'whitelist':
        b = parse_whitelist(text, package)
        state = 'granted' if b else 'denied' if b is False else 'unknown'
    elif v['method'] == 'setting':
        b = parse_setting_contains(text, package)
        state = 'granted' if b else 'denied' if b is False else 'unknown'
    elif v['method'] == 'admin':
        b = parse_device_admin(text, package)
        state = 'granted' if b else 'denied' if b is False else 'unknown'
    elif v['method'] == 'permgrant':
        b = parse_perm_grant(text, v['perm'])
        state = 'granted' if b else 'denied' if b is False else 'unknown'
    else:
        state = 'unknown'
    return {'id': entry['id'], 'state': state, 'method': v['method'],
            'declared': entry['declared'], 'detail': snippet or state}


def verify_all(run, package=COMPANION_PKG, sdk=None):
    return [_verify_entry(run, e, package, sdk) for e in CATALOG]


def verify_one(run, entry_id, package=COMPANION_PKG, sdk=None):
    entry = next((e for e in CATALOG if e['id'] == entry_id), None)
    if entry is None:
        raise PermissionsError('UNKNOWN_PERMISSION')
    return _verify_entry(run, entry, package, sdk)
