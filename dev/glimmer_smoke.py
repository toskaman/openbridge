"""One pinned Muse Glimmer planning call on synthetic facts; records latency, tokens and observed VRAM."""
import json
import time
from urllib.request import build_opener, ProxyHandler
from src.ai.glimmer import GlimmerBroker

b=GlimmerBroker()
print('ready',b.ready(),flush=True)
t=time.monotonic()
r=b.plan({'battery_percent':72,'storage_free_gb':38.5},{'org.nixgame.ruler':'enabled','one.vik.stopwatch':'enabled'},'declutter')
r['wall_ms']=round((time.monotonic()-t)*1000)
ps=json.load(build_opener(ProxyHandler({})).open('http://127.0.0.1:11438/api/ps',timeout=5))
r['loaded']=[{k:m.get(k) for k in ('name','size','size_vram')} for m in ps.get('models',[])]
print(json.dumps(r,indent=1))
