"""Actual local Meta review of the synthetic Forge interface; no code execution."""
import json,time
from pathlib import Path
from src.ai.local_meta import LocalMetaBroker
b=LocalMetaBroker();schema={'type':'object','additionalProperties':False,'required':['summary','suggestion'],'properties':{'summary':{'type':'string'},'suggestion':{'type':'string'}}}
payload={'model':b.model_id,'stream':False,'format':schema,'keep_alive':'30s','options':{**b.options,'num_predict':192},'messages':[{'role':'system','content':'Review a product interface in English. Return only JSON with summary and suggestion. Give one concrete clarity improvement, no code and no invented hardware claims.'},{'role':'user','content':'Capability Forge: charcoal panels, warm orange accents, a PC to simulated TV to simulated beacon path; goal selector; optional local Glimmer planning; explicit rules baseline; consent checkbox; publish, test, API contract and remove buttons. Synthetic data is clearly labeled. No physical relay evidence yet. What should the service lifecycle status say so users understand revocation?'}]}
start=time.perf_counter()
try:
 if not b.ready():raise RuntimeError('Pinned Meta model unavailable')
 proposal,response=b._call(payload)
 if not b.ready():raise RuntimeError('Model identity changed')
 result={'evidence_kind':'ACTUAL_LOCAL_META_UX_REVIEW','model_id':b.model_id,'model_digest':b.model_digest,'elapsed_ms':round(1000*(time.perf_counter()-start)),'usage':{'prompt_tokens':response['prompt_eval_count'],'completion_tokens':response['eval_count']},'provider_cost_usd':0.0,'proposal':proposal,'execution':'advice only, no generated code executed'}
except Exception as e:result={'evidence_kind':'FAILED_LOCAL_META_UX_REVIEW','error':str(e),'provider_cost_usd':0.0}
Path('docs/forge/meta-ux-review-receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2),flush=True)
