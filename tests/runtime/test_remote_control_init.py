import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from src.runtime import api_v2
import src.runtime.remote_controls as controls

class Initialization(unittest.TestCase):
    def test_concurrent_first_reads_share_one_controller(self):
        server=SimpleNamespace(remote_controls=None)
        original=controls.RemoteControls;created=[];results=[]
        def slow(s):
            created.append(1);time.sleep(.05);return original(s)
        with patch.object(controls,'RemoteControls',slow):
            workers=[threading.Thread(target=lambda:results.append(api_v2.remote_controls(server))) for _ in range(8)]
            for worker in workers:worker.start()
            for worker in workers:worker.join(2)
        try:
            self.assertEqual(len(created),1)
            self.assertEqual(len({id(r) for r in results}),1)
        finally:
            for result in results:result.close()
