"""Untrusted JSON plan validation; a model never grants authority."""
from src.forge.compiler import ForgeError,eligible
GOAL='expose_remote_ble_observations'

def candidates(manifests,now):
    out=[]
    for m in manifests:
        try:out.append(eligible(m,now))
        except ForgeError:continue
    ids=[m['capability_id'] for m in out]
    if len(ids)!=len(set(ids)):raise ForgeError('AMBIGUOUS_CAPABILITY_ID')
    return sorted(out,key=lambda m:(m['simulation'],m['relay_id'],m['capability_id']))

def rules_plan(manifests,now):
    options=candidates(manifests,now)
    if not options:return {'goal':GOAL,'decision':'unavailable','steps':[],'evidence_refs':[],'requires_consent':True}
    m=options[0]
    return {'goal':GOAL,'decision':'propose','steps':[{'capability_id':m['capability_id'],'operation':'read_observations'},{'capability_id':'pc.virtual_api.publish','operation':'publish_readonly'}],'evidence_refs':m['evidence_refs'],'requires_consent':True}

def validate_plan(plan,manifests,now):
    if not isinstance(plan,dict) or set(plan)!={'goal','decision','steps','evidence_refs','requires_consent'} or plan['goal']!=GOAL or plan['requires_consent'] is not True:raise ForgeError('INVALID_PLAN')
    options={m['capability_id']:m for m in candidates(manifests,now)}
    if plan['decision']=='unavailable':
        if options or plan['steps']!=[] or plan['evidence_refs']!=[]:raise ForgeError('INCORRECT_REFUSAL')
        return plan
    steps=plan['steps']
    if plan['decision']!='propose' or not isinstance(steps,list) or len(steps)!=2:raise ForgeError('INVALID_PLAN_TRANSITION')
    if any(not isinstance(s,dict) or set(s)!={'capability_id','operation'} for s in steps):raise ForgeError('INVALID_STEP')
    cid=steps[0]['capability_id']
    if not isinstance(cid,str) or cid not in options or steps[0]['operation']!='read_observations' or steps[1]!={'capability_id':'pc.virtual_api.publish','operation':'publish_readonly'}:raise ForgeError('UNKNOWN_CAPABILITY_OR_TRANSITION')
    if plan['evidence_refs']!=options[cid]['evidence_refs']:raise ForgeError('INVALID_EVIDENCE_REFS')
    return plan
