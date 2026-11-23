"""Glasses menus: screens, navigation and the actions they ask OpenBridge to run.

Input is reduced to five events so that every source can drive the same menus:
  next / prev / ok / back / home
- glasses gesture sensor: one wave = next, two quick waves = ok, three = back (see GestureDecoder);
- Companion phone or watch buttons, the HUD Studio keyboard, and voice send the events directly;
- the TV remote screen also accepts up / down / left / right as direct D-pad keys.

A screen never touches a device. Selecting an item returns an Action that the hub runs through the OpenBridge gate
(typed primitive, consent, read-back, receipt); the outcome comes back as a banner.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.glasses import icons as I
from src.glasses.panel import FONTS, H, W, Panel, fit, text_width, wrap

EVENTS = ('next', 'prev', 'ok', 'back', 'home', 'up', 'down', 'left', 'right')

TV_APPS = [  # label, Android TV package
    ('YouTube', 'com.google.android.youtube.tv'), ('Netflix', 'com.netflix.ninja'),
    ('Prime Video', 'com.amazon.amazonvideo.livingroom'), ('Disney+', 'com.disney.disneyplus'),
    ('Spotify', 'com.spotify.tv.android'), ('Plex', 'com.plexapp.android'), ('Twitch', 'tv.twitch.android.app'),
    ('myCANAL', 'com.canal.android.canal'), ('VLC', 'org.videolan.vlc'), ('Kodi', 'org.xbmc.kodi'),
]


@dataclass
class Action:
    """What a menu item asks for. kind: device (a typed primitive on a device class) | voice | read."""
    kind: str
    label: str
    device: str = ''            # 'tv' | 'vacuum'
    primitive: str = ''
    params: dict = field(default_factory=dict)
    item_id: str = ''


def tv_key(key, label):
    return Action('device', label, 'tv', 'device_action', {'action': 'key', 'args': {'key': key}})


def vac(command, label):
    return Action('device', label, 'vacuum', 'tuya_command', {'command': command})


@dataclass
class Context:
    """What the screens can show. Filled by the hub; screens only read it."""
    inbox: object = None
    clock: callable = time.time
    phone_battery: int | None = None
    glasses_battery: int | None = None
    linked: bool = False
    tv_name: str = 'TV'
    tv_app: str = ''
    tv_volume: int | None = None
    vacuum_state: str = ''
    vacuum_battery: int | None = None
    voice: dict = field(default_factory=dict)     # {state: idle|listening|thinking|done|failed, text, result}
    banner: dict | None = None                     # {ok: bool, text, until}
    toast: dict | None = None                      # notification item shown over the screen, with 'until'


# ---------------------------------------------------------------- chrome

def status_bar(p: Panel, ctx: Context):
    t = time.localtime(ctx.clock())
    p.text(22, 14, '%02d:%02d' % (t.tm_hour, t.tm_min), 1, 'secondary')
    x = 284
    if ctx.glasses_battery is not None:
        x -= p.text_right(x, 16, '%d%%' % ctx.glasses_battery, 0, 'muted') + 10
    unread = ctx.inbox.unread() if ctx.inbox else 0
    if unread:
        w = text_width(str(unread), 0)
        p.round_rect(x - w - 26, 13, x, 31, 9, 'accent')
        I.bell(p, x - w - 15, 21, 6, 'accent')
        p.text(x - w - 5, 16, str(unread), 0, 'accent')
        x -= w + 34
    p.circle(x - 4, 22, 3, 'ok' if ctx.linked else 'faint', True)


def hint(p: Panel, text):
    p.text_center(W / 2, 234, text, 0, 'muted', width=264)


def banner(p: Panel, ctx: Context):
    b = ctx.banner
    if not b or b.get('until', 0) < ctx.clock():
        return
    tone = 'ok' if b.get('ok') else 'alert'
    p.erase(20, 190, 284, 252)
    p.round_rect(26, 196, 278, 230, 14, tone)
    (I.check if b.get('ok') else I.cross)(p, 46, 213, 8, tone)
    p.text(62, 204, fit(b.get('text', ''), 1, 206), 1, 'primary')


def toast(p: Panel, ctx: Context):
    n = ctx.toast
    if not n or n.get('until', 0) < ctx.clock():
        return
    p.erase(8, 36, 296, 124)
    p.round_rect(14, 40, 290, 112, 14, 'accent')
    I.badge(p, 40, 62, 15, n.get('letter', '?'), 'accent')
    p.text(64, 48, fit(n.get('sender', ''), 1, 160), 1, 'primary')
    p.text_right(278, 51, n.get('app', ''), 0, 'accent_dim')
    p.text(64, 76, fit(n.get('text', ''), 0, 210), 0, 'secondary')


def ago(ts, now):
    s = max(0, int(now - ts))
    return 'now' if s < 60 else '%d min' % (s // 60) if s < 3600 else '%d h' % (s // 3600) if s < 86400 else '%d d' % (s // 86400)


# ---------------------------------------------------------------- screens

class Screen:
    title = ''

    def __init__(self):
        self.focus = 0

    def items(self, ctx):
        return []

    def on(self, ev, ctx):
        """Returns ('push', Screen) | ('pop',) | ('home',) | ('act', Action) | None."""
        n = len(self.items(ctx))
        if ev in ('next', 'down', 'right') and n:
            self.focus = (self.focus + 1) % n
        elif ev in ('prev', 'up', 'left') and n:
            self.focus = (self.focus - 1) % n
        elif ev == 'back':
            return ('pop',)
        elif ev == 'home':
            return ('home',)
        elif ev == 'ok' and n:
            return self.select(self.items(ctx)[self.focus], ctx)
        return None

    def select(self, item, ctx):
        return None

    def render(self, p: Panel, ctx: Context):
        raise NotImplementedError


class ListScreen(Screen):
    """Header + up to three rows, the focused one in an accent card."""
    rows_per_page = 3
    hint_text = 'wave next · 2× open · 3× back'

    def row(self, p, item, x, y, focused, ctx):
        p.text(x, y + 16, fit(item[0], 2, 230), 2, 'primary' if focused else 'secondary')

    def header_right(self, ctx):
        n = len(self.items(ctx))
        return '%d / %d' % (self.focus + 1, n) if n else ''

    def empty_text(self):
        return 'Nothing here'

    def render(self, p, ctx):
        status_bar(p, ctx)
        p.text(22, 42, fit(self.title, 2, 190), 2, 'primary')
        p.text_right(284, 50, self.header_right(ctx), 0, 'muted')
        items = self.items(ctx)
        if not items:
            p.text_center(W / 2, 120, self.empty_text(), 1, 'muted')
        page = self.focus // self.rows_per_page
        for i, item in enumerate(items[page * self.rows_per_page:(page + 1) * self.rows_per_page]):
            idx = page * self.rows_per_page + i
            y = 78 + i * 50
            if idx == self.focus:
                p.round_rect(14, y, 290, y + 44, 12, 'accent')
            self.row(p, item, 30, y, idx == self.focus, ctx)
        hint(p, self.hint_text)


class Home(Screen):
    """Carousel: one big ring in the middle, neighbours on the sides, page dots."""

    def items(self, ctx):
        unread = ctx.inbox.unread() if ctx.inbox else 0
        vac_sub = ' · '.join(x for x in (ctx.vacuum_state.capitalize(),
                                         '%d%%' % ctx.vacuum_battery if ctx.vacuum_battery is not None else '') if x)
        return [('Messages', 'chat', '%d unread' % unread if unread else 'All caught up', Inbox),
                ('TV', 'tv', ctx.tv_app or ctx.tv_name, TVHub),
                ('Vacuum', 'vacuum', vac_sub or 'Robot vacuum', VacuumScreen),
                ('Voice', 'mic', 'Speak to OpenBridge', VoiceScreen),
                ('Settings', 'gear', 'Glasses and privacy', SettingsScreen)]

    def on(self, ev, ctx):
        if ev == 'back':
            return None
        return super().on(ev, ctx)

    def select(self, item, ctx):
        return ('push', item[3]())

    def render(self, p, ctx):
        status_bar(p, ctx)
        items = self.items(ctx)
        n = len(items)
        cur = items[self.focus]
        cx, cy = W / 2, 106
        p.circle(cx, cy, 44, 'accent')
        p.circle(cx, cy, 47, 'accent_dim')
        I.draw(p, cur[1], cx, cy, 22, 'primary')
        for side, k in ((-1, (self.focus - 1) % n), (1, (self.focus + 1) % n)):
            sx = cx + side * 104
            p.circle(sx, cy, 22, 'faint')
            I.draw(p, items[k][1], sx, cy, 11, 'muted')
        p.text_center(cx, 160, cur[0], 3, 'primary')
        p.text_center(cx, 200, fit(cur[2], 1, 250), 1, 'secondary')
        x0 = cx - (n - 1) * 7
        for i in range(n):
            p.circle(x0 + i * 14, 232, 3 if i == self.focus else 2, 'accent' if i == self.focus else 'muted', True)


class Inbox(ListScreen):
    title = 'Messages'
    hint_text = 'wave next · 2× read · 3× back'

    def items(self, ctx):
        return ctx.inbox.list() if ctx.inbox else []

    def empty_text(self):
        return 'No new messages'

    def row(self, p, n, x, y, focused, ctx):
        I.badge(p, x + 10, y + 22, 13, n['letter'], 'accent' if focused else 'muted', 1)
        p.text(x + 34, y + 6, fit(n['sender'], 1, 170), 1, 'primary' if focused else 'secondary')
        p.text_right(278, y + 9, ago(n['time'], ctx.clock()), 0, 'muted')
        p.text(x + 34, y + 27, fit(n['text'], 0, 220), 0, 'secondary' if focused else 'muted')
        if not n.get('read'):
            p.circle(x - 6, y + 22, 3, 'accent', True)

    def select(self, item, ctx):
        return ('push', MessageView(item))


class MessageView(Screen):
    def __init__(self, item):
        super().__init__()
        self.item, self.marked = item, False

    def on(self, ev, ctx):
        if ev in ('ok', 'back'):
            return ('pop',)
        return super().on(ev, ctx)

    def render(self, p, ctx):
        n = self.item
        if not self.marked and ctx.inbox:
            ctx.inbox.mark_read(n['id'])
            self.marked = True
        status_bar(p, ctx)
        I.badge(p, 36, 56, 14, n['letter'], 'accent')
        p.text(58, 50, n['app'], 0, 'accent')
        p.text_right(284, 50, ago(n['time'], ctx.clock()), 0, 'muted')
        p.text(22, 76, fit(n['sender'], 2, 262), 2, 'primary')
        for i, line in enumerate(wrap(n['text'], 1, 262, 5)):
            p.text(22, 112 + i * 23, line, 1, 'secondary')
        hint(p, '2× or 3× wave: back')


class TVHub(Screen):
    """3 x 2 tiles."""
    TILES = [('Volume', 'volume'), ('Apps', 'apps'), ('Remote', 'dpad'),
             ('Play / Pause', 'play_pause'), ('Home', 'home'), ('Power', 'power')]

    def items(self, ctx):
        return self.TILES

    def select(self, item, ctx):
        name = item[0]
        if name == 'Volume':
            return ('push', VolumeScreen())
        if name == 'Apps':
            return ('push', AppsScreen())
        if name == 'Remote':
            return ('push', RemoteScreen())
        if name == 'Play / Pause':
            return ('act', tv_key('play_pause', 'Play / Pause'))
        if name == 'Home':
            return ('act', tv_key('home', 'TV home'))
        return ('push', PowerScreen())

    def render(self, p, ctx):
        status_bar(p, ctx)
        p.text(22, 42, ctx.tv_name, 2, 'primary')
        p.text_right(284, 50, fit(ctx.tv_app, 0, 120), 0, 'muted')
        for i, (label, icon) in enumerate(self.TILES):
            col, row = i % 3, i // 3
            x0, y0 = 16 + col * 92, 78 + row * 76
            f = i == self.focus
            p.round_rect(x0, y0, x0 + 84, y0 + 68, 12, 'accent' if f else 'faint')
            I.draw(p, icon, x0 + 42, y0 + 26, 13, 'primary' if f else 'muted')
            p.text_center(x0 + 42, y0 + 46, fit(label, 0, 78), 0, 'primary' if f else 'muted')
        hint(p, 'wave next · 2× select · 3× back')


class VolumeScreen(Screen):
    """Big number on a 270° gauge; − and + buttons. Each press is one verified volume step."""

    def items(self, ctx):
        return ['down', 'up']

    def select(self, item, ctx):
        return ('act', Action('device', 'Volume ' + ('up' if item == 'up' else 'down'), 'tv', 'device_action',
                              {'action': 'key', 'args': {'key': 'volume_' + item}}))

    def on(self, ev, ctx):
        if ev in ('up', 'down'):           # phone / watch volume keys: act directly
            return self.select(ev, ctx)
        return super().on(ev, ctx)

    def render(self, p, ctx):
        status_bar(p, ctx)
        cx, cy, r = W / 2, 118, 62
        p.arc(cx, cy, r, 135, 405, 'faint')
        v = ctx.tv_volume
        if v is not None:
            p.arc(cx, cy, r, 135, 135 + int(270 * max(0, min(100, v)) / 100), 'accent')
            p.arc(cx, cy, r - 3, 135, 135 + int(270 * max(0, min(100, v)) / 100), 'accent')
        if v is None:
            p.text_center(cx, cy - 16, '- -', 3, 'muted')
        else:
            p.text_center(cx, cy - 28, str(v), 5, 'primary')
        p.text_center(cx, cy + 34, 'VOLUME', 0, 'muted')
        for i, (bx, ic) in enumerate(((54, 'minus'), (250, 'plus'))):
            f = i == self.focus
            p.circle(bx, cy + 10, 24, 'accent' if f else 'faint')
            I.draw(p, ic, bx, cy + 10, 14, 'primary' if f else 'muted')
        banner(p, ctx)
        hint(p, 'wave switch · 2× press · 3× back')


class AppsScreen(ListScreen):
    title = 'Apps'

    def items(self, ctx):
        return TV_APPS

    def row(self, p, item, x, y, focused, ctx):
        I.apps(p, x + 10, y + 22, 9, 'accent' if focused else 'muted')
        p.text(x + 34, y + 10, item[0], 2, 'primary' if focused else 'secondary')
        if ctx.tv_app and ctx.tv_app.lower() == item[0].lower():
            p.text_right(278, y + 16, 'on screen', 0, 'ok')

    def select(self, item, ctx):
        return ('act', Action('device', 'Open ' + item[0], 'tv', 'device_action',
                              {'action': 'launch_app', 'args': {'package': item[1]}}))


class RemoteScreen(Screen):
    """D-pad: wave cycles the keys, two waves press. Phone / watch arrows press the key directly."""
    KEYS = [('up', 0, -1), ('right', 1, 0), ('down', 0, 1), ('left', -1, 0), ('ok', 0, 0), ('back', None, None),
            ('home', None, None)]

    def items(self, ctx):
        return self.KEYS

    def on(self, ev, ctx):
        if ev in ('up', 'down', 'left', 'right'):
            self.focus = [k[0] for k in self.KEYS].index(ev)
            return ('act', tv_key(ev, ev.capitalize()))
        if ev == 'back' and getattr(self, '_armed_back', False) is False:
            return ('pop',)
        return super().on(ev, ctx)

    def select(self, item, ctx):
        return ('act', tv_key(item[0], 'OK' if item[0] == 'ok' else item[0].capitalize()))

    def render(self, p, ctx):
        status_bar(p, ctx)
        p.text(22, 42, 'Remote', 2, 'primary')
        p.text_right(284, 50, fit(ctx.tv_app, 0, 130), 0, 'muted')
        cx, cy, d = 124, 136, 52
        for i, (name, dx, dy) in enumerate(self.KEYS[:5]):
            x, y = cx + dx * d, cy + dy * d
            f = i == self.focus
            p.circle(x, y, 22 if name != 'ok' else 25, 'accent' if f else 'faint')
            if name == 'ok':
                p.text_center(x, y - 9, 'OK', 1, 'primary' if f else 'muted')
            else:
                ang = {'up': -90, 'right': 0, 'down': 90, 'left': 180}[name]
                import math
                ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                tone = 'primary' if f else 'muted'
                tx, ty = x + ux * 8, y + uy * 8
                p.line(tx, ty, x - ux * 4 - uy * 8, y - uy * 4 + ux * 8, tone)
                p.line(tx, ty, x - ux * 4 + uy * 8, y - uy * 4 - ux * 8, tone)
        for j, (name, label, icon) in enumerate((('back', 'Back', 'back'), ('home', 'Home', 'home'))):
            i = 5 + j
            y = 96 + j * 74
            f = i == self.focus
            p.round_rect(214, y, 286, y + 56, 12, 'accent' if f else 'faint')
            I.draw(p, icon, 250, y + 20, 9, 'primary' if f else 'muted')
            p.text_center(250, y + 34, label, 0, 'primary' if f else 'muted')
        banner(p, ctx)
        hint(p, 'wave next key · 2× press · 3× back')


class PowerScreen(ListScreen):
    title = 'Power'

    def items(self, ctx):
        return [('Sleep', 'tv_sleep'), ('Wake up', 'tv_wake')]

    def row(self, p, item, x, y, focused, ctx):
        I.power(p, x + 10, y + 22, 9, 'accent' if focused else 'muted')
        p.text(x + 34, y + 10, item[0], 2, 'primary' if focused else 'secondary')

    def select(self, item, ctx):
        return ('act', Action('device', 'TV ' + item[0].lower(), 'tv', item[1], {}))


class VacuumScreen(ListScreen):
    title = 'Vacuum'

    def items(self, ctx):
        return [('Start cleaning', 'start', 'play'), ('Pause', 'pause', 'pause'), ('Back to dock', 'dock', 'home'),
                ('Find it (beep)', 'seek', 'search')]

    def header_right(self, ctx):
        bits = [ctx.vacuum_state.capitalize()] if ctx.vacuum_state else []
        if ctx.vacuum_battery is not None:
            bits.append('%d%%' % ctx.vacuum_battery)
        return ' · '.join(bits)

    def row(self, p, item, x, y, focused, ctx):
        I.draw(p, item[2], x + 10, y + 22, 9, 'accent' if focused else 'muted')
        p.text(x + 34, y + 10, item[0], 2, 'primary' if focused else 'secondary')

    def select(self, item, ctx):
        return ('act', vac(item[1], item[0]))

    def render(self, p, ctx):
        super().render(p, ctx)
        banner(p, ctx)


class VoiceScreen(Screen):
    """Listening rings while the phone records; then what was heard, then the outcome."""

    def items(self, ctx):
        return ['talk']

    def select(self, item, ctx):
        return ('act', Action('voice', 'Listen'))

    def render(self, p, ctx):
        status_bar(p, ctx)
        v = ctx.voice or {}
        st = v.get('state', 'idle')
        cx, cy = W / 2, 92
        tone = {'listening': 'accent', 'thinking': 'warn', 'done': 'ok', 'failed': 'alert'}.get(st, 'muted')
        I.mic(p, cx, cy, 20, 'primary' if st != 'idle' else 'secondary')
        p.circle(cx, cy, 36, tone)
        if st == 'listening':
            phase = int(ctx.clock() * 3) % 3
            for k in range(phase + 1):
                p.circle(cx, cy, 44 + k * 9, 'accent_dim')
        label = {'idle': 'Hold the mic on your phone', 'listening': 'Listening…', 'thinking': 'Understanding…',
                 'done': 'Done', 'failed': 'Not done'}[st if st in ('idle', 'listening', 'thinking', 'done', 'failed') else 'idle']
        p.text_center(cx, 140, label, 2 if st != 'idle' else 1, 'primary' if st != 'idle' else 'secondary', width=268)
        heard = v.get('text') or ''
        for i, line in enumerate(wrap('“%s”' % heard if heard else '', 1, 262, 2)):
            p.text_center(cx, 174 + i * 22, line, 1, 'secondary')
        if v.get('result'):
            p.text_center(cx, 220, fit(v['result'], 0, 262), 0, 'ok' if st == 'done' else 'alert')
        else:
            hint(p, 'try: “turn the TV down”')


class SettingsScreen(ListScreen):
    title = 'Settings'

    def items(self, ctx):
        mode = getattr(ctx.inbox, 'privacy', 'full') if ctx.inbox else 'full'
        return [('Message text: ' + {'full': 'shown', 'sender': 'hidden', 'off': 'off'}.get(mode, mode), 'privacy'),
                ('Clear messages', 'clear'), ('Calibrate display', 'calibrate')]

    def row(self, p, item, x, y, focused, ctx):
        p.text(x, y + 12, fit(item[0], 1, 250), 1, 'primary' if focused else 'secondary')

    def select(self, item, ctx):
        if item[1] == 'privacy' and ctx.inbox:
            order = ['full', 'sender', 'off']
            ctx.inbox.privacy = order[(order.index(ctx.inbox.privacy) + 1) % 3] if ctx.inbox.privacy in order else 'full'
            return None
        if item[1] == 'clear' and ctx.inbox:
            ctx.inbox.clear()
            return None
        return ('push', Calibration())


class Calibration(Screen):
    """Run once on new glasses: the arrow must point to the top-left corner. If not, set rotate180."""

    def on(self, ev, ctx):
        return ('pop',) if ev in ('ok', 'back') else None

    def render(self, p, ctx):
        p.rect(0, 0, W - 1, H - 1, 'muted')
        p.line(20, 20, 70, 20, 'accent')
        p.line(20, 20, 20, 70, 'accent')
        p.line(20, 20, 80, 80, 'accent')
        p.text(92, 30, 'TOP LEFT', 1, 'accent')
        p.text_center(W / 2, 120, 'Arrow at the top left?', 2, 'primary')
        p.text_center(W / 2, 156, 'If not: openbridge glasses set --rotate', 0, 'secondary')
        p.text_right(W - 20, H - 36, 'BOTTOM RIGHT', 0, 'muted')


# ---------------------------------------------------------------- the menu stack

class Menu:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.stack: list[Screen] = [Home()]

    @property
    def screen(self):
        return self.stack[-1]

    def handle(self, ev):
        """Apply one input event. Returns an Action to run, or None."""
        if ev not in EVENTS:
            return None
        if self.ctx.toast and self.ctx.toast.get('until', 0) >= self.ctx.clock():
            item = self.ctx.toast
            self.ctx.toast = None
            if ev == 'ok' and item.get('id'):              # open the message that just arrived
                self.stack.append(MessageView(item))
            return None
        r = self.screen.on(ev, self.ctx)
        if not r:
            return None
        if r[0] == 'push':
            self.stack.append(r[1])
        elif r[0] == 'pop' and len(self.stack) > 1:
            self.stack.pop()
        elif r[0] == 'home':
            del self.stack[1:]
        elif r[0] == 'act':
            return r[1]
        return None

    def render(self, colour=True, rotate180=False) -> Panel:
        p = Panel(colour=colour, rotate180=rotate180).begin()
        self.screen.render(p, self.ctx)
        toast(p, self.ctx)
        return p.end()


class GestureDecoder:
    """The ENGO gesture sensor reports single waves. 1 wave = next, 2 within WINDOW = ok, 3 = back."""
    WINDOW = 0.7

    def __init__(self, clock=time.monotonic):
        self.clock, self.count, self.last = clock, 0, 0.0

    def wave(self):
        now = self.clock()
        self.count = self.count + 1 if now - self.last <= self.WINDOW else 1
        self.last = now

    def poll(self):
        """Call regularly; returns an event once the burst of waves is over."""
        if self.count and self.clock() - self.last > self.WINDOW:
            n, self.count = self.count, 0
            return {1: 'next', 2: 'ok'}.get(n, 'back')
        return None
