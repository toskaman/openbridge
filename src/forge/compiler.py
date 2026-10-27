"""Strict versioned manifests -> documents, never executable model output."""
import copy
import hashlib
import json
import math
import re

class ForgeError(ValueError):
    pass

FIELDS={'version','service_id','capability_id','device_id','relay_id','source','status','verified','operation','permissions','available','device_present','identity_conflict','observed_at','max_age_seconds','evidence_refs','observations','simulation'}
ID=re.compile(r'[a-z][a-z0-9_.-]{0,63}\Z')
OBSERVATION_SCHEMA={'type':'object','additionalProperties':False,'required':['observation_id','rssi_dbm'], 'properties':{'observation_id':{'type':'string','maxLength':64},'rssi_dbm':{'type':'integer','minimum':-127,'maximum':20},'name':{'type':'string','maxLength':60},'manufacturer_data_hex':{'type':'string','pattern':'^(?:[0-9a-f]{2}){0,64}$'}}}

def validate_manifest(value):
    if not isinstance(value,dict) or set(value)!=FIELDS:raise ForgeError('MANIFEST_SHAPE')
    m=copy.deepcopy(value)
    if type(m['version']) is not int or m['version']!=1:raise ForgeError('MANIFEST_VERSION')
    for key in ('service_id','capability_id','device_id','relay_id'):
        if not isinstance(m[key],str) or not ID.fullmatch(m[key]):raise ForgeError('INVALID_IDENTIFIER')
    if m['operation']!='read_observations' or m['source']!='RELAY:'+m['relay_id']:raise ForgeError('UNAPPROVED_PRIMITIVE_OR_SOURCE')
    if type(m['simulation']) is not bool or m['status']!=('SIMULATED_VERIFIED' if m['simulation'] else 'REAL_HARDWARE_VERIFIED') or m['verified'] is not True:raise ForgeError('CAPABILITY_UNVERIFIED')
    if not isinstance(m['permissions'],list) or any(not isinstance(p,str) for p in m['permissions']) or len(set(m['permissions']))!=len(m['permissions']) or set(m['permissions'])-{'observe','read'}:raise ForgeError('INVALID_PERMISSION')
    for key in ('available','device_present','identity_conflict'):
        if type(m[key]) is not bool:raise ForgeError('INVALID_AVAILABILITY')
    if type(m['observed_at']) not in (int,float) or not math.isfinite(m['observed_at']):raise ForgeError('INVALID_TIMESTAMP')
    if type(m['max_age_seconds']) is not int or not 1<=m['max_age_seconds']<=300:raise ForgeError('INVALID_FRESHNESS')
    refs=m['evidence_refs']
    if not isinstance(refs,list) or not 1<=len(refs)<=32 or any(not isinstance(r,str) or not ID.fullmatch(r) for r in refs) or len(set(refs))!=len(refs):raise ForgeError('INVALID_EVIDENCE')
    if not isinstance(m['observations'],list) or not 1<=len(m['observations'])<=200:raise ForgeError('DATA_ABSENT')
    seen=set()
    for o in m['observations']:
        if not isinstance(o,dict) or set(o)-set(OBSERVATION_SCHEMA['properties']) or not {'observation_id','rssi_dbm'}<=set(o):raise ForgeError('OBSERVATION_SHAPE')
        oid=o['observation_id']
        if not isinstance(oid,str) or not ID.fullmatch(oid) or oid in seen:raise ForgeError('OBSERVATION_ID')
        seen.add(oid)
        if type(o['rssi_dbm']) is not int or not -127<=o['rssi_dbm']<=20:raise ForgeError('INVALID_SIGNAL')
        if 'name' in o and (not isinstance(o['name'],str) or len(o['name'])>60 or any(ord(c)<32 for c in o['name'])):raise ForgeError('INVALID_NAME')
        if 'manufacturer_data_hex' in o and (not isinstance(o['manufacturer_data_hex'],str) or not re.fullmatch(r'(?:[0-9a-f]{2}){0,64}',o['manufacturer_data_hex'])):raise ForgeError('INVALID_MANUFACTURER_DATA')
    return m

def eligible(m,now):
    m=validate_manifest(m)
    if not m['available'] or not m['device_present']:raise ForgeError('RELAY_OR_DEVICE_UNAVAILABLE')
    if m['identity_conflict']:raise ForgeError('IDENTITY_CONFLICT')
    if not {'observe','read'}<=set(m['permissions']):raise ForgeError('PERMISSION_DENIED')
    if not 0<=now-m['observed_at']<=m['max_age_seconds']:raise ForgeError('OBSERVATION_EXPIRED')
    return m

def binding(m):
    return tuple(m[k] for k in ('version','service_id','capability_id','device_id','relay_id','source','status','simulation','operation'))

def compile_manifest(value):
    m=validate_manifest(value)
    path='/v1/services/'+m['service_id']+'/observations'
    response={'type':'object','additionalProperties':False,'required':['service_id','device_id','relay_id','source','simulation','observed_at','evidence_refs','observations'], 'properties':{
        'service_id':{'const':m['service_id']},'device_id':{'const':m['device_id']},'relay_id':{'const':m['relay_id']},'source':{'const':m['source']},'simulation':{'const':m['simulation']},'observed_at':{'type':'number'},'evidence_refs':{'type':'array','items':{'type':'string'}},'observations':{'type':'array','items':{'$ref':'#/components/schemas/Observation'}}}}
    error={'type':'object','additionalProperties':False,'required':['error'],'properties':{'error':{'type':'string'}}}
    schemas={'Observation':copy.deepcopy(OBSERVATION_SCHEMA),'ObservationResponse':response,'Error':error}
    responses={'200':{'description':'Fresh approved observations','content':{'application/json':{'schema':{'$ref':'#/components/schemas/ObservationResponse'}}}}}
    for code,description in ((401,'Authentication required'),(404,'Service removed'),(409,'Permission, provenance or freshness denied')):
        responses[str(code)]={'description':description,'content':{'application/json':{'schema':{'$ref':'#/components/schemas/Error'}}}}
    api={'openapi':'3.1.0','jsonSchemaDialect':'https://json-schema.org/draft/2020-12/schema',
         'info':{'title':'OpenBridge Capability Forge','version':'1.0.0'},
         'servers':[{'url':'http://127.0.0.1:18766'}], 'security':[{'LocalBearer':[]}],
         'paths':{path:{'get':{'operationId':'read_observations','summary':'Read verified relay observations','responses':responses}}},
         'components':{'securitySchemes':{'LocalBearer':{'type':'http','scheme':'bearer','description':'Ephemeral local token; never embedded in generated documents'}},'schemas':schemas}}

    client='''"""Fixed read-only local client; supply token separately."""\nimport json\nfrom urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler\nclass NoRedirect(HTTPRedirectHandler):\n    def redirect_request(self, *args, **kwargs): return None\ndef read_observations(token):\n    req=Request(URL,headers={"Authorization":"Bearer "+token})\n    with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=5) as response:\n        return json.loads(response.read(131072))\n'''.replace('URL',repr('http://127.0.0.1:18766'+path))
    canonical=json.dumps(m,sort_keys=True,separators=(',',':')).encode()
    standalone={name:{'$schema':'https://json-schema.org/draft/2020-12/schema','$defs':{'Observation':copy.deepcopy(OBSERVATION_SCHEMA)},**json.loads(json.dumps(schema).replace('#/components/schemas/Observation','#/$defs/Observation'))} for name,schema in schemas.items()}
    return {'openapi':api,'schemas':standalone,'python_client':client,'manifest_sha256':hashlib.sha256(canonical).hexdigest(),'documentation':f"Read-only service {m['service_id']} via {m['relay_id']}. Requires observe/read grants and separate owner consent. Maximum age {m['max_age_seconds']} seconds. Signal observations are not temperature or battery measurements. Simulation: {m['simulation']}."}
