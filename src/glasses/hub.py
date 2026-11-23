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

    Writes go to the RX characteristic in chunks no larger than the negotiated MTU, pausing while the glasses'
    flow-control characteristic says their queue is above 75 %. Gesture notifications become waves."""
    MTU_CHUNK = 128

    def __init__(self, on_gesture, address=None, name_hint='ENGO'):
        import asyncio
        from src.adapters import activelook as AL
        self.AL, self.on_gesture = AL, on_gesture
        self.loop = asyncio.new_event_loop()
        self.paused = threading.Event()
        self.q = queue.Queue()
        self.ready = threading.Event()
        self.error = None
        threading.Thread(target=self._run, args=(address, name_hint), daemon=True).start()
        if not self.ready.wait(30):
            raise OSError(self.error or 'glasses not found over Bluetooth')
        if self.error:
            raise OSError(self.error)

    def _run(self, address, name_hint):
        import asyncio
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main(address, name_hint))
        except Exception as e:                       # noqa: BLE001 - reported to the caller
            self.error = '%s: %s' % (type(e).__name__, e)
            self.ready.set()

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
            chunk = max(20, min(self.MTU_CHUNK, (getattr(c, 'mtu_size', 23) or 23) - 3))

            def flow(_, data):
                if data:
                    (self.paused.set if data[0] == 0x02 else self.paused.clear)()

            await c.start_notify(self.AL.FLOW_CHAR_UUID, flow)
            await c.start_notify(self.AL.GESTURE_CHAR_UUID, lambda _, d: self.on_gesture())
            self.ready.set()
            while c.is_connected:
                try:
                    data = self.q.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.02)
                    continue
                for i in range(0, len(data), chunk):
                    while self.paused.is_set():
                        await asyncio.sleep(0.02)
                    await c.write_gatt_char(self.AL.RX_CHAR_UUID, data[i:i + chunk], response=False)

    def write(self, data: bytes):
        self.q.put(data)

    def close(self):
        pass


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
        self.settings = settings if settings is not None else load_settings()
        self.inbox = Inbox(allowed=self.settings.get('apps') or DEFAULT_ALLOWED,
                           privacy=self.settings.get('privacy', 'full'), clock=clock)
        self.ctx = ui.Context(inbox=self.inbox, clock=clock)
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
    def run(self, action: ui.Action):
        if action.kind == 'voice':
            self.ctx.voice = {'state': 'idle', 'text': '', 'result': 'Hold the mic button in the OpenBridge app'}
            return None
        if not grant_covers(self.settings.get('grant'), action):
            return self._outcome(False, 'Not allowed: openbridge glasses grant', action)
        key = self.devices.get(action.device)
        if not key or not self.executor:
            return self._outcome(False, 'No %s connected' % action.device, action)
        try:
            r = self.executor.execute(action.primitive, key, dict(action.params), consent=True)
        except Exception as e:                       # noqa: BLE001 - shown, never retried
            return self._outcome(False, '%s failed' % action.label, action, error=type(e).__name__)
        state = r.get('state')
        ok = bool(r.get('verified')) or state in ('VERIFIED', 'EXECUTED', 'EXECUTED_UNVERIFIED')
        if action.device == 'tv':
            self._absorb_tv(r)
            if ok:
                self.refresh_tv(force=True)
        text = action.label + (' ✓' if r.get('verified') else '' if ok else ': ' + human_error(r, action.device))
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
        action = voice_action(got) if got else None
        if action is None:
            self.ctx.voice = {'state': 'failed', 'text': text, 'result': 'Not something the glasses can do'}
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
        self.redraw(force=False)
        return acted


def human_error(receipt, device):
    """One short line the wearer understands, instead of an error code."""
    e = (receipt.get('errors') or [receipt.get('state') or 'failed'])[0]
    name = {'tv': 'TV', 'vacuum': 'Vacuum'}.get(device, device)
    if 'DEVICE_UNAVAILABLE' in e or 'NOT_LINKED' in e or 'No live' in e:
        return '%s not reachable' % name
    if 'CONSENT' in e or 'BLOCKED' in e:
        return 'refused'
    if 'RECOVERY' in e or 'CONCURRENT' in e:
        return 'busy, try again'
    return e.split(':')[0].replace('_', ' ').lower()[:30]


def voice_action(got):
    """(skill_id, params) from the command model -> the glasses action it means, or None."""
    sid, p = got
    p = p or {}
    if sid == 'tv_volume_step' and p.get('direction') in ('up', 'down'):
        return ui.tv_key('volume_' + p['direction'], 'Volume ' + p['direction'])
    if sid == 'app_launch':
        label = next((lbl for lbl, pkg in ui.TV_APPS if pkg == p.get('package')), None)
        if label:
            return ui.Action('device', 'Open ' + label, 'tv', 'device_action',
                             {'action': 'launch_app', 'args': {'package': p['package']}})
    if sid in ('vacuum.start', 'vacuum.pause', 'vacuum.dock', 'vacuum.seek'):
        cmd = sid.split('.')[1]
        return ui.vac(cmd, {'start': 'Start cleaning', 'pause': 'Pause vacuum', 'dock': 'Vacuum to dock',
                            'seek': 'Find vacuum'}[cmd])
    return None
