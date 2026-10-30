"""RetroArch network-command adapter (loopback UDP, real socket, fake server)."""
import socket
import threading
import time
import unittest

from src.adapters.retroarch import RetroArch, RetroArchError


class FakeRetroArch:
    """Minimal UDP command server speaking the RetroArch plaintext protocol."""

    def __init__(self, replies=None):
        self.replies = replies or {}
        self.seen = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        self.sock.settimeout(0.1)
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            cmd = data.decode('utf-8', 'replace').strip()
            self.seen.append(cmd)
            self.sock.sendto(self.replies.get(cmd, 'UNKNOWN_COMMAND\n').encode(), addr)

    def close(self):
        self._stop.set()
        self.thread.join(timeout=2)
        self.sock.close()


class RetroArchTests(unittest.TestCase):
    def test_version_round_trip(self):
        srv = FakeRetroArch({'VERSION': '1.21.0\n'})
        try:
            self.assertEqual(RetroArch(port=srv.port).command('VERSION'), '1.21.0')
            self.assertEqual(srv.seen, ['VERSION'])
        finally:
            srv.close()

    def test_action_is_fire_and_forget(self):
        srv = FakeRetroArch()
        try:
            self.assertEqual(RetroArch(port=srv.port).command('VOLUME_UP'), 'SENT')
            deadline = time.monotonic() + 5.0  # UDP thread may lag on loaded CI
            while 'VOLUME_UP' not in srv.seen and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(srv.seen, ['VOLUME_UP'])
        finally:
            srv.close()

    def test_rejects_unknown_command_without_sending(self):
        srv = FakeRetroArch()
        try:
            with self.assertRaises(RetroArchError):
                RetroArch(port=srv.port).command('FORMAT C:')
            self.assertEqual(srv.seen, [])
        finally:
            srv.close()

    def test_timeout_is_retro_unavailable(self):
        dead = FakeRetroArch()
        dead.close()
        with self.assertRaises(RetroArchError):
            RetroArch(port=dead.port, timeout=0.2).command('VERSION')

    def test_only_loopback(self):
        with self.assertRaises(RetroArchError):
            RetroArch(host='192.168.1.99', port=55355)

    def test_allowlist_is_auditable(self):
        from src.adapters import retroarch as R
        self.assertIn('VERSION', R.ALLOWED)
        self.assertNotIn('QUIT', R.ALLOWED)  # killing the emulator is not a dashboard action


if __name__ == '__main__':
    unittest.main()
