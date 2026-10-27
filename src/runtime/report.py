"""Multi-device diagnostic report: one read-only pass over every readable device plus the fabric diagnosis.
Labels are replaced by category + ordinal unless the owner asks for them; identifiers never appear."""
from datetime import datetime, timezone

from src.runtime.fabric_diagnosis import diagnose

READABLE = ('phone', 'tv', 'android', 'router', 'computer')


def build(executor, redact=True, recovery=None):
    reg = executor.ctx.fabric_registry
    snap = executor.ctx.fabric_snapshot
    sections, counters = [], {}
    readable = {l['child'] for l in (snap or {}).get('links', []) if 'read' in l['grants']}
    observed_only = 0
    for key, dev in sorted(reg.devices.items(), key=lambda kv: (kv[1]['category'], kv[0])) if reg else ():
        if dev['category'] not in READABLE or key not in readable:
            observed_only += 1          # seen on the network, but OpenBridge holds no read grant for it
            continue
        counters[dev['category']] = counters.get(dev['category'], 0) + 1
        name = f"{dev['category']} {counters[dev['category']]}" if redact else dev['label']
        r = executor.execute('read_facts', key, {})
        facts = r['result'].get('facts', [])
        sections.append({'device': name, 'category': dev['category'], 'state': r['state'], 'verified': r['verified'],
                         'errors': r['errors'], 'facts': facts,
                         'warnings': [f for f in facts if f['level'] == 'warning']})
    fabric = diagnose(snap, (), recovery)
    return {'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'redacted': redact,
            'devices': sections, 'fabric': fabric,
            'summary': {'observed_only': observed_only, 'devices_read': sum(1 for s in sections if s['verified']),
                        'devices_unavailable': sum(1 for s in sections if not s['verified']),
                        'warnings': sum(len(s['warnings']) for s in sections) + sum(1 for f in fabric if f['level'] == 'warning')}}


def markdown(rep):
    def v(f):
        return f"{f['value']}{(' ' + f['unit']) if f['unit'] else ''}"
    out = [f"# OpenBridge diagnostic report", '', f"Generated {rep['generated_at']} · "
           f"{rep['summary']['devices_read']} device(s) read, {rep['summary']['devices_unavailable']} unavailable, "
           f"{rep['summary']['warnings']} warning(s), {rep['summary']['observed_only']} other device(s) seen without a read grant. OBSERVED = read from the device; INFERRED = OpenBridge's conclusion.", '']
    for s in rep['devices']:
        out.append(f"## {s['device']} — {s['state']}")
        if s['errors']:
            out.append(f"Not read: {s['errors'][0]}")
        if s['facts']:
            out += ['', '| Finding | Value | Kind | Basis |', '|---|---|---|---|']
            out += [f"| {f['name']} | {v(f)} | {f['kind']} | {f['basis'] or f['source']} |" for f in s['facts']]
        out.append('')
    out += ['## Fabric', '', '| Finding | Value | Kind | Basis |', '|---|---|---|---|']
    out += [f"| {f['name']} | {v(f)} | {f['kind']} | {f['basis'] or f['source']} |" for f in rep['fabric']]
    return '\n'.join(out) + '\n'
