"""§7 server-side byte store for screen captures and pulled files.

Files live under <state-dir>/captures/<id>.bin. Ids are strict
(<kind>-<16 lowercase hex>) so a crafted id can never escape the directory.
Bounded: oldest-inserted files are evicted beyond max_files, ordered by an
on-disk sequence index (filesystem mtimes are too coarse to order rapid puts
reliably, and ties evicted the wrong file on Windows CI).
"""
import hashlib
import json
import os
import re
import secrets
import threading
from pathlib import Path

MAX_FILE = 32 * 1024 * 1024
MAX_FILES = 64
KINDS = ('cap', 'xfer')
_ID = re.compile(r'(cap|xfer)-[0-9a-f]{16}')


class StoreError(ValueError):
    pass


class CaptureStore:
    def __init__(self, root, max_files=MAX_FILES):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_files = max_files
        self._lock = threading.Lock()

    def _path(self, cid):
        if not isinstance(cid, str) or not _ID.fullmatch(cid):
            raise StoreError(f'bad id {cid!r}')
        return self.root / (cid + '.bin')

    def _read_index(self):
        try:
            idx = json.loads((self.root / 'index.json').read_text(encoding='utf-8'))
            return idx if isinstance(idx, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_index(self, idx):
        tmp = self.root / 'index.json.tmp'
        tmp.write_text(json.dumps(idx), encoding='utf-8')
        os.replace(tmp, self.root / 'index.json')

    def put(self, data, kind='cap'):
        if kind not in KINDS:
            raise StoreError(f'bad kind {kind!r}')
        if not isinstance(data, (bytes, bytearray)) or not data or len(data) > MAX_FILE:
            raise StoreError('bad data')
        with self._lock:
            idx = self._read_index()
            cid = f'{kind}-{secrets.token_hex(8)}'
            p = self._path(cid)
            while p.exists() or cid in idx:  # paranoia: never overwrite
                cid = f'{kind}-{secrets.token_hex(8)}'
                p = self._path(cid)
            tmp = p.with_suffix('.tmp')
            tmp.write_bytes(bytes(data))
            os.replace(tmp, p)
            idx[cid] = max([0] + [v for v in idx.values() if isinstance(v, int)]) + 1
            self._write_index(idx)
            self._evict(idx)
            return cid

    def get(self, cid):
        p = self._path(cid)
        try:
            return p.read_bytes()
        except OSError:
            raise StoreError(f'unknown id {cid!r}') from None

    def sha256(self, cid):
        return hashlib.sha256(self.get(cid)).hexdigest()

    def _evict(self, idx=None):
        idx = self._read_index() if idx is None else idx
        files = sorted(self.root.glob('*.bin'),
                       key=lambda p: (idx.get(p.stem, 0)
                                      if isinstance(idx.get(p.stem), int) else 0,
                                      p.name))
        victims = files[:max(0, len(files) - self.max_files)]
        for victim in victims:
            try:
                victim.unlink()
            except OSError:
                pass
            idx.pop(victim.stem, None)
        if victims:
            # Prune index entries whose files are gone (manual deletes, crashes).
            live = {p.stem for p in self.root.glob('*.bin')}
            for stale in [k for k in idx if k not in live]:
                del idx[stale]
            self._write_index(idx)
