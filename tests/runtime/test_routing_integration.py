import threading
import time
import unittest
from unittest.mock import patch
from tests.runtime.test_routing import Base
from src.runtime.routing import RouteError
from src.runtime import api_v2

class TargetBinding(Base):
    def test_completed_retry_cannot_change_target(self):
        doc=self.routes('tv_volume_step',self.keys['tv'])
        lease=self.arm(doc,{'direction':'up'},'tv_volume_step',self.keys['tv'])
        self.invoke(lease,{'direction':'up'},'tv_volume_step',self.keys['tv'])
        with self.assertRaises(RouteError) as error:
            self.invoke(lease,{'direction':'up'},'tv_volume_step',self.keys['phone'])
        self.assertEqual(error.exception.code,'INVOCATION_ID_REUSED')
        self.assertEqual(len(self.calls),1)
    def test_router_is_singleton_under_concurrent_first_reads(self):
        import src.runtime.routing as routing
        original=routing.Router; self.server.skill_router=None
        entered=threading.Event();created=[];results=[]
        def slow(server):
            created.append(1);entered.set();time.sleep(.05);return original(server)
        with patch.object(routing,'Router',slow):
            workers=[threading.Thread(target=lambda:results.append(api_v2.router(self.server))) for _ in range(8)]
            for worker in workers:worker.start()
            for worker in workers:worker.join(2)
        self.assertEqual(len(created),1)
        self.assertEqual(len({id(r) for r in results}),1)
