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
            for pkt in (self.AL.encode_packet(0x20, b'\x01'), self.AL.cmd_gesture_enable(True)):
                await c.write_gatt_char(self.AL.RX_CHAR_UUID, pkt, response=False)
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


class PhoneLink:
    """ENGO glasses over the phone's Bluetooth, for a PC without Bluetooth.

    The paired Companion holds the Bluetooth connection (relay ops glasses_*); this PC only sends ActiveLook frame
    chunks over the signed, encrypted relay channel and receives the gesture and flow-control notifications. Same
    transport core as BleLink: MTU-sized chunks, nothing written while the glasses say PAUSE, newest screen wins,
    single controller (takeover=True is the owner's explicit switch), bounded reconnect back-off.

    send(op, params) -> reply params: one signed relay call to the phone (CompanionCommands._send)."""

    BATCH_BYTES, BATCH_CHUNKS = 4096, 60

    def __init__(self, on_gesture, send, address=None, takeover=False, on_status=None, connect_seconds=8,
                 on_touch=None):
        import os
        from src.glasses.transport import Backoff, ControllerLock, Transport
        self.on_gesture, self.send = on_gesture, send
        self.on_touch = on_touch or on_gesture          # tap on the temple (ENGO 3); defaults to a wave
        self.on_button = lambda ev: None                # set by the hub owner: Next / Open / Back / Home on the phone
        self.on_resumed = lambda: None                  # the phone's standalone mode handed the glasses back: redraw
        self.on_status = on_status or (lambda *a: None)
        self.address, self.connect_seconds = address, connect_seconds
        self.lock = ControllerLock('pc-via-phone:%d' % os.getpid())
        ok, holder = self.lock.acquire(takeover=takeover)
        if not ok:
            raise OSError('the glasses are driven by %s; use --takeover to switch to this PC' % holder.get('owner'))
        self._pending = []
        self._tlock = threading.Lock()
        self.tr = Transport(self._pending.append)
        self.backoff = Backoff()
        self.state, self.error, self.info = 'CONNECTING', None, {}
        self.stats = {'batches': 0, 'rejected': 0, 'gestures': 0, 'reconnects': 0}
        self._stop = threading.Event()
        try:
            self._connect()                      # first connection is synchronous: a clear error if it fails
        except BaseException:
            self.lock.release()                  # a failed start must not keep the glasses locked
            raise
        threading.Thread(target=self._writer, name='glasses-phone-tx', daemon=True).start()
        threading.Thread(target=self._events, name='glasses-phone-rx', daemon=True).start()

    def _connect(self):
        import base64
        params = {'seconds': self.connect_seconds, 'name_hint': 'ENGO'}
        if self.address:
            params['address'] = self.address
        info = self.send('glasses_connect', params)
        if info.get('state') != 'READY':
            raise OSError('glasses: %s' % (info.get('error') or info.get('state')))
        self.info = info
        self.address = info.get('address') or self.address     # reconnect straight to the same pair, no scan
        with self._tlock:
            self.tr.set_mtu(int(info.get('mtu') or 23))
            self.tr.paused = False
        self.state, self.error = 'READY', None
        self.backoff.reset()
        # Gesture sensor and touch on: ActiveLook commands 0x20 (sensor) and 0x21 (gesture), both 'on'. The ENGO app
        # may have switched them off; they are what lets a wave or a tap drive the menus.
        try:
            from src.adapters.activelook import encode_packet
            self.send('glasses_write', {'chunks': [base64.b64encode(encode_packet(0x20, b'\x01')).decode('ascii'),
                                                   base64.b64encode(encode_packet(0x21, b'\x01')).decode('ascii')]})
        except Exception:                            # noqa: BLE001 - menus still work from the phone and the PC
            pass
        self.on_status(self.state, None)

    def _lost(self, why):
        if self.state != 'READY':
            return
        self.state, self.error = 'DISCONNECTED', str(why)[:200]
        self.on_status(self.state, self.error)

    def _handle(self, events):
        for e in events or ():
            t = e.get('t') if isinstance(e, dict) else None
            if t in ('gesture', 'touch'):          # hand wave, or tap on the temple
                self.stats['gestures'] += 1
                try:
                    (self.on_touch if t == 'touch' else self.on_gesture)()
                except Exception:                    # noqa: BLE001 - a UI error must not kill the link
                    pass
            elif t == 'button' and e.get('v') in ('next', 'ok', 'back', 'home'):
                try:
                    self.on_button(e['v'])
                except Exception:                    # noqa: BLE001
                    pass
            elif t == 'flow':
                with self._tlock:
                    self.tr.on_flow(int(e.get('v', 0)))
            elif t == 'state' and e.get('v') == 'DISCONNECTED':
                self._lost('glasses disconnected from the phone')
            elif t == 'state' and e.get('v') == 'RESUMED':
                try:
                    self.on_resumed()
                except Exception:                    # noqa: BLE001
                    pass

    def _batch(self):
        with self._tlock:
            self.tr.pump(budget=self.BATCH_CHUNKS)
            chunks, self._pending[:] = list(self._pending), []
        out, size = [], 0
        for c in chunks:
            if out and (size + len(c) > self.BATCH_BYTES or len(out) >= self.BATCH_CHUNKS):
                yield out
                out, size = [], 0
            out.append(c)
            size += len(c)
        if out:
            yield out

    def _writer(self):
        import base64
        beat = 0.0
        while not self._stop.is_set():
            if self.state != 'READY':
                delay = self.backoff.next_delay()
                if delay is None:
                    self.on_status('GAVE_UP', self.error)
                    return
                self._stop.wait(delay)
                try:
                    self.stats['reconnects'] += 1
                    self._connect()
                except Exception as e:               # noqa: BLE001 - reported, bounded retry
                    self.error = '%s: %s' % (type(e).__name__, e)
                continue
            sent = False
            for batch in self._batch():
                sent = True
                try:
                    r = self.send('glasses_write', {'chunks': [base64.b64encode(c).decode('ascii') for c in batch]})
                except Exception as e:               # noqa: BLE001 - relay down: reconnect path
                    self._lost(e)
                    break
                self.stats['batches'] += 1
                if int(r.get('accepted', 0)) < len(batch):
                    self.stats['rejected'] += len(batch) - int(r.get('accepted', 0))
                    if r.get('state') != 'READY':
                        self._lost(r.get('error') or 'write refused')
                        break
                self._handle(r.get('events'))
            if time.time() - beat > 5:
                self.lock.beat()
                beat = time.time()
            self._stop.wait(0.01 if sent else 0.03)

    def _events(self):
        while not self._stop.is_set():
            if self.state != 'READY':
                self._stop.wait(0.3)
                continue
            try:
                r = self.send('glasses_events', {'wait_ms': 800})
            except Exception:                        # noqa: BLE001 - the writer handles reconnects
                self._stop.wait(0.5)
                continue
            if r.get('state') not in ('READY', None):
                self._lost(r.get('error') or r.get('state'))
            self._handle(r.get('events'))

    def write(self, data: bytes):
        with self._tlock:
            self.tr.submit(data, 'screen')

    def close(self):
        self._stop.set()
        try:
            self.send('glasses_disconnect', {})
        except Exception:                            # noqa: BLE001 - phone already gone
            pass
        self.lock.release()


class MirrorLink:
    """Sends every frame to the real glasses and, unchanged, to HUD Studio on the PC: what the glasses were sent,
    drawn on screen. A mirror failure never affects the glasses."""

    def __init__(self, main, mirror):
        self.main, self.mirror = main, mirror
        self.tr = getattr(main, 'tr', None)

    def write(self, data: bytes):
        self.main.write(data)
        if self.mirror is not None:
            try:
                self.mirror.write(data)
            except OSError:
                self.mirror = None

    def close(self):
        for link in (self.main, self.mirror):
            if link is not None:
                link.close()


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
        self._auto_open_at = None                       # any explicit input cancels the pending auto-open

    AUTO_OPEN_S = 3.0

    def tap_next(self):
        """ENGO 3 double tap: next item; on the home carousel the item opens by itself after AUTO_OPEN_S."""
        self.events.put('next')
        self._auto_open_at = self.clock() + self.AUTO_OPEN_S if isinstance(self.menu.screen, ui.Home) else None

    def _auto_open(self):
        at = getattr(self, '_auto_open_at', None)
        if at is not None and self.clock() >= at:
            self._auto_open_at = None
            if isinstance(self.menu.screen, ui.Home):  # only the home carousel: opening a menu, never an action
                self.events.put('ok')

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

    def oracle(self, text: str, answer_data: dict, partial: bool = False):
        """Display a real-time VoiceAI Oracle answer (or live listening echo) on the glasses."""
        self.ctx.voice = {
            'state': 'listening' if partial else 'done',
            'text': text,
            'result': answer_data.get('answer', ''),
            'oracle': dict(answer_data),
        }
        if not isinstance(self.menu.screen, ui.OracleScreen):
            self.menu.stack.append(ui.OracleScreen())
        self.menu.screen.page = 0                         # a new answer starts on its first page
        return self.redraw(force=True)

    # ---- full ENGO 3 hardware + HUD controls
    _SCREENS = {
        'home': lambda: ui.Home(),
        'inbox': lambda: ui.Inbox(),
        'sport': lambda: ui.SportMenu(),
        'tv': lambda: ui.TVHub(),
        'vacuum': lambda: ui.VacuumScreen(),
        'voice': lambda: ui.VoiceScreen(),
        'oracle': lambda: ui.OracleScreen(),
        'settings': lambda: ui.SettingsScreen(),
        'calibration': lambda: ui.Calibration(),
    }

    def open_screen(self, name: str):
        key = str(name or 'home').strip().lower()
        factory = self._SCREENS.get(key)
        if factory is None:
            raise ValueError(f'unknown screen: {key}')
        self._auto_open_at = None
        if key == 'home':
            self.menu.stack[1:] = []
        else:
            self.menu.stack = [self.menu.stack[0], factory()]
        if not self.settings.get('screen_on', True):
            self.apply_control('display_on')
        else:
            self.redraw(force=True)
        return key

    def control_summary(self) -> str:
        s = self.settings
        on = 'ON' if s.get('screen_on', True) else 'OFF'
        luma = int(s.get('luma', 10))
        priv = s.get('privacy', 'full')
        rot = ' 180' if s.get('rotate180') else ''
        return f'{on} · Lum {luma} · {priv}{rot}'

    def apply_control(self, op: str, value=None):
        """Execute a direct ENGO 3 hardware/display/navigation control."""
        from src.adapters import activelook as AL
        op_n = str(op or '').strip().lower()
        nav = {'next', 'prev', 'ok', 'back', 'home', 'up', 'down', 'left', 'right'}
        if op_n in nav:
            if not self.settings.get('screen_on', True):
                self.settings['screen_on'] = True
                self.link.write(AL.cmd_power(True))
            self.press(op_n)
            self.tick()
            return {'ok': True, 'op': op_n, 'screen': type(self.menu.screen).__name__, 'status': self.control_summary()}
        if op_n == 'open_screen':
            scr = self.open_screen(str(value or 'home'))
            return {'ok': True, 'op': op_n, 'screen': scr, 'status': self.control_summary()}
        ble_frames = bytearray()
        dirty = False
        msg = op_n
        if op_n in ('display_on', 'display_off', 'display_toggle'):
            cur = bool(self.settings.get('screen_on', True))
            nxt = True if op_n == 'display_on' else (False if op_n == 'display_off' else not cur)
            self.settings['screen_on'] = nxt
            dirty = True
            ble_frames += AL.cmd_power(nxt)
            if not nxt:
                ble_frames += AL.cmd_clear()
            msg = f"Display {'ON' if nxt else 'OFF'}"
        elif op_n == 'clear':
            ble_frames += AL.cmd_clear()
            self._last_frame = b''
            msg = 'Cleared OLED'
            if ble_frames:
                self.link.write(bytes(ble_frames))
            return {'ok': True, 'op': op_n, 'summary': msg, 'status': self.control_summary()}
        elif op_n in ('luma_up', 'luma_down', 'luma_set'):
            cur = int(self.settings.get('luma', 10))
            if op_n == 'luma_up':
                lvl = min(15, cur + 2)
            elif op_n == 'luma_down':
                lvl = max(0, cur - 2)
            else:
                lvl = max(0, min(15, int(value if value is not None else cur)))
            self.settings['luma'] = lvl
            dirty = True
            # Measured on the real ENGO 3 (27 Nov 2026): with ALS auto on, a
            # manual level has no visible effect, so a manual set takes manual
            # control (als_on re-enables auto afterwards).
            if self.settings.get('als', True):
                self.settings['als'] = False
                ble_frames += AL.cmd_als_enable(False)
                msg = f'Luma {lvl}/15 (ALS off)'
            else:
                msg = f'Luma {lvl}/15'
            ble_frames += AL.cmd_luma(lvl)
        elif op_n in ('als_on', 'als_off', 'als_toggle'):
            cur = bool(self.settings.get('als', True))
            nxt = True if op_n == 'als_on' else (False if op_n == 'als_off' else not cur)
            self.settings['als'] = nxt
            dirty = True
            ble_frames += AL.cmd_als_enable(nxt)
            msg = f"Auto-luma {'ON' if nxt else 'OFF'}"
        elif op_n in ('gesture_on', 'gesture_off', 'gesture_toggle'):
            cur = bool(self.settings.get('gesture', True))
            nxt = True if op_n == 'gesture_on' else (False if op_n == 'gesture_off' else not cur)
            self.settings['gesture'] = nxt
            dirty = True
            if nxt:
                ble_frames += AL.encode_packet(0x20, b'\x01')
            ble_frames += AL.cmd_gesture_enable(nxt)
            msg = f"Tap/Gesture {'ON' if nxt else 'OFF'}"
        elif op_n in ('rotate_on', 'rotate_off', 'rotate_toggle'):
            cur = bool(self.settings.get('rotate180', False))
            nxt = True if op_n == 'rotate_on' else (False if op_n == 'rotate_off' else not cur)
            self.settings['rotate180'] = nxt
            dirty = True
            msg = f"Rotate180 {'ON' if nxt else 'OFF'}"
        elif op_n in ('privacy_cycle', 'privacy_set'):
            order = ['full', 'sender', 'off']
            cur = self.settings.get('privacy', 'full')
            nxt = str(value) if (op_n == 'privacy_set' and str(value) in order) else order[(order.index(cur) + 1) % 3 if cur in order else 0]
            self.settings['privacy'] = nxt
            self.inbox.privacy = nxt
            dirty = True
            msg = f'Privacy {nxt}'
        elif op_n in ('lang_toggle', 'lang_set'):
            cur = self.ctx.lang
            nxt = str(value) if (op_n == 'lang_set' and str(value) in ('fr', 'en')) else ('en' if cur == 'fr' else 'fr')
            self.ctx.lang = nxt
            self.settings['hud_language'] = nxt
            dirty = True
            msg = f'Lang {nxt.upper()}'
        elif op_n in ('units_toggle', 'units_set'):
            cur = self.settings.get('units', 'metric')
            nxt = str(value) if (op_n == 'units_set' and str(value) in ('metric', 'imperial')) else ('imperial' if cur == 'metric' else 'metric')
            self.settings['units'] = nxt
            self.ctx.units = nxt
            if self.sport is not None:
                self.sport.units = nxt
            dirty = True
            msg = 'Units km' if nxt == 'metric' else 'Units mi'
        elif op_n in ('shift_left', 'shift_right', 'shift_up', 'shift_down', 'shift_reset'):
            sx = int(self.settings.get('shift_x', 0))
            sy = int(self.settings.get('shift_y', 0))
            if op_n == 'shift_left':
                sx -= 4
            elif op_n == 'shift_right':
                sx += 4
            elif op_n == 'shift_up':
                sy -= 4
            elif op_n == 'shift_down':
                sy += 4
            else:
                sx, sy = 0, 0
            sx, sy = max(-40, min(40, sx)), max(-40, min(40, sy))
            self.settings['shift_x'], self.settings['shift_y'] = sx, sy
            self.settings['x_offset'] = sx
            dirty = True
            ble_frames += AL.cmd_shift(sx, sy)
            msg = f'Shift {sx:+d},{sy:+d}'
        elif op_n == 'inbox_clear':
            self.inbox.clear()
            msg = 'Inbox cleared'
        elif op_n == 'status':
            msg = self.control_summary()
        else:
            raise ValueError(f'unsupported ENGO control: {op_n}')

        if dirty and self.persist:
            save_settings(self.settings)
        if ble_frames:
            self.link.write(bytes(ble_frames))
        if self.settings.get('screen_on', True) and op_n != 'status':
            self.ctx.banner = {'ok': True, 'text': msg, 'until': self.clock() + 2.0}
            self.redraw(force=True)
        return {'ok': True, 'op': op_n, 'summary': msg, 'status': self.control_summary()}

    # ---- loop
    def redraw(self, force=False):
        if not self.settings.get('screen_on', True):
            return b''
        with self._draw:                  # voice runs on another thread: frames never interleave on the link
            frame = self.menu.render(colour=self.colour, rotate180=bool(self.settings.get('rotate180')),
                                     x_offset=self.settings.get('x_offset')).to_bytes()
            if force or frame != self._last_frame:
                self.link.write(frame)
                self._last_frame = frame
        return frame

    def tick(self):
        self._auto_open()
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
