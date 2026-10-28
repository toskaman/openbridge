"""Read-only source probes for merged V4 agent scaffold and PR72; fake transports/effects only."""
import argparse
import ast
import copy
import hashlib
import hmac
import io
import json
import re
import secrets
import subprocess
import threading
import time
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
AGENT_HEAD='c426496a1305584ccf73b023ce9227099a73b55d'
SUBSTRATE_HEAD='8a73b8f395ecf13a979f88fd93649cd3975b3f23'

def probe_agent_layer():
    from src.forge import v4_evidence as E,v4_schemas as S,v4_synthesize as Y,v4_metaclient as M
    b=E.resolve([{'device_id':'synthetic-tv','category':'tv','permission_scope':['observe'],
                  'facts':[{'kind':'supported_actions','value':'read-only','source':'SIMULATED','observed_at':1000}]}],[],['read_facts'],1000)
    prompt=Y.build_prompt(b,'Read this synthetic TV',['read_facts'],'tv')
    refs=[f['evidence_ref'] for d in b['devices'] for f in d['facts']]
    candidate={'schema_version':1,'candidate_id':'audit-candidate','origin':'meta_generated','intent':'read',
               'target_opaque_id':'opaque:device:not-in-bundle','primitive_chain':[{'primitive_id':'read_facts','input':{'untyped_extra':'not permitted'}}],
               'preconditions':[],'postconditions':[],'required_grants':['control'],'evidence_refs':['invented-source']}
    client=M.MetaClient({'low':lambda p,budget:(True,{'text':json.dumps(candidate),'usage':{}})})
    accepted,_=Y.synthesize(client,'low',b,'Read this synthetic TV',['read_facts'],'tv')
    requests=[]
    class Response(io.BytesIO):
        def __enter__(self):return self
        def __exit__(self,*args):self.close()
    def fake_open(req,timeout=None):
        requests.append(json.loads(req.data));return Response(json.dumps({'model':'not-meta-audit','message':{'content':'{}'}}).encode())
    transport=M.ollama_transport('http://127.0.0.1:1','not-meta-audit',urlopen=fake_open)
    wrong_model,_=M.MetaClient({'low':transport}).generate('low','synthetic',{'max_s':1})
    before=[{'skill_id':'existing.same-id','params':{'action':'start'},'version':1}]
    after=[{'skill_id':'existing.same-id','params':{'action':'dock'},'version':2}]
    return {'source_head':AGENT_HEAD,'evidence_refs_sent_in_prompt':all(ref in prompt for ref in refs),
            'target_id_sent_in_prompt':b['devices'][0]['opaque_id'] in prompt,
            'untrusted_candidate_accepted':accepted,'candidate_changes':'foreign target, invented evidence, extra untyped input, expanded grant',
            'unapproved_model_envelope_accepted':wrong_model,'fake_request_model':requests[0]['model'],
            'registry_digest_changed_on_mapping_change':E.registry_digest(before,['read_facts'])!=E.registry_digest(after,['read_facts']),
            'actual_provider_calls':0,'actual_hardware_calls':0,'qualification':'Scaffold/proposal checks only; no deployed kernel escape or actual non-Meta request is claimed.'}

def git_json(path):
    return json.loads(subprocess.check_output(['git','show',SUBSTRATE_HEAD+':'+path],cwd=ROOT))

def probe_substrate_pr72():
    from src.runtime.route_contract import schema_errors
    source=subprocess.check_output(['git','show',SUBSTRATE_HEAD+':src/substrate/kernel.py'],cwd=ROOT,text=True)
    names={'SubstrateError','canonical','manifest_hash','iso','epoch','validate','Substrate'}
    nodes=[n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    scope=dict(globals());scope.update(CONTRACT=git_json('src/substrate/v4_contract.schema.json'),schema_errors=schema_errors,
                                      BACKEND={'input.key':('fake_effect',lambda args:args,None)})
    # Actual schema validation, invoke, signature and fact checks. Compile/device lookup/executor are fakes.
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'PR72_kernel.py','exec'),scope)
    Substrate=scope['Substrate'];iso=scope['iso'];now=1800000000
    s=Substrate(None,clock=lambda:now,key=b'a'*32);m=git_json('tests/substrate/fixtures/manifest_tv_mute.json')
    mh=scope['manifest_hash'](m);g=git_json('tests/substrate/fixtures/grant_tv_mute.json')
    g.update(manifest_hash=mh,max_uses=5,issued_at=iso(now),expires_at=iso(now+100));g.pop('signature',None);g['signature']=s._sign('grant',g)
    req=git_json('tests/substrate/fixtures/invoke_request.json');req.update(manifest_hash=mh,grant_id=g['grant_id'])
    barrier=threading.Barrier(2);lock=threading.Lock();compiles=[];effects=[];errors=[]
    c={'manifest_hash':mh,'permissions':['control','read'],'device_key':'fake',
       'plan':[{'primitive_id':'input.key','repeat':1,'args':{'key':'mute'},'step_id':'mute','on_uncertain':'INCONCLUSIVE'}]}
    def fake_compile(*args,**kwargs):
        with lock:n=len(compiles);compiles.append(n)
        if n<2:barrier.wait(5)
        return c
    def fake_execute(*args,**kwargs):
        with lock:effects.append(1);tx='fake-'+str(len(effects))
        return {'state':'EXECUTED','transaction_id':tx}
    s.compile=fake_compile;s._ex=lambda:SimpleNamespace(execute=fake_execute,emit=lambda *a,**kw:None)
    def worker():
        try:s.invoke(m,g,[],req)
        except Exception as error:errors.append(type(error).__name__+':'+str(error))
    workers=[threading.Thread(target=worker) for _ in range(2)]
    for w in workers:w.start()
    for w in workers:w.join(8)
    if any(w.is_alive() for w in workers):raise RuntimeError('probe timed out')
    checker=Substrate(None,clock=lambda:now,key=b'a'*32);fact=git_json('tests/substrate/fixtures/facts_tv.json')[0]
    fact['signature']=checker._sign('fact',{k:v for k,v in fact.items() if k!='signature'})
    current=copy.deepcopy(fact);current.update(source='UNKNOWN',verified=False)
    current['signature']=checker._sign('fact',{k:v for k,v in current.items() if k!='signature'})
    checker.device_by_fp=lambda fp:{'key':'fake'};checker.facts=lambda key:[current]
    downgrade=checker._check_fact(fact,fact['device_fingerprint'],600)
    fact['verified']=False;fact['signature']=checker._sign('fact',{k:v for k,v in fact.items() if k!='signature'})
    unverified=checker._check_fact(fact,fact['device_fingerprint'],600)
    return {'source_head':SUBSTRATE_HEAD,'schema_validation':'actual PR72 contract/schema_errors; no schema bypass',
            'compile_device_lookup_and_executor':'mocked; probes isolate admission/trust rather than full physical compile pipeline',
            'same_operation_mock_effects':len(effects),'grant_uses':s.grant_uses,'errors':errors,
            'current_provenance_downgrade_accepted':downgrade is None,'signed_unverified_fact_accepted':unverified is None,
            'actual_provider_calls':0,'actual_hardware_calls':0}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    if a.output.exists():raise FileExistsError('Never overwrite audit receipts')
    report={'agent':probe_agent_layer(),'substrate_pr72':probe_substrate_pr72(),'security_release_gate':'BLOCKED',
            'auditor_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'actual_provider_calls':0,'actual_hardware_calls':0,'actual_spend_usd':0}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as f:f.write((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(report));return 2

if __name__=='__main__':raise SystemExit(main())
