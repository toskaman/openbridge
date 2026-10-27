import json,time
from pathlib import Path
from urllib.error import HTTPError
from src.ai.glimmer import GlimmerBroker
from src.forge.fixtures import manifest
from src.forge.meta_planner import MetaCapabilityPlanner
b=GlimmerBroker();original=b.chat;trace={'diagnostic_only':True,'model_id':b.model_id,'model_digest':b.model_digest,'provider_cost_usd':0.0}
def chat(payload):
 try:
  response=original(payload);trace['response']=response;return response
 except HTTPError as e:
  trace['http_status']=e.code;trace['transport_error_body']=e.read(4096).decode(errors='replace');raise
b.chat=chat
try:trace['result']=MetaCapabilityPlanner(b).plan([manifest()],time.time())
except Exception as e:trace['planner_error']=str(e)
Path('docs/forge/meta-transport-diagnostic.json').write_text(json.dumps(trace,indent=2)+'\n')
print(json.dumps(trace,indent=2),flush=True)
