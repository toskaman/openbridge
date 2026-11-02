"""Per-PC full-control consent: deep Windows rights stay OFF unless the owner opts in.

Enabled PCs allow the managed-file skills (pc_place_file, pc_wallpaper)
in addition to the read-only + scoped-open surface. The file holds only
opaque PC identity hashes (never names); a corrupt file fails closed
(everything reads OFF). Written atomically, like the relay store.
"""
import contextlib
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

FILENAME = 'pc_full_control.json'
VERSION = 1
IDENTITY = re.compile(r'^[0-9a-f]{8,64}$')

FULL_CONTROL_WARNING = """FULL CONTROL for this PC — read before confirming.

ON allows OpenBridge, only with per-call owner consent, to:
- write files into %LOCALAPPDATA%\\OpenBridge\\managed\\ (bounded size, allowlisted image types, hashed);
- apply one of those managed files as the desktop wallpaper (previous value recorded).

ON never allows: arbitrary shell from natural language, deletes outside
the managed dir, writes anywhere else, silent or recurring actions.

Revoke any time (toggle OFF): new deep actions stop immediately.
"""


class ConsentError(ValueError):
    pass


class PcConsentStore:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.error = None

    def _read(self):
        if not self.path.exists():
            return {}
        try:
            doc = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(doc, dict) or doc.get('version') != VERSION \
                    or not isinstance(doc.get('pcs'), dict):
                raise ValueError('unexpected layout')
            out = {}
            for ident, row in doc['pcs'].items():
                if not IDENTITY.match(str(ident)) or not isinstance(row, dict) \
                        or not isinstance(row.get('enabled'), bool):
                    raise ValueError('bad entry %r' % ident)
                out[str(ident)] = {'enabled': row['enabled'],
                                   'at': int(row.get('at') or 0)}
            self.error = None
            return out
        except (OSError, ValueError) as e:
            self.error = 'consent store unreadable (%s); all PCs read OFF' % type(e).__name__
            raise

    def _write(self, pcs):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.pcfc-', dir=str(self.path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump({'version': VERSION, 'pcs': pcs}, f, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def allowed(self, identity):
        try:
            with self._lock:
                pcs = self._read()
        except (OSError, ValueError):
            return False
        return bool(pcs.get(str(identity), {}).get('enabled', False))

    def set(self, identity, enabled, confirm=False):
        if not IDENTITY.match(str(identity or '')):
            raise ConsentError('identity must be an opaque hex hash')
        if enabled and not confirm:
            raise ConsentError('enabling full control needs explicit confirm')
        with self._lock:
            try:
                pcs = self._read()
            except (OSError, ValueError):
                return False
            pcs[str(identity)] = {'enabled': bool(enabled), 'at': int(time.time())}
            self._write(pcs)
            return True


@contextlib.contextmanager
def temp_dir():
    with tempfile.TemporaryDirectory(prefix='ob-pcfc-') as tmp:
        yield Path(tmp)


@contextlib.contextmanager
def temp_store():
    with temp_dir() as path:
        yield PcConsentStore(path / FILENAME)
