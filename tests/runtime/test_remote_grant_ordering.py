import threading
import time
import unittest
from tests.runtime import test_remote_controls as fixtures

class GrantOrdering(unittest.TestCase):
    def test_slow_old_grant_cannot_undo_a_newer_revocation(self):
        h=fixtures.RemoteControls();h.setUp();self.addCleanup(h.rc.close)
        started=threading.Event();release=threading.Event();errors=[]
        original=h.rc._send
        def slow(rid,op,params=None):
            if op=='set_controls' and params['controls'] and not started.is_set():
                started.set();release.wait(2)
            return original(rid,op,params)
        h.rc._send=slow
        body={'relay_id':'r-watch','consent':True,'controls':[{'label':'Volume +','skill_id':'tv_volume_step','target':h.keys['tv'],'params':{'direction':'up'}}]}
        def grant():
            try:h.rc.set_controls(body)
            except Exception as e:errors.append(type(e).__name__)
        worker=threading.Thread(target=grant);worker.start();self.assertTrue(started.wait(1))
        revoker=threading.Thread(target=lambda:h.rc.set_controls({'relay_id':'r-watch','consent':True,'controls':[]}))
        revoker.start()
        deadline=time.monotonic()+1
        while h.rc._grant_versions.get('r-watch') != 2 and time.monotonic()<deadline:
            time.sleep(.005)
        release.set();worker.join(2);revoker.join(2)
        self.assertFalse(worker.is_alive());self.assertFalse(revoker.is_alive())
        self.assertEqual(errors,[])
        self.assertEqual(h.rc.state()['controls'],[])
        self.assertEqual(h.calls,[])
        self.assertEqual(h.companion.controls,[])
