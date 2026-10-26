import io
import queue
import threading
import unittest
from src.adapters.android_events import AndroidEventMonitor


class FakeAdapter:
    executable='adb'
    def discover(self):
        return {'status':'READY','devices':[{'id':'opaque-handle','state':'device','source':'ADB','simulated':False}]}


class Process:
    def __init__(self,output):
        self.stdout=io.BytesIO(output);self.stopped=False
    def poll(self):return None if not self.stopped else 0
    def terminate(self):self.stopped=True
    def wait(self,timeout=None):self.stopped=True;return 0
    def kill(self):self.stopped=True


class AndroidEventTests(unittest.TestCase):
    def test_tracking_uses_fixed_command_and_never_publishes_raw_serial(self):
        calls=[]
        def factory(args,**kwargs):
            calls.append(args)
            payload=b'PRIVATE_SERIAL\tdevice\n'
            frame=f'{len(payload):04x}'.encode()+payload
            return Process(frame+frame)
        monitor=AndroidEventMonitor(FakeAdapter(),process_factory=factory)
        with monitor.subscribe() as subscription:
            messages=[]
            while True:
                event=subscription.get(timeout=3)
                messages.append(event)
                if event['type']=='unavailable':break
            self.assertNotIn('PRIVATE_SERIAL',str(messages))
            self.assertEqual(sum(e['type']=='inventory' for e in messages),2)
        monitor.close()
        self.assertEqual(calls,[['adb','track-devices']])

    def test_missing_adb_is_unavailable_without_process(self):
        adapter=FakeAdapter();adapter.executable=None
        def forbidden(*args,**kwargs):raise AssertionError('Must not spawn ADB')
        monitor=AndroidEventMonitor(adapter,process_factory=forbidden)
        with monitor.subscribe() as subscription:
            self.assertEqual(subscription.get(timeout=1)['type'],'unavailable')
        monitor.close()

    def test_last_subscriber_stops_owned_process(self):
        stop=threading.Event()
        class Stream:
            def read(self,length):
                stop.wait(3)
                return b''
            def close(self):stop.set()
        process=Process(b'');process.stdout=Stream()
        original=process.terminate
        def terminate():stop.set();original()
        process.terminate=terminate
        monitor=AndroidEventMonitor(FakeAdapter(),process_factory=lambda *a,**k:process)
        with monitor.subscribe() as subscription:
            self.assertEqual(subscription.get(timeout=1)['type'],'inventory')
        self.assertTrue(process.stopped)
        monitor.close()

    def test_slow_subscriber_queue_is_bounded(self):
        monitor=AndroidEventMonitor(FakeAdapter(),process_factory=lambda *a,**k:Process(b''))
        with monitor.subscribe() as subscription:
            for i in range(100):monitor.publish({'type':'inventory','sequence':i})
            self.assertLessEqual(subscription.qsize(),8)
        monitor.close()

    def test_reconnect_during_old_tracker_teardown_starts_replacement(self):
        entered=threading.Event();release=threading.Event();terminated=threading.Event();replacement=threading.Event()
        class Stream:
            def read(self,length):entered.set();release.wait(3);return b''
            def close(self):release.set()
        first=Process(b'');first.stdout=Stream()
        def terminate():first.stopped=True;terminated.set()
        first.terminate=terminate
        calls=[]
        def factory(*args,**kwargs):
            calls.append(1)
            if len(calls)==1:return first
            replacement.set();return Process(b'0000')
        monitor=AndroidEventMonitor(FakeAdapter(),process_factory=factory)
        original=monitor.subscribe();original.__enter__()
        self.assertTrue(entered.wait(1))
        cleanup=threading.Thread(target=lambda:original.__exit__(None,None,None));cleanup.start()
        self.assertTrue(terminated.wait(1))
        with monitor.subscribe():
            release.set()
            self.assertTrue(replacement.wait(2),'A subscriber must not retain a stopped tracker')
            self.assertEqual(len(calls),2)
        cleanup.join(3);monitor.close()

    def test_new_tracker_does_not_receive_old_terminal_event(self):
        terminal=threading.Event();allow_terminal=threading.Event();second_started=threading.Event();release=threading.Event()
        class LiveStream:
            initial=True
            def read(self,length):
                if self.initial:self.initial=False;return b'0000'
                release.wait(3);return b''
            def close(self):release.set()
        live=Process(b'');live.stdout=LiveStream()
        def terminate():live.stopped=True;release.set()
        live.terminate=terminate
        launches=[]
        def factory(*args,**kwargs):
            launches.append(1)
            return Process(b'') if len(launches)==1 else live
        monitor=AndroidEventMonitor(FakeAdapter(),process_factory=factory)
        original_publish=monitor.publish
        def publish(event):
            if event['type']=='unavailable' and len(launches)==1:
                terminal.set();allow_terminal.wait(3)
            original_publish(event)
        monitor.publish=publish
        first=monitor.subscribe();first.__enter__()
        self.assertTrue(terminal.wait(1))
        connected=queue.Queue()
        def reconnect():
            second_started.set();context=monitor.subscribe();events=context.__enter__();connected.put((context,events))
        worker=threading.Thread(target=reconnect);worker.start()
        self.assertTrue(second_started.wait(1))
        allow_terminal.set()
        context,events=connected.get(timeout=3)
        messages=[events.get(timeout=2),events.get(timeout=2)]
        self.assertEqual([event['type'] for event in messages],['inventory','inventory'])
        first.__exit__(None,None,None);context.__exit__(None,None,None)
        worker.join(2);monitor.close()
