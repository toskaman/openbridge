"""Resource-constrained diagnostic, same pinned Glimmer weights, CPU-only. No other service changed."""
import json,time
from pathlib import Path
from urllib.error import HTTPError
from src.ai.glimmer import GlimmerBroker
from src.forge.fixtures import manifest
from src.forge.meta_planner import MetaCapabilityPlanner
b=GlimmerBroker();b.options={**b.options,'num_gpu':0,'num_ctx':1024,'num_batch':32,'num_thread':4};trace={'evidence_kind':'ACTUAL_LOCAL_META_CPU_DIAGNOSTIC','model_id':b.model_id,'model_digest':b.model_digest,'execution_options':b.options,'provider_cost_usd':0.0};original=b.chat

def chat(payload):
 try:return original(payload)
 except HTTPError as e:trace['http_status']=e.code;trace['error_body']=e.read(2048).decode(errors='replace');raise
b.chat=chat;start=time.perf_counter()
try:trace['result']=MetaCapabilityPlanner(b).plan([manifest()],time.time())
except Exception as e:trace['error']=str(e)
trace['elapsed_ms']=round(1000*(time.perf_counter()-start));Path('docs/forge/glimmer-cpu-diagnostic.json').write_text(json.dumps(trace,indent=2)+'\n');print(json.dumps(trace,indent=2),flush=True)
