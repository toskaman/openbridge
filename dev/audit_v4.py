"""Independent V4 audit probes. Synthetic effects/temp ledgers only; never load credentials or call providers."""
import argparse
import ast
import hashlib
import json
import sqlite3
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
BASELINE='dcf852775aab0a4129b1c9e117f9457db77f985d'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def registry_snapshot():
    from src.runtime.contract import to_json
    from src.runtime.primitives import PRIMITIVES
    from src.runtime.routing import SKILLS
    from src.runtime.skills import all_skills
    registries={'primitives':{k:to_json(v) for k,v in sorted(PRIMITIVES.items())},'b2_skills':SKILLS,
                'command_skills':sorted(all_skills(),key=lambda c:c['skill_id'])}
    # Detach all mutable registry objects; inventory is not runtime authority.
    registries=json.loads(json.dumps(registries))
    return {'registries':registries,'sha256':digest(registries),'counts':{k:len(v) for k,v in registries.items()},
            'classification':'PREBUILT_REGISTRY_SNAPSHOT','hardware_facts_observed':False}

def probe_command_concurrency():
    from src.runtime.command import approve,execute
    from src.runtime.intent import new_intent
    from src.runtime.primitives import Executor
    from src.fabric.session import SessionJournal
    effects=[];results=[];errors=[];sequence=threading.Lock();entered=[]
    # No Barrier: with S1 idempotent claims the second request may legitimately
    # never reach the executor (cache hit), which broke the 2-party barrier on
    # loaded CI (BrokenBarrierError). Best-effort overlap instead: the first
    # entrant yields so the second can join the inflight claim when scheduled.
    with tempfile.TemporaryDirectory(prefix='openbridge-v4-race-') as d:
        server=SimpleNamespace(fabric_registry=SimpleNamespace(devices={'dev-audit-vac':{'key':'dev-audit-vac','category':'vacuum','label':'Synthetic vacuum'}}),
                               session_journal=SessionJournal(str(Path(d)/'session.json')),runtime_executor=None)
        actual=Executor(server)
        def deny(*args):raise AssertionError('UNEXPECTED_RUNNER')
        def fake(self,key,params):
            effects.append({'device':key,'params':params});return 'EXECUTED',None,None,True,{'synthetic':True}
        actual.RUNNERS={k:deny for k in Executor.RUNNERS};actual.RUNNERS['tuya_command']=fake
        class OrderedProxy:
            def execute(self,*args,**kwargs):
                with sequence:index=len(entered);entered.append(index)
                if index==0:time.sleep(0.2)
                return actual.execute(*args,**kwargs)
        server.runtime_executor=OrderedProxy()
        doc=new_intent('Start the synthetic vacuum','en')
        doc.update(status='resolved',skill_id='vacuum.start',outcome='start',confidence=.9,targets=[{'kind':'category','ref':'vacuum'}],risk_level='high')
        preview=approve(server,doc)
        def worker():
            try:results.append(execute(server,doc,True,preview))
            except Exception as error:errors.append(type(error).__name__)
        workers=[threading.Thread(target=worker) for _ in range(2)]
        for worker in workers:worker.start()
        for worker in workers:worker.join(30)
        if any(worker.is_alive() for worker in workers) or errors:raise RuntimeError('Probe failed: '+str(errors))
        return {'evidence':'SIMULATED','same_intent':True,'requests':2,'mock_effects':len(effects),
                'transactions':sorted({r['transaction_id'] for r in results}),'cache_entries':len(server.command_executions),
                'single_effect_gate':len(effects)==1,'actual_hardware_calls':0,
                'note':'Actual Executor used; V4-S1 atomic claim joins the second request onto the first dispatch (one effect, one transaction).'}

def _permit_factory(clock):
    # The runner no longer defines permit_for (permit is built inline in main),
    # so build runner-shaped legacy permits directly: slot 0 is the canonical
    # observation, other slots cycle 4 derived ids. This probes the BROKER's
    # legacy enforcement (freshness, per-observation ceiling, ledger
    # independence), not runner wiring; the evaluation-allowance path needs a
    # dedicated audit pass (out of scope for this CI repair).
    from src.ai.broker import CreditPermit
    class Clock:
        @staticmethod
        def now(tz=None):return clock['now']
    def permit_for(slot):
        obs='audit-one-observation' if slot==0 else 'audit-derived-%d'%(slot%4)
        return CreditPermit(observation_id=obs,verified_at=clock['now'],
                            free_balance_usd=100,session_budget_usd=0.20)
    return permit_for,Clock

def probe_explanation_credit_policy():
    from src.ai import broker
    clock={'now':datetime(2026,10,28,12,tzinfo=timezone.utc)}
    factory,Clock=_permit_factory(clock);original=factory(0)
    with tempfile.TemporaryDirectory(prefix='openbridge-v4-credit-') as d,patch.object(broker,'datetime',Clock):
        path=Path(d)/'freshness.sqlite';broker.RuntimeModelBroker(path,original)._reserve()
        clock['now']+=timedelta(seconds=601);rejected=False
        try:broker.RuntimeModelBroker(path,original)._reserve()
        except broker.ModelBlocked:rejected=True
        renewed=factory(2);accepted=False
        try:broker.RuntimeModelBroker(path,renewed)._reserve();accepted=True
        except broker.ModelBlocked:pass
        factory,_=_permit_factory(clock);shared=Path(d)/'run-a.sqlite'
        for i in range(8):broker.RuntimeModelBroker(shared,factory(i))._reserve()
        with closing(sqlite3.connect(shared)) as db:total=db.execute('select sum(reserved) from reservations').fetchone()[0]/1000000
        alternate=False
        try:broker.RuntimeModelBroker(Path(d)/'run-b.sqlite',factory(0))._reserve();alternate=True
        except broker.ModelBlocked:pass
        return {'evidence':'SIMULATED','observation_age_s':601,'expired_original_rejected':rejected,
                'minted_next_slot_accepted':accepted,'reservation_total_usd':total,'derived_observation_ids':4,
                'new_output_ledger_accepted':alternate,'guard_pass':not(accepted or total>.20 or alternate),
                'actual_provider_calls':0,'actual_spend_usd':0,
                'note':'Tests enforcement properties only; does not assert historical account charges exceeded owner authorization.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Audit receipts are never overwritten')
    paths=['src/runtime/command.py','src/runtime/skills.py','src/runtime/fabric_status.py','src/runtime/primitives.py',
           'src/forge/planner.py','src/forge/planner_v2.py','src/forge/compiler.py','dev/run_explain_eval.py','src/ai/broker.py']
    subprocess.run(['git','diff','--exit-code',BASELINE,'--',*paths],cwd=ROOT,check=True)
    hashes={p:hashlib.sha256(subprocess.check_output(['git','show',BASELINE+':'+p],cwd=ROOT)).hexdigest() for p in paths}
    report={'baseline_revision':BASELINE,'auditor_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'source_blob_sha256':hashes,'registry':registry_snapshot(),
            'command_concurrency':probe_command_concurrency(),'explanation_credit_policy':probe_explanation_credit_policy(),
            'actual_hardware_calls':0,'actual_provider_calls':0,'actual_spend_usd':0,
            'security_release_gate':'BLOCKED','v4_runtime_novel_adapter':'NOT_ESTABLISHED','heldout_hardware_gold':'NOT_FROZEN',
            'scope':'Independent development probes; not physical acceptance or held-out model performance.'}
    report['security_release_gate']='BLOCKED' if not (report['command_concurrency']['single_effect_gate'] and report['explanation_credit_policy']['guard_pass']) else 'PASS_FOR_EXECUTED_PROBES_ONLY'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('xb') as handle:handle.write((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps({'output':str(args.output),'security_release_gate':report['security_release_gate'],
                      'registry_sha256':report['registry']['sha256'],'command_effects':report['command_concurrency']['mock_effects']}))
    return 2 if report['security_release_gate']=='BLOCKED' else 0

if __name__=='__main__':raise SystemExit(main())
