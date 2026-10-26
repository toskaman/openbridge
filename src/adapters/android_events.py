"""On-demand ADB connection events with redacted inventory and owned-process cleanup."""
from contextlib import contextmanager
import hashlib
import queue
import subprocess
import threading


class AndroidEventMonitor:
    def __init__(self,adapter,process_factory=subprocess.Popen):
        self.adapter=adapter
        self.factory=process_factory
        self._lock=threading.RLock()
        self._listeners=set()
        self._process=None
        self._thread=None
        self._stop=threading.Event()
        self._closed=False

    def publish(self,event):
        with self._lock:
            for listener in self._listeners:
                if listener.full():
                    try:listener.get_nowait()
                    except queue.Empty:pass
                try:listener.put_nowait(event)
                except queue.Full:pass

    @staticmethod
    def _stop_process(process):
        if process is None:return
        try:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait(timeout=2)
        except (OSError,subprocess.SubprocessError):pass

    def _watch(self,stop):
        process=None
        try:
            if stop.is_set():return
            process=self.factory([self.adapter.executable,'track-devices'],stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,bufsize=0,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            with self._lock:
                self._process=process
            if stop.is_set():return
            last_digest=None
            while not stop.is_set():
                header=self._read_exact(process.stdout,4)
                if header is None:break
                try:length=int(header,16)
                except ValueError:break
                if length>16384:break
                frame=self._read_exact(process.stdout,length)
                if frame is None:break
                digest=hashlib.sha256(frame).digest()
                if digest!=last_digest:
                    last_digest=digest
                    self.publish({'type':'inventory',**self.adapter.discover()})
        except (OSError,ValueError,subprocess.SubprocessError):
            pass
        finally:
            self._stop_process(process)
            if process is not None and process.stdout is not None:
                process.stdout.close()
            with self._lock:
                if not stop.is_set():
                    self.publish({'type':'unavailable','status':'ADB_UNAVAILABLE','devices':[]})
                if self._process is process:self._process=None
                if self._thread is threading.current_thread():self._thread=None
                if stop.is_set() and self._listeners and not self._closed:
                    self._start_locked()

    @staticmethod
    def _read_exact(stream,length):
        data=bytearray()
        while len(data)<length:
            chunk=stream.read(length-len(data))
            if not chunk:return None
            data.extend(chunk)
        return bytes(data)

    def _start_locked(self):
        self._stop=threading.Event()
        self._thread=threading.Thread(target=self._watch,args=(self._stop,),daemon=True)
        self._thread.start()

    @contextmanager
    def subscribe(self):
        subscription=queue.Queue(maxsize=8)
        with self._lock:
            if self._closed:raise ValueError('Android event monitor closed')
            self._listeners.add(subscription)
            if not self.adapter.executable:
                subscription.put({'type':'unavailable','status':'ADB_MISSING','devices':[]})
            else:
                subscription.put({'type':'inventory',**self.adapter.discover()})
                if self._thread is None or not self._thread.is_alive():
                    self._start_locked()
        try:yield subscription
        finally:
            process=None;thread=None
            with self._lock:
                self._listeners.discard(subscription)
                if not self._listeners:
                    self._stop.set();process=self._process;thread=self._thread
            if thread is not None:
                self._stop_process(process)
                thread.join(timeout=3)

    def close(self):
        with self._lock:
            self._closed=True;self._stop.set()
            process=self._process;thread=self._thread
            self.publish({'type':'closed'})
        self._stop_process(process)
        if thread is not None:thread.join(timeout=3)
