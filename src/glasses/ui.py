"""Glasses menus: screens, navigation and the actions they ask OpenBridge to run.

Input is reduced to five events so that every source can drive the same menus:
  next / prev / ok / back / home
- glasses gesture sensor: one wave = next, two quick waves = ok, three = back (see GestureDecoder);
- Companion phone or watch buttons, the HUD Studio keyboard, and voice send the events directly;
- the TV remote screen also accepts up / down / left / right as direct D-pad keys.

A screen never touches a device. Selecting an item returns an Action that the hub runs through the OpenBridge gate
(typed primitive, consent, read-back, receipt); the outcome comes back as a banner. Every word on screen comes from
the FR / EN locale files (i18n.t), in the glasses language chosen by the owner.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from src.glasses import icons as I
from src.glasses.i18n import NATIVE_NAMES, fmt_distance, fmt_duration, fmt_pace, fmt_speed, t
from src.glasses.panel import H, W, Panel, fit, text_width, wrap

EVENTS = ('next', 'prev', 'ok', 'back', 'home', 'up', 'down', 'left', 'right')

TV_APPS = [  # label, Android TV package
    ('YouTube', 'com.google.android.youtube.tv'), ('Netflix', 'com.netflix.ninja'),
    ('Prime Video', 'com.amazon.amazonvideo.livingroom'), ('Disney+', 'com.disney.disneyplus'),
    ('Spotify', 'com.spotify.tv.android'), ('Plex', 'com.plexapp.android'), ('Twitch', 'tv.twitch.android.app'),
    ('myCANAL', 'com.canal.android.canal'), ('VLC', 'org.videolan.vlc'), ('Kodi', 'org.xbmc.kodi'),
]
DIRECTION_ANGLE = {'straight': 0, 'slight_right': 35, 'right': 90, 'sharp_right': 135,
                   'slight_left': -35, 'left': -90, 'sharp_left': -135}
PRIORITY_TONE = {'CRITICAL': 'alert', 'ACTION_RECEIPT': 'ok', 'INTERACTION': 'accent', 'SPORT': 'accent',
                 'AMBIENT': 'secondary'}


@dataclass
class Action:
    """What a menu item asks for. kind: device (a typed primitive on a device class) | voice."""
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
    lang: str = 'en'
    units: str = 'metric'
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
    event: object = None                           # current HudEvent from the scheduler
    sport: dict = field(default_factory=dict)      # live values from the sport engines (None = unknown / stale)

    def tr(self, key, **kw):
        return t(key, self.lang, **kw)


# ---------------------------------------------------------------- chrome

# Part of the logical canvas the wearer sees on a real ENGO 3 (with the default 20 px left offset): ~258 x 250.
VIS_X0, VIS_X1 = 22, 282
VIS_W, VIS_CX = VIS_X1 - VIS_X0, (22 + 282) // 2

def status_bar(p: Panel, ctx: Context):
    tm = time.localtime(ctx.clock())
    p.text(VIS_X0, 6, '%02d:%02d' % (tm.tm_hour, tm.tm_min), 1, 'secondary')
    x = VIS_X1
    if ctx.glasses_battery is not None:
        x -= p.text_right(x, 16, '%d%%' % ctx.glasses_battery, 0, 'muted') + 10
    unread = ctx.inbox.unread() if ctx.inbox else 0
    if unread:
        w = text_width(str(unread), 0)
        p.round_rect(x - w - 26, 13, x, 31, 9, 'accent')
        I.bell(p, x - w - 15, 21, 6, 'accent')
        p.text(x - w - 5, 16, str(unread), 0, 'accent')
        x -= w + 34
    gps = (ctx.sport or {}).get('gps')
    if gps:
        p.text_right(x - 12, 16, 'GPS', 0, {'READY': 'ok', 'STALE': 'warn'}.get(gps, 'alert'))
        x -= 40
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


def event_card(p: Panel, ctx: Context):
    """The scheduler's current HUD event (alert, receipt, step change...) over the screen; the screen returns after."""
    ev = ctx.event
    if ev is None:
        return
    tone = PRIORITY_TONE.get(ev.priority, 'accent')
    p.erase(8, 150, 296, 236)
    p.round_rect(14, 156, 290, 228, 14, tone)
    if ev.priority == 'CRITICAL':
        p.round_rect(16, 158, 288, 226, 13, tone)
    for i, line in enumerate(wrap(ctx.tr(ev.message_key, **ev.params), 2 if len(ev.params) < 3 else 1, 256, 2)):
        p.text_center(W / 2, 166 + i * 28, line, 2 if len(ev.params) < 3 else 1, 'primary')


def ago(ts, ctx):
    s = max(0, int(ctx.clock() - ts))
    if s < 60:
        return ctx.tr('common.now')
    if s < 3600:
        return ctx.tr('common.min', n=s // 60)
    if s < 86400:
        return ctx.tr('common.hours', n=s // 3600)
    return ctx.tr('common.days', n=s // 86400)


# ---------------------------------------------------------------- screens

class Screen:
    def __init__(self):
        self.focus = 0

    def title(self, ctx):
        return ''

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
    hint_key = 'hint.list'

    def row(self, p, item, x, y, focused, ctx):
        p.text(x, y + 10, fit(item[0], 2, 230), 2, 'primary' if focused else 'secondary')

    def header_right(self, ctx):
        n = len(self.items(ctx))
        return '%d / %d' % (self.focus + 1, n) if n else ''

    def empty_text(self, ctx):
        return ctx.tr('list.empty')

    def render(self, p, ctx):
        status_bar(p, ctx)
        p.text(22, 42, fit(self.title(ctx), 2, 190), 2, 'primary')
        p.text_right(284, 50, self.header_right(ctx), 0, 'muted')
        items = self.items(ctx)
        if not items:
            p.text_center(W / 2, 120, self.empty_text(ctx), 1, 'muted')
        page = self.focus // self.rows_per_page
        for i, item in enumerate(items[page * self.rows_per_page:(page + 1) * self.rows_per_page]):
            idx = page * self.rows_per_page + i
            y = 78 + i * 50
            if idx == self.focus:
                p.round_rect(14, y, 290, y + 44, 12, 'accent')
            self.row(p, item, 30, y, idx == self.focus, ctx)
        hint(p, ctx.tr(self.hint_key))
        banner(p, ctx)


class IconList(ListScreen):
    """Rows of (label, payload, icon)."""

    def row(self, p, item, x, y, focused, ctx):
        I.draw(p, item[2], x + 10, y + 22, 9, 'accent' if focused else 'muted')
        p.text(x + 34, y + 10, fit(item[0], 2, 220), 2, 'primary' if focused else 'secondary')


class Home(Screen):
    """Carousel: one big ring in the middle, neighbours on the sides, page dots."""

    def items(self, ctx):
        unread = ctx.inbox.unread() if ctx.inbox else 0
        vac_sub = ' · '.join(x for x in (ctx.vacuum_state.capitalize(),
                                         '%d%%' % ctx.vacuum_battery if ctx.vacuum_battery is not None else '') if x)
        return [(ctx.tr('menu.messages'), 'chat',
                 ctx.tr('menu.messages.unread', n=unread) if unread else ctx.tr('menu.messages.none'), Inbox),
                (ctx.tr('menu.sport'), 'runner', ctx.tr('hud.sport.subtitle'), SportMenu),
                (ctx.tr('menu.tv'), 'tv', ctx.tv_app or ctx.tv_name, TVHub),
                (ctx.tr('menu.vacuum'), 'vacuum', vac_sub or ctx.tr('menu.vacuum.sub'), VacuumScreen),
                (ctx.tr('menu.voice'), 'mic', ctx.tr('menu.voice.sub'), VoiceScreen),
                (ctx.tr('menu.settings'), 'gear', ctx.tr('menu.settings.sub'), SettingsScreen)]

    def on(self, ev, ctx):
        if ev == 'back':
            return None
        return super().on(ev, ctx)

    def select(self, item, ctx):
        return ('push', item[3]())

    def render(self, p, ctx):
        # Laid out for the real ENGO 3: visible width ~258 px (VIS_X0..VIS_X1), 24/38 px fonts.
        status_bar(p, ctx)
        items = self.items(ctx)
        n = len(items)
        cur = items[self.focus]
        cx, cy = VIS_CX, 94
        p.circle(cx, cy, 40, 'accent')
        p.circle(cx, cy, 43, 'accent_dim')
        I.draw(p, cur[1], cx, cy, 20, 'primary')
        for side, k in ((-1, (self.focus - 1) % n), (1, (self.focus + 1) % n)):
            sx = cx + side * 96
            p.circle(sx, cy, 18, 'faint')
            I.draw(p, items[k][1], sx, cy, 9, 'muted')
        p.text_center(cx, 144, fit(cur[0], 2, VIS_W - 8), 2, 'primary')
        p.text_center(cx, 186, fit(cur[2], 1, VIS_W - 8), 1, 'secondary')
        x0 = cx - (n - 1) * 7
        for i in range(n):
            p.circle(x0 + i * 14, 226, 3 if i == self.focus else 2, 'accent' if i == self.focus else 'muted', True)


class Inbox(ListScreen):
    hint_key = 'hint.inbox'

    def title(self, ctx):
        return ctx.tr('menu.messages')

    def items(self, ctx):
        return ctx.inbox.list() if ctx.inbox else []

    def empty_text(self, ctx):
        return ctx.tr('inbox.empty')

    def row(self, p, n, x, y, focused, ctx):
        I.badge(p, x + 10, y + 22, 13, n['letter'], 'accent' if focused else 'muted', 1)
        p.text(x + 34, y + 6, fit(n['sender'], 1, 170), 1, 'primary' if focused else 'secondary')
        p.text_right(278, y + 9, ago(n['time'], ctx), 0, 'muted')
        text = ctx.tr('inbox.privacy_hidden') if n.get('text') == 'New message' else n['text']
        p.text(x + 34, y + 27, fit(text, 0, 220), 0, 'secondary' if focused else 'muted')
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
        p.text_right(284, 50, ago(n['time'], ctx), 0, 'muted')
        p.text(22, 76, fit(n['sender'], 2, 262), 2, 'primary')
        text = ctx.tr('inbox.privacy_hidden') if n.get('text') == 'New message' else n['text']
        for i, line in enumerate(wrap(text, 1, 262, 5)):
            p.text(22, 112 + i * 23, line, 1, 'secondary')
        hint(p, ctx.tr('hint.message'))


class TVHub(Screen):
    """3 x 2 tiles."""
    TILES = [('tv.volume', 'volume'), ('tv.apps', 'apps'), ('tv.remote', 'dpad'),
             ('tv.play_pause', 'play_pause'), ('tv.home', 'home'), ('tv.power', 'power')]

    def items(self, ctx):
        return self.TILES

    def select(self, item, ctx):
        key = item[0]
        if key == 'tv.volume':
            return ('push', VolumeScreen())
        if key == 'tv.apps':
            return ('push', AppsScreen())
        if key == 'tv.remote':
            return ('push', RemoteScreen())
        if key == 'tv.play_pause':
            return ('act', tv_key('play_pause', ctx.tr('tv.play_pause')))
        if key == 'tv.home':
            return ('act', tv_key('home', ctx.tr('tv.home')))
        return ('push', PowerScreen())

    def render(self, p, ctx):
        status_bar(p, ctx)
        p.text(22, 42, fit(ctx.tv_name, 2, 170), 2, 'primary')
        p.text_right(284, 50, fit(ctx.tv_app, 0, 100), 0, 'muted')
        for i, (key, icon) in enumerate(self.TILES):
            col, row = i % 3, i // 3
            x0, y0 = 16 + col * 92, 78 + row * 76
            f = i == self.focus
            p.round_rect(x0, y0, x0 + 84, y0 + 68, 12, 'accent' if f else 'faint')
            I.draw(p, icon, x0 + 42, y0 + 26, 13, 'primary' if f else 'muted')
            p.text_center(x0 + 42, y0 + 46, fit(ctx.tr(key), 0, 78), 0, 'primary' if f else 'muted')
        hint(p, ctx.tr('hint.select'))
        banner(p, ctx)


class VolumeScreen(Screen):
    """Big number on a 270° gauge; − and + buttons. Each press is one volume step, read back from the TV."""

    def items(self, ctx):
        return ['down', 'up']

    def select(self, item, ctx):
        return ('act', Action('device', ctx.tr('tv.volume_' + item), 'tv', 'device_action',
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
            end = 135 + int(270 * max(0, min(100, v)) / 100)
            p.arc(cx, cy, r, 135, end, 'accent')
            p.arc(cx, cy, r - 3, 135, end, 'accent')
            p.text_center(cx, cy - 28, str(v), 5, 'primary')
        else:
            p.text_center(cx, cy - 16, '- -', 3, 'muted')
        p.text_center(cx, cy + 34, ctx.tr('tv.volume_label'), 0, 'muted')
        for i, (bx, ic) in enumerate(((54, 'minus'), (250, 'plus'))):
            f = i == self.focus
            p.circle(bx, cy + 10, 24, 'accent' if f else 'faint')
            I.draw(p, ic, bx, cy + 10, 14, 'primary' if f else 'muted')
        hint(p, ctx.tr('hint.switch'))
        banner(p, ctx)


class AppsScreen(ListScreen):
    def title(self, ctx):
        return ctx.tr('tv.apps')

    def items(self, ctx):
        return TV_APPS

    def row(self, p, item, x, y, focused, ctx):
        I.apps(p, x + 10, y + 22, 9, 'accent' if focused else 'muted')
        p.text(x + 34, y + 10, item[0], 2, 'primary' if focused else 'secondary')
        if ctx.tv_app and ctx.tv_app.lower() == item[0].lower():
            p.text_right(278, y + 16, ctx.tr('tv.on_screen'), 0, 'ok')

    def select(self, item, ctx):
        return ('act', Action('device', ctx.tr('tv.open_app', app=item[0]), 'tv', 'device_action',
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
        if ev == 'back':
            return ('pop',)
        return super().on(ev, ctx)

    def select(self, item, ctx):
        label = {'ok': 'OK', 'back': ctx.tr('tv.back'), 'home': ctx.tr('tv.home')}.get(item[0], item[0].capitalize())
        return ('act', tv_key(item[0], label))

    def render(self, p, ctx):
        status_bar(p, ctx)
        p.text(22, 42, ctx.tr('tv.remote'), 2, 'primary')
        p.text_right(284, 50, fit(ctx.tv_app, 0, 110), 0, 'muted')
        cx, cy, d = 124, 136, 52
        for i, (name, dx, dy) in enumerate(self.KEYS[:5]):
            x, y = cx + dx * d, cy + dy * d
            f = i == self.focus
            p.circle(x, y, 22 if name != 'ok' else 25, 'accent' if f else 'faint')
            tone = 'primary' if f else 'muted'
            if name == 'ok':
                p.text_center(x, y - 9, 'OK', 1, tone)
            else:
                ang = {'up': -90, 'right': 0, 'down': 90, 'left': 180}[name]
                ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                tx, ty = x + ux * 8, y + uy * 8
                p.line(tx, ty, x - ux * 4 - uy * 8, y - uy * 4 + ux * 8, tone)
                p.line(tx, ty, x - ux * 4 + uy * 8, y - uy * 4 - ux * 8, tone)
        for j, (name, key, icon) in enumerate((('back', 'tv.back', 'back'), ('home', 'tv.home', 'home'))):
            i = 5 + j
            y = 96 + j * 74
            f = i == self.focus
            p.round_rect(214, y, 286, y + 56, 12, 'accent' if f else 'faint')
            I.draw(p, icon, 250, y + 20, 9, 'primary' if f else 'muted')
            p.text_center(250, y + 34, fit(ctx.tr(key), 0, 68), 0, 'primary' if f else 'muted')
        hint(p, ctx.tr('hint.remote'))
        banner(p, ctx)


class PowerScreen(IconList):
    def title(self, ctx):
        return ctx.tr('tv.power')

    def items(self, ctx):
        return [(ctx.tr('tv.sleep'), 'tv_sleep', 'power'), (ctx.tr('tv.wake'), 'tv_wake', 'power')]

    def select(self, item, ctx):
        return ('act', Action('device', 'TV · ' + item[0], 'tv', item[1], {}))


class VacuumScreen(IconList):
    def title(self, ctx):
        return ctx.tr('menu.vacuum')

    def items(self, ctx):
        return [(ctx.tr('vac.start'), 'start', 'play'), (ctx.tr('vac.pause'), 'pause', 'pause'),
                (ctx.tr('vac.dock'), 'dock', 'home'), (ctx.tr('vac.seek'), 'seek', 'search')]

    def header_right(self, ctx):
        bits = [ctx.vacuum_state.capitalize()] if ctx.vacuum_state else []
        if ctx.vacuum_battery is not None:
            bits.append('%d%%' % ctx.vacuum_battery)
        return ' · '.join(bits)

    def select(self, item, ctx):
        return ('act', vac(item[1], item[0]))


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
        st = st if st in ('idle', 'listening', 'thinking', 'done', 'failed') else 'idle'
        cx, cy = W / 2, 92
        tone = {'listening': 'accent', 'thinking': 'warn', 'done': 'ok', 'failed': 'alert'}.get(st, 'muted')
        I.mic(p, cx, cy, 20, 'primary' if st != 'idle' else 'secondary')
        p.circle(cx, cy, 36, tone)
        if st == 'listening':
            for k in range(int(ctx.clock() * 3) % 3 + 1):
                p.circle(cx, cy, 44 + k * 9, 'accent_dim')
        label = ctx.tr({'idle': 'voice.idle', 'listening': 'voice.listening', 'thinking': 'voice.thinking',
                        'done': 'voice.done', 'failed': 'voice.failed'}[st])
        p.text_center(cx, 140, label, 2 if st != 'idle' else 1, 'primary' if st != 'idle' else 'secondary', width=268)
        heard = v.get('text') or ''
        for i, line in enumerate(wrap('“%s”' % heard if heard else '', 1, 262, 2)):
            p.text_center(cx, 174 + i * 22, line, 1, 'secondary')
        if v.get('result'):
            p.text_center(cx, 220, fit(v['result'], 0, 262), 0, 'ok' if st == 'done' else 'alert')
        else:
            hint(p, ctx.tr('voice.try'))


ORACLE_LINES_PER_PAGE, ORACLE_FONT, ORACLE_WIDTH = 4, 2, 264


def oracle_pages(answer: str) -> list:
    """A long answer is cut into pages of 4 lines in the large font (one wave = next page)."""
    lines = wrap(answer, ORACLE_FONT, ORACLE_WIDTH, 999)
    return [lines[i:i + ORACLE_LINES_PER_PAGE] for i in range(0, len(lines), ORACLE_LINES_PER_PAGE)] or [[]]


class OracleScreen(Screen):
    """Real-time VoiceAI Oracle answer card for ENGO 3 (304x256 MicroOLED). Long answers are paged."""
    page = 0

    def _pages(self, ctx):
        v = ctx.voice or {}
        ans = ((v.get('oracle') or {}).get('answer') or v.get('result') or '').strip()
        return oracle_pages(ans)

    def on(self, ev, ctx):
        n = len(self._pages(ctx))
        if ev in ('next', 'down', 'right') and n > 1:
            self.page = (self.page + 1) % n
            return None
        if ev in ('prev', 'up', 'left') and n > 1:
            self.page = (self.page - 1) % n
            return None
        if ev in ('ok', 'back'):
            return ('pop',)
        if ev == 'home':
            return ('home',)
        return None

    def render(self, p, ctx):
        v = ctx.voice or {}
        o = v.get('oracle') or {}
        st = v.get('state', 'done')
        qclass = o.get('query_class', 'GENERAL')
        lat = int(o.get('latency_ms', 0) or 0)

        # Header badge + latency
        badge_tone = {'MATH': 'accent', 'LOCATE': 'warn', 'GENERAL': 'ok'}.get(qclass, 'accent')
        badge = {'MATH': 'ORACLE MATH', 'LOCATE': 'ORACLE INFO', 'GENERAL': 'ORACLE AI'}.get(qclass, 'ORACLE AI')
        if st == 'listening':
            badge = 'ECOUTE...'
            badge_tone = 'accent'
        p.text(22, 16, badge, 1, badge_tone)
        if st != 'listening':
            lat_tone = 'ok' if lat < 600 else 'warn' if lat < 2000 else 'alert'
            p.text_right(284, 16, f'{lat}ms', 1, lat_tone)
        p.line(18, 38, 286, 38, 'faint')

        # Heard transcript (1-2 lines)
        heard = v.get('text') or o.get('transcript') or ''
        for i, line in enumerate(wrap('> ' + heard if heard else '', 0, 264, 2)):
            p.text(20, 44 + i * 16, line, 0, 'secondary')
        p.line(18, 80, 286, 80, 'faint')

        # Answer body: large font, 4 lines per page; a wave shows the next page
        pages = self._pages(ctx)
        self.page = min(self.page, len(pages) - 1)
        if st == 'listening':
            p.text_center(W / 2, 128, '...', 2, 'accent')
        elif pages[self.page]:
            ans_tone = 'ok' if qclass != 'LOCATE' else 'primary'
            for i, ln in enumerate(pages[self.page]):
                p.text(20, 84 + i * 29, ln, ORACLE_FONT, ans_tone)
            if len(pages) > 1:
                p.text_right(284, 206, '%d/%d' % (self.page + 1, len(pages)), 1, 'accent')

        # Footer source + dismiss hint
        src = str(o.get('source') or '').upper()
        if src:
            p.text(22, 206, src[:18], 0, 'muted')
        hint(p, ctx.tr('hint.message'))


class SettingsScreen(ListScreen):
    def title(self, ctx):
        return ctx.tr('menu.settings')

    def items(self, ctx):
        mode = getattr(ctx.inbox, 'privacy', 'full') if ctx.inbox else 'full'
        return [(ctx.tr('settings.language_value', lang=NATIVE_NAMES.get(ctx.lang, ctx.lang)), 'lang'),
                (ctx.tr('settings.message_text', mode=ctx.tr('settings.mode.' + mode)), 'privacy'),
                (ctx.tr('settings.clear'), 'clear'), (ctx.tr('settings.calibrate'), 'calibrate')]

    def row(self, p, item, x, y, focused, ctx):
        p.text(x, y + 12, fit(item[0], 1, 250), 1, 'primary' if focused else 'secondary')

    def select(self, item, ctx):
        if item[1] == 'lang':
            ctx.lang = 'en' if ctx.lang == 'fr' else 'fr'      # the hub saves it as the glasses language
            return ('act', Action('setting', 'hud_language', params={'hud_language': ctx.lang}))
        if item[1] == 'privacy' and ctx.inbox:
            order = ['full', 'sender', 'off']
            ctx.inbox.privacy = order[(order.index(ctx.inbox.privacy) + 1) % 3] if ctx.inbox.privacy in order else 'full'
            return ('act', Action('setting', 'privacy', params={'privacy': ctx.inbox.privacy}))
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
        p.text(92, 30, ctx.tr('calib.top_left'), 1, 'accent')
        p.text_center(W / 2, 120, fit(ctx.tr('calib.question'), 2, 280), 2, 'primary')
        p.text_center(W / 2, 156, fit(ctx.tr('calib.fix'), 0, 280), 0, 'secondary')
        p.text_right(W - 20, H - 36, ctx.tr('calib.bottom_right'), 0, 'muted')


# ---------------------------------------------------------------- sport

class SportMenu(IconList):
    def title(self, ctx):
        return ctx.tr('menu.sport')

    def items(self, ctx):
        return [(ctx.tr('hud.sport.run'), 'run', 'runner'), (ctx.tr('hud.sport.ride'), 'ride', 'bike'),
                (ctx.tr('hud.sport.navigate'), 'nav', 'flag'), (ctx.tr('hud.sport.ghost'), 'ghost', 'ghost'),
                (ctx.tr('hud.sport.workout'), 'workout', 'timer')]

    def select(self, item, ctx):
        return ('push', {'run': lambda: SportDashboard('run'), 'ride': lambda: SportDashboard('ride'),
                         'nav': NavScreen, 'ghost': GhostScreen, 'workout': WorkoutScreen}[item[1]]())


def _metric(p, x, y, label, value, tone='primary', width=128):
    p.text(x, y, label, 0, 'muted')
    p.text(x, y + 14, fit(value, 3, width), 3, tone)


class SportDashboard(Screen):
    """One big number (pace for running, speed for cycling), four small ones. Stale values show as —."""

    def __init__(self, mode='run'):
        super().__init__()
        self.mode = mode

    def render(self, p, ctx):
        s = ctx.sport or {}
        status_bar(p, ctx)
        if self.mode == 'run':
            big, unit = fmt_pace(s.get('pace_s_per_km'), ctx.units), ('/km' if ctx.units == 'metric' else '/mi')
            label = ctx.tr('hud.metric.pace')
        else:
            big, unit = fmt_speed(s.get('speed_mps'), ctx.units, ctx.lang), ('km/h' if ctx.units == 'metric' else 'mph')
            label = ctx.tr('hud.metric.speed')
        p.text(22, 40, label, 0, 'muted')
        w = p.text(22, 50, big, 5, 'primary')
        p.text(30 + w, 82, unit, 1, 'secondary')
        hr, zone = s.get('heart_rate'), s.get('hr_zone')
        if hr is not None:
            I.heart(p, 250, 62, 9, {5: 'alert', 4: 'warn'}.get(zone, 'accent'))
            p.text_right(284, 76, str(int(hr)), 2, 'primary')
            if zone:
                p.text_right(284, 104, 'Z%d' % zone, 0, {5: 'alert', 4: 'warn'}.get(zone, 'accent'))
        p.line(22, 124, 282, 124, 'faint')
        _metric(p, 22, 132, ctx.tr('hud.metric.distance'), fmt_distance(s.get('distance_m'), ctx.units, ctx.lang))
        _metric(p, 160, 132, ctx.tr('hud.metric.time'), fmt_duration(s.get('elapsed_s')))
        third = (ctx.tr('hud.metric.power'), '%d W' % s['power']) if s.get('power') is not None else \
                (ctx.tr('hud.metric.cadence'), '%d' % s['cadence']) if s.get('cadence') is not None else \
                (ctx.tr('hud.metric.lap'), fmt_duration(s.get('lap_s')) if s.get('lap_s') else '—')
        _metric(p, 22, 182, third[0], third[1])
        if s.get('lap_n'):
            _metric(p, 160, 182, ctx.tr('hud.metric.lap') + ' %d' % s['lap_n'], fmt_duration(s.get('last_lap_s')))
        event_card(p, ctx)


class NavScreen(Screen):
    """Arrow + distance + one short instruction (spec §5.3). Off route: the arrow turns red and says so."""

    def render(self, p, ctx):
        s = ctx.sport or {}
        nav = s.get('nav') or {}
        status_bar(p, ctx)
        if not nav:
            p.text_center(W / 2, 110, ctx.tr('common.unavailable'), 2, 'muted')
            return
        if nav.get('arrived'):
            I.flag(p, W / 2, 96, 30, 'ok')
            p.text_center(W / 2, 150, ctx.tr('hud.navigation.arrival'), 3, 'ok')
            return
        off = nav.get('off_route')
        turn = nav.get('next_turn') or {'direction': 'straight', 'in_m': nav.get('remaining_m')}
        direction = turn['direction']
        tone = 'alert' if off else 'accent'
        cx, cy = 76, 112
        p.circle(cx, cy, 52, tone)
        if direction == 'u_turn':
            I.u_turn(p, cx, cy, 30, 'primary')
        else:
            I.arrow(p, cx, cy, 32, DIRECTION_ANGLE.get(direction, 0), 'primary')
        if off:
            label = ctx.tr('hud.navigation.off_route')
            size = 2 if text_width(label, 2) <= 140 else 1          # "Hors itinéraire" is wider than "Off route"
            p.text(150, 60 if size == 2 else 66, fit(label, size, 140), size, 'alert')
            p.text(150, 92, fmt_distance(nav.get('off_by_m'), ctx.units, ctx.lang), 3, 'primary')
        else:
            p.text(150, 56, fmt_distance(turn.get('in_m'), ctx.units, ctx.lang), 4, 'primary')
            p.text(150, 110, fit(ctx.tr('hud.dir.' + direction), 1, 140), 1, 'secondary')
        p.line(22, 184, 282, 184, 'faint')
        p.text(22, 194, ctx.tr('hud.navigation.remaining', distance=fmt_distance(nav.get('remaining_m'), ctx.units, ctx.lang)),
               1, 'secondary')
        if nav.get('eta_s') is not None:
            eta = time.localtime(ctx.clock() + nav['eta_s'])
            p.text_right(282, 194, ctx.tr('hud.navigation.eta', time='%02d:%02d' % (eta.tm_hour, eta.tm_min)), 1, 'secondary')
        poi = nav.get('nearest_poi')
        if poi and poi.get('distance_m', 1e9) < 2000:
            p.text(22, 222, fit('%s · %s' % (poi['name'], fmt_distance(poi['distance_m'], ctx.units, ctx.lang)), 0, 260), 0, 'accent')
        event_card(p, ctx)


class GhostScreen(Screen):
    """Gap to the ghost in seconds (green ahead, amber behind) and both positions on one line."""

    def render(self, p, ctx):
        s = ctx.sport or {}
        g = s.get('ghost') or {}
        status_bar(p, ctx)
        I.ghost(p, 36, 54, 12, 'muted')
        p.text(56, 44, fit(g.get('ghost_name') or ctx.tr('hud.sport.ghost'), 1, 220), 1, 'secondary')
        gap = g.get('gap_s')
        if gap is None:
            p.text_center(W / 2, 100, '—', 5, 'muted')
        else:
            ahead = gap >= 0
            tone = 'ok' if ahead else 'warn'
            txt = ('+' if ahead else '−') + fmt_duration(abs(gap))
            p.text_center(W / 2, 82, txt, 5, tone)
            key = 'hud.ghost.even' if abs(gap) < 1 else 'hud.ghost.ahead' if ahead else 'hud.ghost.behind'
            p.text_center(W / 2, 146, ctx.tr(key, gap=fmt_distance(abs(g.get('gap_m') or 0), ctx.units, ctx.lang)), 1, 'secondary')
        total = g.get('total_m') or 0
        if total:
            x0, x1, y = 30, 274, 186
            p.line(x0, y, x1, y, 'faint')
            for dist, tone, r in ((g.get('ghost_m') or 0, 'muted', 5), (s.get('distance_m') or 0, 'accent', 6)):
                x = x0 + (x1 - x0) * max(0, min(1, dist / total))
                p.circle(x, y, r, tone, True)
        if g.get('projected_finish_s'):
            p.text_center(W / 2, 206, ctx.tr('hud.ghost.projection', time=fmt_duration(g['projected_finish_s'])), 1, 'muted')
        event_card(p, ctx)


class WorkoutScreen(Screen):
    """Current step, what is left of it, target vs current pace, progress through the session."""

    def render(self, p, ctx):
        s = ctx.sport or {}
        w = s.get('workout') or {}
        status_bar(p, ctx)
        if not w:
            p.text_center(W / 2, 110, ctx.tr('common.unavailable'), 2, 'muted')
            return
        if w.get('done'):
            I.check(p, W / 2, 96, 30, 'ok')
            p.text_center(W / 2, 146, ctx.tr('hud.training.done'), 2, 'ok')
            return
        kind_tone = {'work': 'warn', 'recovery': 'ok'}.get(w.get('kind'), 'accent')
        p.text(22, 42, ctx.tr('hud.training.' + w.get('kind', 'work')), 2, kind_tone)
        p.text_right(284, 50, ctx.tr('hud.training.step', n=w.get('n', 1), total=w.get('total', 1)), 0, 'muted')
        unit, left = w.get('remaining') or ('s', None)
        big = fmt_duration(left) if unit == 's' else fmt_distance(left, ctx.units, ctx.lang)
        p.text_center(W / 2, 84, big, 5, 'primary')
        tgt, cur = w.get('target_pace'), s.get('pace_s_per_km')
        if tgt:
            p.text(22, 162, ctx.tr('hud.training.target_pace', pace=fmt_pace(tgt, ctx.units)), 1, 'secondary')
            if cur:
                tone = 'ok' if abs(cur - tgt) <= 5 else 'warn'
                p.text_right(282, 162, fmt_pace(cur, ctx.units), 2, tone)
        n, total = w.get('n', 1), max(1, w.get('total', 1))
        p.rect(22, 204, 282, 210, 'faint')
        p.rect(22, 204, 22 + int(260 * (n - 1) / total), 210, 'accent', True)
        event_card(p, ctx)


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
        if self.ctx.event is not None and ev in ('ok', 'back') and self.ctx.event.dismissible:
            self.ctx.event = None                         # a gesture acknowledges the card, nothing else
            return Action('ack', 'ack')
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

    def render(self, colour=True, rotate180=False, x_offset=None) -> Panel:
        p = Panel(colour=colour, rotate180=rotate180, **({} if x_offset is None else {'x_offset': x_offset})).begin()
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
