"""Owner-run: read-only Freebox watch 'internet_state != up' (an internet-down alert). Expects no trigger while online."""
import json, time
from src.runtime import api_v2
from src.server import create_server

s = create_server(0)
ex = api_v2.executor(s)
ex.execute('bounded_discovery', 'fabric', {'providers': ['freebox']})
box = next(k for k, d in s.fabric_registry.devices.items() if d['category'] == 'router')
w = ex.execute('watch_start', box, {'finding': 'internet_state', 'op': 'ne', 'threshold_text': 'up', 'interval_s': 30, 'lifetime_s': 60}, consent=True)
time.sleep(35)
lst = api_v2.reader(s)('/api/v2/watches')['watches'][0]
print(json.dumps({'start': w['state'], 'runs': lst['runs'], 'last_value': lst['last_value'], 'triggered': lst['triggered'],
                  'last_state': lst['last_state'], 'stop': ex.execute('watch_stop', 'fabric', {'watch_id': lst['watch_id']})['after']}))
s.server_close()
