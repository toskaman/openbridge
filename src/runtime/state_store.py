"""Small durable runtime state next to the session journal (runtime-state.json).

Persists what must survive a server restart:
- `policies`: B2 skill routing policies set by the owner (otherwise a restart silently returns to AUTO).
- `unresolved`: receipts of potentially changing operations that ended without verification (UNKNOWN_TIMEOUT,
  FAILED, PARTIAL) and were not acknowledged, so recovery() and the admission bound still see them after a restart.

Atomic replace (tmp file + os.replace); malformed content is ignored field by field (fail closed to defaults, never to
"nothing pending" for a readable list). No device names, keys or free text beyond what receipts already carry.
"""
import json
import os
import threading
from pathlib import Path

VERSION = 1


class StateStore:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()

    @classmethod
    def for_server(cls, server):
        j = getattr(server, 'session_journal', None)
        p = getattr(j, 'path', None)
        return cls(Path(p).with_name('runtime-state.json')) if p else None

    def load(self):
        try:
            d = json.loads(self.path.read_text(encoding='utf-8'))
            return d if isinstance(d, dict) and d.get('version') == VERSION else {}
        except (OSError, ValueError):
            return {}

    def update(self, **fields):
        with self._lock:
            d = self.load()
            d.update(fields, version=VERSION)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(d, sort_keys=True, default=str), encoding='utf-8')
            os.replace(tmp, self.path)
