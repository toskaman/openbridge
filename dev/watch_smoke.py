"""Owner-run: new power/thermal diagnostics and a live read-only watch on every connected Android device.
Prints finding names/values for power and thermal only, plus watch events."""
import json
import time

from src.runtime import api_v2
from src.server import create_server


def main():
    s = create_server(0)
    ex = api_v2.executor(s)
    ex.execute('bounded_discovery', 'fabric', {'providers': ['android']})
    out = {'devices': {}, 'watches': []}
    keys = [k for k, d in s.fabric_registry.devices.items() if d['category'] in ('phone', 'tv') and any(i.strong for i in d['identifiers'])]
    for k in keys:
        cat = s.fabric_registry.devices[k]['category']
        r = ex.execute('read_facts', k, {})
        out['devices'][cat] = {'state': r['state'], 'facts': {f['name']: f['value'] for f in r['result'].get('facts', [])
                                                             if f['name'] in ('power_state', 'thermal_status', 'thermal_throttling_likely', 'battery_level', 'memory_available')}}
        rule = {'finding': 'memory_available', 'op': 'gt', 'threshold_number': 0.01, 'interval_s': 30, 'lifetime_s': 60}
        w = ex.execute('watch_start', k, rule, consent=True)
        out['watches'].append({'device': cat, 'state': w['state'], 'watch_id': w['result'].get('watch_id')})
    time.sleep(40)
    out['watch_list'] = [{k: w[k] for k in ('state', 'runs', 'triggered', 'last_state')} for w in api_v2.reader(s)('/api/v2/watches')['watches']]
    out['events'] = [{k: v for k, v in e.items() if k in ('kind', 'finding', 'op', 'finding_kind', 'state', 'errors')}
                     for e in ex.events_since(0) if e['kind'].startswith('watch')]
    for w in out['watches']:
        out.setdefault('stop', []).append(ex.execute('watch_stop', 'fabric', {'watch_id': w['watch_id']})['after'])
    s.server_close()
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
