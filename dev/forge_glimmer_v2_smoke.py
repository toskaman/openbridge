"""Actual experimental v2 proposal, recorded separately from frozen v1 evaluations."""
import json,time
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
from src.forge.local_models import IsolatedGlimmerCPU
from src.forge.planner_v2 import SchemaConstrainedPlanner
from src.forge.fixtures import manifest
output=Path('docs/forge/glimmer-v2-constrained-proposal-receipt.json')
if output.exists():raise SystemExit('Receipt already exists; preserve prior evidence')
b=IsolatedGlimmerCPU();original=b._call;trace={'evidence_kind':'ACTUAL_LOCAL_META_V2_PROPOSAL','model_id':b.model_id,'model_digest':b.model_digest,'endpoint':b.endpoint,'input':'SIMULATED','provider_cost_usd':0.0,'benchmark_score':False};start=time.monotonic()
def observed(payload):
 proposal,response=original(payload);trace['raw_proposal']=proposal;trace['usage']={'prompt_tokens':response['prompt_eval_count'],'completion_tokens':response['eval_count']};return proposal,response
b._call=observed
try:trace['result']=SchemaConstrainedPlanner(b).plan([manifest()],time.time());trace['status']='VALIDATED_PLAN'
except Exception as e:trace['status']='FAILED';trace['error']=str(e)
try:
 with build_opener(ProxyHandler({})).open(b.endpoint+'/api/ps',timeout=3) as r:loaded=json.load(r)
 trace['observed_model_memory']=[{k:m.get(k) for k in ('name','size','size_vram')} for m in loaded.get('models',[]) if m.get('name')==b.model_id]
except Exception:trace['observed_model_memory']=None
trace['wall_ms']=round(1000*(time.monotonic()-start));output.write_text(json.dumps(trace,indent=2)+'\n',encoding='utf-8');print(json.dumps(trace,indent=2),flush=True)
