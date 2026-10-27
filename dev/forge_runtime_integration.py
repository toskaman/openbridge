"""Run only in a throwaway runtime+Forge integration build. No hardware, network discovery or writes."""
import json
from pathlib import Path
import tempfile
import threading
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from src.server import create_server
from src.runtime.api_v2 import reader
from src.fabric.registry import Registry
from src.fabric.contracts import Identifier,Capability,Link
from src.fabric.discovery import ingest_ble
from src.fabric.session import SessionJournal
from src.forge.runtime_bridge import RuntimeV1Provider
from src.forge.demo_host import create_forge_server

with tempfile.TemporaryDirectory() as directory:
 runtime=create_server(0,fabric_salt=b'fixture-only-salt',session_journal=SessionJournal(Path(directory)/'session.sqlite'))
 registry=Registry();relay=registry.upsert([Identifier('companion_key','test-only',True)],category='phone',label='Controlled test relay')
 registry.devices[relay].setdefault('handles',{})['USB']='test-handle'
 registry.link(Link('pc',relay,'USB',('observe','read'),'ADB'))
 rid='fixture-relay'
 runtime.relays.enroll(rid,b'fixture-key','test-handle',{'capabilities':['ble_scan'],'permissions':{'BLUETOOTH_SCAN':True,'owner_enabled':True}})
 observations=[{'address':'01:02:03:04:05:06','address_kind':'static_random','rssi':-61,'company_ids':[],'service_uuids':[],'name':'Fixture advertiser'}]
 ingest_ble(registry,{'devices':observations},b'fixture-salt',observer=relay,source='RELAY:'+rid)
 registry.capability(relay,Capability('ble_relay','observe','SIMULATED_VERIFIED','RELAY:'+rid,'controlled integration fixture'))
 runtime.fabric_registry=registry;runtime.fabric_snapshot=registry.snapshot()
 target=next(d['key'] for d in runtime.fabric_snapshot['devices'] if d['category']=='ble')
 provider=RuntimeV1Provider(reader(runtime),relay+':ble_relay',target,rid,allow_simulated=True)
 forge=create_forge_server(0,provider=provider,capability_id=provider.capability_id);worker=threading.Thread(target=forge.serve_forever,daemon=True);worker.start();base='http://127.0.0.1:'+str(forge.server_port)
 def request(path,body=None):
  headers={'Authorization':'Bearer '+forge.token,'Origin':base,'Content-Type':'application/json'}
  req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
  try:r=urlopen(req,timeout=3)
  except HTTPError as e:r=e
  with r:return r.status,json.loads(r.read())
 try:
  catalog=request('/api/catalog')[1];assert catalog['mode']=='SIMULATED';assert catalog['available']
  assert request('/api/publish',{'consent':True})[0]==200
  code,response=request(catalog['observation_path']);assert code==200 and response['observations'][0]['rssi_dbm']==-61
  runtime.relays.relays[rid]['permissions']['owner_enabled']=False
  denied=request(catalog['observation_path']);assert denied[0]==409
  assert request('/api/remove',{})[0]==200
  assert request(catalog['observation_path'])[0]==404
  result={'evidence_kind':'CROSS_BRANCH_CONTROLLED_RUNTIME_HTTP','hardware_calls':0,'model_calls':0,'source_mode':'SIMULATED_VERIFIED','trusted_runtime_reader':'src.runtime.api_v2.reader','authenticated_http_read':'passed','rssi_dbm':-61,'runtime_grant_revocation_http':denied[0],'service_removal_http':404,'fixture_reset_enabled':catalog['fixture_reset_enabled']}
  print(json.dumps(result,indent=2))
 finally:forge.shutdown();forge.server_close();worker.join();runtime.server_close()
