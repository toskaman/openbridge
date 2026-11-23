"""Glasses hub: menus on the ENGO glasses, messages from the phone, TV and vacuum control, voice from the phone mic.

    phone (Companion)  --notifications, voice, buttons-->  PC hub  --ActiveLook frames-->  glasses (BLE) / HUD Studio
                                                            |
                                                            +--typed primitives through the gate--> TV, vacuum

Safety:
- Nothing acts without a standing grant the owner gives once on the PC (`openbridge glasses grant --consent ALLOW`),
  listing exactly which kinds of action the glasses may run. The grant plus one deliberate gesture, button press or
  voice command stands for consent to one action, like the remote controls on a watch.
- Every action is a typed primitive (device_action key / launch_app, tuya_command...) run by the Executor: allowlist,
  consent, read-back where the device can be read, receipt. Doors, garages and alarms are never reachable from here.
- Notifications stay in memory; only the apps the owner allowed are shown; a privacy mode hides the text.
"""
from __future__ import annotations

import json
import os
import queue
import socket
import struct
import threading
import time
from pathlib import Path

from src.glasses import ui
from src.glasses.events import Scheduler
from src.glasses.i18n import resolve, t
from src.glasses.notifications import DEFAULT_ALLOWED, Inbox

# What a grant can cover. Each maps to the exact primitive + params pattern it allows.
GRANTABLE = {
    'tv_remote': 'TV keys: arrows, OK, back, home, play/pause, volume up/down',
    'tv_apps': 'open an app on the TV',
    'tv_power': 'TV sleep / wake',
    'vacuum': 'robot vacuum: start, pause, dock, find',
}
TV_KEYS = {'up', 'down', 'left', 'right', 'ok', 'back', 'home', 'play_pause', 'volume_up', 'volume_down', 'mute'}
VAC_COMMANDS = {'start', 'pause', 'dock', 'seek'}


def settings_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'glasses.json'


def load_settings(path=None):
    try:
        return json.loads(Path(path or settings_path()).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_settings(data, path=None):
    p = Path(path or settings_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=1), encoding='utf-8')
    os.replace(tmp, p)


def grant_covers(grant, action: ui.Action):
    """True only when the owner's grant covers this exact action."""
    g = set(grant or ())
    if action.kind != 'device':
        return False
    p = action.params
    if action.device == 'tv' and action.primitive == 'device_action':
        if p.get('action') == 'key':
            return 'tv_remote' in g and p.get('args', {}).get('key') in TV_KEYS
        if p.get('action') == 'launch_app':
            return 'tv_apps' in g and p.get('args', {}).get('package') in {pkg for _, pkg in ui.TV_APPS}
        return False
    if action.device == 'tv' and action.primitive in ('tv_sleep', 'tv_wake'):
        return 'tv_power' in g and not p
    if action.device == 'vacuum' and action.primitive == 'tuya_command':
        return 'vacuum' in g and set(p) == {'command'} and p['command'] in VAC_COMMANDS
    return False


# ---------------------------------------------------------------- transports

class StudioLink:
    """HUD Studio phone port (TCP 7789): raw ActiveLook frames out, gesture frames (FF 0A 01 code AA) back."""

    def __init__(self, on_gesture, host='127.0.0.1', port=7789):
        self.on_gesture, self.addr = on_gesture, (host, port)
        self.sock = socket.create_connection(self.addr, timeout=5)
        self.sock.settimeout(None)
        threading.Thread(target=self._rx, daemon=True).start()

    def write(self, data: bytes):
        self.sock.sendall(data)

    def _rx(self):
        buf = b''
        while True:
            try:
                d = self.sock.recv(1024)
            except OSError:
                return
            if not d:
                return
            buf += d
            while b'\xff\x0a' in buf:
                i = buf.index(b'\xff\x0a')
                if len(buf) < i + 5:
                    break
                if buf[i + 4] == 0xAA:
                    self.on_gesture()
                buf = buf[i + 5:]

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class BleLink:
    """Real ENGO glasses over Bluetooth LE from this PC (optional dependency: bleak).

    Uses the transport core (src.glasses.transport): MTU-sized writes, no write while the glasses report PAUSE, newest
    screen wins, bounded queue; reconnects with a bounded back-off; holds the single-controller lock so the phone and
    the PC never drive the glasses at the same time (takeover=True is the owner's explicit switch)."""

    def __init__(self, on_gesture, address=None, name_hint='ENGO', takeover=False, on_status=None):
        import asyncio
        import os
        from src.adapters import activelook as AL
        from src.glasses.transport import Backoff, ControllerLock, Transport
        self.AL, self.on_gesture, self.on_status = AL, on_gesture, on_status or (lambda *a: None)
        self.lock = ControllerLock('pc:%d' % os.getpid())
        ok, holder = self.lock.acquire(takeover=takeover)
        if not ok:
            raise OSError('the glasses are driven by %s; use --takeover to switch to this PC' % holder.get('owner'))
        self._pending = []
        self._tlock = threading.Lock()
        self.tr = Transport(self._pending.append)
        self.backoff = Backoff()
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.error = None
        self.state = 'CONNECTING'
        threading.Thread(target=self._run, args=(address, name_hint), daemon=True).start()
        if not self.ready.wait(30):
            raise OSError(self.error or 'glasses not found over Bluetooth')
        if self.error and self.state != 'READY':
            raise OSError(self.error)

    def _run(self, address, name_hint):
        import asyncio
        asyncio.set_event_loop(self.loop)
        while True:
            try:
                self.loop.run_until_complete(self._main(address, name_hint))
                self.backoff.reset()
            except Exception as e:                   # noqa: BLE001 - reported, then a bounded retry
                self.error = '%s: %s' % (type(e).__name__, e)
            self.state = 'DISCONNECTED'
            self.on_status(self.state, self.error)
            delay = self.backoff.next_delay()
            if delay is None:
                self.ready.set()
                return
            time.sleep(delay)
            self.state = 'CONNECTING'

    async def _main(self, address, name_hint):
        import asyncio
        from bleak import BleakClient, BleakScanner
        if not address:
            dev = await BleakScanner.find_device_by_filter(
                lambda d, ad: (d.name or '').upper().startswith(name_hint.upper())
                or self.AL.SERVICE_UUID in [u.lower() for u in (ad.service_uuids or [])], timeout=20)
            if dev is None:
                raise OSError('no ENGO glasses advertising nearby (are they on, and not connected to a phone?)')
            address = dev.address
        async with BleakClient(address) as c:
            with self._tlock:
                self.tr.set_mtu(getattr(c, 'mtu_size', 23) or 23)
                self.tr.paused = False
            await c.start_notify(self.AL.FLOW_CHAR_UUID, lambda _, d: d and self._flow(d[0]))
            await c.start_notify(self.AL.GESTURE_CHAR_UUID, lambda _, d: self.on_gesture())
            self.state = 'READY'
            self.ready.set()
            self.on_status(self.state, None)
            beat = 0.0
            while c.is_connected:
                with self._tlock:
                    self.tr.pump(budget=8)
                    chunks, self._pending[:] = list(self._pending), []
                for ch in chunks:
                    await c.write_gatt_char(self.AL.RX_CHAR_UUID, ch, response=False)
                if time.time() - beat > 5:
                    self.lock.beat()
                    beat = time.time()
                await asyncio.sleep(0.01 if chunks else 0.03)

    def _flow(self, status):
        with self._tlock:
            self.tr.on_flow(status)

    def write(self, data: bytes):
        with self._tlock:
            self.tr.submit(data, 'screen')

    def close(self):
        self.lock.release()


class NullLink:
    def __init__(self):
        self.last = b''

    def write(self, data: bytes):
        self.last = data

    def close(self):
        pass


# ---------------------------------------------------------------- the hub

class Hub:
    def __init__(self, link=None, executor=None, devices=None, settings=None, colour=True, clock=time.time,
                 understand=None):
        """executor: object with execute(primitive, device_key, params, consent) -> receipt (the OpenBridge gate).
        devices: {'tv': key, 'vacuum': key}. understand(text) -> (skill_id, params) or None (voice)."""
        self.persist = settings is None
        self.settings = settings if settings is not None else load_settings()
        self.inbox = Inbox(allowed=self.settings.get('apps') or DEFAULT_ALLOWED,
                           privacy=self.settings.get('privacy', 'full'), clock=clock)
        app_lang, hud_lang = resolve(self.settings)
        self.ctx = ui.Context(inbox=self.inbox, clock=clock, lang=hud_lang, units=self.settings.get('units', 'metric'))
        self.scheduler = Scheduler(clock=clock)
        self.sport = None                 # live.SportEngine once a sport session starts
        self.menu = ui.Menu(self.ctx)
        self.gestures = ui.GestureDecoder()
        self.link = link or NullLink()
        self.executor, self.devices = executor, dict(devices or {})
        self.colour, self.clock = colour, clock
        self.understand = understand
        self.events = queue.Queue()
        self.log = []                     # last outcomes, for tests and `glasses status`
        self._last_frame = b''
        self._draw = threading.Lock()
        self.ctx.linked = bool(self.executor)

    # ---- sport
    def start_sport(self, sport='run', route=None, workout=None, ghost=None, max_hr=None):
        from src.glasses.live import SportEngine
        self.sport = SportEngine(sport, clock=self.clock, scheduler=self.scheduler, max_hr=max_hr,
                                 units=self.ctx.units, lang=self.ctx.lang)
        if route is not None:
            self.sport.set_route(route)
        if workout is not None:
            self.sport.set_workout(workout)
        if ghost is not None:
            self.sport.set_ghost(ghost)
        return self.sport

    # ---- inputs
    def wave(self):
        self.gestures.wave()

    def press(self, ev):
        self.events.put(ev)

    def notify(self, n):
        item = self.inbox.add(n)
        if item:
            self.ctx.toast = dict(self.inbox.shown(item), until=self.clock() + 6)
            self.redraw()
        return item

    # ---- actions
    def tr(self, key, **kw):
        return t(key, self.ctx.lang, **kw)

    def run(self, action: ui.Action):
        if action.kind == 'voice':
            self.ctx.voice = {'state': 'idle', 'text': '', 'result': self.tr('voice.idle')}
            return None
        if action.kind == 'ack':
            self.scheduler.ack()
            return None
        if action.kind == 'setting':                  # changed from the glasses Settings screen
            self.settings.update(action.params)
            if self.persist:
                save_settings(self.settings)
            return None
        if not grant_covers(self.settings.get('grant'), action):
            return self._outcome(False, self.tr('hud.action.not_allowed'), action)
        key = self.devices.get(action.device)
        if not key or not self.executor:
            return self._outcome(False, self.tr('hud.action.no_device', device=action.device), action)
        try:
            r = self.executor.execute(action.primitive, key, dict(action.params), consent=True)
        except Exception as e:                       # noqa: BLE001 - shown, never retried
            return self._outcome(False, self.tr('hud.action.failed', action=action.label), action, error=type(e).__name__)
        state = r.get('state')
        ok = bool(r.get('verified')) or state in ('VERIFIED', 'EXECUTED', 'EXECUTED_UNVERIFIED')
        if action.device == 'tv':
            self._absorb_tv(r)
            if ok:
                self.refresh_tv(force=True)
        if r.get('verified'):
            text = self.tr('hud.action.verified', action=action.label)
        elif ok:
            text = self.tr('hud.action.unverified', action=action.label) if state == 'EXECUTED_UNVERIFIED' else action.label
        else:
            text = action.label + ': ' + human_error(r, action.device, self.ctx.lang)
        return self._outcome(ok, text, action, receipt=r)

    def refresh_tv(self, force=False):
        """Read the TV's volume and the app on screen (read-only actions, no change), at most every 10 s."""
        key = self.devices.get('tv')
        if not key or not self.executor or not set(self.settings.get('grant') or ()) & {'tv_remote', 'tv_apps', 'tv_power'}:
            return False
        now = self.clock()
        if not force and now - getattr(self, '_tv_read_at', 0) < 10:
            return False
        self._tv_read_at = now
        for what in ('audio_state', 'screen_state'):
            try:
                self._absorb_tv(self.executor.execute('device_action', key, {'action': what}, consent=True))
            except Exception:                        # noqa: BLE001 - a failed read only leaves the old value
                return False
        return True

    def _absorb_tv(self, r):
        res = r.get('result') or {}
        if isinstance(res, dict) and isinstance(res.get('volume_index'), int) and res.get('max_index'):
            self.ctx.tv_volume = round(100 * res['volume_index'] / res['max_index'])
        scr = res.get('screen') or res if isinstance(res, dict) else {}
        if isinstance(scr, dict):
            app = scr.get('focused_app') or scr.get('app') or scr.get('package')
            if app:
                self.ctx.tv_app = next((lbl for lbl, pkg in ui.TV_APPS if pkg == app), str(app).rsplit('.', 1)[-1])
        if isinstance(r.get('after'), int):
            self.ctx.tv_volume = r['after']

    def _outcome(self, ok, text, action, **extra):
        self.ctx.banner = {'ok': ok, 'text': text, 'until': self.clock() + 2.5}
        entry = dict(ok=ok, text=text, action=action.label, at=self.clock(), **extra)
        self.log.append(entry)
        del self.log[:-100]
        return entry

    def voice(self, text):
        """A transcript from the phone mic: understand it, run it if the grant covers it, show each step."""
        self.ctx.voice = {'state': 'thinking', 'text': text}
        if not isinstance(self.menu.screen, ui.VoiceScreen):
            self.menu.stack.append(ui.VoiceScreen())
        self.redraw()
        got = self.understand(text) if self.understand else None
        action = voice_action(got, self.ctx.lang) if got else None
        if action is None:
            self.ctx.voice = {'state': 'failed', 'text': text, 'result': self.tr('voice.not_understood')}
            self.redraw()
            return None
        out = self.run(action)
        self.ctx.voice = {'state': 'done' if out['ok'] else 'failed', 'text': text, 'result': out['text']}
        self.redraw()
        return out

    # ---- loop
    def redraw(self, force=False):
        with self._draw:                  # voice runs on another thread: frames never interleave on the link
            frame = self.menu.render(colour=self.colour, rotate180=bool(self.settings.get('rotate180'))).to_bytes()
            if force or frame != self._last_frame:
                self.link.write(frame)
                self._last_frame = frame
        return frame

    def tick(self):
        ev = self.gestures.poll()
        if ev:
            self.events.put(ev)
        if isinstance(self.menu.screen, (ui.TVHub, ui.VolumeScreen, ui.AppsScreen, ui.RemoteScreen)):
            self.refresh_tv()
        acted = False
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            action = self.menu.handle(ev)
            if action:
                self.run(action)
            acted = True
        if self.ctx.toast and self.ctx.toast['until'] < self.clock():
            self.ctx.toast = None
            acted = True
        if self.sport is not None:
            self.ctx.sport = self.sport.snapshot()
        self.ctx.event = self.scheduler.tick()
        self.redraw(force=False)
        return acted


def human_error(receipt, device, lang='en'):
    """One short line the wearer understands, instead of an error code."""
    e = (receipt.get('errors') or [receipt.get('state') or 'failed'])[0]
    name = t('menu.' + device, lang) if device in ('tv', 'vacuum') else device
    if 'DEVICE_UNAVAILABLE' in e or 'NOT_LINKED' in e or 'No live' in e:
        return t('hud.action.not_reachable', lang, device=name)
    if 'CONSENT' in e or 'BLOCKED' in e:
        return t('hud.action.refused', lang, action='').strip(' :')
    if 'RECOVERY' in e or 'CONCURRENT' in e:
        return t('hud.action.busy', lang)
    return e.split(':')[0].replace('_', ' ').lower()[:30]


def voice_action(got, lang='en'):
    """(skill_id, params) from the command model -> the glasses action it means, or None."""
    sid, p = got
    p = p or {}
    if sid == 'tv_volume_step' and p.get('direction') in ('up', 'down'):
        return ui.tv_key('volume_' + p['direction'], t('tv.volume_' + p['direction'], lang))
    if sid == 'app_launch':
        label = next((lbl for lbl, pkg in ui.TV_APPS if pkg == p.get('package')), None)
        if label:
            return ui.Action('device', t('tv.open_app', lang, app=label), 'tv', 'device_action',
                             {'action': 'launch_app', 'args': {'package': p['package']}})
    if sid in ('vacuum.start', 'vacuum.pause', 'vacuum.dock', 'vacuum.seek'):
        cmd = sid.split('.')[1]
        return ui.vac(cmd, t('vac.' + cmd, lang))
    return None
