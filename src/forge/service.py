"""Provider boundary and revocable service lifecycle. No hardware or OS dispatch."""
import copy
import threading
import time
from typing import Protocol
from src.forge.compiler import ForgeError, binding, compile_manifest, eligible, validate_manifest

class CapabilityProvider(Protocol):
    def snapshot(self,capability_id:str)->dict:
        """Return fresh trusted adapter data with current grants; never trust HTTP caller claims."""
        ...

class MemoryProvider:
    """Test-only provider. Integration must replace this with Claude's trusted snapshot bridge."""
    def __init__(self,manifest):self.current=copy.deepcopy(manifest)
    def snapshot(self,capability_id):
        if capability_id!=self.current['capability_id']:raise ForgeError('UNKNOWN_CAPABILITY')
        return copy.deepcopy(self.current)

class ForgeService:
    def __init__(self,provider,clock=time.time):
        self.provider=provider; self.clock=clock; self._services={}; self._lock=threading.RLock(); self._events=[]
    def _audit(self,operation,sid,outcome):
        self._events.append({'operation':operation,'service_id':sid,'outcome':outcome,'at':self.clock()})
        self._events=self._events[-200:]
    def _current(self,requested):
        current=eligible(self.provider.snapshot(requested['capability_id']),self.clock())
        if binding(current)!=binding(requested):raise ForgeError('PROVENANCE_CHANGED')
        return current
    def publish(self,manifest,*,consent=False):
        if consent is not True:raise ForgeError('OWNER_CONSENT_REQUIRED')
        requested=validate_manifest(manifest)
        with self._lock:
            current=self._current(requested); sid=current['service_id']
            if sid not in self._services and len(self._services)>=32:raise ForgeError('SERVICE_LIMIT')
            if sid in self._services and binding(self._services[sid])!=binding(current):raise ForgeError('SERVICE_ID_CONFLICT')
            self._services[sid]=current; self._audit('publish',sid,'published')
            return {'service_id':sid,'state':'published','simulation':current['simulation']}
    def read(self,sid):
        with self._lock:
            if sid not in self._services:raise ForgeError('SERVICE_REMOVED')
            try:current=self._current(self._services[sid])
            except ForgeError:
                self._audit('read',sid,'denied'); raise
            self._audit('read',sid,'verified')
            return {key:copy.deepcopy(current[key]) for key in ('service_id','device_id','relay_id','source','simulation','observed_at','evidence_refs','observations')}
    def documents(self,sid):
        with self._lock:
            if sid not in self._services:raise ForgeError('SERVICE_REMOVED')
            return compile_manifest(self._current(self._services[sid]))
    def remove(self,sid):
        with self._lock:
            self._services.pop(sid,None); self._audit('remove',sid,'revoked')
    def list_services(self):
        with self._lock:return [{'service_id':k,'simulation':v['simulation']} for k,v in sorted(self._services.items())]
    def history(self):
        with self._lock:return copy.deepcopy(self._events)
    def close(self):
        with self._lock:self._services.clear()
