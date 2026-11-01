"""Owner-authorized test helper: one bounded relay scan over USB with the stored test pairing; prints a sanitized summary."""
import json, sys, time
from pathlib import Path
from src.adapters.android import AndroidAdapter
from src.fabric import relay as R
from src.fabric.ble_local import address_kind

tv=len(sys.argv)>2
cfg=json.loads((Path.home()/('AppData/Local/OpenBridge/relay-test'+('-tv' if tv else '')+'.json')).read_text(encoding='utf-8'));key=bytes.fromhex(cfg['key']);rid=cfg['relay_id']
if tv:send=R.http_transport('http://'+sys.argv[2]+':47800')
else:
    a=AndroidAdapter();d=[x for x in a.discover()['devices'] if x['state']=='device' and x['transport']=='USB'][0]
    send=R.http_transport(a.forward_companion(d['id']))
seen=set()
status=R.verify(key,send(None,R.command(key,rid,'get_status')),seen)['params']
print('status',json.dumps(status['permissions']))
t=time.monotonic()
try:
    reply=send(None,R.command(key,rid,'start_discovery',{'radio':'ble','seconds':int(sys.argv[1]) if len(sys.argv)>1 else 8}))
except R.RelayError as e:
    print('REFUSED_BY_RELAY',e);sys.exit(0)
obs=R.validate_report(R.verify(key,reply,seen)['params'])
send(None,R.command(key,rid,'stop_discovery'))
kinds={}
for o in obs:k=address_kind(o['address']);kinds[k]=kinds.get(k,0)+1
print('SCAN_OK',json.dumps({'seconds':round(time.monotonic()-t,1),'advertisers':len(obs),'named':sum(1 for o in obs if o['name']),
  'with_company_id':sum(1 for o in obs if o['company_ids']),'address_kinds':kinds,'strongest_rssi':max([o['rssi'] for o in obs if o['rssi'] is not None],default=None)}))
