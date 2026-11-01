"""Frozen Forge gate-and-selection ablation; synthetic data, local Meta only, no retries."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
import tracemalloc
from urllib.request import build_opener,ProxyHandler
from src.ai.broker import NoRedirect
from src.ai.glimmer import GlimmerBroker
from src.ai.local_meta import LocalMetaBroker
from src.forge.compiler import ForgeError
from src.forge.meta_planner import MetaCapabilityPlanner
from src.forge.planner import rules_plan,validate_plan

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'docs/forge/composition-scenarios.json'

def model_memory(broker):
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(broker.endpoint+'/api/ps',timeout=3) as r:data=json.loads(r.read(131072))
        row=next((m for m in data.get('models',[]) if m.get('name')==broker.model_id),None)
        return {k:row.get(k) for k in ('size','size_vram')} if row else None
    except Exception:return None

def evaluate(route,cases):
    broker=GlimmerBroker() if route=='glimmer' else LocalMetaBroker() if route=='llama3b' else None
    planner=MetaCapabilityPlanner(broker) if broker else None
    rows=[]
    for case in cases:
        raw=None;usage=None;err=None;elapsed=0;result=None;capture={}
        if broker:
            original=broker._call
            def observed(payload):
                proposal,response=original(payload);capture['proposal']=proposal;capture['response']=response;return proposal,response
            broker._call=observed
        tracemalloc.start();start=time.perf_counter()
        try:
            if planner:
                result=planner.plan(case['manifests'],case['now']);proposal=result['plan'];usage=result['usage']
            else:proposal=rules_plan(case['manifests'],case['now']);validate_plan(proposal,case['manifests'],case['now'])
            raw=proposal
        except Exception as e:err=str(e)[:160];raw=capture.get('proposal')
        finally:
            elapsed=round(1000*(time.perf_counter()-start));_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            if broker:broker._call=original
        decision=raw.get('decision') if isinstance(raw,dict) else None
        steps=raw.get('steps',[]) if isinstance(raw,dict) and isinstance(raw.get('steps'),list) else []
        picked=steps[0].get('capability_id') if steps and isinstance(steps[0],dict) else None
        known={m['capability_id'] for m in case['manifests']}|{'pc.virtual_api.publish'}
        hallucination=any(not isinstance(s,dict) or s.get('capability_id') not in known for s in steps)
        permission_violation=any(isinstance(s,dict) and s.get('capability_id')==m['capability_id'] and not {'observe','read'}<=set(m['permissions']) for s in steps for m in case['manifests'])
        correct=not err and decision==case['expected_decision'] and (case['expected_capability'] is None or picked==case['expected_capability'])
        if not usage and capture.get('response'):usage={'prompt_tokens':capture['response'].get('prompt_eval_count'),'completion_tokens':capture['response'].get('eval_count')}
        rows.append({'case':case['id'],'category':case['category'],'split':case['split'],'correct':correct,'expected_decision':case['expected_decision'],'expected_capability':case['expected_capability'],'raw_plan':raw,'error':err,'hallucination':hallucination,'permission_violation_proposed':permission_violation,'unnecessary_steps':max(0,len(steps)-(2 if case['expected_capability'] else 0)),'elapsed_ms':elapsed,'usage':usage,'python_peak_allocated_bytes':peak,'model_memory_bytes':model_memory(broker) if broker else None,'provider_cost_usd':0.0})
        if len(rows)%4==0:print(f'{route}: {len(rows)}/{len(cases)}; correct={sum(r["correct"] for r in rows)}',flush=True)
    refusals=[r for r in rows if r['expected_decision']=='unavailable']
    return {'route':route,'model_id':broker.model_id if broker else None,'model_digest':broker.model_digest if broker else None,'cases':len(rows),'accuracy_pct':round(100*sum(r['correct'] for r in rows)/len(rows),2),'correct_refusal_pct':round(100*sum(r['correct'] for r in refusals)/len(refusals),2) if refusals else None,'complete_plan_success_pct':round(100*sum(r['correct'] for r in rows if r['expected_decision']=='propose')/max(1,sum(r['expected_decision']=='propose' for r in rows)),2),'hallucinations':sum(r['hallucination'] for r in rows),'permission_violations_proposed':sum(r['permission_violation_proposed'] for r in rows),'unnecessary_steps':sum(r['unnecessary_steps'] for r in rows),'median_latency_ms':statistics.median(r['elapsed_ms'] for r in rows),'tokens_in':sum((r['usage'] or {}).get('prompt_tokens',0) or 0 for r in rows),'tokens_out':sum((r['usage'] or {}).get('completion_tokens',0) or 0 for r in rows),'provider_cost_usd':0.0,'rows':rows}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--route',choices=['rules','llama3b','glimmer'],required=True);p.add_argument('--limit',type=int);args=p.parse_args()
    cases=json.loads(DATA.read_text(encoding='utf-8'))['cases'];cases=cases[:args.limit] if args.limit else cases
    result=evaluate(args.route,cases);result['dataset_sha256']=hashlib.sha256(DATA.read_bytes()).hexdigest();result['scope']='Rules-gated two-step observation publication; not unrestricted multi-device reasoning. Synthetic scenarios only. Held-out cases frozen before model execution, no prompt tuning on results.'
    target=ROOT/f'docs/forge/benchmark-{args.route}.json';target.write_text(json.dumps(result,indent=2)+'\n', encoding='utf-8');print({k:v for k,v in result.items() if k!='rows'},flush=True)
if __name__=='__main__':main()
