"""Skill service: the skill library, alive inside the server.

The Library itself is passive (the CLI drives one command at a time). This
service owns one Library for the running server and feeds it:

- state triggers: every TICK_S the current device states are read (Home
  Assistant when it is connected) and passed to Library.tick();
- schedules: Library.run_due() runs about once a minute;
- buttons: approved manual recipes are exposed as remote-control buttons
  (see RemoteControls.set_skill_controls); a press runs Library.run() with
  actor 'relay:<relay_id>'.

Safety is unchanged: the Library only runs approved, enabled recipes through
the Executor (schema, policy, consent, read-back, receipt), automatic runs
keep their cooldown, hourly cap and chain guard, and a run stops at the first
step that is not verified. When Home Assistant is unreachable the tick is
skipped (no state snapshot, no edge); nothing fires on stale data.
"""
import threading
import time

from src.runtime.skill_library import Library, SkillError  # noqa: F401  (re-exported for callers)

TICK_S = 15
DUE_S = 60


class SkillService:
    def __init__(self, server, tick_s=TICK_S, due_s=DUE_S, persist=True, path=None, clock=time.time):
        self.server = server
        self.tick_s = tick_s
        self.due_s = due_s
        self.clock = clock
        from src.runtime.api_v2 import executor
        self.ex = executor(server)
        from src.runtime.device_learning import Learner
        self.learner = Learner(persist=persist)
        self.lib = Library(self.ex, learner=self.learner, persist=persist, path=path, clock=clock)
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self.last_tick_at = None
        self.last_tick_states = 0
        self.last_error = None

    # ---------- lifetime ----------
    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name='openbridge-skill-service', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        with self._lock:
            t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(self.tick_s + 5)

    def close(self):
        self.stop()

    # ---------- state source ----------
    def states(self):
        """{device_key: state} from the connected sources (Home Assistant today)."""
        adapters = getattr(self.server, 'fabric_adapters', None)
        reg = getattr(self.server, 'fabric_registry', None)
        if not callable(adapters) or reg is None:
            return {}
        try:
            ha = (adapters() or {}).get('home_assistant')
        except Exception:
            return {}
        if ha is None:
            return {}
        try:
            devices = getattr(reg, 'devices', {}) or {}
            keys = {d.get('ha_entity'): k for k, d in devices.items() if d.get('ha_entity')}
            return {keys[s['entity_id']]: s.get('state') for s in ha.states() if s['entity_id'] in keys}
        except Exception as e:
            self.last_error = '%s: %s' % (type(e).__name__, str(e)[:100])
            return {}

    # ---------- engine ----------
    def poll_once(self):
        """One pass: state edges, then due schedules. Returns {'fired': [...], 'due': [...]}, never raises."""
        try:
            states = self.states()
        except Exception as e:
            self.last_error = '%s: %s' % (type(e).__name__, str(e)[:100])
            return {'fired': [], 'due': []}
        fired, due = [], []
        try:
            if states:
                self.last_tick_states = len(states)
                self.last_tick_at = self.clock()
                fired = self.lib.tick(states) or []
            due = self.lib.run_due() or []
        except (SkillError, ValueError, OSError) as e:
            self.last_error = '%s: %s' % (type(e).__name__, str(e)[:100])
        for entry in list(fired) + list(due):
            if entry.get('actor') != 'owner' and entry.get('result') != 'blocked':
                try:
                    self.ex.emit('skill_fired', skill=entry.get('skill'), result=entry.get('result'),
                                 actor=entry.get('actor'), steps=len(entry.get('steps') or []))
                except Exception:
                    pass
        return {'fired': fired, 'due': due}

    def _loop(self):
        next_due = 0.0
        while not self._stop.is_set():
            try:
                states = self.states()
            except Exception as e:
                self.last_error = '%s: %s' % (type(e).__name__, str(e)[:100])
                states = {}
            try:
                if states:
                    self.last_tick_states = len(states)
                    self.last_tick_at = self.clock()
                    for entry in self.lib.tick(states) or []:
                        self._announce(entry)
                now = time.monotonic()
                if now >= next_due:
                    next_due = now + self.due_s
                    for entry in self.lib.run_due() or []:
                        self._announce(entry)
            except (SkillError, ValueError, OSError) as e:
                self.last_error = '%s: %s' % (type(e).__name__, str(e)[:100])
            self._stop.wait(self.tick_s)

    def _announce(self, entry):
        if entry.get('actor') != 'owner' and entry.get('result') != 'blocked':
            try:
                self.ex.emit('skill_fired', skill=entry.get('skill'), result=entry.get('result'),
                             actor=entry.get('actor'), steps=len(entry.get('steps') or []))
            except Exception:
                pass

    def state(self):
        with self._lock:
            alive = self._thread is not None and self._thread.is_alive()
        return {'running': alive, 'tick_s': self.tick_s, 'due_s': self.due_s,
                'last_tick_at': self.last_tick_at, 'last_tick_states': self.last_tick_states,
                'last_error': self.last_error, 'skills': self.lib.summary(), 'buttons': self.lib.buttons()}
