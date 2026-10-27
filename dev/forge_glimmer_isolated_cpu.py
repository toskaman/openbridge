"""Same frozen planner, pinned Glimmer, isolated CPU environment. Synthetic inputs only."""
import json,time
from pathlib import Path
from urllib.error import HTTPError
from src.ai.glimmer import GlimmerBroker
from src.forge.fixtures import manifest
from src.forge.meta_planner import MetaCapabilityPlanner
b=GlimmerBroker();b.endpoint='http://127.0.0.1:11439';b.catalog=lambda:__import__('src.ai.local_meta',fromlist=['local_request']).local_request('/api/tags',endpoint=b.endpoint)
b.chat=lambda payload:__import__('src.ai.local_meta',fromlist=['local_request']).local_request('/api/chat',payload,endpoint=b.endpoint,timeout=180)
b.options={**b.options,'num_gpu':0,'num_ctx':1024,'num_batch':32,'num_thread':4};trace={'model_id':b.model_id,'model_digest':b.model_digest,'endpoint':b.endpoint,'cpu_environment':True,'provider_cost_usd':0.0,'input':'SIMULATED','prompt_changed':False};start=time.monotonic()
try:trace['result']=MetaCapabilityPlanner(b).plan([manifest()],time.time());trace['status']='VALIDATED_PLAN'
except Exception as e:trace['status']='FAILED';trace['error']=str(e)
trace['elapsed_ms']=round(1000*(time.monotonic()-start));Path('docs/forge/glimmer-isolated-cpu-receipt.json').write_text(json.dumps(trace,indent=2)+'\n',encoding='utf-8');print(json.dumps(trace,indent=2),flush=True)
