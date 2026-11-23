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
    if args.privacy:
        s['privacy'] = args.privacy
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
        return {'screen': type(h.menu.screen).__name__, 'unread': h.inbox.unread(), 'devices': h.devices,
                'grant': h.settings.get('grant'), 'log': h.log[-10:]}


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


def cmd_run(args):
    from src import cli
    from src.runtime import api_v2
    lock = threading.RLock()
    settings = G.load_settings()
    holder = {}

    def wave():
        h = holder.get('hub')
        if h:
            h.wave()

    if args.link == 'studio':
        try:
            link = G.StudioLink(wave, port=args.studio_port)
        except OSError:
            raise _err(cli, 'STUDIO_NOT_RUNNING', 'Start HUD Studio first: python -m src.adapters.hud_studio --model "ENGO 3"', 'device')
    elif args.link == 'ble':
        try:
            link = G.BleLink(wave, address=args.address)
        except (OSError, ImportError) as e:
            raise _err(cli, 'GLASSES_UNAVAILABLE', str(e)[:200], 'device')
    else:
        link = G.NullLink()
    with cli.Core() as server:
        executor = devices = None
        if not args.offline:
            cli.ensure_discovery(server, cli.default_providers(args))
            executor, devices = api_v2.executor(server), _find_devices(server)
        hub = G.Hub(link=link, executor=executor, devices=devices, settings=settings,
                    colour='3' in args.glasses_model,
                    understand=_understand_factory(args.intent_model, args.endpoint))
        holder['hub'] = hub
        cc = None
        if not args.offline:
            from src.runtime.companion_commands import companion_commands
            cc = companion_commands(server)
            cc.listeners = getattr(cc, 'listeners', [])
            cc.listeners.append(lambda rid, text, doc: hub.voice(text))
        Control(hub, lock, args.control_port)
        hub.redraw(force=True)
        end = time.time() + args.seconds if args.seconds else None
        last_phone = 0.0
        while end is None or time.time() < end:
            with lock:
                hub.tick()
            if cc and time.time() - last_phone > args.phone_poll:
                last_phone = time.time()
                _poll_phone(server, hub, lock)
            time.sleep(0.05)
        link.close()
        return {'ran_s': args.seconds, 'devices': devices, 'log': hub.log[-20:]}


def register(subs, leaf):
    g = subs.add_parser('glasses', help='ENGO / ActiveLook glasses: menus, messages, TV, vacuum, voice')
    gs = g.add_subparsers(dest='glasses_command')
    r = leaf(gs, 'run', cmd_run, 'glasses run')
    r.add_argument('--link', choices=['studio', 'ble', 'none'], default='studio')
    r.add_argument('--address', default=None, help='Bluetooth address of the glasses (default: first ENGO found)')
    r.add_argument('--glasses', dest='glasses_model', default='ENGO 3', help='ENGO 1, ENGO 2 or ENGO 3')
    r.add_argument('--seconds', type=float, default=0, help='stop after N seconds (default: run until Ctrl+C)')
    r.add_argument('--offline', action='store_true', help='no device discovery (menus and messages only)')
    r.add_argument('--studio-port', type=int, default=7789)
    r.add_argument('--control-port', type=int, default=CONTROL_PORT)
    r.add_argument('--phone-poll', type=float, default=2.0)
    r.add_argument('--intent-model', default='openbridge-intent')
    r.add_argument('--endpoint', default='http://127.0.0.1:11434')
    gr = leaf(gs, 'grant', cmd_grant, 'glasses grant')
    gr.add_argument('--allow', required=True, help=', '.join(G.GRANTABLE))
    leaf(gs, 'revoke', cmd_revoke, 'glasses revoke')
    st = leaf(gs, 'set', cmd_set, 'glasses set')
    st.add_argument('--rotate', choices=['on', 'off'], default=None, help='display mounted upside down')
    st.add_argument('--privacy', choices=['full', 'sender', 'off'], default=None)
    st.add_argument('--apps', default=None, help='apps whose messages are shown, e.g. discord,telegram,sms,messages')
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
