"""Durable relay pairings: a server restart no longer forces the owner to re-pair every Companion.

Metadata (relay id, stable ADB serial, declared capabilities, negotiated transport) lives in a small JSON file written
atomically; the pairing key itself is stored only in the OS vault (DPAPI on Windows), never in the file. Without a
vault the store is disabled and pairings stay in memory, as before (no silent plaintext key on disk).
A corrupt file fails closed: nothing is restored, the error is reported, the file is left for inspection.
Read-modify-write cycles hold a thread lock plus an OS file lock (.lock sidecar, mirroring StateStore._locked),
so two processes sharing one store file can no longer lose pairings.
"""
import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

RID = re.compile(r'^relay-[0-9a-f]{6,32}$')
SERIAL = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')
VERSION = 1


class RelayStoreError(OSError):
    def __init__(self, code, detail):
        super().__init__(f'{code}: {detail}')
        self.code = code


def default_owner_store():
    """Owner dev-tool store: LOCALAPPDATA/OpenBridge/relays.json + OS vault.

    Single spelling of the owner path shared by relay_pair, preflight and
    the flagship vehicle, so a pairing made by one tool is visible to all.
    """
    from src.fabric.credential_vault import Vault
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
    return RelayStore(root / 'relays.json', Vault())


class RelayStore:
    def __init__(self, path, vault):
        self.path, self.vault = Path(path), vault
        self._lock = threading.Lock()
        self.error = None

    @property
    def enabled(self):
        return bool(self.vault is not None and getattr(self.vault, 'available', False))

    @contextmanager
    def _locked(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.with_suffix('.lock').open('a+b') as handle:
                if os.fstat(handle.fileno()).st_size == 0:
                    handle.write(b'0'); handle.flush()
                deadline = time.monotonic() + 5
                while True:
                    try:
                        handle.seek(0)
                        if os.name == 'nt':
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RelayStoreError('RELAY_STORE_LOCK_FAILED', 'Relay store is busy; operation blocked') from None
                        time.sleep(.01)
                try:
                    yield
                finally:
                    handle.seek(0)
                    if os.name == 'nt':
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self):
        if not self.path.exists():
            return {}
        try:
            doc = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(doc, dict) or doc.get('version') != VERSION or not isinstance(doc.get('relays'), dict):
                raise ValueError('unexpected layout')
            out = {}
            for rid, r in doc['relays'].items():
                if not RID.match(rid) or not isinstance(r, dict) or not SERIAL.match(str(r.get('serial', ''))):
                    raise ValueError('bad entry %r' % rid)
                out[rid] = r
            self.error = None
            return out
        except (OSError, ValueError) as e:
            self.error = 'relay store unreadable (%s); nothing restored, re-pair devices' % type(e).__name__
            raise

    def _write(self, relays):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.relays-', dir=str(self.path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump({'version': VERSION, 'relays': relays}, f, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def save(self, relay_id, serial, key, declared, aead=None):
        if not self.enabled or not RID.match(str(relay_id)) or not SERIAL.match(str(serial or '')):
            return False
        try:
            with self._locked():
                try:
                    relays = self._read()
                except (OSError, ValueError):
                    return False                                  # never overwrite a file we could not parse
                for other, r in list(relays.items()):            # one pairing per device: a re-pair replaces the old one
                    if r.get('serial') == serial and other != relay_id:
                        relays.pop(other)
                        self.vault.delete('relay-key-' + other[6:])
                self.vault.put('relay-key-' + relay_id[6:], key.hex())
                relays[relay_id] = {'serial': serial, 'aead': aead, 'paired_at': int(time.time()),
                                    'declared': {'capabilities': sorted(str(c) for c in (declared.get('capabilities') or [])),
                                                 'battery_powered': bool(declared.get('battery_powered'))}}
                self._write(relays)
                return True
        except RelayStoreError as e:
            self.error = 'relay store busy (%s); pairing not saved' % e.code
            return False

    def remove(self, relay_id):
        if not self.enabled:
            return
        try:
            with self._locked():
                try:
                    relays = self._read()
                except (OSError, ValueError):
                    return
                if relays.pop(relay_id, None) is not None:
                    self._write(relays)
                self.vault.delete('relay-key-' + str(relay_id)[6:])
        except RelayStoreError as e:
            self.error = 'relay store busy (%s); removal not applied' % e.code

    def load(self):
        """[(relay_id, serial, key bytes, declared, aead)]; entries whose key is missing are skipped."""
        if not self.enabled:
            return []
        try:
            with self._locked():
                try:
                    relays = self._read()
                except (OSError, ValueError):
                    return []
        except RelayStoreError as e:
            self.error = 'relay store busy (%s); nothing restored' % e.code
            return []
        out = []
        for rid, r in sorted(relays.items()):
            k = self.vault.get('relay-key-' + rid[6:])
            if not k or not re.fullmatch(r'[0-9a-f]{64}', k):
                continue
            out.append((rid, r['serial'], bytes.fromhex(k), r.get('declared') or {}, r.get('aead')))
        return out
