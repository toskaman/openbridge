"""One actual Meta preload -> fresh synthetic plan -> memory release. No video or hardware work."""
import argparse,json,time
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
from src.ai.broker import NoRedirect
from src.forge.local_models import IsolatedGlimmerCPU
from src.forge.planner_v2 import SchemaConstrainedPlanner
from src.forge.fixtures import manifest
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--use-mmap',action='store_true');args=parser.parse_args()
output=Path('docs/forge/model-memory-mmap-receipt.json' if args.use_mmap else 'docs/forge/model-memory-receipt.json')
if output.exists():raise SystemExit('Receipt exists; preserve previous evidence')
b=IsolatedGlimmerCPU()
if args.use_mmap:b.options={**b.options,'use_mmap':True}
planner=SchemaConstrainedPlanner(b)
trace={'purpose':'actual_local_meta_preparation_and_release','model_id':b.model_id,'model_digest':b.model_digest,'provider_cost_usd':0.0,'hardware_calls':0,'input':'SIMULATED','benchmark_score':False,'execution_options':dict(b.options)};start=time.monotonic()
def resident():
 with build_opener(ProxyHandler({}),NoRedirect()).open(b.endpoint+'/api/ps',timeout=3) as r:data=json.load(r)
 return [{k:m.get(k) for k in ('name','size','size_vram')} for m in data.get('models',[]) if m.get('name')==b.model_id]
try:
 trace['prepare']=planner.prepare();trace['memory_after_prepare']=resident();print('Preparation confirmed; collecting fresh synthetic evidence now.',flush=True)
 trace['plan']=planner.plan([manifest()],time.time());trace['status']='PLAN_VALIDATED'
except Exception as e:trace['status']='FAILED';trace['error']=str(e)
finally:
 try:trace['release']=planner.release();trace['memory_after_release']=resident()
 except Exception as e:trace['release_error']=str(e)
trace['total_ms']=round(1000*(time.monotonic()-start));output.write_text(json.dumps(trace,indent=2)+'\n',encoding='utf-8');print(json.dumps(trace,indent=2),flush=True)
