"""Explicit build-time Meta web-design request; stdin credential, shared durable credit guard."""
import argparse
from datetime import datetime,timezone
import hashlib,json,os,sys,time
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
from src.ai.broker import RuntimeModelBroker,CreditPermit,NoRedirect,ModelBlocked

def main():
    p=argparse.ArgumentParser();p.add_argument('--observed-at',required=True);p.add_argument('--free-credits',type=float,required=True);p.add_argument('--observation-id',required=True);p.add_argument('--brief',required=True);p.add_argument('--model',choices=['muse-wonder-1.0','muse-spark-1.3'],default='muse-wonder-1.0');a=p.parse_args()
    observed=datetime.fromisoformat(a.observed_at)
    if observed.tzinfo is None or not 0<=(datetime.now(timezone.utc)-observed).total_seconds()<=300:raise SystemExit('Fresh free-credit verification required')
    brief=Path(a.brief).read_text(encoding='utf-8');system='You are the lead web designer and frontend engineer for OpenBridge. Return ONLY a JSON object as requested. All text English. No tools, URLs, external fonts, images, video, code execution or fabricated data. Produce polished, accessible, modular interface code. Existing application permissions, consent and runtime safety must remain intact.'
    if len((system+brief).encode('utf-8'))>5500:raise SystemExit('Design input exceeds conservative request budget')
    key=sys.stdin.readline().strip()
    if not key.startswith('LLM_'):raise SystemExit('Credential unavailable')
    root=Path(os.environ['LOCALAPPDATA'])/'OpenBridge'
    guard=RuntimeModelBroker(root/'runtime-budget.sqlite',CreditPermit(a.observation_id,observed,a.free_credits,.20))
    payload={'model':a.model,'max_completion_tokens':3500,'reasoning_effort':'low','messages':[{'role':'developer','content':system},{'role':'user','content':brief}]}
    result={'purpose':'BUILD_TIME_WEBSITE_REDESIGN','model_requested':a.model,'input_sha256':hashlib.sha256(brief.encode()).hexdigest(),'source':'public interface brief only','automatic_retry':False,'recorded_at_utc':datetime.now(timezone.utc).isoformat()}
    target=Path('artifacts/meta-web-design');target.mkdir(parents=True,exist_ok=True);dest=target/('attempt-'+datetime.now().strftime('%Y-%m-%d_%H-%M-%S')+'.json')
    guard._reserve();start=time.monotonic()
    try:
        req=Request('https://api.meta.ai/v1/chat/completions',data=json.dumps(payload).encode(),method='POST',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=180) as response:
            data=response.read(262145)
            if len(data)>262144:raise ModelBlocked('Response too large')
            data=json.loads(data)
        result['model_id']=data.get('model');result['request_id']=data.get('id');result['usage']=data.get('usage');result['finish_reason']=data['choices'][0].get('finish_reason')
        if data.get('model')!=a.model or data['choices'][0]['message'].get('tool_calls'):raise ModelBlocked('Unexpected model or tool output')
        usage=data['usage']
        for field in ('prompt_tokens','completion_tokens'):
            if type(usage[field]) is not int or not 0<=usage[field]<=100000:raise ModelBlocked('Usage invalid')
        rates=(4,20) if a.model=='muse-wonder-1.0' else (1.25,4.25)
        estimate=(usage['prompt_tokens']*rates[0]+usage['completion_tokens']*rates[1])/1000000
        result['estimated_cost_usd']=estimate;result['reservation_usd']=.10
        result['raw_content']=data['choices'][0]['message'].get('content')
        if estimate>.10 or result['finish_reason']!='stop':raise ModelBlocked('Budget or completion boundary not satisfied')
        result['proposal']=json.loads(result['raw_content']);result['status']='GENERATED_FOR_REVIEW'
    except HTTPError as error:
        result['status']='BLOCKED';result['http_status']=error.code
        result['provider_error']=error.read(4096).decode('utf-8',errors='replace');error.close()
    except Exception as error:result['status']='BLOCKED';result['error']=str(error) if isinstance(error,ModelBlocked) else type(error).__name__
    result['elapsed_ms']=round((time.monotonic()-start)*1000)
    with dest.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'status':result['status'],'receipt':str(dest),'model_id':result.get('model_id'),'estimated_cost_usd':result.get('estimated_cost_usd')}),flush=True)
    return 0 if result['status']=='GENERATED_FOR_REVIEW' else 1

if __name__=='__main__':raise SystemExit(main())
