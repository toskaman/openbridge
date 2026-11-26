"""`openbridge glasses ...`: run the glasses hub, give or revoke its grant, preview the screens, drive a running hub.

    openbridge glasses preview --out captures/glasses           # every screen as PNG (lens + raw) + contact sheet
    openbridge glasses grant --allow tv_remote,tv_apps,vacuum --consent ALLOW
    openbridge glasses run --link studio                        # HUD Studio (no glasses needed)
    openbridge glasses run --link ble                           # real ENGO glasses over Bluetooth from this PC
    openbridge glasses press next|prev|ok|back|home|up|down|left|right
    openbridge glasses notify --app telegram --from "Maman" --text "Tu viens ?"
    openbridge glasses say "baisse le son de la télé"
"""
from __future__ import annotations

import json
import socket
import threading
import time

from src.glasses import hub as G

CONTROL_PORT = 7791
APP_ALIASES = {'discord': 'com.discord', 'telegram': 'org.telegram.messenger', 'sms': 'com.android.mms',
               'messages': 'com.google.android.apps.messaging', 'samsung': 'com.samsung.android.messaging',
               'whatsapp': 'com.whatsapp', 'signal': 'org.thoughtcrime.securesms'}


def _err(cli, code, msg, kind='args'):
    return cli.CliError(kind, code, msg)


# ---------------------------------------------------------------- settings

def cmd_grant(args):
    from src import cli
    if getattr(args, 'consent', None) != 'ALLOW':
        raise _err(cli, 'CONSENT_REQUIRED', 'The glasses will be able to run these actions on a gesture or a voice '
                                            'command. Re-run with --consent ALLOW.', 'permission')
    wanted = [w.strip() for w in (args.allow or '').split(',') if w.strip()]
    bad = [w for w in wanted if w not in G.GRANTABLE]
    if bad or not wanted:
        raise _err(cli, 'BAD_GRANT', 'choose from: %s' % ', '.join(G.GRANTABLE))
    s = G.load_settings()
    s['grant'] = sorted(set(wanted))
    s['granted_at'] = time.time()
    G.save_settings(s)
    return {'grant': {k: G.GRANTABLE[k] for k in s['grant']}, 'note': 'revoke any time: openbridge glasses revoke'}


def cmd_revoke(args):
    s = G.load_settings()
    s['grant'] = []
    G.save_settings(s)
    return {'grant': []}


def cmd_set(args):
    from src.glasses.notifications import APPS
    s = G.load_settings()
    if args.rotate is not None:
        s['rotate180'] = args.rotate == 'on'
    if getattr(args, 'x_offset', None) is not None:
        s['x_offset'] = max(-60, min(60, args.x_offset))
    if args.privacy:
        s['privacy'] = args.privacy
    if args.lang:
        s['language'] = args.lang
    if args.hud_lang:
        s['hud_language'] = args.hud_lang
    if args.units:
        s['units'] = args.units
    if args.apps:
        pkgs = [APP_ALIASES.get(a.strip().lower(), a.strip()) for a in args.apps.split(',') if a.strip()]
        unknown = [p for p in pkgs if p not in APPS]
        if unknown:
            from src import cli
            raise _err(cli, 'UNKNOWN_APP', 'unknown app(s): %s; known: %s' % (', '.join(unknown), ', '.join(sorted(APP_ALIASES))))
        s['apps'] = pkgs
    G.save_settings(s)
    return {'settings': s}


def cmd_status(args):
    s = G.load_settings()
    out = {'settings': s, 'grantable': G.GRANTABLE}
    try:
        out['running'] = send({'status': True}, timeout=2)
    except OSError:
        out['running'] = None
    return out


def cmd_preview(args):
    from src.glasses import preview
    names = preview.write_gallery(args.out, args.glasses_model)
    return {'screens': names, 'out': args.out, 'contact_sheet': '%s/contact_sheet.png' % args.out.rstrip('/\\')}


# ---------------------------------------------------------------- talking to a running hub

def send(req, port=CONTROL_PORT, timeout=10):
    with socket.create_connection(('127.0.0.1', port), timeout=timeout) as s:
        s.sendall((json.dumps(req) + '\n').encode())
        buf = b''
        while not buf.endswith(b'\n'):
            d = s.recv(65536)
            if not d:
                break
            buf += d
    return json.loads(buf or b'{}')


def _send_or_explain(req):
    from src import cli
    try:
        return send(req)
    except OSError:
        raise _err(cli, 'HUB_NOT_RUNNING', 'Start it first: openbridge glasses run --link studio (or ble)', 'device')


def cmd_press(args):
    return _send_or_explain({'press': args.event})


def cmd_notify(args):
    return _send_or_explain({'notify': {'package': APP_ALIASES.get(args.app.lower(), args.app), 'sender': args.sender,
                                        'text': args.text}})


def cmd_say(args):
    return _send_or_explain({'voice': args.text})


def cmd_module(args):
    """Switch an optional Companion module (the Oracle) on or off, on one paired screen or all of them."""
    from src import cli
    from src.fabric import relay as fabric_relay
    from src.fabric.relay_store import default_owner_store
    from src.runtime import companion_modules as CM
    with cli.Core() as server:
        server.relay_store = default_owner_store()
        cli.ensure_discovery(server, ['android'])
        rids = [args.relay] if args.relay else list(CM._relays(server))
        if not rids:
            raise _err(cli, 'NO_PAIRED_PHONE', 'Pair a Companion first', 'device')
        out = []
        for rid in rids:
            try:
                out.append(CM.set_module(server, rid, args.module, args.state == 'on'))
            except (fabric_relay.RelayError, ValueError) as e:
                out.append({'relay_id': rid, 'error': str(e)[:200]})
        return {'modules': out}


def cmd_oracle(args):
    if getattr(args, 'mic', False):
        from src.ai import mic_oracle
        from src import cli

        def _on_ans(res):
            send({'oracle': res}, port=args.control_port, timeout=1.0)

        try:
            mic_oracle.run_mic_loop(
                mic_source=args.source,
                language=args.lang,
                on_answer=_on_ans,
            )
        except ImportError as e:
            raise _err(cli, 'DEP_MISSING', f'Microphone capture requires sounddevice ({e})', 'dep')
        return {'stopped': True}
    if not getattr(args, 'text', None):
        from src import cli
        raise _err(cli, 'ARGS_REQUIRED', 'Pass --text "..." or --mic', 'args')
    return _send_or_explain({'oracle_query': args.text})


class Control:
    """127.0.0.1 only: one JSON request per line."""

    def __init__(self, hub, lock, port=CONTROL_PORT):
        self.hub, self.lock = hub, lock
        self.srv = socket.create_server(('127.0.0.1', port))
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(c,), daemon=True).start()

    def _one(self, c):
        with c:
            try:
                req = json.loads(c.makefile('rb').readline(65536) or b'{}')
                out = self.handle(req)
            except Exception as e:                       # noqa: BLE001 - reported to the client
                out = {'error': type(e).__name__}
            c.sendall((json.dumps(out, default=str) + '\n').encode())

    def handle(self, req):
        h = self.hub
        with self.lock:
            if 'press' in req:
                h.press(str(req['press']))
                h.tick()
                return {'screen': type(h.menu.screen).__name__, 'last': h.log[-1] if h.log else None}
            if 'notify' in req:
                item = h.notify(dict(req['notify']))
                return {'shown': bool(item), 'unread': h.inbox.unread()}
        if 'voice' in req:                              # outside the lock: the model takes a moment
            return {'outcome': h.voice(str(req['voice'])), 'voice': h.ctx.voice}
        if 'oracle' in req and isinstance(req['oracle'], dict):
            ans = dict(req['oracle'])
            with self.lock:
                h.oracle(str(ans.get('transcript', '')), ans, partial=bool(req.get('partial')))
            return {'shown': True, 'screen': type(h.menu.screen).__name__}
        if 'oracle_query' in req:
            from src.ai import oracle as Oracle
            q = str(req['oracle_query'])
            ans = Oracle.oracle_answer(q)
            with self.lock:
                h.oracle(q, ans, partial=False)
            return {'oracle': ans}
        tr = getattr(h.link, 'tr', None)                 # BLE transport counters (MTU, pauses, drops), when on BLE
        return {'screen': type(h.menu.screen).__name__, 'unread': h.inbox.unread(), 'devices': h.devices,
                'grant': h.settings.get('grant'), 'log': h.log[-10:],
                'transport': dict(tr.stats, chunk=tr.chunk, paused=tr.paused) if tr else None}


# ---------------------------------------------------------------- the running hub

def _understand_factory(model, endpoint):
    from src import cli
    from src.runtime import intent as I
    from src.runtime import nl_router as NR

    def understand(text):
        fr = cli._words_of(text) & {'le', 'la', 'les', 'du', 'de', 'baisse', 'monte', 'lance', 'mets', 'ouvre', 'son'}
        lang = 'fr' if fr else 'en'
        try:
            reply = cli._ollama_intent(model, NR.build_prompt(text, lang), endpoint)
        except Exception:                                # noqa: BLE001 - "not understood" on the glasses
            return None
        doc = NR._interpret(I.new_intent(text, lang), reply, 'local', model)
        return (doc['skill_id'], doc.get('params') or {}) if doc['status'] == 'resolved' else None
    return understand


def _find_devices(server):
    reg = getattr(server, 'fabric_registry', None)
    out = {}
    for key, d in (getattr(reg, 'devices', None) or {}).items():
        if d.get('category') == 'tv' and 'tv' not in out:
            out['tv'] = key
        if d.get('category') == 'vacuum' and 'vacuum' not in out:
            out['vacuum'] = key
    return out


def _poll_phone(server, hub, lock):
    """Notifications from paired Companions (op get_notifications), and voice through CompanionCommands."""
    from src.fabric import relay as fabric_relay
    from src.runtime.companion_commands import companion_commands
    cc = companion_commands(server)
    relays = getattr(getattr(server, 'relays', None), 'relays', None) or {}
    for rid, r in list(relays.items()):
        if 'notifications' not in r.get('capabilities', ()) or not r.get('online'):
            continue
        try:
            got = cc._send(rid, 'get_notifications')
        except fabric_relay.RelayError:
            continue
        for n in (got.get('notifications') or [])[:50]:
            if isinstance(n, dict):
                with lock:
                    hub.notify(n)
    try:
        cc.poll_once()
    except Exception:                                    # noqa: BLE001 - phone offline: try again next round
        pass


def _studio_mirror(wave, args):
    """HUD Studio window on the PC showing the same frames as the glasses (started if not running)."""
    import subprocess
    import sys
    try:
        return G.StudioLink(wave, port=args.studio_port)
    except OSError:
        pass
    subprocess.Popen([sys.executable, '-m', 'src.adapters.hud_studio', '--model', args.glasses_model])
    for _ in range(40):
        time.sleep(0.5)
        try:
            return G.StudioLink(wave, port=args.studio_port)
        except OSError:
            continue
    return None                                          # glasses keep working without the mirror


def _phone_link(server, wave, args):
    """ENGO glasses through the Bluetooth of a paired phone (Companion op glasses_connect), for a PC without Bluetooth."""
    from src import cli
    from src.fabric import relay as fabric_relay
    from src.runtime.companion_commands import companion_commands
    cc = companion_commands(server)
    relays = getattr(getattr(server, 'relays', None), 'relays', None) or {}
    ids = [rid for rid, r in relays.items() if (args.relay in (None, rid)) and 'glasses_link' in r.get('capabilities', ())]
    if not ids:
        ids = [rid for rid in relays if args.relay in (None, rid)]
    if not ids:
        raise _err(cli, 'NO_PAIRED_PHONE', 'Pair the phone first (OpenBridge Companion), then retry --link phone', 'device')
    errors = []
    for rid in ids:
        try:
            return G.PhoneLink(wave, lambda op, p, rid=rid: cc._send(rid, op, p), address=args.address,
                               takeover=args.takeover)
        except (OSError, fabric_relay.RelayError) as e:
            errors.append('%s: %s' % (rid, e))
    raise _err(cli, 'GLASSES_UNAVAILABLE', ('; '.join(errors))[:300], 'device')


def cmd_run(args):
    from src import cli
    from src.runtime import api_v2
    lock = threading.RLock()
    settings = G.load_settings()
    holder = {}

    def wave():
        h = holder.get('hub')
        if h:
            h.tap_next() if holder.get('tap') else h.wave()

    if args.link == 'studio':
        try:
            link = G.StudioLink(wave, port=args.studio_port)
        except OSError:
            raise _err(cli, 'STUDIO_NOT_RUNNING', 'Start HUD Studio first: python -m src.adapters.hud_studio --model "ENGO 3"', 'device')
    elif args.link == 'ble':
        try:
            link = G.BleLink(wave, address=args.address, takeover=args.takeover)
        except (OSError, ImportError) as e:
            raise _err(cli, 'GLASSES_UNAVAILABLE', str(e)[:200], 'device')
    elif args.link == 'phone':
        link = None                                      # needs the paired phone: opened once the core is up
    else:
        link = G.NullLink()
    with cli.Core() as server:
        executor = devices = None
        if getattr(server, 'relay_store', None) is None:
            # The in-process core starts without the owner's pairings; without them no paired phone is reachable
            # (messages, voice, Oracle, and --link phone).
            from src.fabric.relay_store import default_owner_store
            server.relay_store = default_owner_store()
        if not args.offline:
            cli.ensure_discovery(server, cli.default_providers(args))
            executor, devices = api_v2.executor(server), _find_devices(server)
        if link is None:
            link = _phone_link(server, wave, args)
        if args.mirror and args.link in ('ble', 'phone'):
            link = G.MirrorLink(link, _studio_mirror(wave, args))
        hub = G.Hub(link=link, executor=executor, devices=devices, settings=settings,
                    colour=__import__('src.adapters.activelook_emulator', fromlist=['is_colour']).is_colour(args.glasses_model),
                    understand=_understand_factory(args.intent_model, args.endpoint))
        holder['hub'] = hub
        if hasattr(link, 'on_button'):                   # Next / Open / Back / Home buttons on the phone
            link.on_button = hub.press
        elif hasattr(getattr(link, 'main', None), 'on_button'):
            link.main.on_button = hub.press
        if '3' in args.glasses_model:
            # ENGO 3: the only input is a double tap on the temple (one event, value 1; single taps send nothing and
            # 3-4 taps still send one event, measured 26 Nov 2026). Each one is 'next'; open/back come from the phone
            # buttons, the voice, or the 3 s auto-open on the home carousel.
            holder['tap'] = True
            hub.ctx.input = 'tap'
        server.glasses_hub = hub
        server.glasses_control_port = args.control_port
        from src.ai import oracle as Oracle
        threading.Thread(target=Oracle.warmup, name='oracle-warmup', daemon=True).start()
        cc = None
        if not args.offline:
            from src.runtime.companion_commands import companion_commands
            cc = companion_commands(server)
            cc.listeners = getattr(cc, 'listeners', [])
            cc.listeners.append(lambda rid, text, doc: None if doc.get('skill_id') == 'voice.oracle' else hub.voice(text))
        Control(hub, lock, args.control_port)
        sim = _start_sport(hub, args)
        hub.redraw(force=True)
        end = time.time() + args.seconds if args.seconds else None
        last_phone = 0.0
        while end is None or time.time() < end:
            with lock:
                if sim is not None:
                    _feed_simulation(hub, sim)
                hub.tick()
            if cc and time.time() - last_phone > args.phone_poll:
                last_phone = time.time()
                _poll_phone(server, hub, lock)
            time.sleep(0.05)
        link.close()
        return {'ran_s': args.seconds, 'devices': devices, 'log': hub.log[-20:]}


def _parse_workout(spec):
    """'6x400@4:15' -> 6 x 400 m at 4:15 /km, 10 min warm-up, 90 s recovery, 10 min cool-down."""
    import re
    from src.glasses import sport as S
    m = re.fullmatch(r'(\d{1,2})x(\d{2,5})(?:@(\d{1,2}):(\d{2}))?', spec or '')
    if not m:
        raise ValueError('workout like 6x400@4:15')
    pace = int(m[3]) * 60 + int(m[4]) if m[3] else None
    return S.Workout.intervals(spec, 600, int(m[1]), int(m[2]), 90, 600, target_pace=pace)


def _start_sport(hub, args):
    """Start a sport session when asked. Returns a simulation iterator (SIMULATED GPS) or None."""
    if not getattr(args, 'sport', None):
        return None
    from pathlib import Path
    from src import cli
    from src.glasses import nav
    route = None
    if args.gpx:
        try:
            route = nav.parse_gpx(Path(args.gpx).read_bytes(), Path(args.gpx).stem)
        except (OSError, nav.GpxError) as e:
            raise _err(cli, 'BAD_GPX', str(e)[:200])
    try:
        workout = _parse_workout(args.workout) if args.workout else None
    except ValueError as e:
        raise _err(cli, 'BAD_WORKOUT', str(e))
    hub.start_sport(args.sport, route=route, workout=workout, max_hr=args.max_hr)
    hub.menu.stack[1:] = []
    from src.glasses import ui
    hub.menu.stack.append(ui.NavScreen() if route is not None else ui.WorkoutScreen() if workout else ui.SportDashboard(args.sport))
    if args.simulate and route is not None:
        return {'it': nav.simulate(route, args.simulate, time.time(), 1.0, jitter_m=2.0), 'next': None}
    return None


def _feed_simulation(hub, sim):
    now = time.time()
    while True:
        if sim['next'] is None:
            sim['next'] = next(sim['it'], False)
        if sim['next'] is False or sim['next'].t > now:
            return
        hub.sport.gps(sim['next'])
        sim['next'] = None


def register(subs, leaf):
    g = subs.add_parser('glasses', help='ENGO / ActiveLook glasses: menus, messages, TV, vacuum, voice')
    gs = g.add_subparsers(dest='glasses_command')
    r = leaf(gs, 'run', cmd_run, 'glasses run')
    r.add_argument('--link', choices=['studio', 'ble', 'phone', 'none'], default='studio',
                   help="phone: the paired phone's Bluetooth holds the link (PC without Bluetooth)")
    r.add_argument('--mirror', action='store_true', help='with ble or phone: also draw every frame in HUD Studio on the PC')
    r.add_argument('--relay', default=None, help='with --link phone: which paired phone (relay id), default: the first')
    r.add_argument('--address', default=None, help='Bluetooth address of the glasses (default: first ENGO found)')
    r.add_argument('--glasses', dest='glasses_model', default='ENGO 3', help='ENGO 1, ENGO 2 or ENGO 3')
    r.add_argument('--seconds', type=float, default=0, help='stop after N seconds (default: run until Ctrl+C)')
    r.add_argument('--offline', action='store_true', help='no device discovery (menus and messages only)')
    r.add_argument('--studio-port', type=int, default=7789)
    r.add_argument('--control-port', type=int, default=CONTROL_PORT)
    r.add_argument('--phone-poll', type=float, default=0.35)
    r.add_argument('--intent-model', default='openbridge-intent')
    r.add_argument('--endpoint', default='http://127.0.0.1:11434')
    r.add_argument('--takeover', action='store_true', help='take the glasses over from the phone (explicit switch)')
    r.add_argument('--sport', choices=['run', 'ride', 'hike'], default=None, help='start a sport session on the glasses')
    r.add_argument('--gpx', default=None, help='route to follow (GPX track or route)')
    r.add_argument('--workout', default=None, help='intervals, e.g. 6x400@4:15')
    r.add_argument('--max-hr', type=int, default=None, help='your max heart rate, for zones')
    r.add_argument('--simulate', type=float, default=None, help='SIMULATED: move along the GPX at this speed (m/s)')
    gr = leaf(gs, 'grant', cmd_grant, 'glasses grant')
    gr.add_argument('--allow', required=True, help=', '.join(G.GRANTABLE))
    leaf(gs, 'revoke', cmd_revoke, 'glasses revoke')
    st = leaf(gs, 'set', cmd_set, 'glasses set')
    st.add_argument('--rotate', choices=['on', 'off'], default=None, help='display mounted upside down')
    st.add_argument('--x-offset', dest='x_offset', type=int, default=None,
                    help='move the picture left (negative) or right, in pixels, to fit the visible area (default -20)')
    st.add_argument('--privacy', choices=['full', 'sender', 'off'], default=None)
    st.add_argument('--apps', default=None, help='apps whose messages are shown, e.g. discord,telegram,sms,messages')
    st.add_argument('--lang', choices=['auto', 'fr', 'en'], default=None, help='app language (Français / English)')
    st.add_argument('--hud-lang', choices=['follow', 'fr', 'en'], default=None, help='glasses language (default: same as app)')
    st.add_argument('--units', choices=['metric', 'imperial'], default=None)
    leaf(gs, 'status', cmd_status, 'glasses status')
    pv = leaf(gs, 'preview', cmd_preview, 'glasses preview')
    pv.add_argument('--out', default='captures/glasses')
    pv.add_argument('--glasses', dest='glasses_model', default='ENGO 3')
    pr = leaf(gs, 'press', cmd_press, 'glasses press')
    pr.add_argument('event', choices=list(__import__('src.glasses.ui', fromlist=['EVENTS']).EVENTS))
    nt = leaf(gs, 'notify', cmd_notify, 'glasses notify')
    nt.add_argument('--app', required=True)
    nt.add_argument('--from', dest='sender', required=True)
    nt.add_argument('--text', required=True)
    sy = leaf(gs, 'say', cmd_say, 'glasses say')
    sy.add_argument('text')
    md = leaf(gs, 'module', cmd_module, 'glasses module')
    md.add_argument('module', choices=['oracle'])
    md.add_argument('state', choices=['on', 'off'])
    md.add_argument('--relay', default=None, help='one paired Companion (relay id); default: all of them')
    oc = leaf(gs, 'oracle', cmd_oracle, 'glasses oracle')
    oc.add_argument('--text', default=None, help='question to answer on the ENGO glasses')
    oc.add_argument('--mic', action='store_true', help='stream PC/USB/Bluetooth mic continuously to the glasses')
    oc.add_argument('--source', default='pc_mic', help='mic source label (pc_mic, ble_headset, usb_mic)')
    oc.add_argument('--lang', default='fr', choices=['fr', 'en'])
    oc.add_argument('--control-port', type=int, default=CONTROL_PORT)
