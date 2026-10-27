"""Local Meta planning only. Execution and consent remain outside this module."""
import json
import threading
import time
from src.ai.glimmer import GLIMMER_ID,GLIMMER_DIGEST
from src.ai.local_meta import MODEL_ID,MODEL_DIGEST
from src.forge.compiler import ForgeError
from src.forge.planner import GOAL,candidates,validate_plan

class MetaCapabilityPlanner:
    def __init__(self,broker):
        if broker.local_only is not True or (broker.model_id,broker.model_digest) not in ((GLIMMER_ID,GLIMMER_DIGEST),(MODEL_ID,MODEL_DIGEST)):
            raise ForgeError('UNAPPROVED_META_MODEL')
        self.broker=broker;self._lock=threading.Lock()
    def plan(self,manifests,now):
        if not self._lock.acquire(blocking=False):raise ForgeError('PLANNER_BUSY')
        try:
            b=self.broker
            if not b.ready():raise ForgeError('META_UNAVAILABLE')
            options=candidates(manifests,now)
            # Only opaque capability references and facts needed for composition; no labels, addresses, observations or credentials.
            safe=[{k:m[k] for k in ('capability_id','relay_id','evidence_refs','operation','simulation')} for m in options]
            schema={'type':'object','additionalProperties':False,'required':['goal','decision','steps','evidence_refs','requires_consent'],
                'properties':{'goal':{'const':GOAL},'decision':{'enum':['propose','unavailable']},'steps':{'type':'array','maxItems':2,'items':{'type':'object','additionalProperties':False,'required':['capability_id','operation'],'properties':{'capability_id':{'enum':[m['capability_id'] for m in options]+['pc.virtual_api.publish']},'operation':{'enum':['read_observations','publish_readonly']}}}},'evidence_refs':{'type':'array','items':{'enum':sorted({r for m in options for r in m['evidence_refs']}) or ['none']}},'requires_consent':{'const':True}}}
            payload={'model':b.model_id,'stream':False,'format':schema,'keep_alive':'30s',**b.extra,'options':{**b.options,'temperature':0,'num_predict':384},'messages':[{'role':'system','content':'Return only English JSON matching the schema. Goal: expose_remote_ble_observations. Choose one eligible capability, then pc.virtual_api.publish, in that order, with read_observations then publish_readonly. Copy the chosen evidence_refs exactly in order. If no eligible capability exists, decision unavailable with empty steps and evidence_refs. requires_consent is always true: this plan never grants permission. Never invent an ID or command. Prefer real evidence over simulated evidence, then relay_id alphabetically.'},{'role':'user','content':json.dumps({'goal':GOAL,'eligible_capabilities':safe,'constraints':['read-only','owner-consent-required','no-device-actions']},sort_keys=True)}]}
            start=time.perf_counter()
            try:proposal,response=b._call(payload)
            except Exception:raise ForgeError('META_RESPONSE_FAILED') from None
            if not b.ready():raise ForgeError('META_DIGEST_CHANGED')
            validated=validate_plan(proposal,manifests,now)
            return {'plan':validated,'model_id':b.model_id,'model_digest':b.model_digest,'elapsed_ms':round(1000*(time.perf_counter()-start)),'usage':{'prompt_tokens':response['prompt_eval_count'],'completion_tokens':response['eval_count']},'provider_cost_usd':0.0,'source':'LOCAL_META','authorizes_execution':False}
        finally:self._lock.release()
