"""OS-protected secret storage. Windows: DPAPI (CryptProtectData, current user). Elsewhere: not supported
(secrets stay in memory only) rather than falling back to plaintext files. Secrets are never logged."""
import ctypes
import os
import sys
from pathlib import Path


class VaultUnavailable(RuntimeError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [('cbData', ctypes.c_uint32), ('pbData', ctypes.POINTER(ctypes.c_char))]


def _dpapi(data, protect, entropy):
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    src = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    ent = _Blob(len(entropy), ctypes.cast(ctypes.create_string_buffer(entropy, len(entropy)), ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x1, ctypes.byref(out))  # UI_FORBIDDEN
    if not ok:
        raise VaultUnavailable('DPAPI operation failed')
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


class Vault:
    def __init__(self, root=None, backend=None):
        self.root = Path(root or os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'vault'
        if backend is not None:
            self.protect, self.unprotect = backend
        elif sys.platform == 'win32':
            self.protect = lambda d, e: _dpapi(d, True, e)
            self.unprotect = lambda d, e: _dpapi(d, False, e)
        else:
            self.protect = self.unprotect = None

    @property
    def available(self):
        return self.protect is not None

    def _path(self, name):
        if not name.replace('-', '').replace('_', '').isalnum() or len(name) > 64:
            raise ValueError('Invalid secret name')
        return self.root / (name + '.bin')

    def put(self, name, secret: str):
        if not self.available:
            raise VaultUnavailable('No OS secret store on this platform; secret kept in memory only')
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(name).write_bytes(self.protect(secret.encode(), name.encode()))

    def get(self, name):
        path = self._path(name)
        if not self.available or not path.exists():
            return None
        try:
            return self.unprotect(path.read_bytes(), name.encode()).decode()
        except (VaultUnavailable, UnicodeError):
            return None

    def delete(self, name):
        try:
            self._path(name).unlink()
        except FileNotFoundError:
            pass
