import json,time
from src.ai.glimmer import GlimmerBroker
b=GlimmerBroker();cap={}
orig=b.chat
def spy(p):
    t=time.monotonic();r=orig(p);cap['ms']=round((time.monotonic()-t)*1000);cap['r']=r;return r
b.chat=spy
try:print(b.plan({'battery_percent':72,'storage_free_gb':38.5},{'org.nixgame.ruler':'enabled'},'declutter')['proposal'])
except Exception as e:print('BLOCKED',e)
r=cap.get('r',{});print('ms',cap.get('ms'),'model',r.get('model'),'done',r.get('done'),r.get('done_reason'),r.get('prompt_eval_count'),r.get('eval_count'))
m=r.get('message',{});print('content',repr(m.get('content'))[:600]);print('thinking',repr(m.get('thinking'))[:300])
