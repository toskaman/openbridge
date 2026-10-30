"""§7 server-side byte store for screen captures and pulled files.

Files live under <state-dir>/captures/<id>.bin. Ids are strict
(<kind>-<16 lowercase hex>) so a crafted id can never escape the directory.
Bounded: oldest files are evicted beyond max_files.
"""
import hashlib
import os
import re
import secrets
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

    def _path(self, cid):
        if not isinstance(cid, str) or not _ID.fullmatch(cid):
            raise StoreError(f'bad id {cid!r}')
        return self.root / (cid + '.bin')

    def put(self, data, kind='cap'):
        if kind not in KINDS:
            raise StoreError(f'bad kind {kind!r}')
        if not isinstance(data, (bytes, bytearray)) or not data or len(data) > MAX_FILE:
            raise StoreError('bad data')
        cid = f'{kind}-{secrets.token_hex(8)}'
        p = self._path(cid)
        while p.exists():  # paranoia: never overwrite
            cid = f'{kind}-{secrets.token_hex(8)}'
            p = self._path(cid)
        tmp = p.with_suffix('.tmp')
        tmp.write_bytes(bytes(data))
        os.replace(tmp, p)
        self._evict()
        return cid

    def get(self, cid):
        p = self._path(cid)
        try:
            return p.read_bytes()
        except OSError:
            raise StoreError(f'unknown id {cid!r}') from None

    def sha256(self, cid):
        return hashlib.sha256(self.get(cid)).hexdigest()

    def _evict(self):
        files = sorted(self.root.glob('*.bin'), key=lambda p: p.stat().st_mtime)
        for victim in files[:max(0, len(files) - self.max_files)]:
            try:
                victim.unlink()
            except OSError:
                pass
