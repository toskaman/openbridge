"""Coverage-advisor ablation on synthetic graphs (no device access): rules vs local Meta models.
Reports validity, agreement with the goal-priority rule, and goal-fit (chosen step kind matches the goal's primary kind)."""
import argparse, json, random, statistics, time
from pathlib import Path
from src.fabric.advisor import advise, candidate_steps, rule_choice, PRIORITY
from src.ai.broker import ModelBlocked

CATS=('phone','tv','media','iot','computer','router')

def graphs(n=12, seed=7):
    rng=random.Random(seed);out=[]
    for i in range(n):
        devs=[];links=[]
        for j in range(rng.randint(4,14)):
            cat=rng.choice(CATS);caps=[]
            if cat=='router' and rng.random()<0.6:caps.append({'name':'lan_inventory','status':'BLOCKED'})
            if cat in ('phone','tv') and rng.random()<0.6:caps.append({'name':'ble_relay','status':'NOT_SUPPORTED'})
            if cat=='tv' and rng.random()<0.5:caps.append({'name':'tv_remote_protocol','status':'NOT_SUPPORTED'})
            devs.append({'key':f'k{j:02d}','category':cat,'label':'x','capabilities':caps,'possibly_same_as':[]})
            links.append({'parent':'pc','child':f'k{j:02d}'})
        if len(devs)>3 and rng.random()<0.5:devs[1]['possibly_same_as']=['k02'];devs[2]['possibly_same_as']=['k01']
        snap={'devices':devs,'links':links}
        if len(candidate_steps(snap)[0])>=2:out.append(snap)
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--route',choices=['llama3b','glimmer'],required=True);ap.add_argument('--repeats',type=int,default=2)
    a=ap.parse_args()
    if a.route=='llama3b':
        from src.ai.local_meta import LocalMetaBroker;b=LocalMetaBroker()
    else:
        from src.ai.glimmer import GlimmerBroker;b=GlimmerBroker()
    rows=[]
    for r in range(a.repeats):
        for gi,snap in enumerate(graphs()):
            steps,_=candidate_steps(snap);kinds={s['kind'] for s in steps}
            for goal in PRIORITY:
                primary=next(k for k in PRIORITY[goal] if k in kinds)
                t=time.monotonic()
                try:res=advise(b,snap,goal);step=res['step'];err=None
                except ModelBlocked as e:step=None;err=str(e)
                rows.append({'graph':gi,'goal':goal,'repeat':r,'step':step,'rule':rule_choice(steps,goal),'error':err,
                             'goal_fit':bool(step) and step.split(':')[0]==primary,'ms':round((time.monotonic()-t)*1000)})
    n=len(rows);valid=[x for x in rows if x['step']]
    res={'route':a.route,'graphs':len(graphs()),'goals':3,'repeats':a.repeats,'attempts':n,
         'valid_pct':round(100*len(valid)/n,1),'agree_with_rule_pct':round(100*sum(x['step']==x['rule'] for x in rows)/n,1),
         'goal_fit_pct':round(100*sum(x['goal_fit'] for x in rows)/n,1),'median_ms':statistics.median(x['ms'] for x in rows),
         'rule_goal_fit_pct':100.0,'synthetic_inputs_only':True,'recorded_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'rows':rows}
    Path(f'docs/benchmark/advisor-benchmark-{a.route}.json').write_text(json.dumps(res,indent=1)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in res.items() if k!='rows'}))

if __name__=='__main__':main()
