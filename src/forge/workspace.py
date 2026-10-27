"""Explicit runtime-to-Forge selection. The trusted reader is injected by the launcher only."""
import json
import secrets
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from src.forge.compiler import ForgeError
from src.forge.demo_host import Handler, create_forge_server
from src.forge.runtime_bridge import RuntimeV1Provider
from src.forge.service import ForgeService


class BoundForgeService(ForgeService):
    """Closing a bound workspace is terminal; fixture reset retains its separate reusable service."""
    def __init__(self, provider):
        super().__init__(provider)
        self._stopped = threading.Event()

    def _current(self, requested):
        if self._stopped.is_set():
            raise ForgeError('WORKSPACE_CLOSED')
        current = super()._current(requested)
        if self._stopped.is_set():
            raise ForgeError('WORKSPACE_CLOSED')
        return current

    def close(self):
        self._stopped.set()
        self._discard_if_closed()

    def _discard_if_closed(self):
        # An in-flight trusted read cannot be cancelled, but cannot hold closure hostage.
        # Logical revocation is immediate. Its bounded registry is cleared by the worker
        # when it unwinds, or immediately when no provider operation holds the lock.
        if self._stopped.is_set() and self._lock.acquire(blocking=False):
            try:
                self._services.clear()
            finally:
                self._lock.release()

    def _operation(self, method, *args, **kwargs):
        if self._stopped.is_set():
            raise ForgeError('WORKSPACE_CLOSED')
        try:
            result = method(*args, **kwargs)
            if self._stopped.is_set():
                raise ForgeError('WORKSPACE_CLOSED')
            return result
        finally:
            self._discard_if_closed()

    def publish(self, *args, **kwargs):
        return self._operation(super().publish, *args, **kwargs)

    def publish_verified(self, *args, **kwargs):
        return self._operation(super().publish_verified, *args, **kwargs)

    def read(self, *args, **kwargs):
        if self._stopped.is_set():
            raise ForgeError('SERVICE_REMOVED')
        return self._operation(super().read, *args, **kwargs)

    def documents(self, *args, **kwargs):
        return self._operation(super().documents, *args, **kwargs)

    def list_services(self):
        return [] if self._stopped.is_set() else super().list_services()

    def history(self):
        return [] if self._stopped.is_set() else super().history()

    def remove(self, sid):
        # A bound child exposes only one service. Stop ends its authority window;
        # a new publication requires a newly selected workspace, never a late request.
        self.close()


class WorkspaceManager:
    def __init__(self, read_json, planner=None, *, allow_simulated=False):
        self.read = read_json
        self.planner = planner
        self.allow_simulated = allow_simulated
        self.max_sessions = 8
        self._lock = threading.RLock()
        self._candidates = {}
        self._candidate_deadline = 0
        self._sessions = {}
        self._pending = 0
        self._closed = False
        self._stop = threading.Event()
        self._reaper = threading.Thread(target=self._reap, daemon=True)
        self._reaper.start()

    def candidates(self):
        """Read already collected facts only: no discovery, permission or execute primitive."""
        try:
            graph = self.read('/api/v2/graph')
            caps = self.read('/api/v2/capabilities')['capabilities']
            routes = self.read('/api/v2/routes')['routes']
            links = graph['links']
            if len(caps) > 1000 or len(routes) > 128 or len(links) > 4000:
                raise ForgeError('RUNTIME_GRAPH_LIMIT')
            bindings = set()
            for cap in caps:
                if cap.get('name') != 'ble_relay':
                    continue
                for route in routes:
                    if route.get('relay_device') != cap.get('device_key'):
                        continue
                    source = 'RELAY:' + route['relay_id']
                    for link in links:
                        if (link.get('parent') == route['relay_device'] and link.get('source') == source
                                and link.get('transport') == 'BLE' and 'observe' in link.get('grants', [])):
                            bindings.add((cap['capability_id'], link['child'], route['relay_id']))
                            if len(bindings) > 64:
                                raise ForgeError('CANDIDATE_LIMIT')
            choices, rows = {}, []
            for cap, target, relay in sorted(bindings):
                provider = RuntimeV1Provider(self.read, cap, target, relay, allow_simulated=self.allow_simulated)
                try:
                    manifest = provider.snapshot(provider.capability_id)
                except ForgeError:
                    continue
                key = secrets.token_urlsafe(24)
                choices[key] = provider
                rows.append({'id': key, 'relay': manifest['relay_id'], 'target': manifest['device_id'],
                             'signal_dbm': manifest['observations'][0]['rssi_dbm'],
                             'observed_at': manifest['observed_at'], 'simulation': manifest['simulation']})
            with self._lock:
                if self._closed:
                    raise ForgeError('WORKSPACE_CLOSED')
                self._candidates = choices
                self._candidate_deadline = time.monotonic() + 30
            return rows
        except ForgeError:
            raise
        except Exception:
            raise ForgeError('RUNTIME_NOT_READY: discover and scan an approved relay in the main workspace first') from None

    def select(self, candidate_id):
        with self._lock:
            if self._closed:
                raise ForgeError('WORKSPACE_CLOSED')
            if time.monotonic() > self._candidate_deadline:
                raise ForgeError('CANDIDATE_EXPIRED: refresh the route list')
            if not isinstance(candidate_id, str) or candidate_id not in self._candidates:
                raise ForgeError('CANDIDATE_UNKNOWN')
            if len(self._sessions) + self._pending >= self.max_sessions:
                raise ForgeError('SESSION_LIMIT: close an existing workspace first')
            provider = self._candidates[candidate_id]
            self._pending += 1
        child = None
        try:
            # Source I/O must not hold the manager lock: other workspaces remain removable.
            child = create_forge_server(0, self.planner, provider=provider, capability_id=provider.capability_id)
            child.forge = BoundForgeService(provider)
            original_snapshot = child.snapshot
            def bound_snapshot():
                if child_service._stopped.is_set():
                    raise ForgeError('WORKSPACE_CLOSED')
                return original_snapshot()
            child_service = child.forge
            child.snapshot = bound_snapshot
            with self._lock:
                if self._closed:
                    raise ForgeError('WORKSPACE_CLOSED')
                key = secrets.token_urlsafe(24)
                worker = threading.Thread(target=child.serve_forever, daemon=True)
                entry = {'server': child, 'worker': worker, 'expires': time.monotonic() + 1800}
                self._sessions[key] = entry
                try:
                    worker.start()
                except Exception:
                    del self._sessions[key]
                    raise
                child = None  # Registered worker now owns the listener.
                return self._view(key, entry)
        finally:
            if child is not None:
                child.server_close()
            with self._lock:
                self._pending -= 1

    @staticmethod
    def _view(key, entry):
        return {'id': key, 'url': f'http://127.0.0.1:{entry["server"].server_port}',
                'simulation': entry['server'].simulation,
                'remaining_seconds': max(0, int(entry['expires'] - time.monotonic()))}

    def sessions(self):
        with self._lock:
            return [self._view(key, entry) for key, entry in self._sessions.items()]

    def remove_session(self, key):
        with self._lock:
            try:
                entry = self._sessions.pop(key)
            except (KeyError, TypeError):
                raise ForgeError('SESSION_UNKNOWN') from None
        entry['server'].shutdown()
        entry['server'].server_close()
        entry['worker'].join(timeout=2)

    def _reap(self):
        while not self._stop.wait(5):
            with self._lock:
                expired = [key for key, entry in self._sessions.items() if entry['expires'] < time.monotonic()]
            for key in expired:
                try:
                    self.remove_session(key)
                except ForgeError:
                    pass

    def close(self):
        with self._lock:
            self._closed = True
            self._candidates.clear()
            keys = list(self._sessions)
        self._stop.set()
        self._reaper.join(timeout=2)
        for key in keys:
            try:
                self.remove_session(key)
            except ForgeError:
                pass


class WorkspaceServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_close(self):
        self.manager.close()
        super().server_close()


class WorkspaceHandler(Handler):
    def do_GET(self):
        if not self.guard():
            return
        assets = {'/': ('workspace.html', 'text/html; charset=utf-8'),
                  '/workspace.js': ('workspace.js', 'text/javascript; charset=utf-8'),
                  '/forge.css': ('forge.css', 'text/css; charset=utf-8')}
        if self.path in assets:
            name, mime = assets[self.path]
            body = (Path(__file__).parent / 'ui' / name).read_bytes()
            if name == 'workspace.html':
                body = body.replace(b'__MAIN_URL__', self.server.main_url.encode())
            return self.reply(200, body, mime)
        if self.path == '/api/session':
            return self.reply(200, {'token': self.server.token})
        if not self.authorized():
            return
        try:
            if self.path == '/api/candidates':
                return self.reply(200, {'candidates': self.server.manager.candidates(), 'selection_lifetime_seconds': 30})
            if self.path == '/api/sessions':
                return self.reply(200, {'sessions': self.server.manager.sessions()})
        except ForgeError as error:
            return self.reply(409, {'error': str(error)})
        self.reply(404, {'error': 'UNKNOWN_ROUTE'})

    def do_POST(self):
        if not self.guard(True) or not self.authorized():
            return
        if self.path not in ('/api/select', '/api/close'):
            return self.reply(404, {'error': 'UNKNOWN_ROUTE'})
        if self.headers.get('Content-Type') != 'application/json':
            return self.reply(415, {'error': 'JSON_CONTENT_TYPE_REQUIRED'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if self.headers.get('Transfer-Encoding') or not 0 < length <= 1024:
                return self.reply(413, {'error': 'BODY_SIZE_DENIED'})
            body = json.loads(self.rfile.read(length))
            field = 'candidate_id' if self.path == '/api/select' else 'session_id'
            if not isinstance(body, dict) or set(body) != {field} or not isinstance(body[field], str) or len(body[field]) > 64:
                return self.reply(400, {'error': 'INVALID_BODY'})
            if field == 'candidate_id':
                return self.reply(200, self.server.manager.select(body[field]))
            self.server.manager.remove_session(body[field])
            return self.reply(200, {'state': 'closed', 'services_removed': True})
        except ForgeError as error:
            return self.reply(409, {'error': str(error)})
        except (ValueError, TypeError):
            self.reply(400, {'error': 'INVALID_BODY'})


def create_workspace_server(port, manager, *, main_port=18765):
    if type(main_port) is not int or not 0 < main_port < 65536:
        raise ForgeError('INVALID_MAIN_PORT')
    server = WorkspaceServer(('127.0.0.1', port), WorkspaceHandler)
    server.manager = manager
    server.token = secrets.token_urlsafe(32)
    server.main_url = f'http://127.0.0.1:{main_port}'
    return server
