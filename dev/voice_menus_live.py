"""Live: owner VOICE on the watch -> local Meta designs the watch buttons -> taps drive the TV.

    python -m dev.voice_menus_live --tv-serial 192.168.1.15:5555 [--minutes 25] [--console-port 18790]

One process holds the paired relay, the RemoteControls poller and the command drain
with the opt-in voice layout layer (src/runtime/voice_layout.py) enabled: creation is
drafted by the pinned local Meta model, removal is a deterministic revoke. Starts with
an EMPTY watch layout so creation is visible. Voice never presses.

A read-only live console (http://127.0.0.1:<console-port>/) shows every step as it
happens -- heard transcript, Meta run (model, digest, latency, proposed widgets),
install (control ids, grant generation), each press (request id, outcome, invocation,
transaction), TV volume read back over ADB -- for the split-screen demo recording.
Everything is also appended as JSON lines to --events (the proof file).
On exit the buttons are removed (owner's watch is left clean).
"""
import argparse
import json
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

EVENTS, LOCK = [], threading.Lock()
STATE = {'volume': None, 'buttons': [], 'meta': None, 'heard': None, 'started': None,
         'presses': 0, 'executed': 0, 'model': None}
_EV_FILE = [None]


def emit(kind, text, **data):
    ev = {'t': time.time(), 'utc': datetime.now(timezone.utc).strftime('%H:%M:%S.%f')[:-3],
          'kind': kind, 'text': text, **data}
    with LOCK:
        EVENTS.append(ev)
        del EVENTS[:-400]
    print('%s [%s] %s' % (ev['utc'], kind, text), flush=True)
    if _EV_FILE[0]:
        try:
            with open(_EV_FILE[0], 'a', encoding='utf-8') as f:
                f.write(json.dumps(ev, ensure_ascii=False) + '\n')
        except OSError:
            pass


def log(msg):
    """voice_layout log lines -> structured events."""
    kind = msg.split(']')[0].strip('[') if msg.startswith('[') else 'info'
    text = msg.split('] ', 1)[1] if '] ' in msg else msg
    if kind == 'voice' and 'heard:' in text:
        STATE['heard'] = text
    emit(kind, text)


class _Tee:
    """Mirror the drain's stderr lines ('[drain] ... -> status: text') into the console."""
    def __init__(self, inner):
        self.inner, self.buf = inner, ''

    def write(self, s):
        self.inner.write(s)
        self.buf += s
        while '\n' in self.buf:
            line, self.buf = self.buf.split('\n', 1)
            if line.startswith('[drain]'):
                emit('report', line[len('[drain] '):][:220])
        return len(s)

    def flush(self):
        self.inner.flush()


def console(port):
    page = (Path(__file__).parent / 'live_console' / 'index.html').read_bytes()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith('/state'):
                since = float((self.path.split('since=') + ['0'])[1] or 0)
                with LOCK:
                    body = json.dumps({'state': STATE, 'events': [e for e in EVENTS if e['t'] > since]},
                                      ensure_ascii=False).encode()
                ctype = 'application/json; charset=utf-8'
            elif self.path in ('/', '/index.html'):
                body, ctype = page, 'text/html; charset=utf-8'
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    threading.Thread(target=srv.serve_forever, daemon=True, name='live-console').start()
    return srv


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--tv-serial', required=True)
    ap.add_argument('--minutes', type=float, default=25)
    ap.add_argument('--drain-interval', type=float, default=2.0)
    ap.add_argument('--console-port', type=int, default=18790)
    ap.add_argument('--events', default=r'E:\OpenBridge-Overnight\device-frontier\voice-live-events.jsonl')
    ap.add_argument('--evidence-dir', default=r'E:\OpenBridge-Overnight\device-frontier\meta-runs')
    args = ap.parse_args(argv)
    _EV_FILE[0] = args.events
    STATE['started'] = time.time()
    console(args.console_port)
    emit('boot', 'OpenBridge live console on http://127.0.0.1:%d' % args.console_port)
    sys.stderr = _Tee(sys.stderr)

    from src.server import create_server
    from src.adapters.android import default_remember_path
    from src.cli import ensure_discovery, default_providers
    from src.fabric.relay_store import default_owner_store
    from src.runtime import command_drain, voice_layout, nl_router
    from src.runtime.api_v2 import remote_controls
    from dev.flagship_c_vehicle import LiveIO, resolve_relay_id

    server = create_server(port=0, relay_store=default_owner_store(), adb_remember=default_remember_path())
    snap = ensure_discovery(server, default_providers(argparse.Namespace()))
    devs = (snap or {}).get('devices', []) if isinstance(snap, dict) else []
    emit('discovery', '%d devices: %s' % (len(devs), ', '.join(sorted({d.get('category', '?') for d in devs}))))
    rid = resolve_relay_id(server)
    tv = voice_layout.resolve_tv_key(server)
    relay = server.relays.relays[rid]
    emit('relay', '%s online, transport %s, caps %s' % (rid, relay.get('aead') or 'plaintext',
                                                       ','.join(sorted(relay.get('capabilities') or ()))))
    STATE['model'] = '%s @ %s (local, pinned)' % nl_router.TIERS['low']
    emit('meta', 'model ready: %s' % STATE['model'])
    io = LiveIO(server, rid, tv, args.tv_serial)   # TV volume oracle (ADB dumpsys) + ADB freshness touch
    rc = remote_controls(server)
    rc.set_controls({'relay_id': rid, 'controls': [], 'consent': True})
    emit('layout', 'watch layout cleared: start EMPTY')
    voice_layout.enable(server, log=log, evidence_dir=args.evidence_dir)
    command_drain.start(server, interval_s=args.drain_interval)
    emit('ready', 'voice drain ON (poll %.0fs). Speak to the watch.' % args.drain_interval)

    stop = threading.Event()

    def toucher():
        while not stop.is_set():
            try:
                io._touch_attached()
            except Exception as e:  # noqa: BLE001
                emit('warn', 'touch failed %s' % e)
            stop.wait(20)

    def volume_poller():
        last = None
        while not stop.is_set():
            try:
                v = io.read_volume()
            except Exception:  # noqa: BLE001
                v = None
            if v is not None and v != last:
                emit('tv', 'TV volume = %d (ADB dumpsys audio, STREAM_MUSIC)' % v, volume=v)
                STATE['volume'], last = v, v
            stop.wait(1.5)
    threading.Thread(target=toucher, daemon=True).start()
    threading.Thread(target=volume_poller, daemon=True).start()

    seen_hist, last_layout, deadline = set(), None, time.time() + args.minutes * 60
    try:
        while time.time() < deadline:
            st = rc.state()
            mine = [c for c in st['controls'] if c['relay_id'] == rid]
            layout = [(c['label'], c['control_id'], c.get('skill_id'), c.get('params'), c.get('generation'))
                      for c in mine]
            if layout != last_layout:
                STATE['buttons'] = [{'label': l, 'control_id': cid, 'skill': s, 'params': p, 'gen': g}
                                    for l, cid, s, p, g in layout]
                emit('layout', 'watch buttons now: %s' % (', '.join('%s [%s g%s]' % (l, cid[:14], g)
                                                                   for l, cid, _s, _p, g in layout) or '(none)'),
                     buttons=STATE['buttons'])
                last_layout = layout
            for e in st['history']:
                k = e.get('request_id')
                if k and k not in seen_hist:
                    seen_hist.add(k)
                    STATE['presses'] += 1
                    if e.get('state') == 'EXECUTED':
                        STATE['executed'] += 1
                    emit('press', 'tap %s -> %s %s | req %s inv %s tx %s' % (
                        e.get('control_id', '')[:14], e.get('state'), e.get('reason') or '',
                        k[:12], (e.get('invocation_id') or '-')[:14], (e.get('transaction_id') or '-')[:14]),
                        state=e.get('state'))
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        try:
            rc.set_controls({'relay_id': rid, 'controls': [], 'consent': True})
            emit('layout', 'exit: watch buttons removed')
        except Exception as e:  # noqa: BLE001
            emit('warn', 'exit cleanup failed %s' % e)
    return 0


if __name__ == '__main__':
    sys.exit(main())
