"""Consumer of Claude's Device Capability Contract v1. Never executes a primitive."""
from datetime import datetime
import hashlib
import re
import time
from urllib.parse import quote
from src.forge.compiler import ForgeError,eligible


def opaque(kind,value):
    return kind+'-'+hashlib.sha256(value.encode()).hexdigest()[:24]

class RuntimeV1Provider:
    """read_json is a trusted internal authenticated GET client, not supplied by HTTP/model input.

    Capability and target bindings are selected by the integration layer. Only the five approved
    v1 read endpoints are used. Unknown additive fields are ignored; missing authority blocks.
    """
    def __init__(self,read_json,runtime_capability_id,target_device,relay_id,*,allow_simulated=False,clock=time.time):
        for value in (runtime_capability_id,target_device,relay_id):
            if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',value):raise ForgeError('RUNTIME_BINDING_INVALID')
        self.read=read_json;self.runtime_id=runtime_capability_id;self.target=target_device;self.relay=relay_id
        self.allow_simulated=allow_simulated;self.clock=clock
        self.capability_id=opaque('cap',runtime_capability_id+'|'+target_device+'|'+relay_id)
    def _authority(self):
        graph=self.read('/api/v2/graph');caps=self.read('/api/v2/capabilities');routes=self.read('/api/v2/routes')
        cap=[c for c in caps.get('capabilities',[]) if c.get('capability_id')==self.runtime_id]
        route=[r for r in routes.get('routes',[]) if r.get('relay_id')==self.relay and r.get('radio')=='ble' and r.get('target_device') in ('*',self.target)]
        if len(cap)!=1 or len(route)!=1:raise ForgeError('RUNTIME_CAPABILITY_OR_ROUTE_UNKNOWN')
        cap,route=cap[0],route[0];source='RELAY:'+self.relay
        if cap.get('name')!='ble_relay' or cap.get('source')!=source or cap.get('device_key')!=route.get('relay_device'):raise ForgeError('RUNTIME_PROVENANCE_MISMATCH')
        if any(cap.get(k) is not True for k in ('discovered','observed','readable')) or 'relay_ble_scan' not in cap.get('operations',[]):raise ForgeError('RUNTIME_CAPABILITY_UNAVAILABLE')
        status=cap.get('verified')
        if status!='REAL_HARDWARE_VERIFIED' and not (self.allow_simulated is True and status=='SIMULATED_VERIFIED'):raise ForgeError('RUNTIME_CAPABILITY_UNVERIFIED')
        for key in ('permission_granted','owner_enabled','online'):
            if route.get(key) is not True:raise ForgeError('RUNTIME_PERMISSION_OR_RELAY_UNAVAILABLE')
        permissions=cap.get('permissions',[])
        for required in ('android.permission.BLUETOOTH_SCAN','pairing'):
            rows=[p for p in permissions if p.get('name')==required]
            if len(rows)!=1 or rows[0].get('granted') is not True:raise ForgeError('RUNTIME_PERMISSION_DENIED')
        devices={}
        for d in graph.get('devices',[]):
            key=d.get('device_key')
            if key in devices:raise ForgeError('RUNTIME_IDENTITY_CONFLICT')
            devices[key]=d
        for key in (self.target,route['relay_device']):
            if key not in devices or devices[key].get('possibly_same_as')!=[]:raise ForgeError('RUNTIME_DEVICE_ABSENT_OR_AMBIGUOUS')
        links=[l for l in graph.get('links',[]) if l.get('parent')==route['relay_device'] and l.get('child')==self.target and l.get('source')==source and l.get('transport')=='BLE' and 'observe' in l.get('grants',[])]
        if len(links)!=1:raise ForgeError('RUNTIME_TARGET_PROVENANCE_MISSING')
        return {'source':source,'status':status,'relay_device':route['relay_device']}
    def snapshot(self,capability_id):
        if capability_id!=self.capability_id:raise ForgeError('UNKNOWN_CAPABILITY')
        try:
            contract=self.read('/api/v2/contract')
            if not isinstance(contract.get('version'),str) or contract['version'].split('.')[0]!='1':raise ForgeError('RUNTIME_CONTRACT_INCOMPATIBLE')
            authority=self._authority()
            data=self.read('/api/v2/facts?device='+quote(self.target,safe='')+'&source='+quote(authority['source'],safe=''))
            if data.get('device')!=self.target:raise ForgeError('RUNTIME_FACT_DEVICE_MISMATCH')
            facts=[f for f in data.get('facts',[]) if f.get('name')=='ble_rssi']
            if len(facts)!=1:raise ForgeError('RUNTIME_SIGNAL_ABSENT_OR_AMBIGUOUS')
            fact=facts[0]
            if fact.get('device_key')!=self.target or fact.get('sources')!=[authority['source']] or fact.get('verified') is not True or fact.get('inferred') is not False:raise ForgeError('RUNTIME_FACT_UNTRUSTED')
            observed=datetime.fromisoformat(fact['observed_at'])
            if observed.tzinfo is None:raise ForgeError('RUNTIME_TIME_UNTRUSTED')
            if self._authority()!=authority:raise ForgeError('RUNTIME_AUTHORITY_CHANGED')
            m={'version':1,'service_id':opaque('service',self.capability_id),'capability_id':self.capability_id,'device_id':opaque('device',self.target),'relay_id':opaque('relay',self.relay),'status':authority['status'],'verified':True,'operation':'read_observations','permissions':['observe','read'],'available':True,'device_present':True,'identity_conflict':False,'observed_at':observed.timestamp(),'max_age_seconds':120,'evidence_refs':[opaque('evidence',self.target+'|'+authority['source']+'|'+fact['observed_at'])],'observations':[{'observation_id':opaque('obs',self.target),'rssi_dbm':fact['value']}],'simulation':authority['status']=='SIMULATED_VERIFIED'}
            m['source']='RELAY:'+m['relay_id']
            return eligible(m,self.clock())
        except ForgeError:raise
        except Exception:raise ForgeError('RUNTIME_SNAPSHOT_UNAVAILABLE') from None
