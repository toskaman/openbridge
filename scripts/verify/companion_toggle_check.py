"""On-device regression check for the Companion 'Background relay' toggle.

Bug: the button never showed its state, and rapid taps toggled the service
more than once (no debounce, no visual feedback).

Checks, on a real device over adb (no emulator needed):
  T1  the button exposes its state (content-desc 'Background relay, on|off')
      matching the actual RelayService state from dumpsys.
  T2  one tap flips the service state exactly once.
  T3  two taps 200 ms apart flip it exactly once (debounce).

Restores the initial service state before exiting.
Exit 0 when all checks pass, 1 otherwise.

Usage: python scripts/verify/companion_toggle_check.py [--serial SERIAL]
"""
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PKG = 'fr.openbridge.companion'
ACTIVITY = PKG + '/.MainActivity'
BUTTON_TEXT = 'Background relay'
SYS_HEADER = 'SYSTEM & PERMISSIONS'


def adb(serial, *args, timeout=60):
    cmd = ['adb'] + (['-s', serial] if serial else []) + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding='utf-8', errors='replace')
    return r.stdout + r.stderr


def service_running(serial):
    return 'RelayService' in adb(serial, 'shell', 'dumpsys', 'activity', 'services')


def dump_ui(serial, path):
    adb(serial, 'shell', 'uiautomator', 'dump', '/sdcard/ob-toggle.xml')
    adb(serial, 'pull', '/sdcard/ob-toggle.xml', path)
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def find_nodes(xml_text, text):
    root = ET.fromstring(xml_text)
    out = []
    for node in root.iter('node'):
        if (node.get('text') or '') == text:
            m = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds') or '')
            if m:
                x0, y0, x1, y1 = map(int, m.groups())
                if x1 > x0 and y1 > y0:
                    out.append({'text': text, 'desc': node.get('content-desc') or '',
                                'cx': (x0 + x1) // 2, 'cy': (y0 + y1) // 2,
                                'y0': y0, 'y1': y1})
    return out


def tap(serial, cx, cy):
    adb(serial, 'shell', 'input', 'tap', str(cx), str(cy))


def safe_swipe_up(serial):
    adb(serial, 'shell', 'input', 'swipe', '1020', '1800', '1020', '500', '400')


def screen_height(serial):
    m = re.search(r'(\d+)x(\d+)', adb(serial, 'shell', 'wm', 'size'))
    return int(m.group(2)) if m else 2400


def wait_state(serial, want_running, timeout_s=8):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if service_running(serial) == want_running:
            return True
        time.sleep(0.2)
    return False


def main():
    serial = None
    args = sys.argv[1:]
    if '--serial' in args:
        serial = args[args.index('--serial') + 1]
    failures = []

    def check(name, cond, detail=''):
        print(('PASS ' if cond else 'FAIL ') + name + (' — ' + detail if detail and not cond else ''))
        if not cond:
            failures.append(name)

    adb(serial, 'shell', 'am', 'start', '-n', ACTIVITY)
    time.sleep(3)
    height = screen_height(serial)
    # Open the SYSTEM section, then scroll until the toggle is on screen.
    btn = []
    for _ in range(8):
        ui = dump_ui(serial, 'C:\\tmp\\ob-toggle.xml')
        btn = [n for n in find_nodes(ui, BUTTON_TEXT)
               if 0 < n['cy'] < height and n['y1'] - n['y0'] > 40]
        if btn:
            break
        show = [n for n in find_nodes(ui, 'Show') if 0 < n['cy'] < height]
        if show:
            tap(serial, show[0]['cx'], show[0]['cy'])
            time.sleep(2)
            continue
        safe_swipe_up(serial)
        time.sleep(1.5)
    check('toggle visible', bool(btn), 'button never appeared on screen')
    if not btn:
        return 1

    def tap_button():
        """Re-locate (the feed above shifts geometry) then tap. Returns False if lost."""
        ui = dump_ui(serial, 'C:\\tmp\\ob-toggle.xml')
        cand = [n for n in find_nodes(ui, BUTTON_TEXT)
                if 0 < n['cy'] < height and n['y1'] - n['y0'] > 40]
        if not cand:
            return False
        tap(serial, cand[0]['cx'], cand[0]['cy'])
        return True

    initial = service_running(serial)
    desc = btn[0]['desc']
    m = re.fullmatch(r'Background relay, (on|off)', desc)
    check('T1 state exposed', bool(m), 'content-desc=%r' % desc)
    if m:
        check('T1 state matches service', (m.group(1) == 'on') == initial,
              'desc=%r running=%s' % (desc, initial))

    # Fill the 6-row activity feed so geometry stays put for the fast double tap.
    state = initial
    for _ in range(6):
        if not tap_button():
            break
        state = not state
        wait_state(serial, state)
        time.sleep(1.2)
    check('feed primed, back to initial', service_running(serial) == initial,
          'priming toggles failed')

    tap_button()
    flipped = wait_state(serial, not initial)
    check('T2 one tap flips once', flipped, 'service did not flip')
    time.sleep(1.2)
    check('T2 state stable', service_running(serial) == (not initial) if flipped else False,
          'service flipped back on its own')

    # Restore, then prove the debounce: two fast taps act as one.
    tap_button()
    restored = wait_state(serial, initial)
    check('restore initial state', restored, 'could not restore')
    if restored:
        ui = dump_ui(serial, 'C:\\tmp\\ob-toggle.xml')
        cand = [n for n in find_nodes(ui, BUTTON_TEXT)
                if 0 < n['cy'] < height and n['y1'] - n['y0'] > 40]
        if cand:
            tap(serial, cand[0]['cx'], cand[0]['cy'])
            time.sleep(0.2)
            tap(serial, cand[0]['cx'], cand[0]['cy'])
            one = wait_state(serial, not initial)
            time.sleep(1.5)
            still_one = service_running(serial) == (not initial)
            check('T3 double tap flips once', one and still_one,
                  'debounce missing (two transitions)')
        else:
            check('T3 double tap flips once', False, 'button lost')
        if service_running(serial) != initial:
            tap_button()
            wait_state(serial, initial)

    print('RESULT: %s (%d failure(s))' % ('OK' if not failures else 'KO', len(failures)))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
