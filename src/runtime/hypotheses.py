"""Competing hypotheses over the cross-transport timeline (V4-01). Deterministic rules, no model required.

Wording rules (from the V4 spec): a hypothesis says "consistent with", never "caused by"; every hypothesis cites
timeline entry ids; counterexamples are counted and shown; an explicit "unobserved cause" alternative is always
present, so there are at least two hypotheses whenever there is a symptom; with no symptom the answer is
UNKNOWN_NOT_ENOUGH_DATA. Nothing here reads or writes a device. An optional Meta model may *rephrase* the result
later, but the ranking and the citations come from these rules.
"""

DEFAULT_WINDOW_S = 90
ASLEEP = ('asleep', 'dozing')


def _is_symptom(e):
    n, v = e['name'], e['value']
    return ((n == 'link' and v in ('lost', 'identity_changed')) or (n == 'wifi' and v == 'disabled')
            or (n == 'internet_state' and v not in (None, 'up')) or (n == 'airplane_mode' and v is True))


RULES = (
    # rule id, statement template, predicate(entry, target) -> bool, scope ('target'|'other'|'router'|'any')
    ('router_radio_change', 'consistent with a Wi-Fi radio or channel change on the router',
     lambda e, tgt: e['category'] == 'router' and e['kind'] == 'change' and e['name'].startswith(('wifi_channel_', 'wifi_radio_', 'wifi_enabled'))),
    ('wan_outage', 'consistent with an upstream Internet outage reported by the router',
     lambda e, tgt: e['category'] == 'router' and ((e['name'] == 'internet_state' and e['value'] != 'up') or (e['name'] == 'fiber_link' and e['value'] is False))),
    ('device_sleep', 'consistent with the device going to sleep (power state), not a network fault',
     lambda e, tgt: e['device_key'] == tgt and e['name'] == 'power_state' and e['value'] in ASLEEP),
    ('device_radio_off', 'consistent with Wi-Fi being switched off on the device itself',
     lambda e, tgt: e['device_key'] == tgt and ((e['name'] == 'wifi' and e['value'] == 'disabled') or (e['name'] == 'airplane_mode' and e['value'] is True))),
    ('device_thermal', 'consistent with thermal stress on the device',
     lambda e, tgt: e['device_key'] == tgt and e['name'] in ('thermal_throttling_likely', 'battery_hot') and e['value'] is True),
    ('shared_outage', 'consistent with a cause shared by several devices (another device lost its link at the same time)',
     lambda e, tgt: e['device_key'] not in (tgt, '') and e['category'] != 'router' and e['name'] == 'link' and e['value'] == 'lost'),
)


def _confidence(support, missing, spurious):
    if support >= 3 and missing == 0 and spurious == 0:
        return 'high'
    if support >= 2 or (support >= 1 and missing == 0 and spurious == 0):
        return 'medium'
    return 'low'


def analyze(entries, target, window_s=DEFAULT_WINDOW_S):
    """entries: Timeline.rows() (any order). target: device_key whose symptom is being explained."""
    es = sorted(entries, key=lambda e: (e['t'], e['id']))
    symptoms = [e for e in es if e['device_key'] == target and _is_symptom(e)]
    trace = []
    if not symptoms:
        return {'target': target, 'window_s': window_s, 'verdict': 'UNKNOWN_NOT_ENOUGH_DATA', 'symptoms': [],
                'hypotheses': [], 'trace': [{'step': 'symptoms', 'found': 0,
                                             'note': 'no link loss, Wi-Fi off or WAN-down entry for this device in the timeline'}],
                'probe': None}
    trace.append({'step': 'symptoms', 'found': len(symptoms), 'ids': [s['id'] for s in symptoms]})
    hyps = []
    for rid, statement, pred in RULES:
        causes = [e for e in es if pred(e, target)]
        cited, support, missing = [], 0, 0
        for s in symptoms:
            near = [c for c in causes if abs(c['t'] - s['t']) <= window_s]
            if near:
                support += 1
                cited += [c['id'] for c in near]
            else:
                missing += 1
        spurious = sum(1 for c in causes if not any(abs(c['t'] - s['t']) <= window_s for s in symptoms))
        trace.append({'step': 'rule', 'rule': rid, 'candidates': len(causes), 'support': support,
                      'symptoms_without_it': missing, 'occurrences_without_symptom': spurious})
        if support:
            hyps.append({'id': rid, 'statement': statement, 'confidence': _confidence(support, missing, spurious),
                         'support': support, 'counterexamples': {'symptoms_without_it': missing, 'occurrences_without_symptom': spurious},
                         'cites': sorted(set(cited), key=lambda x: int(x[1:])) + [s['id'] for s in symptoms],
                         'kind': 'INFERRED', 'claim': 'correlation in time, not proven cause'})
    rank = {'high': 0, 'medium': 1, 'low': 2}
    hyps.sort(key=lambda h: (rank[h['confidence']], -h['support'], h['id']))
    if not hyps:
        hyps.append({'id': 'device_local_link', 'confidence': 'low', 'support': 0,
                     'statement': "consistent with a problem local to this device's own link (no other observed source changed in the window)",
                     'counterexamples': {}, 'cites': [s['id'] for s in symptoms], 'kind': 'INFERRED',
                     'claim': 'absence of other evidence, not a measurement'})
    explained = sum(1 for s in symptoms if any(s['id'] in h['cites'] for h in hyps if h['support']))
    hyps.append({'id': 'unobserved_cause', 'confidence': 'medium' if not hyps else 'low', 'support': 0,
                 'statement': 'consistent with a cause OpenBridge cannot observe (interference, firmware, an app on the device, or a source without a read grant)',
                 'counterexamples': {}, 'cites': [s['id'] for s in symptoms], 'kind': 'INFERRED',
                 'claim': 'alternative kept on purpose; no measurement supports or excludes it'})
    devices = sorted({target} | {e['device_key'] for h in hyps for e in es if e['id'] in h['cites'] and e['device_key']})
    probe = {'primitive_id': 'diagnostic_probe', 'params': {'device_keys': devices[:4], 'samples': 3, 'interval_s': 10},
             'why': 'read-only re-measurement of the devices cited above; no setting is changed', 'reversibility': 'NONE'}
    return {'target': target, 'window_s': window_s, 'verdict': 'HYPOTHESES', 'symptoms': [s['id'] for s in symptoms],
            'symptoms_explained_by_an_observed_rule': explained, 'hypotheses': hyps, 'trace': trace, 'probe': probe}
