"""RetroArch network-command client (loopback UDP only).

Talks to a local RetroArch with `network_cmd_enable=true` (default port 55355)
using its plaintext command protocol. Only this PC is ever contacted: the host
is pinned to 127.0.0.1 and only allowlisted commands are sent. QUIT is
deliberately excluded: killing the user's emulator session is not a dashboard
action.

Observed on RetroArch 1.21.0 (2026-10-30): queries (VERSION, GET_STATUS)
reply; actions (PAUSE_TOGGLE, VOLUME_UP, VOLUME_DOWN) are fire-and-forget and
send no reply. Actions therefore report delivery, never verified effect.
"""
import socket

DEFAULT_PORT = 55355
QUERIES = ('VERSION', 'GET_STATUS')
ACTIONS = ('PAUSE_TOGGLE', 'VOLUME_UP', 'VOLUME_DOWN')
ALLOWED = QUERIES + ACTIONS
MAX_REPLY = 4096


class RetroArchError(ValueError):
    pass


class RetroArch:
    def __init__(self, port=DEFAULT_PORT, host='127.0.0.1', timeout=5):
        if host != '127.0.0.1':
            raise RetroArchError('only loopback RetroArch is contacted')
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise RetroArchError('bad port')
        self.port, self.timeout = port, timeout

    def command(self, name):
        """Queries return the reply text; actions return 'SENT' (delivered, effect unverified)."""
        if name not in ALLOWED:
            raise RetroArchError(f'command not allowlisted: {name!r}')
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            sock.sendto((name + '\n').encode(), ('127.0.0.1', self.port))
            if name not in QUERIES:
                return 'SENT'
            data, _ = sock.recvfrom(MAX_REPLY)
        except (OSError, socket.timeout) as e:
            raise RetroArchError(f'RetroArch unreachable on 127.0.0.1:{self.port} ({e})') from None
        finally:
            sock.close()
        return data.decode('utf-8', 'replace').strip()
