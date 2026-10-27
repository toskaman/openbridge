"""Deterministic, vendor-aware guidance for steps only the owner can perform. No model involved.
Each guide states: goal, why, what OpenBridge already tried, minimal owner action, and how waiting resolves."""

VENDORS = {
    'xiaomi': ('xiaomi', 'redmi', 'poco'), 'samsung': ('samsung',), 'bbk': ('oppo', 'realme', 'oneplus', 'vivo', 'iqoo'),
    'huawei': ('huawei', 'honor'), 'google': ('google',), 'sony': ('sony',), 'motorola': ('motorola', 'lenovo'),
}


def vendor_of(manufacturer):
    m = (manufacturer or '').lower()
    return next((v for v, names in VENDORS.items() if any(n in m for n in names)), 'generic')


def _dev_options(vendor, tv):
    if tv:
        return 'Settings > Device Preferences > About > press "Build" 7 times, then Settings > Device Preferences > Developer options'
    return {
        'xiaomi': 'Settings > About phone > tap "MIUI/HyperOS version" 7 times, then Settings > Additional settings > Developer options',
        'samsung': 'Settings > About phone > Software information > tap "Build number" 7 times, then Settings > Developer options',
        'bbk': 'Settings > About device > Version > tap "Build number" 7 times, then Settings > Additional settings > Developer options',
        'huawei': 'Settings > About phone > tap "Build number" 7 times, then Settings > System & updates > Developer options',
        'google': 'Settings > About phone > tap "Build number" 7 times, then Settings > System > Developer options',
    }.get(vendor, 'Settings > About phone > tap "Build number" 7 times, then open Developer options')


def guide(issue, manufacturer=None, sdk=None, television=False, tried=()):
    vendor = vendor_of(manufacturer)
    tv = bool(television)
    dev = _dev_options(vendor, tv)
    tried = list(tried)
    g = None
    if issue == 'usb_debugging_off':
        g = ('Turn on USB debugging', 'OpenBridge reads device facts only through Android\'s official debugging bridge.',
             [f'Open {dev}.', 'Turn on "USB debugging".', 'Reconnect the cable.'],
             'The device list refreshes by itself when the phone appears.')
    elif issue == 'usb_authorization_pending':
        g = ('Approve this computer on the device', 'Android requires the owner to trust each computer once.',
             ['Unlock the device.', 'Accept "Allow USB debugging?" (tick "Always allow" only on your own PC).',
              'No prompt? Unplug and reconnect, or revoke USB debugging authorizations in Developer options and retry.'],
             'Closes automatically when the device reports "authorized".')
    elif issue == 'companion_install_blocked':
        steps = {
            'xiaomi': [f'Open {dev}.', 'Turn on "Install via USB" (Xiaomi may ask you to sign in to a Mi account).',
                       'Also turn on "USB debugging (Security settings)" if offered.', 'When "Install OpenBridge Companion?" appears, tap Install.'],
            'bbk': [f'Open {dev}.', 'Turn off "Disable permission monitoring" / turn on "Install via USB" if present.', 'Tap Install on the prompt.'],
            'huawei': ['Tap "Install" on the confirmation; if blocked, Settings > Security > More settings > allow installation from external sources for USB.'],
        }.get(vendor, ['Look at the device: confirm the installation prompt if one appears.',
                       f'If nothing appears, check {dev} for an "Install via USB" or "Verify apps over USB" option.'])
        g = ('Allow installing the OpenBridge Companion', 'Your device blocks app installs over USB until you allow them.', steps,
             'OpenBridge retries the installation every 15 seconds for 10 minutes.')
    elif issue == 'companion_not_running':
        g = ('Open the OpenBridge Companion', 'The relay only listens while the app is open (no background scanning).',
             ['Open "OpenBridge Companion" on the device' + (' from the TV home screen apps row.' if tv else '.')],
             'Retry pairing once the app shows "Listening for OpenBridge".')
    elif issue == 'bluetooth_off':
        g = ('Turn Bluetooth on', 'Scanning needs the device radio; OpenBridge never turns it on silently.',
             ['Settings > Remotes & Accessories (TV) or the quick-settings panel (phone): turn Bluetooth on.' if tv else 'Swipe down the quick-settings panel and turn Bluetooth on.'],
             'The next scan request checks the radio again.')
    elif issue == 'bluetooth_service_disabled':
        g = ('Re-enable the system Bluetooth app', 'Android\'s own Bluetooth app is disabled on this device, so the radio cannot start (often after removing pre-installed apps).',
             ['Settings > Apps > See all apps > Show system apps > Bluetooth > Enable.' if not tv else 'Settings > Apps > See all apps > Show system apps > Bluetooth > Enable (use the remote).',
              'Then select "Set up everything" in the OpenBridge Companion.'],
             'OpenBridge never re-enables system apps on its own.')
    elif issue == 'ble_permission':
        perm = 'Nearby devices' if (sdk or 0) >= 31 else 'Location'
        g = ('Allow Bluetooth scanning in the Companion', f'Android protects scanning with the "{perm}" permission.',
             ['In the Companion app, select "Allow Bluetooth scanning".', f'Choose "Allow" for {perm}.'] +
             (['Android 11 or older: Location services must also be on during scans.'] if (sdk or 99) < 31 else []),
             'Status in the Companion updates immediately.')
    elif issue == 'owner_scan_disabled':
        g = ('Resume scans in the Companion', 'Scans were paused on the device by its owner.',
             ['In the Companion app, select "Resume scans".'], 'You can pause them again at any time.')
    elif issue == 'wifi_adb_pairing':
        g = ('Pair wireless debugging', 'Some devices (TVs) are only reachable over Wi-Fi debugging.',
             [f'Open {dev}.', 'Turn on "Wireless debugging" and select "Pair device with pairing code".', 'Keep that screen open; OpenBridge will ask for the code.'],
             'Only devices you pair yourself are used; OpenBridge never scans ports.')
    elif issue == 'tv_network_debugging':
        brand = (manufacturer or '').lower()
        about = ('Settings > System > About > select "Android TV OS build" 7 times' if 'google' in brand or 'chromecast' in brand
                 else 'Settings > Device Preferences > About > select "Build" 7 times with the remote OK button')
        toggle = ('In Developer options turn on "Network debugging".' if 'nvidia' in brand or 'shield' in brand
                  else 'In Developer options turn on "USB debugging" (on most Android TVs it also enables debugging over the network) and, if listed, "Network debugging" or "ADB over network".')
        g = ('Enable debugging on the TV', 'OpenBridge reads TV facts through Android\'s official debugging bridge over your home network.',
             [about + ' until "You are now a developer" appears.',
              'Go back: Developer options now appear under Device Preferences (or System).', toggle,
              'Google TV 12 or newer without that option: use "Wireless debugging" > "Pair device with pairing code".',
              'Then select "Connect over ADB Wi-Fi" again in OpenBridge.'],
             'Only this TV is contacted, on its local address and debugging port; nothing is scanned.')
    elif issue == 'tv_debug_prompt':
        g = ('Accept debugging on the TV screen', 'Android asks the owner to trust each computer once.',
             ['A dialog "Allow debugging?" is shown on the TV.', 'With the remote, tick "Always allow from this computer".', 'Select OK.'],
             'OpenBridge checks every few seconds and continues automatically.')
    elif issue == 'watch_wireless_debugging':
        about = {'samsung': 'Settings > About watch > Software information > tap "Software version" until "Developer mode turned on" appears',
                 'google': 'Settings > System > About > Versions > tap "Build number" 7 times'}.get(
                     vendor, 'Settings > System > About > tap "Build number" 7 times')
        g = ('Connect your smartwatch', 'Wear OS watches are reached over Wi-Fi with Android\'s official wireless debugging, paired once with a code.',
             ['Put the watch on the same Wi-Fi as this PC and keep its screen awake.',
              about + '.',
              'Open Settings > Developer options: turn on "ADB debugging", then "Wireless debugging".',
              'Tap "Pair new device": the watch shows an IP address:port and a 6-digit code.',
              'Type both in OpenBridge and select "Pair watch". Accept "Allow debugging?" on the watch if asked.'],
             'Pairing is remembered; next time OpenBridge only reconnects. Read-only by default.')
    elif issue == 'watch_pair_failed':
        g = ('Pairing did not complete', 'The code expires after a short time or was mistyped.',
             ['On the watch, tap "Pair new device" again to get a fresh code.', 'Type the new IP:port and code, then retry.'],
             'Nothing was changed on the watch.')
    elif issue == 'freebox_pending':
        g = ('Approve OpenBridge on your Freebox', 'The Freebox only issues app tokens after a press on its front panel.',
             ['Wake the Freebox Server display with an arrow key.', 'Select ✓ for "OpenBridge Device Fabric".'],
             'Read-only LAN inventory; Wi-Fi, DHCP, DNS and firewall stay blocked.')
    if g is None:
        raise ValueError('Unknown guidance issue')
    title, why, steps, waiting = g
    return {'issue': issue, 'vendor': vendor, 'title': title, 'why': why, 'tried': tried, 'steps': steps, 'waiting': waiting}


INSTALL_ERRORS = {'INSTALL_FAILED_USER_RESTRICTED': 'companion_install_blocked', 'INSTALL_FAILED_VERIFICATION_FAILURE': 'companion_install_blocked',
                  'INSTALL_FAILED_OLDER_SDK': None, 'INSTALL_FAILED_INSUFFICIENT_STORAGE': None, 'INSTALL_FAILED_UPDATE_INCOMPATIBLE': None}


def classify_install(output):
    for code, issue in INSTALL_ERRORS.items():
        if code in output:
            return code, issue
    return ('SUCCESS', None) if 'Success' in output else ('UNKNOWN_FAILURE', None)
