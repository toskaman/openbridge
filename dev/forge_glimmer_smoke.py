"""One actual synthetic local Glimmer plan trace. No hardware or provider credits."""
import json
from pathlib import Path
import time
from src.ai.glimmer import GlimmerBroker
from src.forge.fixtures import manifest
from src.forge.meta_planner import MetaCapabilityPlanner
now=time.time()
try:
 result=MetaCapabilityPlanner(GlimmerBroker()).plan([manifest(now)],now)
 result.update({'evidence_kind':'ACTUAL_LOCAL_META_SYNTHETIC_PLAN','recorded_at_unix':time.time(),'hardware_proof':False})
except Exception as e:
 result={'evidence_kind':'ACTUAL_LOCAL_META_FAILED_ATTEMPT','error':str(e),'recorded_at_unix':time.time(),'hardware_proof':False,'provider_cost_usd':0.0}
Path('docs/forge/glimmer-plan-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2),flush=True)
