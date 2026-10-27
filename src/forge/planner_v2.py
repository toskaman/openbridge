"""Experimental v2: deterministic availability, model-authored complete bounded proposals.

V1 and its frozen unfavorable results remain unchanged. This is not an intelligence advantage.
"""
import json
import time
from src.forge.compiler import ForgeError
from src.forge.meta_planner import MetaCapabilityPlanner
from src.forge.planner import GOAL,candidates,rules_plan,validate_plan

class SchemaConstrainedPlanner(MetaCapabilityPlanner):
    @property
    def supports_model_control(self):
        return callable(getattr(self.broker,'prepare',None)) and callable(getattr(self.broker,'release',None))

    def _model_control(self,release):
        if not self._lock.acquire(blocking=False):raise ForgeError('PLANNER_BUSY')
        try:
            method=getattr(self.broker,'release' if release else 'prepare',None)
            if not callable(method):raise ForgeError('MODEL_CONTROL_UNAVAILABLE')
            return {**method(),'authorizes_execution':False}
        finally:self._lock.release()

    def prepare(self):return self._model_control(False)
    def release(self):return self._model_control(True)

    def plan(self,manifests,now):
        plan_started=time.monotonic()
        options=candidates(manifests,now)
        if not options:
            return {'plan':rules_plan(manifests,now),'source':'RULES','model_called':False,'planner_version':2,'authorizes_execution':False,'provider_cost_usd':0.0,'usage':{'prompt_tokens':0,'completion_tokens':0},'elapsed_ms':0}
        if not self._lock.acquire(blocking=False):raise ForgeError('PLANNER_BUSY')
        try:
            b=self.broker
            if not b.ready():raise ForgeError('META_UNAVAILABLE')
            ids=[m['capability_id'] for m in options]
            schema={'type':'object','additionalProperties':False,'required':['goal','decision','steps','evidence_refs','requires_consent'],'properties':{
                'goal':{'type':'string','enum':[GOAL]},'decision':{'type':'string','enum':['propose']},
                'steps':{'type':'array','enum':[[{'capability_id':cid,'operation':'read_observations'},{'capability_id':'pc.virtual_api.publish','operation':'publish_readonly'}] for cid in ids]},
                'evidence_refs':{'type':'array','enum':[m['evidence_refs'] for m in options]},'requires_consent':{'type':'boolean','enum':[True]}}}
            safe=[{k:m[k] for k in ('capability_id','relay_id','operation','evidence_refs','simulation')} for m in options]
            payload={'model':b.model_id,'stream':False,'format':schema,'keep_alive':getattr(b,'keep_alive','30s'),**b.extra,'options':{**b.options,'temperature':0,'num_predict':384},'messages':[
                {'role':'system','content':'Return only the complete JSON proposal matching the schema. Deterministic policy has ALREADY verified all supplied candidates are available and permitted for reading. You do not decide availability or grant consent. Choose ONE candidate. Step 1: its exact capability_id and read_observations. Step 2: pc.virtual_api.publish and publish_readonly. Copy only the selected candidate evidence_refs, exactly in order. decision is propose. requires_consent true means the owner must approve LATER before publication; it does not prevent proposing now. Prefer real evidence over simulated evidence, then relay_id alphabetically. Do not execute anything or invent identifiers.'},
                {'role':'user','content':json.dumps({'goal':GOAL,'verified_eligible_candidates':safe},sort_keys=True)}]}
            started=time.monotonic()
            try:proposal,response=b._call(payload)
            except Exception:raise ForgeError('META_RESPONSE_FAILED') from None
            if not b.ready():raise ForgeError('META_DIGEST_CHANGED')
            validated=validate_plan(proposal,manifests,now+max(0,time.monotonic()-plan_started))
            return {'plan':validated,'model_id':b.model_id,'model_digest':b.model_digest,'source':'LOCAL_META','model_called':True,'planner_version':2,'eligibility_source':'DETERMINISTIC_RULES','authorizes_execution':False,'elapsed_ms':round(1000*(time.monotonic()-started)),'usage':{'prompt_tokens':response['prompt_eval_count'],'completion_tokens':response['eval_count']},'provider_cost_usd':0.0}
        finally:self._lock.release()
