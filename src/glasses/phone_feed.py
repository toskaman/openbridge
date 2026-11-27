"""What the glasses hub exchanges with paired Companions besides the glasses link (Companion 0.15).

- Modules and profile (``get_status``, every 15 s): a module switched off on the phone hides its glasses menu.
- Device cards (``set_cards``, when they change): what the TV, the vacuum, the messages and the sport session are
  doing, for the Companion's Devices page. Display only.
- Phone sensors (``get_sensors``, once a second while a sport screen is open and the owner switched the Sensors
  module on): GPS fixes, compass, Bluetooth sport sensors held by the phone (decoded here with the same code as
  sensors connected to the PC), and a fall alert.
- Standalone sessions (``get_sessions``): sport sessions the phone recorded while the PC was away, saved here.

Every call goes through the signed, encrypted relay; a Companion that is offline or too old is skipped.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from src.fabric import relay as fabric_relay

# Phone sensor kind -> src.glasses.sensors kind
SENSOR_KINDS = {'heart_rate': 'heart_rate', 'rsc': 'rsc', 'csc': 'csc', 'power': 'cycling_power',
                'trainer': 'indoor_bike'}
STATUS_EVERY, CARDS_EVERY, SESSIONS_EVERY = 15.0, 10.0, 300.0


def sessions_dir() -> Path:
    import os
    base = Path(os.environ.get('OB_DATA_DIR') or Path.home() / '.openbridge')
    d = base / 'sport_sessions'
    d.mkdir(parents=True, exist_ok=True)
    return d


class PhoneFeed:
    def __init__(self, server, hub, lock, clock=time.time):
        self.server, self.hub, self.lock, self.clock = server, hub, lock, clock
        self._at = {}                         # (relay, what) -> last time
        self._cards_sent = {}                 # relay -> last cards json
        self._sensors = {}                    # (relay, kind) -> src.glasses.sensors.Sensor
        self._raw_at = {}                     # (relay, kind) -> last reading time already fed
        self._fix_at = {}                     # relay -> last GPS fix time already fed
        self._fall_seen = {}                  # relay -> fall already shown
        self.modules = {}                     # relay -> {module: bool}
        self.profile = {}                     # relay -> profile id
        self.saved_sessions = 0
        self._stop = threading.Event()

    # ---- plumbing
    def _relays(self):
        return getattr(getattr(self.server, 'relays', None), 'relays', None) or {}

    def _send(self, rid, op, params=None):
        from src.runtime.companion_commands import companion_commands
        return companion_commands(self.server)._send(rid, op, params)

    def _due(self, rid, what, every):
        now = self.clock()
        if now - self._at.get((rid, what), 0) < every:
            return False
        self._at[(rid, what)] = now
        return True

    def start(self):
        threading.Thread(target=self._loop, name='glasses-phone-feed', daemon=True).start()
        return self

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:                 # noqa: BLE001 - a phone going away never stops the hub
                pass
            self._stop.wait(1.0)

    # ---- one round
    def tick(self):
        for rid, r in list(self._relays().items()):
            if not r.get('online'):
                continue
            caps = r.get('capabilities', ()) or ()
            if 'modules' in caps and self._due(rid, 'status', STATUS_EVERY):
                self.read_status(rid)
            if 'cards' in caps and self._due(rid, 'cards', CARDS_EVERY):
                self.push_cards(rid)
            if 'cards' in caps and self._due(rid, 'sessions', SESSIONS_EVERY):
                self.pull_sessions(rid)
            if self.wants_sensors(rid):
                self.pull_sensors(rid)

    def read_status(self, rid):
        try:
            st = self._send(rid, 'get_status')
        except fabric_relay.RelayError:
            return
        mods = st.get('modules') if isinstance(st.get('modules'), dict) else {}
        self.modules[rid] = {k: bool(v) for k, v in mods.items()}
        self.profile[rid] = str(st.get('profile') or '')[:20]
        caps = st.get('capabilities') or []
        r = self._relays().get(rid)
        if r is not None and isinstance(caps, list):
            r['capabilities'] = [c for c in caps if isinstance(c, str)][:32]
        merged = {}
        for m in self.modules.values():       # a menu shows unless every Companion that knows the module turned it off
            for k, v in m.items():
                merged[k] = merged.get(k, False) or v
        with self.lock:
            self.hub.ctx.modules = merged

    def cards(self):
        """Cards from what the hub knows right now."""
        ctx, tr = self.hub.ctx, self.hub.ctx.tr
        out = []
        if self.hub.devices.get('tv') or ctx.tv_app or ctx.tv_volume is not None:
            detail = ' · '.join(x for x in (ctx.tv_app, '%s %d' % (tr('tv.volume_label'), ctx.tv_volume)
                                                     if ctx.tv_volume is not None else '') if x)
            out.append({'id': 'tv', 'title': ctx.tv_name or 'TV', 'kind': 'tv',
                        'state': ctx.tv_app or tr('menu.tv'), 'detail': detail, 'tone': 'ok' if ctx.tv_app else 'muted'})
        if self.hub.devices.get('vacuum') or ctx.vacuum_state:
            out.append({'id': 'vacuum', 'title': tr('menu.vacuum'), 'kind': 'vacuum',
                        'state': (ctx.vacuum_state or '-').capitalize(),
                        'detail': '%d%%' % ctx.vacuum_battery if ctx.vacuum_battery is not None else '', 'tone': ''})
        unread = ctx.inbox.unread() if ctx.inbox else 0
        out.append({'id': 'messages', 'title': tr('menu.messages'), 'kind': 'messages',
                    'state': tr('menu.messages.unread', n=unread) if unread else tr('menu.messages.none'),
                    'detail': '', 'tone': 'warn' if unread else 'muted'})
        s = self.hub.sport
        if s is not None:
            snap = s.snapshot()
            dist = snap.get('distance_m') or 0
            out.append({'id': 'sport', 'title': tr('menu.sport'), 'kind': 'sport',
                        'state': '%.2f km' % (dist / 1000) if dist >= 1000 else '%d m' % dist,
                        'detail': '%d:%02d' % divmod(int(snap.get('elapsed_s') or 0), 60), 'tone': 'ok'})
        for c in out:
            for k, v in list(c.items()):
                c[k] = str(v)[:fabric_relay.CARD_FIELD]
        return out[:fabric_relay.MAX_CARDS]

    def push_cards(self, rid):
        with self.lock:
            cards = self.cards()
        doc = json.dumps(cards, sort_keys=True)
        if self._cards_sent.get(rid) == doc:
            return
        try:
            self._send(rid, 'set_cards', {'cards': cards})
            self._cards_sent[rid] = doc
        except fabric_relay.RelayError:
            pass

    def pull_sessions(self, rid):
        try:
            got = self._send(rid, 'get_sessions').get('sessions') or []
        except fabric_relay.RelayError:
            return
        for s in got[:50]:
            if not isinstance(s, dict) or not isinstance(s.get('start'), (int, float)):
                continue
            doc = {k: s.get(k) for k in ('start', 'end', 'distance_m', 'source')}
            doc['relay_id'] = rid
            (sessions_dir() / ('phone-%d.json' % int(doc['start']))).write_text(json.dumps(doc), encoding='utf-8')
            self.saved_sessions += 1

    # ---- phone sensors
    def wants_sensors(self, rid):
        from src.glasses import ui
        r = self._relays().get(rid) or {}
        if 'phone_sensors' not in (r.get('capabilities') or ()) or not self.modules.get(rid, {}).get('sensors'):
            return False
        screen = self.hub.menu.screen
        return isinstance(screen, (ui.SportDashboard, ui.NavScreen, ui.GhostScreen, ui.WorkoutScreen)) \
            or self.hub.sport is not None

    def pull_sensors(self, rid):
        try:
            snap = self._send(rid, 'get_sensors').get('sensors') or {}
        except fabric_relay.RelayError:
            return
        self.feed(rid, snap)

    def feed(self, rid, snap):
        """Feed one get_sensors snapshot into the hub's sport engine (started on the open sport screen if needed)."""
        from src.glasses import sensors as SN, sport as S, ui
        now = self.clock()
        with self.lock:
            if self.hub.sport is None:
                screen = self.hub.menu.screen
                kind = getattr(screen, 'mode', None) if isinstance(screen, ui.SportDashboard) else 'run'
                self.hub.start_sport(kind or 'run')
            eng = self.hub.sport
            loc = snap.get('location') if isinstance(snap.get('location'), dict) else None
            if loc and isinstance(loc.get('lat'), (int, float)) and isinstance(loc.get('lon'), (int, float)):
                age = float(loc.get('age_s') or 0)
                t = now - age
                if age < 5 and t > self._fix_at.get(rid, 0) + 0.5:
                    self._fix_at[rid] = t
                    acc = loc.get('accuracy_m')
                    eng.gps(S.Point(t, float(loc['lat']), float(loc['lon']),
                                    float(acc) if isinstance(acc, (int, float)) and acc > 0 else 10.0, loc.get('alt_m')))
            for r in snap.get('sport') or []:
                if not isinstance(r, dict) or r.get('kind') not in SENSOR_KINDS:
                    continue
                age = float(r.get('age_s') or 99)
                key = (rid, r['kind'])
                at = now - age
                if age > 5 or at <= self._raw_at.get(key, 0):
                    continue
                self._raw_at[key] = at
                sensor = self._sensors.get(key)
                if sensor is None:
                    sensor = self._sensors[key] = SN.Sensor(SENSOR_KINDS[r['kind']], 'phone-' + r['kind'], clock=self.clock)
                try:
                    raw = bytes.fromhex(str(r.get('raw', '')))
                except ValueError:
                    continue
                for o in sensor.feed(raw):
                    eng.observe(o)
            fall = snap.get('fall_age_s')
            if isinstance(fall, (int, float)) and fall < 30 and not self._fall_seen.get(rid):
                self._fall_seen[rid] = True
                self.hub.ctx.banner = {'ok': False, 'text': self.hub.ctx.tr('phone.fall'), 'until': now + 15}
            elif not isinstance(fall, (int, float)) or fall >= 30:
                self._fall_seen[rid] = False
