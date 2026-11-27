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
from src.glasses.panel import FONTS, H, W, Panel, ascii_fold, fit, text_width, wrap

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
    input: str = 'wave'                            # 'wave' (ENGO 1/2 gesture sensor) or 'tap' (ENGO 3 double tap)
    modules: dict = field(default_factory=dict)    # Companion modules switched off on the phone hide their menu

    def tr(self, key, **kw):
        return t(key, self.lang, **kw)


# ---------------------------------------------------------------- chrome

# Part of the logical canvas the wearer sees on a real ENGO 3 (measured: x 0-~292, y 0-~236), with a small margin.
# Every screen below is laid out for that window and the real fonts (24 px for ids 0-1, 38 px id 2, 64 px id 3,
# 82 px id 5; a letter is about half as wide as the font is tall).
VIS_X0, VIS_X1, VIS_Y0, VIS_Y1 = 12, 284, 4, 234
VIS_W, VIS_CX = VIS_X1 - VIS_X0, (12 + 284) // 2
HEAD_Y, BODY_Y, HINT_Y = 34, 76, 210          # title row, first content row, bottom hint row

def status_bar(p: Panel, ctx: Context):
    tm = time.localtime(ctx.clock())
    p.text(VIS_X0, 6, '%02d:%02d' % (tm.tm_hour, tm.tm_min), 1, 'secondary')
    x = VIS_X1
    if ctx.glasses_battery is not None:
        x -= p.text_right(x, 6, '%d%%' % ctx.glasses_battery, 0, 'muted') + 10
    unread = ctx.inbox.unread() if ctx.inbox else 0
    if unread:
        w = text_width(str(unread), 0)
        p.round_rect(x - w - 26, 6, x, 30, 10, 'accent')
        I.bell(p, x - w - 15, 18, 6, 'accent')
        p.text(x - w - 5, 6, str(unread), 0, 'accent')
        x -= w + 34
    gps = (ctx.sport or {}).get('gps')
    if gps:
        x -= p.text_right(x - 6, 6, 'GPS', 0, {'READY': 'ok', 'STALE': 'warn'}.get(gps, 'alert')) + 12
    p.circle(x - 4, 18, 3, 'ok' if ctx.linked else 'faint', True)


def hint(p: Panel, text):
    p.text_center(VIS_CX, HINT_Y, text, 0, 'muted', width=VIS_W)


def best_font(text, fonts, width):
    """First font of `fonts` (largest first) in which `text` fits `width`; the last one otherwise (then cut)."""
    clean = ' '.join(ascii_fold(text).split())
    for f in fonts:
        if text_width(clean, f) <= width:
            return f
    return fonts[-1]


def text_fit(p, x, ymid, text, fonts, width, tone='primary', align='left'):
    """Text in the largest font that fits, centred vertically on ymid. Returns the width drawn."""
    f = best_font(text, fonts, width)
    y = ymid - FONTS[f][0] // 2
    s = fit(text, f, width)
    if align == 'center':
        return p.text_center(x, y, s, f, tone)
    if align == 'right':
        return p.text_right(x, y, s, f, tone)
    return p.text(x, y, s, f, tone)


def hint_key(ctx: Context, key: str) -> str:
    """Bottom hint for the wearer's input: the ENGO 3 only has the double tap, so its hints mention the voice."""
    if ctx.input == 'tap':
        tap = ctx.tr(key + '.tap')
        if tap != key + '.tap':
            return tap
    return ctx.tr(key)


def banner(p: Panel, ctx: Context):
    b = ctx.banner
    if not b or b.get('until', 0) < ctx.clock():
        return
    tone = 'ok' if b.get('ok') else 'alert'
    p.erase(VIS_X0, 168, VIS_X1, VIS_Y1)
    p.round_rect(VIS_X0, 172, VIS_X1, 212, 14, tone)
    (I.check if b.get('ok') else I.cross)(p, VIS_X0 + 22, 192, 8, tone)
    p.text(VIS_X0 + 40, 180, fit(b.get('text', ''), 1, VIS_W - 52), 1, 'primary')


def toast(p: Panel, ctx: Context):
    n = ctx.toast
    if not n or n.get('until', 0) < ctx.clock():
        return
    p.erase(VIS_X0, 30, VIS_X1, 124)
    p.round_rect(VIS_X0, 34, VIS_X1, 120, 14, 'accent')
    I.badge(p, VIS_X0 + 24, 62, 14, n.get('letter', '?'), 'accent')
    app = fit(n.get('app', ''), 0, 84)
    p.text(VIS_X0 + 46, 40, fit(n.get('sender', ''), 1, VIS_W - 64 - text_width(app, 0)), 1, 'primary')
    p.text_right(VIS_X1 - 10, 40, app, 0, 'accent_dim')
    for i, line in enumerate(wrap(n.get('text', ''), 1, VIS_W - 58, 2)):
        p.text(VIS_X0 + 46, 66 + i * 24, line, 1, 'secondary')


def event_card(p: Panel, ctx: Context):
    """The scheduler's current HUD event (alert, receipt, step change...) over the screen; the screen returns after."""
    ev = ctx.event
    if ev is None:
        return
    tone = PRIORITY_TONE.get(ev.priority, 'accent')
    p.erase(VIS_X0, 140, VIS_X1, VIS_Y1)
    p.round_rect(VIS_X0, 144, VIS_X1, VIS_Y1, 14, tone)
    if ev.priority == 'CRITICAL':
        p.round_rect(VIS_X0 + 2, 146, VIS_X1 - 2, VIS_Y1 - 2, 13, tone)
    msg = ctx.tr(ev.message_key, **ev.params)
    font = 2 if len(wrap(msg, 2, VIS_W - 20, 3)) <= 2 else 1
    step = 38 if font == 2 else 26
    for i, line in enumerate(wrap(msg, font, VIS_W - 20, 2 if font == 2 else 3)):
        p.text_center(VIS_CX, 150 + i * step, line, font, 'primary')


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
            return self.select(self.items(ctx)[self.focus % n], ctx)
        return None

    def select(self, item, ctx):
        return None

    def render(self, p: Panel, ctx: Context):
        raise NotImplementedError


class ListScreen(Screen):
    """Header + up to three rows, the focused one in an accent card."""
    rows_per_page = 3
    row_h = 44
    hint_key = 'hint.list'

    def row(self, p, item, x, y, focused, ctx):
        text_fit(p, x, y + 20, item[0], (2, 1), VIS_X1 - x - 10, 'primary' if focused else 'secondary')

    def header_right(self, ctx):
        n = len(self.items(ctx))
        return '%d / %d' % (self.focus + 1, n) if n else ''

    def empty_text(self, ctx):
        return ctx.tr('list.empty')

    def render(self, p, ctx):
        status_bar(p, ctx)
        right = self.header_right(ctx)
        rw = p.text_right(VIS_X1, HEAD_Y + 8, right, 1, 'muted') if right else 0
        text_fit(p, VIS_X0, HEAD_Y + 19, self.title(ctx), (2, 1), VIS_W - rw - 10)
        items = self.items(ctx)
        if not items:
            p.text_center(VIS_CX, 120, self.empty_text(ctx), 1, 'muted', width=VIS_W)
        page = self.focus // self.rows_per_page
        for i, item in enumerate(items[page * self.rows_per_page:(page + 1) * self.rows_per_page]):
            idx = page * self.rows_per_page + i
            y = BODY_Y + i * self.row_h
            if idx == self.focus:
                p.round_rect(VIS_X0, y, VIS_X1, y + self.row_h - 4, 12, 'accent')
            self.row(p, item, VIS_X0 + 12, y, idx == self.focus, ctx)
        hint(p, hint_key(ctx, self.hint_key))
        banner(p, ctx)


class IconList(ListScreen):
    """Rows of (label, payload, icon)."""

    def row(self, p, item, x, y, focused, ctx):
        I.draw(p, item[2], x + 10, y + 20, 9, 'accent' if focused else 'muted')
        text_fit(p, x + 32, y + 20, item[0], (2, 1), VIS_X1 - x - 42, 'primary' if focused else 'secondary')


class Home(Screen):
    """Carousel: one big ring in the middle, neighbours on the sides, page dots."""

    def items(self, ctx):
        unread = ctx.inbox.unread() if ctx.inbox else 0
        vac_sub = ' · '.join(x for x in (ctx.vacuum_state.capitalize(),
                                         '%d%%' % ctx.vacuum_battery if ctx.vacuum_battery is not None else '') if x)
        items = [(ctx.tr('menu.messages'), 'chat',
                 ctx.tr('menu.messages.unread', n=unread) if unread else ctx.tr('menu.messages.none'), Inbox),
                (ctx.tr('menu.sport'), 'runner', ctx.tr('hud.sport.subtitle'), SportMenu),
                (ctx.tr('menu.tv'), 'tv', ctx.tv_app or ctx.tv_name, TVHub),
                (ctx.tr('menu.vacuum'), 'vacuum', vac_sub or ctx.tr('menu.vacuum.sub'), VacuumScreen),
                (ctx.tr('menu.voice'), 'mic', ctx.tr('menu.voice.sub'), VoiceScreen),
                (ctx.tr('menu.settings'), 'gear', ctx.tr('menu.settings.sub'), SettingsScreen)]
        return [i for i in items if ctx.modules.get(HOME_MODULE.get(i[3]), True)]

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
        self.focus %= max(1, len(items))                 # a module switched off can shorten the list
        cur = items[self.focus]
        cx, cy = VIS_CX, 94
        p.circle(cx, cy, 40, 'accent')
        p.circle(cx, cy, 43, 'accent_dim')
        I.draw(p, cur[1], cx, cy, 20, 'primary')
        for side, k in ((-1, (self.focus - 1) % n), (1, (self.focus + 1) % n)):
            sx = cx + side * 104
            p.circle(sx, cy, 18, 'faint')
            I.draw(p, items[k][1], sx, cy, 9, 'muted')
        p.text_center(cx, 144, fit(cur[0], 2, VIS_W - 8), 2, 'primary')
        p.text_center(cx, 186, fit(cur[2], 1, VIS_W - 8), 1, 'secondary')
        x0 = cx - (n - 1) * 7
        for i in range(n):
            p.circle(x0 + i * 14, 226, 3 if i == self.focus else 2, 'accent' if i == self.focus else 'muted', True)


class Inbox(ListScreen):
    hint_key = 'hint.inbox'
    rows_per_page, row_h = 2, 66

    def title(self, ctx):
        return ctx.tr('menu.messages')

    def items(self, ctx):
        return ctx.inbox.list() if ctx.inbox else []

    def empty_text(self, ctx):
        return ctx.tr('inbox.empty')

    def row(self, p, n, x, y, focused, ctx):
        I.badge(p, x + 10, y + 30, 13, n['letter'], 'accent' if focused else 'muted', 1)
        when = ago(n['time'], ctx)
        ww = p.text_right(VIS_X1 - 10, y + 4, when, 0, 'muted')
        p.text(x + 32, y + 4, fit(n['sender'], 1, VIS_X1 - x - 52 - ww), 1, 'primary' if focused else 'secondary')
        text = ctx.tr('inbox.privacy_hidden') if n.get('text') == 'New message' else n['text']
        p.text(x + 32, y + 30, fit(text, 1, VIS_X1 - x - 42), 1, 'secondary' if focused else 'muted')
        if not n.get('read'):
            p.circle(x - 6, y + 30, 3, 'accent', True)

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
        I.badge(p, VIS_X0 + 14, HEAD_Y + 12, 13, n['letter'], 'accent')
        ww = p.text_right(VIS_X1, HEAD_Y, ago(n['time'], ctx), 0, 'muted')
        p.text(VIS_X0 + 34, HEAD_Y, fit(n['app'], 0, VIS_W - 44 - ww), 0, 'accent')
        p.text(VIS_X0, 60, fit(n['sender'], 2, VIS_W), 2, 'primary')
        text = ctx.tr('inbox.privacy_hidden') if n.get('text') == 'New message' else n['text']
        for i, line in enumerate(wrap(text, 1, VIS_W, 4)):
            p.text(VIS_X0, 100 + i * 26, line, 1, 'secondary')
        hint(p, hint_key(ctx, 'hint.message'))


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
        app = fit(ctx.tv_app, 1, 110)
        aw = p.text_right(VIS_X1, HEAD_Y + 8, app, 1, 'muted') if app else 0
        text_fit(p, VIS_X0, HEAD_Y + 19, ctx.tv_name, (2, 1), VIS_W - aw - 10)
        tw = (VIS_W - 8) // 2
        for i, (key, icon) in enumerate(self.TILES):
            col, row = i % 2, i // 2
            x0, y0 = VIS_X0 + col * (tw + 8), BODY_Y + row * 44
            f = i == self.focus
            p.round_rect(x0, y0, x0 + tw, y0 + 40, 12, 'accent' if f else 'faint')
            I.draw(p, icon, x0 + 20, y0 + 20, 9, 'primary' if f else 'muted')
            p.text(x0 + 38, y0 + 8, fit(ctx.tr(key), 1, tw - 46), 1, 'primary' if f else 'muted')
        hint(p, hint_key(ctx, 'hint.select'))
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
        cx, cy, r = VIS_CX, 118, 66
        p.arc(cx, cy, r, 135, 405, 'faint')
        v = ctx.tv_volume
        if v is not None:
            end = 135 + int(270 * max(0, min(100, v)) / 100)
            p.arc(cx, cy, r, 135, end, 'accent')
            p.arc(cx, cy, r - 3, 135, end, 'accent')
            p.text_center(cx, cy - 34, str(v), 3, 'primary')
        else:
            p.text_center(cx, cy - 34, '- -', 3, 'muted')
        p.text_center(cx, cy + 34, fit(ctx.tr('tv.volume_label'), 0, 110), 0, 'muted')
        for i, (bx, ic) in enumerate(((VIS_X0 + 26, 'minus'), (VIS_X1 - 26, 'plus'))):
            f = i == self.focus
            p.circle(bx, cy + 10, 24, 'accent' if f else 'faint')
            I.draw(p, ic, bx, cy + 10, 14, 'primary' if f else 'muted')
        hint(p, hint_key(ctx, 'hint.switch'))
        banner(p, ctx)


class AppsScreen(ListScreen):
    def title(self, ctx):
        return ctx.tr('tv.apps')

    def items(self, ctx):
        return TV_APPS

    def row(self, p, item, x, y, focused, ctx):
        I.apps(p, x + 10, y + 20, 9, 'accent' if focused else 'muted')
        on = ctx.tv_app and ctx.tv_app.lower() == item[0].lower()
        if on:
            p.circle(VIS_X1 - 16, y + 20, 5, 'ok', True)           # 'on screen' dot
        text_fit(p, x + 32, y + 20, item[0], (2, 1), VIS_X1 - x - 42 - (20 if on else 0), 'primary' if focused else 'secondary')

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
        p.text(VIS_X0, HEAD_Y, fit(ctx.tr('tv.remote'), 2, VIS_W), 2, 'primary')
        cx, cy, d = 92, 140, 46
        for i, (name, dx, dy) in enumerate(self.KEYS[:5]):
            x, y = cx + dx * d, cy + dy * d
            f = i == self.focus
            p.circle(x, y, 20 if name != 'ok' else 23, 'accent' if f else 'faint')
            tone = 'primary' if f else 'muted'
            if name == 'ok':
                p.text_center(x, y - 12, 'OK', 1, tone)
            else:
                ang = {'up': -90, 'right': 0, 'down': 90, 'left': 180}[name]
                ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                tx, ty = x + ux * 8, y + uy * 8
                p.line(tx, ty, x - ux * 4 - uy * 8, y - uy * 4 + ux * 8, tone)
                p.line(tx, ty, x - ux * 4 + uy * 8, y - uy * 4 - ux * 8, tone)
        for j, (name, key, icon) in enumerate((('back', 'tv.back', 'back'), ('home', 'tv.home', 'home'))):
            i = 5 + j
            y = BODY_Y + 8 + j * 66
            f = i == self.focus
            p.round_rect(180, y, VIS_X1, y + 58, 12, 'accent' if f else 'faint')
            I.draw(p, icon, 232, y + 18, 9, 'primary' if f else 'muted')
            p.text_center(232, y + 30, fit(ctx.tr(key), 0, VIS_X1 - 188), 0, 'primary' if f else 'muted')
        hint(p, hint_key(ctx, 'hint.remote'))
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
        cx, cy = VIS_CX, 76
        tone = {'listening': 'accent', 'thinking': 'warn', 'done': 'ok', 'failed': 'alert'}.get(st, 'muted')
        I.mic(p, cx, cy, 18, 'primary' if st != 'idle' else 'secondary')
        p.circle(cx, cy, 32, tone)
        if st == 'listening':
            for k in range(int(ctx.clock() * 3) % 3 + 1):
                p.circle(cx, cy, 38 + k * 7, 'accent_dim')
        label = ctx.tr({'idle': 'voice.idle', 'listening': 'voice.listening', 'thinking': 'voice.thinking',
                        'done': 'voice.done', 'failed': 'voice.failed'}[st])
        if st == 'idle':
            for i, line in enumerate(wrap(label, 1, VIS_W, 2)):
                p.text_center(cx, 116 + i * 26, line, 1, 'secondary')
        else:
            text_fit(p, cx, 132, label, (2, 1), VIS_W, 'primary', 'center')
        heard = v.get('text') or ''
        for i, line in enumerate(wrap('"%s"' % heard if heard else '', 1, VIS_W, 2)):
            p.text_center(cx, 160 + i * 24, line, 1, 'secondary')
        if v.get('result'):
            p.text_center(cx, HINT_Y, fit(v['result'], 0, VIS_W), 0, 'ok' if st == 'done' else 'alert')
        elif st == 'idle':
            for i, line in enumerate(wrap(ctx.tr('voice.try'), 0, VIS_W, 2)):
                p.text_center(cx, 182 + i * 24, line, 0, 'muted')


ORACLE_LINES_PER_PAGE, ORACLE_FONT, ORACLE_WIDTH = 3, 2, 270


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
        p.text(VIS_X0, VIS_Y0, badge, 1, badge_tone)
        if st != 'listening':
            lat_tone = 'ok' if lat < 600 else 'warn' if lat < 2000 else 'alert'
            p.text_right(VIS_X1, VIS_Y0, f'{lat}ms', 1, lat_tone)
        p.line(VIS_X0, 30, VIS_X1, 30, 'faint')

        # Heard transcript (one line)
        heard = v.get('text') or o.get('transcript') or ''
        if heard:
            p.text(VIS_X0, 34, fit('> ' + heard, 1, VIS_W), 1, 'secondary')
        p.line(VIS_X0, 62, VIS_X1, 62, 'faint')

        # Answer body: large font, 4 lines per page; a wave shows the next page
        pages = self._pages(ctx)
        self.page = min(self.page, len(pages) - 1)
        if st == 'listening':
            p.text_center(VIS_CX, 110, '...', 2, 'accent')
        elif pages[self.page]:
            ans_tone = 'ok' if qclass != 'LOCATE' else 'primary'
            for i, ln in enumerate(pages[self.page]):
                p.text(VIS_X0, 68 + i * 40, ln, ORACLE_FONT, ans_tone)
            if len(pages) > 1:
                p.text_right(VIS_X1, HINT_Y, '%d/%d' % (self.page + 1, len(pages)), 1, 'accent')

        # Footer: where the answer came from
        src = str(o.get('source') or '').upper()
        if src:
            p.text(VIS_X0, HINT_Y, fit(src, 0, 150), 0, 'muted')


class SettingsScreen(ListScreen):
    def title(self, ctx):
        return ctx.tr('menu.settings')

    def items(self, ctx):
        mode = getattr(ctx.inbox, 'privacy', 'full') if ctx.inbox else 'full'
        return [(ctx.tr('settings.language_value', lang=NATIVE_NAMES.get(ctx.lang, ctx.lang)), 'lang'),
                (ctx.tr('settings.message_text', mode=ctx.tr('settings.mode.' + mode)), 'privacy'),
                (ctx.tr('settings.clear'), 'clear'), (ctx.tr('settings.calibrate'), 'calibrate')]

    def row(self, p, item, x, y, focused, ctx):
        p.text(x, y + 8, fit(item[0], 1, VIS_X1 - x - 10), 1, 'primary' if focused else 'secondary')

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
        p.rect(VIS_X0 - 8, VIS_Y0, VIS_X1 + 6, VIS_Y1, 'muted')
        p.line(VIS_X0, 12, VIS_X0 + 50, 12, 'accent')
        p.line(VIS_X0, 12, VIS_X0, 62, 'accent')
        p.line(VIS_X0, 12, VIS_X0 + 56, 68, 'accent')
        p.text(VIS_X0 + 64, 16, fit(ctx.tr('calib.top_left'), 1, VIS_W - 64), 1, 'accent')
        for i, line in enumerate(wrap(ctx.tr('calib.question'), 1, VIS_W, 2)):
            p.text_center(VIS_CX, 96 + i * 26, line, 1, 'primary')
        for i, line in enumerate(wrap(ctx.tr('calib.fix'), 0, VIS_W, 2)):
            p.text_center(VIS_CX, 152 + i * 24, line, 0, 'secondary')
        p.text_right(VIS_X1, VIS_Y1 - 26, ctx.tr('calib.bottom_right'), 0, 'muted')


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
    p.text(x, y, fit(label, 0, width), 0, 'muted')
    p.text(x, y + 24, fit(value, 2, width), 2, tone)


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
        hr, zone = s.get('heart_rate'), s.get('hr_zone')
        hr_w = 0
        if hr is not None:
            ztone = {5: 'alert', 4: 'warn'}.get(zone, 'accent')
            hr_w = p.text_right(VIS_X1, 44, str(int(hr)), 2, 'primary')
            I.heart(p, VIS_X1 - hr_w - 14, 62, 8, ztone)
            if zone:
                p.text_right(VIS_X1, 84, 'Z%d' % zone, 0, ztone)
            hr_w += 26
        p.text(VIS_X0, 32, fit(label, 0, 150), 0, 'muted')
        room = VIS_W - hr_w - text_width(unit, 0) - 10
        f = best_font(big, (5, 4, 3), room)
        w = text_fit(p, VIS_X0, 92, big, (f,), room)
        p.text(VIS_X0 + w + 6, 92 + FONTS[f][0] // 2 - 24, unit, 0, 'secondary')
        p.line(VIS_X0, 140, VIS_X1, 140, 'faint')
        half = VIS_W // 2
        _metric(p, VIS_X0, 144, ctx.tr('hud.metric.distance'), fmt_distance(s.get('distance_m'), ctx.units, ctx.lang),
                width=half - 6)
        _metric(p, VIS_X0 + half, 144, ctx.tr('hud.metric.time'), fmt_duration(s.get('elapsed_s')), width=half)
        third = (ctx.tr('hud.metric.power'), '%d W' % s['power']) if s.get('power') is not None else \
                (ctx.tr('hud.metric.cadence'), '%d' % s['cadence']) if s.get('cadence') is not None else \
                (ctx.tr('hud.metric.lap'), fmt_duration(s.get('lap_s')) if s.get('lap_s') else '-')
        line = '%s %s' % (third[0], third[1])
        if s.get('lap_n'):
            line += '   %s %d %s' % (ctx.tr('hud.metric.lap'), s['lap_n'], fmt_duration(s.get('last_lap_s')))
        p.text(VIS_X0, HINT_Y, fit(line, 0, VIS_W), 0, 'secondary')
        event_card(p, ctx)


class NavScreen(Screen):
    """Arrow + distance + one short instruction (spec §5.3). Off route: the arrow turns red and says so."""

    def render(self, p, ctx):
        s = ctx.sport or {}
        nav = s.get('nav') or {}
        status_bar(p, ctx)
        if not nav:
            p.text_center(VIS_CX, 110, ctx.tr('common.unavailable'), 2, 'muted', width=VIS_W)
            return
        if nav.get('arrived'):
            I.flag(p, VIS_CX, 84, 28, 'ok')
            p.text_center(VIS_CX, 130, ctx.tr('hud.navigation.arrival'), 2, 'ok', width=VIS_W)
            return
        off = nav.get('off_route')
        turn = nav.get('next_turn') or {'direction': 'straight', 'in_m': nav.get('remaining_m')}
        direction = turn['direction']
        tone = 'alert' if off else 'accent'
        cx, cy = VIS_X0 + 48, 96
        p.circle(cx, cy, 46, tone)
        if direction == 'u_turn':
            I.u_turn(p, cx, cy, 30, 'primary')
        else:
            I.arrow(p, cx, cy, 32, DIRECTION_ANGLE.get(direction, 0), 'primary')
        tx, tw = VIS_X0 + 106, VIS_X1 - VIS_X0 - 106
        if off:
            label = ctx.tr('hud.navigation.off_route')
            for i, line in enumerate(wrap(label, 1, tw, 2)):
                p.text(tx, 40 + i * 24, line, 1, 'alert')
            p.text(tx, 92, fit(fmt_distance(nav.get('off_by_m'), ctx.units, ctx.lang), 2, tw), 2, 'primary')
        else:
            dist = fmt_distance(turn.get('in_m'), ctx.units, ctx.lang)
            size = 3 if text_width(dist, 3) <= tw else 2
            p.text(tx, 46 if size == 3 else 58, fit(dist, size, tw), size, 'primary')
            p.text(tx, 114, fit(ctx.tr('hud.dir.' + direction), 1, tw), 1, 'secondary')
        p.line(VIS_X0, 150, VIS_X1, 150, 'faint')
        eta_txt = ''
        if nav.get('eta_s') is not None:
            eta = time.localtime(ctx.clock() + nav['eta_s'])
            eta_txt = ctx.tr('hud.navigation.eta', time='%02d:%02d' % (eta.tm_hour, eta.tm_min))
        p.text(VIS_X0, 156, fit(ctx.tr('hud.navigation.remaining', distance=fmt_distance(nav.get('remaining_m'), ctx.units, ctx.lang)),
                                1, VIS_W), 1, 'secondary')
        if eta_txt:
            p.text(VIS_X0, 182, fit(eta_txt, 1, VIS_W), 1, 'secondary')
        poi = nav.get('nearest_poi')
        if poi and poi.get('distance_m', 1e9) < 2000:
            p.text(VIS_X0, 208, fit('%s - %s' % (poi['name'], fmt_distance(poi['distance_m'], ctx.units, ctx.lang)), 1, VIS_W), 1, 'accent')
        event_card(p, ctx)


class GhostScreen(Screen):
    """Gap to the ghost in seconds (green ahead, amber behind) and both positions on one line."""

    def render(self, p, ctx):
        s = ctx.sport or {}
        g = s.get('ghost') or {}
        status_bar(p, ctx)
        I.ghost(p, VIS_X0 + 12, 46, 11, 'muted')
        p.text(VIS_X0 + 30, 34, fit(g.get('ghost_name') or ctx.tr('hud.sport.ghost'), 1, VIS_W - 30), 1, 'secondary')
        gap = g.get('gap_s')
        if gap is None:
            p.text_center(VIS_CX, 66, '-', 5, 'muted')
        else:
            ahead = gap >= 0
            tone = 'ok' if ahead else 'warn'
            txt = ('+' if ahead else '-') + fmt_duration(abs(gap))
            p.text_center(VIS_CX, 62, txt, 5 if text_width(txt, 5) <= VIS_W else 3, tone)
            key = 'hud.ghost.even' if abs(gap) < 1 else 'hud.ghost.ahead' if ahead else 'hud.ghost.behind'
            p.text_center(VIS_CX, 148, ctx.tr(key, gap=fmt_distance(abs(g.get('gap_m') or 0), ctx.units, ctx.lang)), 1, 'secondary', width=VIS_W)
        total = g.get('total_m') or 0
        if total:
            x0, x1, y = VIS_X0 + 8, VIS_X1 - 8, 188
            p.line(x0, y, x1, y, 'faint')
            for dist, tone, r in ((g.get('ghost_m') or 0, 'muted', 5), (s.get('distance_m') or 0, 'accent', 6)):
                x = x0 + (x1 - x0) * max(0, min(1, dist / total))
                p.circle(x, y, r, tone, True)
        if g.get('projected_finish_s'):
            p.text_center(VIS_CX, HINT_Y, ctx.tr('hud.ghost.projection', time=fmt_duration(g['projected_finish_s'])), 0, 'muted', width=VIS_W)
        event_card(p, ctx)


class WorkoutScreen(Screen):
    """Current step, what is left of it, target vs current pace, progress through the session."""

    def render(self, p, ctx):
        s = ctx.sport or {}
        w = s.get('workout') or {}
        status_bar(p, ctx)
        if not w:
            p.text_center(VIS_CX, 110, ctx.tr('common.unavailable'), 2, 'muted', width=VIS_W)
            return
        if w.get('done'):
            I.check(p, VIS_CX, 84, 28, 'ok')
            p.text_center(VIS_CX, 130, ctx.tr('hud.training.done'), 2, 'ok', width=VIS_W)
            return
        kind_tone = {'work': 'warn', 'recovery': 'ok'}.get(w.get('kind'), 'accent')
        sw = p.text_right(VIS_X1, HEAD_Y + 8, '%d/%d' % (w.get('n', 1), w.get('total', 1)), 1, 'muted')
        text_fit(p, VIS_X0, HEAD_Y + 19, ctx.tr('hud.training.' + w.get('kind', 'work')), (2, 1), VIS_W - sw - 10, kind_tone)
        unit, left = w.get('remaining') or ('s', None)
        big = fmt_duration(left) if unit == 's' else fmt_distance(left, ctx.units, ctx.lang)
        text_fit(p, VIS_CX, 116, big, (5, 4, 3), VIS_W, 'primary', 'center')
        tgt, cur = w.get('target_pace'), s.get('pace_s_per_km')
        if tgt:
            cw = 0
            if cur:
                tone = 'ok' if abs(cur - tgt) <= 5 else 'warn'
                cw = p.text_right(VIS_X1, 160, fmt_pace(cur, ctx.units), 2, tone)
            p.text(VIS_X0, 168, fit(ctx.tr('hud.training.target_pace', pace=fmt_pace(tgt, ctx.units)), 1, VIS_W - cw - 10), 1, 'secondary')
        n, total = w.get('n', 1), max(1, w.get('total', 1))
        p.rect(VIS_X0, 210, VIS_X1, 216, 'faint')
        p.rect(VIS_X0, 210, VIS_X0 + int(VIS_W * (n - 1) / total), 216, 'accent', True)
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
    """The glasses report single input events: a wave (ENGO 1/2 sensor) or, on the ENGO 3, a double tap on the temple
    (measured 26 Nov 2026: the hand wave does nothing there, each double tap arrives as one event).
    1 event = next, 2 within the window = ok, 3 = back. A double tap takes longer to repeat than a wave, hence the
    longer window for the ENGO 3 (TAP_WINDOW)."""
    WINDOW = 0.7
    TAP_WINDOW = 1.6

    def __init__(self, clock=time.monotonic, window=None):
        self.clock, self.count, self.last = clock, 0, 0.0
        self.window = self.WINDOW if window is None else window

    def wave(self):
        now = self.clock()
        self.count = self.count + 1 if now - self.last <= self.window else 1
        self.last = now

    def poll(self):
        """Call regularly; returns an event once the burst of waves is over."""
        if self.count and self.clock() - self.last > self.window:
            n, self.count = self.count, 0
            return {1: 'next', 2: 'ok'}.get(n, 'back')
        return None


# Home menu entry -> Companion module that hides it when switched off on the phone (Settings > Modules).
HOME_MODULE = {Inbox: 'messages', SportMenu: 'sport', TVHub: 'tv', VacuumScreen: 'vacuum'}
