"""Pinned CPU-local Meta Llama advisory; no provider credentials or cloud fallback."""
from decimal import Decimal
import hashlib
import json
import math
import re
import threading
import time
from urllib.request import Request,build_opener,ProxyHandler
import uuid
from src.ai.broker import ModelBlocked,NoRedirect,ALLOWED_FACTS

MODEL_ID='llama3.2:3b-instruct-q4_K_M'
MODEL_DIGEST='a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72'
LOCAL_ENDPOINT='http://127.0.0.1:11437'
GOALS={'review':'Review the device state only. Prefer inspect_only.',
    'declutter':'The owner wants to declutter: propose temporarily disabling the single least essential optional app from the candidates, unless none is enabled.'}
UNCERTAINTY_LIMIT='Device health and write permission are unknown from these limited facts.'


def local_request(path,payload=None):
    if path not in ('/api/tags','/api/chat'):
        raise ModelBlocked('Unapproved local model endpoint')
    data=None if payload is None else json.dumps(payload).encode()
    request=Request(LOCAL_ENDPOINT+path,data=data,headers={'Content-Type':'application/json'},method='GET' if data is None else 'POST')
    with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=3 if path=='/api/tags' else 120) as response:
        body=response.read(131073)
        if len(body)>131072:raise ModelBlocked('Local model response too large')
        return json.loads(body)


class LocalMetaBroker:
    local_only=True
    model_id=MODEL_ID
    inference_mode='local'

    def __init__(self,catalog=None,chat=None):
        self.catalog=catalog or (lambda:local_request('/api/tags'))
        self.chat=chat or (lambda payload:local_request('/api/chat',payload))
        self._inflight=threading.Lock()

    def ready(self):
        try:
            rows=self.catalog().get('models',[])
            match=next((row for row in rows if row.get('name')==MODEL_ID),None)
            return bool(match and match.get('digest','').removeprefix('sha256:')==MODEL_DIGEST)
        except Exception:return False

    def _call(self,payload):
        response=self.chat(payload)
        if response.get('model')!=MODEL_ID or response.get('done') is not True or response.get('done_reason')!='stop':
            raise ModelBlocked('Local model identity or completion state is invalid')
        message=response['message']
        if message.get('tool_calls') or not isinstance(message.get('content'),str) or len(message['content'])>16384:
            raise ModelBlocked('Unexpected local agent or output shape')
        for key in ('prompt_eval_count','eval_count'):
            if type(response.get(key)) is not int or not 0<=response[key]<=8192:
                raise ModelBlocked('Local usage metadata is invalid')
        return json.loads(message['content']),response

    def plan(self,facts,candidates,goal='review'):
        """Agent planning step. candidates: {package: 'enabled'|'disabled'} limited to the reviewed allowlist."""
        if not isinstance(facts,dict) or set(facts)-ALLOWED_FACTS or any(type(v) not in (int,float) or not math.isfinite(v) for v in facts.values()):
            raise ModelBlocked('Only approved non-identifying numeric device facts are allowed')
        if not isinstance(candidates,dict) or any(not re.fullmatch(r'[a-z][a-z0-9_.]{1,100}',k) or v not in ('enabled','disabled') for k,v in candidates.items()):
            raise ModelBlocked('Invalid candidate list')
        if goal not in GOALS:raise ModelBlocked('Unknown owner goal')
        eligible=sorted(k for k,v in candidates.items() if v=='enabled')
        if not self._inflight.acquire(blocking=False):
            raise ModelBlocked('Local Meta inference is busy; no request queued or forwarded')
        try:
            if not self.ready():raise ModelBlocked('Pinned Meta model is unavailable or its digest does not match')
            refs=list(facts)+['app:'+k for k in eligible]
            schema={'type':'object','additionalProperties':False,'required':['summary','action','package','evidence_refs','uncertainty'],
                'properties':{'summary':{'type':'string'},'uncertainty':{'type':'string','enum':[UNCERTAINTY_LIMIT]},
                    'action':{'type':'string','enum':['inspect_only']+(['disable_optional_app'] if eligible else [])},
                    'package':{'type':'string','enum':['']+eligible},
                    'evidence_refs':{'type':'array','minItems':1,'uniqueItems':True,'items':{'type':'string','enum':refs}}}}
            payload={'model':MODEL_ID,'stream':False,'format':schema,'keep_alive':'30s',
                'options':{'temperature':0,'num_gpu':0,'num_thread':4,'num_ctx':2048,'num_predict':384},
                'messages':[{'role':'system','content':
                    'You are the planning step of a device assistant. Respond in English only as compact JSON matching the schema. '
                    'Goal: help the owner declutter by proposing at most ONE reversible step: temporarily disabling one optional utility app from the supplied candidate list, '
                    'or inspect_only if nothing is worth changing. Disabling keeps app data and can be undone exactly. '
                    'Never claim battery, speed or storage gains. Write the summary with this exact template, copying the numbers from facts: '
                    '"Battery is <battery_percent>% and <storage_free_gb> GB of storage is free. Proposed: temporarily disable <package>." '
                    '(for inspect_only, end with "No change proposed." instead). '
                    'Do not invent numbers. A separate deterministic policy and the owner decide whether anything runs. '
                    'If action is inspect_only, package must be empty. The uncertainty field must use the exact policy limitation required by the schema.'},
                    {'role':'user','content':json.dumps({'owner_goal':GOALS[goal],'facts':facts,'optional_app_candidates':candidates},sort_keys=True)}]}
            started=time.monotonic()
            proposal,response=self._call(payload)
            if not isinstance(proposal,dict) or set(proposal)!={'summary','action','package','evidence_refs','uncertainty'}:
                raise ModelBlocked('Agent plan schema is invalid')
            if proposal['uncertainty']!=UNCERTAINTY_LIMIT or not isinstance(proposal['summary'],str) or not 1<=len(proposal['summary'])<=2000:
                raise ModelBlocked('Agent plan must retain the explicit policy limitation')
            if proposal['action']=='inspect_only' and proposal['package']!='':
                raise ModelBlocked('Observation-only plan cannot name a package')
            if proposal['action']=='disable_optional_app' and proposal['package'] not in eligible:
                raise ModelBlocked('Agent plan targets an ineligible package')
            if proposal['action'] not in ('inspect_only','disable_optional_app'):
                raise ModelBlocked('Unknown agent action')
            if not isinstance(proposal['evidence_refs'],list) or not proposal['evidence_refs'] or any(r not in refs for r in proposal['evidence_refs']):
                raise ModelBlocked('Agent plan references unknown evidence')
            supplied={Decimal(str(v)) for v in facts.values()}
            for number in re.findall(r'(?<![\w.])[-+]?\d+(?:\.\d+)?(?![\w])',proposal['summary']):
                if Decimal(number) not in supplied:
                    raise ModelBlocked('Agent plan introduced an unverified numeric claim')
            stated={Decimal(n) for n in re.findall(r'(?<![\w.])\d+(?:\.\d+)?(?![\w])',proposal['summary'])}
            for ref in proposal['evidence_refs']:
                if ref in facts and Decimal(str(facts[ref])) not in stated:
                    raise ModelBlocked('Agent plan summary must state every referenced value exactly')
            if proposal['action']=='disable_optional_app' and proposal['package'] not in proposal['summary']:
                raise ModelBlocked('Agent plan summary must name the proposed app')
            if not self.ready():raise ModelBlocked('Local model digest changed during inference')
            return {'model_id':MODEL_ID,'provider':'Ollama local CPU','model_manifest_digest':MODEL_DIGEST,
                'request_id':'local-'+uuid.uuid4().hex,'proposal':proposal,
                'usage':{'prompt_tokens':response['prompt_eval_count'],'completion_tokens':response['eval_count']},
                'estimated_cost_usd':0.0,'elapsed_ms':round((time.monotonic()-started)*1000),'cpu_only_requested':True,
                'goal':goal,'input_sha256':hashlib.sha256(json.dumps({'f':facts,'c':candidates,'g':goal},sort_keys=True).encode()).hexdigest()}
        except ModelBlocked:raise
        except Exception:
            raise ModelBlocked('Local Meta request failed; no cloud fallback was used') from None
        finally:self._inflight.release()

    def recommend(self,facts,*,source='SIMULATED'):
        if source not in ('SIMULATED','ADB') or not isinstance(facts,dict) or not facts or set(facts)-ALLOWED_FACTS:
            raise ModelBlocked('Only approved non-identifying numeric device facts are allowed')
        for key,value in facts.items():
            if type(value) not in (int,float) or not math.isfinite(value) or not 0 <= value <= 1_000_000:
                raise ModelBlocked('Invalid numeric device fact')
            if key=='battery_percent' and value>100:
                raise ModelBlocked('Invalid battery percentage')
        if not self._inflight.acquire(blocking=False):
            raise ModelBlocked('Local Meta inference is busy; no request queued or forwarded')
        try:
            if not self.ready():raise ModelBlocked('Pinned Meta model is unavailable or its digest does not match')
            schema={'type':'object','additionalProperties':False,'required':['summary','evidence_refs','action','uncertainty'],
                'properties':{'summary':{'type':'string'},'uncertainty':{'type':'string','enum':[UNCERTAINTY_LIMIT]},
                    'action':{'type':'string','enum':['inspect_only']},
                    'evidence_refs':{'type':'array','minItems':1,'uniqueItems':True,'items':{'type':'string','enum':list(facts)}}}}
            payload={'model':MODEL_ID,'stream':False,'format':schema,'keep_alive':'30s',
                'options':{'temperature':0,'num_gpu':0,'num_thread':4,'num_ctx':2048,'num_predict':384},
                'messages':[{'role':'system','content':
                    'Respond in English only, as a compact JSON object matching the schema. Review only the supplied numeric facts. '
                    'Repeat supplied numbers exactly; do not invent numbers or derive quantities. Reference only supplied fact keys. '
                    'Give one short read-only observation that states the exact value of every fact you reference, using the form: Battery is <battery_percent>% and <storage_free_gb> GB of storage is free. Clearly state uncertainty. Do not infer device health or optimization gains. '
                    'Action must be inspect_only. No commands, setting changes, personal identifiers or external requests. '
                    'The uncertainty field must use the exact policy limitation required by the schema.'},
                    {'role':'user','content':json.dumps({'source':source,'facts':facts},sort_keys=True)}]}
            started=time.monotonic()
            response=self.chat(payload)
            if response.get('model')!=MODEL_ID or response.get('done') is not True or response.get('done_reason')!='stop':
                raise ModelBlocked('Local model identity or completion state is invalid')
            message=response['message']
            if message.get('tool_calls') or not isinstance(message.get('content'),str) or len(message['content'])>16384:
                raise ModelBlocked('Unexpected local agent or output shape')
            proposal=json.loads(message['content'])
            if not isinstance(proposal,dict) or set(proposal)!={'summary','evidence_refs','action','uncertainty'}:
                raise ModelBlocked('Local advisory schema is invalid')
            if proposal['action']!='inspect_only' or any(not isinstance(proposal[key],str) or not 1<=len(proposal[key])<=2000 for key in ('summary','uncertainty')):
                raise ModelBlocked('Local advisory does not remain read-only')
            if proposal['uncertainty']!=UNCERTAINTY_LIMIT:
                raise ModelBlocked('Local advisory must retain the explicit policy limitation')
            refs=proposal['evidence_refs']
            if not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or ref not in facts for ref in refs) or len(set(refs))!=len(refs):
                raise ModelBlocked('Local advisory references unknown evidence')
            supplied={Decimal(str(value)) for value in facts.values()}
            for text in (proposal['summary'],proposal['uncertainty']):
                for number in re.findall(r'(?<![\d.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?',text):
                    if Decimal(number) not in supplied:
                        raise ModelBlocked('Local advisory introduced an unverified numeric claim')
            stated={Decimal(n) for n in re.findall(r'(?<![\d.])\d+(?:\.\d+)?',proposal['summary'])}
            if any(Decimal(str(facts[ref])) not in stated for ref in refs):
                raise ModelBlocked('Local advisory summary must state every referenced value exactly')
            for key in ('prompt_eval_count','eval_count'):
                if type(response.get(key)) is not int or not 0<=response[key]<=8192:
                    raise ModelBlocked('Local usage metadata is invalid')
            if not self.ready():raise ModelBlocked('Local model digest changed during inference')
            return {'model_id':MODEL_ID,'provider':'Ollama local CPU','model_manifest_digest':MODEL_DIGEST,
                'request_id':'local-'+uuid.uuid4().hex,'source':source,'proposal':proposal,
                'usage':{'prompt_tokens':response['prompt_eval_count'],'completion_tokens':response['eval_count']},
                'estimated_cost_usd':0.0,'billing':'LOCAL_COMPUTE_NO_PROVIDER_CREDITS',
                'elapsed_ms':round((time.monotonic()-started)*1000),'cpu_only_requested':True,
                'input_sha256':hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest()}
        except ModelBlocked:raise
        except Exception:
            raise ModelBlocked('Local Meta request failed; no cloud fallback was used') from None
        finally:self._inflight.release()
