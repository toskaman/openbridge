"""Typed action catalog for owner-authorized Android devices (phone, Android TV, Wear OS watch) over ADB.

Every action is a named, schema-checked operation mapped to a fixed ADB argument list; clients never send shell
strings. The catalog is what OpenBridge (and the Meta planner / Capability Forge) can compose into new features:
`probe()` measures which actions a given device actually supports, `run()` executes one action and reads back
whatever the device reports, and macros (src/runtime/primitives.py: device_macro) chain up to 20 steps under one
consent that lists every step.

Reversibility is declared per action: settings with a readable value (media volume, screen brightness, screen
timeout) are EXACT (before value recorded, independent read-back, exact restore); key presses, taps, launches and
power changes are IRREVERSIBLE and say so.
"""
import re

KEYS = {  # name -> Android KEYCODE
    'power': 26, 'wakeup': 224, 'sleep': 223, 'home': 3, 'back': 4, 'menu': 82, 'search': 84, 'app_switch': 187,
    'up': 19, 'down': 20, 'left': 21, 'right': 22, 'ok': 23, 'enter': 66, 'delete': 67,
    'volume_up': 24, 'volume_down': 25, 'mute': 164, 'channel_up': 166, 'channel_down': 167, 'last_channel': 229,
    'play_pause': 85, 'stop': 86, 'next': 87, 'previous': 88, 'rewind': 89, 'fast_forward': 90,
    'tv_input': 178, 'settings': 176, 'guide': 172, 'info': 165, 'captions': 175, 'notifications': 83,
    **{f'digit_{i}': 7 + i for i in range(10)},
}
TV_ONLY = {'channel_up', 'channel_down', 'last_channel', 'tv_input', 'guide', 'captions'}
SETTINGS = {  # name -> (get args, set args template, value range)
    'media_volume': (('cmd', 'media_session', 'volume', '--stream', '3', '--get'), ('cmd', 'media_session', 'volume', '--stream', '3', '--set', '{v}'), (0, 100)),
    'screen_brightness': (('settings', 'get', 'system', 'screen_brightness'), ('settings', 'put', 'system', 'screen_brightness', '{v}'), (0, 255)),
    'screen_timeout_ms': (('settings', 'get', 'system', 'screen_off_timeout'), ('settings', 'put', 'system', 'screen_off_timeout', '{v}'), (10000, 1800000)),
}
ACTIONS = {
    'key': {'params': {'key': sorted(KEYS)}, 'reversibility': 'IRREVERSIBLE', 'what': 'press one remote/keyboard key'},
    'text': {'params': {'text': 'string<=100, letters digits space .,-_@'}, 'reversibility': 'IRREVERSIBLE', 'what': 'type text in the focused field'},
    'tap': {'params': {'x': '0..1', 'y': '0..1'}, 'reversibility': 'IRREVERSIBLE', 'what': 'touch/click at a screen fraction (mouse)'},
    'swipe': {'params': {'x1': '0..1', 'y1': '0..1', 'x2': '0..1', 'y2': '0..1', 'ms': '50..2000'}, 'reversibility': 'IRREVERSIBLE', 'what': 'drag (mouse move / scroll)'},
    'long_press': {'params': {'x': '0..1', 'y': '0..1'}, 'reversibility': 'IRREVERSIBLE', 'what': 'touch and hold'},
    'launch_app': {'params': {'package': 'installed launchable package'}, 'reversibility': 'IRREVERSIBLE', 'what': 'open an installed app'},
    'open_url': {'params': {'url': 'http(s) URL'}, 'reversibility': 'IRREVERSIBLE', 'what': 'open a web address'},
    'set': {'params': {'setting': sorted(SETTINGS), 'value': 'integer in range'}, 'reversibility': 'EXACT', 'what': 'change a setting with read-back; exact restore'},
    'get': {'params': {'setting': sorted(SETTINGS)}, 'reversibility': 'NONE', 'what': 'read a setting'},
    'list_apps': {'params': {}, 'reversibility': 'NONE', 'what': 'list launchable apps'},
    'screen_state': {'params': {}, 'reversibility': 'NONE', 'what': 'screen on/off/screensaver and focused app'},
    'audio_state': {'params': {}, 'reversibility': 'NONE', 'what': 'media stream muted flag, volume index and output devices'},
}
PKG = re.compile(r'[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+\Z')
TEXT = re.compile(r'[A-Za-z0-9 .,\-_@]{1,100}\Z')


class ActionError(ValueError):
    pass


def _num(v, lo, hi, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
        raise ActionError(f'{name} out of range')
    return v


def _int_out(s):
    m = re.search(r'-?\d+', s or '')
    return int(m[0]) if m else None


class AndroidActions:
    """shell(*args) -> stdout (raises ValueError/OSError). Used through the Executor only."""
    def __init__(self, shell, category):
        self.shell, self.category = shell, category
        self._size = None
        self.before = {}

    def size(self):
        if self._size is None:
            m = re.search(r'(\d+)x(\d+)', self.shell('wm', 'size') or '')
            if not m:
                raise ActionError('screen size unreadable')
            self._size = (int(m[1]), int(m[2]))
        return self._size

    def _xy(self, x, y):
        w, h = self.size()
        return str(int(_num(x, 0, 1, 'x') * (w - 1))), str(int(_num(y, 0, 1, 'y') * (h - 1)))

    def get(self, setting):
        if setting not in SETTINGS:
            raise ActionError('unknown setting')
        return _int_out(self.shell(*SETTINGS[setting][0]).split('volume is')[-1] if setting == 'media_volume' else self.shell(*SETTINGS[setting][0]))

    def _apply(self, s, v):
        """Write a setting; for media volume fall back to volume keys (some builds ignore media_session --set)."""
        self.shell(*[a.format(v=v) for a in SETTINGS[s][1]])
        now = self.get(s)
        if s != 'media_volume' or now == v or now is None:
            return now
        for _ in range(40):
            if now == v:
                break
            key = 'volume_up' if now < v else 'volume_down'
            try:
                self.shell('input', 'keyevent', str(KEYS[key]))
            except (ValueError, OSError):
                break
            nxt = self.get(s)
            if nxt is None or nxt == now or (key == 'volume_up' and nxt > v) or (key == 'volume_down' and nxt < v):
                now = nxt if nxt is not None else now
                break                         # cannot move, or the step size skips the exact value
            now = nxt
        return now

    def apps(self):
        cat = 'android.intent.category.LEANBACK_LAUNCHER' if self.category == 'tv' else 'android.intent.category.LAUNCHER'
        out = self.shell('cmd', 'package', 'query-activities', '--brief', '-a', 'android.intent.action.MAIN', '-c', cat) or ''
        self._components = {}
        for l in out.splitlines():
            l = l.strip()
            if '/' in l and PKG.match(l.split('/')[0]) and re.fullmatch(r'[A-Za-z0-9_.$/]+', l):
                self._components.setdefault(l.split('/')[0], l)
        return sorted(self._components)

    def screen_state(self):
        p = re.search(r'mWakefulness=(\w+)', self.shell('dumpsys', 'power') or '')
        w = re.search(r'mCurrentFocus=Window\{[^ ]+ [^ ]+ ([A-Za-z0-9_.]+)', self.shell('dumpsys', 'window') or '')
        return {'power': p[1].lower() if p else None, 'focused_app': w[1] if w else None}

    def audio_state(self):
        """Read-only media-stream state from `dumpsys audio`. Unknown fields stay None (never guessed)."""
        out = (self.shell('dumpsys', 'audio') or '').replace('\r\n', '\n')
        m = re.search(r'- STREAM_MUSIC:\n(.*?)(?:\n\s*- STREAM_|\Z)', out, re.S)
        block = m[1] if m else ''
        def field(name, conv):
            f = re.search(r'^\s*' + name + r':\s*(\S+)', block, re.M)
            return conv(f[1]) if f else None
        muted = field('Muted', lambda v: {'true': True, 'false': False}.get(v.lower()))
        vol = field('streamVolume', lambda v: int(v) if v.isdigit() else None)
        mx = field('Max', lambda v: int(v) if v.isdigit() else None)
        dev = re.search(r'^\s*Devices:\s*(.+)$', block, re.M)
        return {'stream': 'music', 'muted': muted, 'volume_index': vol, 'max_index': mx,
                'devices': re.findall(r'([a-z][a-z_0-9]*)(?:\(\d+\))?', dev[1]) if dev else [],
                'readable': m is not None and muted is not None}

    def run(self, action, params):
        p = params or {}
        if action == 'key':
            k = p.get('key')
            if k not in KEYS:
                raise ActionError('unknown key')
            self.shell('input', 'keyevent', str(KEYS[k]))
            return {'sent': k}
        if action == 'text':
            t = p.get('text')
            if not isinstance(t, str) or not TEXT.match(t):
                raise ActionError('text: 1..100 of letters, digits, space . , - _ @')
            self.shell('input', 'text', t.replace(' ', '%s'))
            return {'typed_chars': len(t)}
        if action in ('tap', 'long_press'):
            x, y = self._xy(p.get('x'), p.get('y'))
            if action == 'tap':
                self.shell('input', 'tap', x, y)
            else:
                self.shell('input', 'swipe', x, y, x, y, '800')
            return {'at_px': [int(x), int(y)]}
        if action == 'swipe':
            x1, y1 = self._xy(p.get('x1'), p.get('y1')); x2, y2 = self._xy(p.get('x2'), p.get('y2'))
            ms = int(_num(p.get('ms', 300), 50, 2000, 'ms'))
            self.shell('input', 'swipe', x1, y1, x2, y2, str(ms))
            return {'from_px': [int(x1), int(y1)], 'to_px': [int(x2), int(y2)]}
        if action == 'launch_app':
            pkg = p.get('package')
            if not isinstance(pkg, str) or not PKG.match(pkg) or pkg not in self.apps():
                raise ActionError('package not installed or not launchable')
            self.shell('am', 'start', '-n', self._components[pkg])          # fast and exact (monkey is slow on watches)
            return {'launched': pkg, 'screen': self.screen_state()}
        if action == 'open_url':
            u = p.get('url')
            if not isinstance(u, str) or not re.fullmatch(r'https?://[^\s"\'`$;|&<>]{1,300}', u):
                raise ActionError('http(s) URL only')
            self.shell('am', 'start', '-a', 'android.intent.action.VIEW', '-d', u)
            return {'opened': True}
        if action == 'get':
            return {'setting': p.get('setting'), 'value': self.get(p.get('setting'))}
        if action == 'set':
            s = p.get('setting')
            if s not in SETTINGS:
                raise ActionError('unknown setting')
            lo, hi = SETTINGS[s][2]
            if s == 'media_volume':
                m = re.search(r'range \[(\d+)\.\.(\d+)\]', self.shell(*SETTINGS[s][0]) or '')
                if m:
                    lo, hi = int(m[1]), int(m[2])
            v = int(_num(p.get('value'), lo, hi, 'value'))
            before = self.get(s)
            if before is None:
                raise ActionError('setting not readable on this device')
            self.before[s] = before
            after = self._apply(s, v)
            return {'setting': s, 'before': before, 'after': after, 'verified': after == v}
        if action == 'restore':
            s = p.get('setting')
            if s not in self.before:
                raise ActionError('nothing to restore')
            b = self.before[s]
            now = self._apply(s, b)
            if now == b:
                self.before.pop(s)
            return {'setting': s, 'restored': now, 'exact': now == b}
        if action == 'list_apps':
            return {'apps': self.apps()}
        if action == 'screen_state':
            return self.screen_state()
        if action == 'audio_state':
            return self.audio_state()
        raise ActionError('unknown action')

    def probe(self):
        """Which catalog entries this device supports, measured with read-only calls."""
        out = {'category': self.category, 'actions': {}}
        try:
            w, h = self.size(); out['screen_px'] = [w, h]; pointer = True
        except (ActionError, ValueError, OSError):
            pointer = False
        out['ranges'] = {}
        for s in SETTINGS:
            try:
                out['actions'][f'set:{s}'] = self.get(s) is not None
                if s == 'media_volume' and out['actions'][f'set:{s}']:   # measured, read-only: enables EXACT routing (B2)
                    m = re.search(r'range \[(\d+)\.\.(\d+)\]', self.shell(*SETTINGS[s][0]) or '')
                    if m:
                        out['ranges'][s] = [int(m[1]), int(m[2])]
            except (ActionError, ValueError, OSError):
                out['actions'][f'set:{s}'] = False
        try:
            apps = self.apps(); out['launchable_apps'] = len(apps)
        except (ValueError, OSError):
            apps = []
        keys = [k for k in KEYS if self.category == 'tv' or k not in TV_ONLY]
        out['actions'].update({'key': keys, 'text': True, 'tap': pointer, 'swipe': pointer, 'long_press': pointer,
                               'launch_app': bool(apps), 'open_url': True, 'list_apps': bool(apps), 'screen_state': True})
        try:
            out['actions']['audio_state'] = self.audio_state()['readable']
        except (ValueError, OSError):
            out['actions']['audio_state'] = False
        return out
