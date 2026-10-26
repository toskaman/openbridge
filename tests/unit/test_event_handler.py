from contextlib import contextmanager
from email.message import Message
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from src.server import Handler


class EventHandlerTests(unittest.TestCase):
    def test_windows_connection_abort_releases_subscription_without_traceback(self):
        monitor=SimpleNamespace(released=False)
        @contextmanager
        def subscribe():
            events=queue.Queue();events.put({'type':'inventory','devices':[]})
            try:yield events
            finally:monitor.released=True
        monitor.subscribe=subscribe
        handler=object.__new__(Handler)
        handler.path='/api/device-events?source=android'
        handler.headers=Message();handler.headers['Host']='127.0.0.1:18765'
        handler.server=SimpleNamespace(server_port=18765,android_events=monitor)
        handler.send_response=Mock();handler.send_header=Mock();handler.end_headers=Mock()
        handler.connection=Mock();handler.wfile=Mock()
        handler.wfile.write.side_effect=ConnectionAbortedError('Simulated Windows disconnect')
        handler.do_GET()
        self.assertTrue(monitor.released)
