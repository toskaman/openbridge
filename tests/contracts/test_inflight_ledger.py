import threading
import unittest
from src.runtime.route_contract import InvocationLedger

class InflightExpiry(unittest.TestCase):
    def test_expired_age_cannot_redispatch_running_invocation(self):
        now = [0]
        ledger = InvocationLedger(ttl_s=1, clock=lambda: now[0])
        started = threading.Event(); release = threading.Event(); duplicate = threading.Event()
        calls = []; errors = []; results = []
        def original():
            calls.append('original'); started.set(); release.wait(2); return {'state':'VERIFIED'}
        def invoke(callback):
            try: results.append(ledger.run('owner','same-id','binding',callback))
            except Exception as error: errors.append(type(error).__name__)
        one = threading.Thread(target=invoke,args=(original,)); one.start(); self.assertTrue(started.wait(1)); now[0] = 2
        def again(): calls.append('duplicate'); duplicate.set(); return {'state':'DUPLICATE'}
        two = threading.Thread(target=invoke,args=(again,)); two.start()
        try: duplicate.wait(.1)
        finally: release.set(); one.join(2); two.join(2)
        self.assertEqual(calls,['original'])
        self.assertEqual(errors,[])
        self.assertEqual(results,[{'state':'VERIFIED'},{'state':'VERIFIED'}])
