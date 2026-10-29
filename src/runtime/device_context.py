"""N5: read-only device context snapshot for model reasoning.

Pure function, no I/O, no hardware: turns the fabric registry dict into a
provenance-honest context document. A missing 'online' flag becomes 'unknown'
(never assumed online); malformed input fails closed with ValueError.
"""
import copy


def build_snapshot(devices):
    if not isinstance(devices, dict):
        raise ValueError('devices must be a dict')
    out = []
    by_category = {}
    unknown_reach = 0
    for key in sorted(devices):
        d = devices[key]
        if not isinstance(d, dict):
            raise ValueError('device %r must be a dict' % (key,))
        flag = d.get('online')
        reach = 'online' if flag is True else ('offline' if flag is False else 'unknown')
        if reach == 'unknown':
            unknown_reach += 1
        cat = d.get('category') or 'unknown'
        by_category[cat] = by_category.get(cat, 0) + 1
        out.append({'key': key, 'label': d.get('label') or key, 'category': cat,
                    'reachability': reach})
    snap = {'devices': copy.deepcopy(out),
            'counts': {'total': len(out), 'by_category': by_category,
                       'unknown_reachability': unknown_reach}}
    if not out:
        snap['note'] = 'no devices paired: run discovery first'
    return snap
