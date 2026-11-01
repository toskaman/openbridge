"""Campaign Two S4.5: Universal Device Diagnostics.

Answers owner why-questions from OBSERVED permitted facts only. Each answer
cites the evidence refs it rests on; when telemetry is insufficient the
answer names the missing measurement instead of guessing. No benchmark data
is ever invented: comparisons use observed metric values only, and devices
without measurements are reported as unmeasured, never filled in.

Pipeline: deterministic analysis (findings + candidate recommendations) ->
Meta-generated explanation + safe recommendations (proposer interface;
deterministic stub in tests, no live model needed) -> strict validation ->
report. The model may only explain the supplied findings and pick from the
supplied candidate recommendations; anything else is rejected.
"""
import copy
import hashlib
import re
from decimal import Decimal

QUESTIONS = ('battery_drain', 'best_pc_for_dev', 'strongest_connectivity',
             'tv_control_loss', 'relay_unavailable', 'watch_sleep_drops',
             'what_to_install')

CONFIDENCE = ('high', 'medium', 'low', 'insufficient')

LIMIT = ('Diagnostics explains only observed facts; it never guesses causes, '
         'never invents measurements, and every recommendation still needs '
         'owner action.')

# Observed-fact vocabulary. Facts outside this set are rejected, never read.
PERMITTED_FACTS = frozenset({
    # battery
    'battery_percent', 'battery_charging', 'battery_plugged',
    'battery_discharge_pct_per_hour', 'battery_capacity_mah',
    'screen_on_hours', 'top_consumer',
    # pc / dev fitness (observed metrics only, never benchmark scores)
    'cpu_threads', 'ram_gb', 'disk_free_gb', 'os', 'gpu_name', 'gpu_vram_gb',
    # connectivity
    'wifi_band', 'wifi_rssi_dbm', 'link_type', 'rtt_ms', 'cellular',
    # tv control path
    'adb_authorized', 'adb_transport', 'network_reachable', 'tv_power',
    'last_seen_s_ago',
    # relay path
    'relay_online', 'relay_busy', 'relay_owner_enabled', 'relay_permission',
    'relay_battery_powered', 'companion_running', 'bluetooth_on',
    # watch sleep
    'watch_battery_percent', 'watch_wifi_connected', 'watch_ble_connected',
    'phone_ble_connected', 'overnight_gap_minutes',
    # install advice
    'companion_installed', 'sdk', 'storage_free_gb',
    'install_blocked_reason',
})

FACT_CONFIDENCE = ('measured', 'reported', 'unknown')


class DiagnosticError(ValueError):
    pass


def ref(opaque_id, name):
    return '%s#%s' % (opaque_id, name)


# -- recommendation catalog: read-only or owner-action steps only -------------
# 'guide' points at a deterministic guide in src.fabric.guidance, when one
# exists for the step. Nothing here runs a command on any device.
RECOMMENDATIONS = {
    'plug_in_charger': {'title': 'Plug in the charger',
                        'owner_action': 'Connect the charger; re-check the battery level after a while.',
                        'kind': 'owner_action'},
    'check_top_consumer': {'title': 'Look at the top battery consumer',
                           'owner_action': 'Open Settings > Battery and look at the top consumer; close or restrict it if you do not need it.',
                           'kind': 'read_only'},
    'rerun_battery_sample': {'title': 'Take another battery sample later',
                             'owner_action': 'Leave the device unplugged, then refresh the device facts to record a second sample.',
                             'kind': 'read_only'},
    'use_top_pc_for_dev': {'title': 'Develop on the best-measured PC',
                           'owner_action': 'Use the PC ranked first below; the ranking rests only on observed CPU, RAM and free disk.',
                           'kind': 'read_only'},
    'free_disk_space': {'title': 'Free disk space',
                        'owner_action': 'Delete files you no longer need, or move them elsewhere, then refresh the facts.',
                        'kind': 'owner_action'},
    'rerun_pc_facts': {'title': 'Refresh the PC facts',
                       'owner_action': 'Refresh the device facts so unmeasured PCs can be ranked.',
                       'kind': 'read_only'},
    'prefer_best_link': {'title': 'Prefer the strongest observed link',
                         'owner_action': 'Use the device or band ranked first below for tasks that need connectivity.',
                         'kind': 'read_only'},
    'move_closer_to_router': {'title': 'Move closer to the router',
                              'owner_action': 'Move the device closer to the router or access point, then refresh the signal reading.',
                              'kind': 'owner_action'},
    'rerun_link_sample': {'title': 'Refresh the link measurements',
                          'owner_action': 'Refresh the device facts to record signal strength and latency.',
                          'kind': 'read_only'},
    'check_tv_power': {'title': 'Check the TV is on and on the home network',
                       'owner_action': 'Turn the TV on with its remote and confirm it is on your home Wi-Fi.',
                       'kind': 'owner_action'},
    'reaccept_adb_prompt': {'title': 'Accept debugging on the TV screen',
                            'owner_action': 'Accept the "Allow debugging?" dialog on the TV.',
                            'kind': 'owner_action', 'guide': 'tv_debug_prompt'},
    'repair_wifi_adb': {'title': 'Pair wireless debugging again',
                        'owner_action': 'Re-pair wireless debugging from the TV developer options.',
                        'kind': 'owner_action', 'guide': 'wifi_adb_pairing'},
    'open_companion': {'title': 'Open the OpenBridge Companion',
                       'owner_action': 'Open the Companion app on the relay device.',
                       'kind': 'owner_action', 'guide': 'companion_not_running'},
    'resume_scans': {'title': 'Resume scans in the Companion',
                     'owner_action': 'In the Companion app, select "Resume scans".',
                     'kind': 'owner_action', 'guide': 'owner_scan_disabled'},
    'enable_bluetooth': {'title': 'Turn Bluetooth on',
                         'owner_action': 'Turn Bluetooth on from the quick-settings panel.',
                         'kind': 'owner_action', 'guide': 'bluetooth_off'},
    'grant_ble_permission': {'title': 'Allow Bluetooth scanning in the Companion',
                             'owner_action': 'In the Companion app, allow Bluetooth scanning.',
                             'kind': 'owner_action', 'guide': 'ble_permission'},
    'charge_watch_overnight': {'title': 'Charge the watch before sleep',
                               'owner_action': 'Charge the watch before bed so it lasts the night.',
                               'kind': 'owner_action'},
    'keep_phone_nearby': {'title': 'Keep the phone near the watch overnight',
                          'owner_action': 'Keep the paired phone within Bluetooth range overnight.',
                          'kind': 'owner_action'},
    'rerun_sleep_sample': {'title': 'Record another night of link samples',
                           'owner_action': 'Leave both devices on overnight, then refresh the facts.',
                           'kind': 'read_only'},
    'install_companion': {'title': 'Install the OpenBridge Companion',
                          'owner_action': 'Install the Companion on the device, accepting the on-device prompt.',
                          'kind': 'owner_action', 'guide': 'companion_install_blocked'},
    'free_storage': {'title': 'Free storage on the device',
                     'owner_action': 'Free storage on the device, then retry the install.',
                     'kind': 'owner_action'},
    'check_install_prompt': {'title': 'Confirm the install prompt on the device',
                             'owner_action': 'Look at the device and confirm the installation prompt.',
                             'kind': 'owner_action', 'guide': 'companion_install_blocked'},
}


# -- bundle validation ------------------------------------------------------
# Bundle shape: {'devices': [{'opaque_id', 'category', 'label'?,
#   'facts': [{'name', 'value', 'unit', 'source', 'observed_at',
#   'confidence'?}]}], 'links'?: [...]}. Raw identifiers are never accepted:
# devices carry opaque ids only.

def _index(bundle):
    if not isinstance(bundle, dict) or not isinstance(bundle.get('devices'), list):
        raise DiagnosticError('BUNDLE_MUST_HAVE_DEVICES')
    devices = bundle['devices']
    if not devices:
        raise DiagnosticError('NO_DEVICES')
    facts = {}
    for d in devices:
        if not isinstance(d, dict) or not d.get('opaque_id') or not d.get('category'):
            raise DiagnosticError('DEVICE_NEEDS_OPAQUE_ID_AND_CATEGORY')
        if not isinstance(d.get('facts'), list):
            raise DiagnosticError('DEVICE_NEEDS_FACTS')
        for f in d['facts']:
            if not isinstance(f, dict) or 'name' not in f or 'value' not in f:
                raise DiagnosticError('FACT_NEEDS_NAME_AND_VALUE')
            if f['name'] not in PERMITTED_FACTS:
                raise DiagnosticError('UNKNOWN_FACT:%s' % f['name'])
            if f.get('confidence', 'measured') not in FACT_CONFIDENCE:
                raise DiagnosticError('BAD_FACT_CONFIDENCE:%s' % f['name'])
            facts[ref(d['opaque_id'], f['name'])] = f
    return devices, facts


def _observed(facts, opaque_id, name):
    """Observed fact value, or None when unmeasured. Facts with 'unknown'
    confidence are treated as unmeasured: they cite nothing."""
    f = facts.get(ref(opaque_id, name))
    if f is None or f.get('confidence', 'measured') == 'unknown':
        return None
    return f['value']


def _label(device):
    return device.get('label') or device['opaque_id']


def _target(devices, categories, device):
    if device is not None:
        hit = [d for d in devices if d['opaque_id'] == device]
        if not hit:
            raise DiagnosticError('UNKNOWN_DEVICE')
        return hit[0]
    for d in devices:
        if d['category'] in categories:
            return d
    return devices[0]


def _finding(text, evidence_refs):
    return {'text': text, 'evidence_refs': list(evidence_refs)}


def _missing(measurement, how):
    return '%s -- %s' % (measurement, how)


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# -- deterministic analyzers --------------------------------------------------
# Each returns (target_opaque_id, findings, missing, confidence, candidates).
# Finding texts embed observed values only, never constants or guesses, so a
# grounded explanation can quote them verbatim.

def _analyze_battery_drain(devices, facts, device):
    d = _target(devices, ('phone', 'watch', 'tablet'), device)
    oid, label = d['opaque_id'], _label(d)
    pct = _observed(facts, oid, 'battery_percent')
    charging = _observed(facts, oid, 'battery_charging')
    rate = _observed(facts, oid, 'battery_discharge_pct_per_hour')
    consumer = _observed(facts, oid, 'top_consumer')
    screen = _observed(facts, oid, 'screen_on_hours')
    findings, missing = [], []
    if pct is None and charging is None and rate is None:
        return oid, findings, [
            _missing('battery_percent', 'refresh the device facts once'),
            _missing('battery_discharge_pct_per_hour',
                     'two battery_percent reads while unplugged, some time apart'),
            _missing('top_consumer', 'per-app battery use from Settings > Battery'),
        ], 'insufficient', ['rerun_battery_sample']
    if charging is True:
        findings.append(_finding(
            '%s is charging now, so it is not draining.' % label,
            [ref(oid, 'battery_charging')]))
        return oid, findings, [], 'high', []
    if _num(rate):
        findings.append(_finding(
            '%s is draining at %s percent per hour while unplugged.' % (label, rate),
            [ref(oid, 'battery_discharge_pct_per_hour')]))
    elif pct is not None:
        findings.append(_finding(
            '%s is at %s percent battery.' % (label, pct),
            [ref(oid, 'battery_percent')]))
        missing.append(_missing('battery_discharge_pct_per_hour',
                                'two battery_percent reads while unplugged, some time apart'))
    if consumer:
        findings.append(_finding(
            'The largest observed consumer on %s is %s.' % (label, consumer),
            [ref(oid, 'top_consumer')]))
    elif rate is not None:
        missing.append(_missing('top_consumer', 'per-app battery use from Settings > Battery'))
    if _num(screen):
        findings.append(_finding(
            'The screen was on for %s hours on %s.' % (screen, label),
            [ref(oid, 'screen_on_hours')]))
    if charging is False:
        findings.append(_finding('%s is unplugged.' % label, [ref(oid, 'battery_charging')]))
    if _num(rate) and consumer:
        confidence = 'high'
    elif _num(rate):
        confidence = 'medium'
    else:
        confidence = 'low'
    candidates = ['rerun_battery_sample']
    if pct is not None and _num(pct) and pct < 25:
        candidates = ['plug_in_charger'] + candidates
    if consumer:
        candidates = ['check_top_consumer'] + candidates
    return oid, findings, missing, confidence, candidates


def _analyze_best_pc_for_dev(devices, facts, device):
    del device  # comparative question: every measured PC is ranked
    pcs = [d for d in devices if d['category'] in ('computer', 'pc')]
    rows, missing = [], []
    for d in pcs:
        oid = d['opaque_id']
        t = _observed(facts, oid, 'cpu_threads')
        ram = _observed(facts, oid, 'ram_gb')
        disk = _observed(facts, oid, 'disk_free_gb')
        have = [n for n, v in (('cpu_threads', t), ('ram_gb', ram), ('disk_free_gb', disk))
                if _num(v)]
        if not have:
            rows.append({'device': oid, 'label': _label(d), 'observed_score': None,
                         'confidence': 'insufficient', 'evidence_refs': []})
            missing.append(_missing('cpu_threads/ram_gb/disk_free_gb for %s' % _label(d),
                                    'refresh the PC facts'))
            continue
        score = 3 * (t or 0) + 4 * (ram or 0) + 0.1 * min(disk or 0, 200)
        for n in ('cpu_threads', 'ram_gb', 'disk_free_gb'):
            if not _num(_observed(facts, oid, n)):
                missing.append(_missing('%s for %s' % (n, _label(d)), 'refresh the PC facts'))
        rows.append({'device': oid, 'label': _label(d), 'observed_score': round(score, 1),
                     'confidence': 'high' if len(have) == 3 else 'medium' if len(have) == 2 else 'low',
                     'evidence_refs': [ref(oid, n) for n in have]})
    measured = [r for r in rows if r['observed_score'] is not None]
    measured.sort(key=lambda r: r['observed_score'], reverse=True)
    if not measured:
        return None, [], missing or [_missing('cpu_threads/ram_gb/disk_free_gb',
                                              'no computer in the bundle has observed metrics')], \
            'insufficient', ['rerun_pc_facts']
    top = measured[0]
    parts = []
    for n in ('cpu_threads', 'ram_gb', 'disk_free_gb'):
        v = _observed(facts, top['device'], n)
        if _num(v):
            parts.append('%s %s' % (v, {'cpu_threads': 'threads', 'ram_gb': 'GB RAM',
                                        'disk_free_gb': 'GB free'}[n]))
    findings = [_finding(
        '%s ranks first for development on observed metrics (%s).'
        % (top['label'], ', '.join(parts)), top['evidence_refs'])]
    if len(measured) > 1:
        second = measured[1]
        spares = []
        for n in ('cpu_threads', 'ram_gb', 'disk_free_gb'):
            v = _observed(facts, second['device'], n)
            if _num(v):
                spares.append('%s %s' % (v, {'cpu_threads': 'threads', 'ram_gb': 'GB RAM',
                                             'disk_free_gb': 'GB free'}[n]))
        findings.append(_finding(
            '%s ranks next on observed metrics (%s).'
            % (second['label'], ', '.join(spares) if spares else 'fewer metrics observed'),
            second['evidence_refs']))
    confidence = top['confidence']
    candidates = ['use_top_pc_for_dev', 'rerun_pc_facts']
    low_disk = [r for r in measured
                if _num(_observed(facts, r['device'], 'disk_free_gb'))
                and _observed(facts, r['device'], 'disk_free_gb') < 10]
    if low_disk:
        candidates.insert(1, 'free_disk_space')
    return top['device'], findings, missing, confidence, candidates


def _analyze_strongest_connectivity(devices, facts, device):
    del device  # comparative question: every measured device is ranked
    rows, missing = [], []
    for d in devices:
        oid = d['opaque_id']
        rssi = _observed(facts, oid, 'wifi_rssi_dbm')
        rtt = _observed(facts, oid, 'rtt_ms')
        band = _observed(facts, oid, 'wifi_band')
        have = [n for n, v in (('wifi_rssi_dbm', rssi), ('rtt_ms', rtt), ('wifi_band', band))
                if v is not None]
        if not have:
            missing.append(_missing('wifi_rssi_dbm/rtt_ms for %s' % _label(d),
                                    'refresh the link measurements'))
            continue
        rows.append({'device': oid, 'label': _label(d), 'rssi': rssi if _num(rssi) else None,
                     'rtt': rtt if _num(rtt) else None, 'band': band,
                     'evidence_refs': [ref(oid, n) for n in have]})
    if not rows:
        return None, [], missing, 'insufficient', ['rerun_link_sample']
    rows.sort(key=lambda r: (r['rssi'] is None, -(r['rssi'] or 0),
                             r['rtt'] is None, r['rtt'] or 0))
    top = rows[0]
    detail = []
    if top['rssi'] is not None:
        detail.append('%s dBm' % top['rssi'])
    if top['rtt'] is not None:
        detail.append('%s ms round-trip' % top['rtt'])
    if top['band']:
        detail.append('on %s' % top['band'])
    findings = [_finding(
        '%s has the strongest observed connectivity (%s).' % (top['label'], ', '.join(detail)),
        top['evidence_refs'])]
    if len(rows) > 1 and rows[1]['rssi'] is not None and top['rssi'] is not None:
        findings.append(_finding(
            'Next is %s at %s dBm.' % (rows[1]['label'], rows[1]['rssi']),
            rows[1]['evidence_refs']))
    confidence = 'high' if top['rssi'] is not None and top['rtt'] is not None else 'medium'
    candidates = ['prefer_best_link', 'rerun_link_sample']
    if top['rssi'] is not None and top['rssi'] < -70:
        candidates.insert(1, 'move_closer_to_router')
    return top['device'], findings, missing, confidence, candidates


def _analyze_tv_control_loss(devices, facts, device):
    d = _target(devices, ('tv',), device)
    oid, label = d['opaque_id'], _label(d)
    authorized = _observed(facts, oid, 'adb_authorized')
    reachable = _observed(facts, oid, 'network_reachable')
    power = _observed(facts, oid, 'tv_power')
    seen = _observed(facts, oid, 'last_seen_s_ago')
    findings, missing = [], []
    if reachable is None and authorized is None and power is None and seen is None:
        return oid, findings, [
            _missing('network_reachable', 'ping the TV address once from this PC'),
            _missing('adb_authorized', 'read the ADB authorization state'),
            _missing('tv_power', 'look at the TV: on, standby, or off'),
        ], 'insufficient', ['check_tv_power']
    if reachable is False:
        findings.append(_finding(
            '%s is not reachable on the home network, so control cannot reach it.'
            % label, [ref(oid, 'network_reachable')]))
    if power in ('off', 'standby'):
        findings.append(_finding(
            '%s is observed %s, which explains the lost control.' % (label, power),
            [ref(oid, 'tv_power')]))
    if reachable is not False and authorized is False:
        findings.append(_finding(
            '%s is reachable but its ADB authorization is gone; the owner prompt must be accepted again.'
            % label, [ref(oid, 'adb_authorized')] +
            ([ref(oid, 'network_reachable')] if reachable is True else [])))
    if _num(seen):
        findings.append(_finding(
            '%s was last seen %s seconds ago.' % (label, seen),
            [ref(oid, 'last_seen_s_ago')]))
    if reachable is None:
        missing.append(_missing('network_reachable', 'ping the TV address once from this PC'))
    if authorized is None:
        missing.append(_missing('adb_authorized', 'read the ADB authorization state'))
    if power is None:
        missing.append(_missing('tv_power', 'look at the TV: on, standby, or off'))
    if reachable is True and authorized is True:
        findings.append(_finding(
            '%s is reachable and authorized; the control path looks intact from observed facts.'
            % label, [ref(oid, 'network_reachable'), ref(oid, 'adb_authorized')]))
        return oid, findings, missing, 'medium', ['check_tv_power']
    candidates = []
    if power in ('off', 'standby') or reachable is False:
        candidates.append('check_tv_power')
    if authorized is False:
        candidates += ['reaccept_adb_prompt', 'repair_wifi_adb']
    if not candidates:
        candidates = ['check_tv_power']
    confidence = 'high' if (reachable is False or authorized is False) else 'low'
    return oid, findings, missing, confidence, candidates


def _analyze_relay_unavailable(devices, facts, device):
    d = _target(devices, ('phone', 'tv', 'tablet'), device)
    oid, label = d['opaque_id'], _label(d)
    gates = (  # checked in order; the first failing OBSERVED gate explains it
        ('relay_owner_enabled', True, 'owner_enabled', 'resume_scans',
         '%s has scans paused by its owner.' % label),
        ('relay_permission', True, 'granted', 'grant_ble_permission',
         '%s has not granted Bluetooth scanning.' % label),
        ('companion_running', True, 'running', 'open_companion',
         'The Companion is not running on %s.' % label),
        ('bluetooth_on', True, 'on', 'enable_bluetooth',
         'Bluetooth is off on %s.' % label),
        ('relay_online', True, 'online', 'open_companion',
         '%s is offline as a relay.' % label),
        ('relay_busy', False, 'idle', 'rerun_link_sample',
         '%s is busy serving another request.' % label),
    )
    observed_any = any(_observed(facts, oid, name) is not None for name, _, _, _, _ in gates)
    if not observed_any:
        return oid, [], [
            _missing('relay_owner_enabled', 'read the Companion scan toggle'),
            _missing('relay_permission', 'read the Bluetooth scanning grant'),
            _missing('companion_running', 'check whether the Companion is open'),
            _missing('bluetooth_on', 'read the Bluetooth radio state'),
            _missing('relay_online', 'read the relay presence'),
        ], 'insufficient', ['open_companion']
    findings, missing, candidates = [], [], []
    explained = False
    for name, want, word, rec, text in gates:
        v = _observed(facts, oid, name)
        if v is None:
            missing.append(_missing(name, 'refresh the relay facts for %s' % label))
            continue
        if not explained and v is not want:
            findings.append(_finding(text + ' Observed %s=%s (needs %s).' % (name, v, word),
                                     [ref(oid, name)]))
            candidates.append(rec)
            explained = True
    if not explained:
        findings.append(_finding(
            'Every observed relay gate on %s is open; the relay looks available from observed facts.'
            % label,
            [ref(oid, name) for name, _, _, _, _ in gates
             if _observed(facts, oid, name) is not None]))
        return oid, findings, missing, 'medium', ['rerun_link_sample']
    return oid, findings, missing, 'high', candidates


def _analyze_watch_sleep_drops(devices, facts, device):
    d = _target(devices, ('watch',), device)
    oid, label = d['opaque_id'], _label(d)
    gap = _observed(facts, oid, 'overnight_gap_minutes')
    batt = _observed(facts, oid, 'watch_battery_percent')
    wifi = _observed(facts, oid, 'watch_wifi_connected')
    ble = _observed(facts, oid, 'watch_ble_connected')
    findings, missing = [], []
    if gap is None and batt is None and wifi is None and ble is None:
        return oid, findings, [
            _missing('overnight_gap_minutes', 'link up/down observations through one night'),
            _missing('watch_battery_percent', 'read the watch battery before bed and at wake'),
            _missing('watch_ble_connected/watch_wifi_connected', 'read the watch link state'),
        ], 'insufficient', ['rerun_sleep_sample']
    if _num(gap):
        findings.append(_finding(
            '%s dropped for %s minutes overnight.' % (label, gap),
            [ref(oid, 'overnight_gap_minutes')]))
    else:
        missing.append(_missing('overnight_gap_minutes', 'link up/down observations through one night'))
    if _num(batt):
        findings.append(_finding(
            'The watch battery was observed at %s percent.' % batt,
            [ref(oid, 'watch_battery_percent')]))
    else:
        missing.append(_missing('watch_battery_percent', 'read the watch battery before bed and at wake'))
    if ble is False and wifi is False:
        findings.append(_finding(
            'Both watch links on %s were observed down.' % label,
            [ref(oid, 'watch_ble_connected'), ref(oid, 'watch_wifi_connected')]))
    elif ble is False:
        findings.append(_finding(
            'The watch Bluetooth link on %s was observed down.' % label,
            [ref(oid, 'watch_ble_connected')]))
    elif ble is None and wifi is None:
        missing.append(_missing('watch_ble_connected/watch_wifi_connected',
                                'read the watch link state'))
    if _num(gap) and _num(batt):
        confidence = 'high'
    elif _num(gap) or _num(batt):
        confidence = 'medium'
    else:
        confidence = 'low'
    candidates = ['rerun_sleep_sample']
    if _num(batt) and batt < 30:
        candidates = ['charge_watch_overnight'] + candidates
    if ble is False:
        candidates = ['keep_phone_nearby'] + candidates
    return oid, findings, missing, confidence, candidates


def _analyze_what_to_install(devices, facts, device):
    targets = [d for d in devices] if device is None else [_target(devices, (), device)]
    findings, missing, candidates = [], [], []
    for d in targets:
        if d['category'] not in ('phone', 'tv', 'tablet', 'watch'):
            continue
        oid, label = d['opaque_id'], _label(d)
        installed = _observed(facts, oid, 'companion_installed')
        blocked = _observed(facts, oid, 'install_blocked_reason')
        sdk = _observed(facts, oid, 'sdk')
        storage = _observed(facts, oid, 'storage_free_gb')
        if installed is True:
            findings.append(_finding(
                'The Companion is already installed on %s; nothing to install there.'
                % label, [ref(oid, 'companion_installed')]))
            continue
        if blocked:
            findings.append(_finding(
                'Install on %s is blocked: %s.' % (label, blocked),
                [ref(oid, 'install_blocked_reason')]))
            candidates.append('check_install_prompt')
            continue
        if installed is False:
            detail = []
            if _num(storage):
                detail.append('%s GB free' % storage)
            if _num(sdk):
                detail.append('SDK %s' % sdk)
            findings.append(_finding(
                '%s has no Companion installed%s.' % (
                    label, ' (%s)' % ', '.join(detail) if detail else ''),
                [ref(oid, 'companion_installed')] +
                ([ref(oid, 'storage_free_gb')] if _num(storage) else []) +
                ([ref(oid, 'sdk')] if _num(sdk) else [])))
            if _num(storage) and storage < 1:
                candidates.append('free_storage')
            else:
                candidates.append('install_companion')
        else:
            missing.append(_missing('companion_installed for %s' % label,
                                    'read the package state on the device'))
        if sdk is None and installed is not True and not blocked:
            missing.append(_missing('sdk for %s' % label, 'read the OS version'))
        if storage is None and installed is not True and not blocked:
            missing.append(_missing('storage_free_gb for %s' % label, 'read free storage'))
    if not findings and not missing:
        return None, [], [_missing('companion_installed',
                                   'the bundle has no phone, TV, tablet or watch to advise on')], \
            'insufficient', []
    # de-duplicate candidates, keep order
    seen, ordered = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    if not findings:
        return None, findings, missing, 'insufficient', ordered or ['check_install_prompt']
    confidence = 'high' if not missing else 'medium'
    target = targets[0]['opaque_id'] if targets else None
    return target, findings, missing, confidence, ordered


ANALYZERS = {'battery_drain': _analyze_battery_drain, 'best_pc_for_dev': _analyze_best_pc_for_dev,
             'strongest_connectivity': _analyze_strongest_connectivity,
             'tv_control_loss': _analyze_tv_control_loss, 'relay_unavailable': _analyze_relay_unavailable,
             'watch_sleep_drops': _analyze_watch_sleep_drops, 'what_to_install': _analyze_what_to_install}
assert set(ANALYZERS) == set(QUESTIONS)


def analyze(question, bundle, device=None):
    """Deterministic analysis: no model involved. Returns findings grounded
    in observed facts, the missing measurements, confidence, and the
    candidate safe recommendations the proposer may pick from."""
    if question not in ANALYZERS:
        raise DiagnosticError('UNKNOWN_QUESTION:%s' % question)
    devices, facts = _index(bundle)
    target, findings, missing, confidence, candidates = ANALYZERS[question](devices, facts, device)
    known_refs = sorted({r for f in findings for r in f['evidence_refs']})
    evidence = {r: {'name': r.split('#', 1)[1], 'value': facts[r]['value'],
                    'unit': facts[r].get('unit'), 'source': facts[r].get('source')}
                for r in known_refs}
    allowed_numbers = set()
    for r in known_refs:
        v = facts[r]['value']
        if _num(v):
            allowed_numbers.add(str(v))
        elif isinstance(v, str):
            # Names may carry digits (e.g. an app version); quoting observed
            # text is grounded, so its numbers are quotable too.
            allowed_numbers.update(_NUMBER_RE.findall(v))
    for d in devices:
        allowed_numbers.update(_NUMBER_RE.findall(_label(d)))
    allowed_numbers |= {str(len(devices)), str(len(bundle.get('links') or []))}
    for c in candidates:
        if c not in RECOMMENDATIONS:
            raise DiagnosticError('ANALYZER_OFFERED_UNKNOWN_RECOMMENDATION:%s' % c)
    return {'question': question, 'target': target, 'findings': findings, 'missing': list(missing),
            'confidence': confidence, 'candidates': list(candidates), 'evidence': evidence,
            'evidence_refs': known_refs,
            'allowed_numbers': sorted(allowed_numbers), 'device_count': len(devices)}


# -- proposer interface -------------------------------------------------------
# A proposer turns deterministic findings into an owner-facing explanation
# and picks safe recommendations. Production uses a Meta model; tests use
# DeterministicStubProposer. Either way the output is validated: the model
# cannot invent facts, numbers, or recommendations.

class DeterministicStubProposer:
    """Test-only Meta proposer: deterministic explanation, no live model.

    Quotes the deterministic findings verbatim and recommends every
    candidate, citing only evidence refs present in the analysis.
    """

    def __init__(self, model='stub-meta-1'):
        self.model = model
        self.calls = []

    def propose(self, request):
        self.calls.append(copy.deepcopy(request))
        findings = request['findings']
        if request['confidence'] == 'insufficient' or not findings:
            explanation = ('I cannot answer from observed facts yet: %s.'
                           % '; '.join(request['missing'][:3]))
        else:
            explanation = ' '.join(f['text'] for f in findings)
            if request['missing']:
                explanation += ' Still missing: %s.' % '; '.join(request['missing'][:3])
            if len(re.findall(r'[A-Za-z]{3,}', explanation)) < 5:
                explanation += ' This rests only on observed facts.'
        refs = sorted({r for f in findings for r in f['evidence_refs']})
        run_id = 'mr-' + hashlib.sha256(
            ('stub|%s|%s|%s' % (request['question'], request.get('target'),
                                '|'.join(refs))).encode()).hexdigest()[:16]
        return {'explanation': explanation, 'recommendations': list(request['candidates']),
                'evidence_refs': refs, 'uncertainty': LIMIT,
                'model': self.model, 'model_run_id': run_id}


class MetaProposer:
    """Meta-backed proposer over an injected chat callable.

    `chat` takes an OpenAI-style payload dict and returns a response dict
    with usage counts and the assistant message content (as produced by
    LocalMetaBroker-compatible transports). No network happens here: the
    caller supplies the transport, and tests supply a fake.
    """

    def __init__(self, chat, model='meta-1'):
        self.chat = chat
        self.model = model

    def propose(self, request):
        schema = {'type': 'object', 'additionalProperties': False,
                  'required': ['explanation', 'recommendations', 'evidence_refs', 'uncertainty'],
                  'properties': {
                      'explanation': {'type': 'string'},
                      'recommendations': {'type': 'array',
                                          'items': {'type': 'string', 'enum': request['candidates'] or ['none']}},
                      'evidence_refs': {'type': 'array', 'items': {'type': 'string'}},
                      'uncertainty': {'type': 'string', 'enum': [LIMIT]}}}
        payload = {'model': self.model, 'stream': False, 'format': schema,
                   'messages': [
                       {'role': 'system', 'content':
                        'You explain device diagnostics to the owner in English as compact JSON matching '
                        'the schema. Explain ONLY the supplied findings, using only the supplied evidence '
                        'and numbers. Never invent measurements, causes, devices, or numbers. Pick '
                        'recommendations ONLY from the supplied candidate ids. The uncertainty field must '
                        'use the exact policy text.'},
                       {'role': 'user', 'content': {
                           'question': request['question'], 'findings': request['findings'],
                           'missing': request['missing'], 'confidence': request['confidence'],
                           'candidates': {c: RECOMMENDATIONS[c] for c in request['candidates']},
                           'evidence': request['evidence']}}]}
        response = self.chat(payload)
        try:
            import json
            content = response['message']['content'] \
                if isinstance(response.get('message'), dict) else response['content']
            body = json.loads(content)
        except (KeyError, TypeError, ValueError):
            raise DiagnosticError('PROPOSAL_UNREADABLE')
        if not isinstance(body, dict):
            raise DiagnosticError('PROPOSAL_UNREADABLE')
        body = dict(body)
        body['model'] = response.get('model', self.model)
        body['usage'] = {k: response.get(k) for k in ('prompt_eval_count', 'eval_count')}
        return body


# Optional sign (RSSI is negative) and no trailing dot/word run (so band names
# like 2.4GHz contribute no number while observed values like 8.0 do).
_NUMBER_RE = re.compile(r'(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])')
_WORD_RE = re.compile(r'[A-Za-z]{3,}')


def _validate_proposal(body, analysis):
    if not isinstance(body, dict) or set(body) - {'explanation', 'recommendations', 'evidence_refs',
                                                  'uncertainty', 'model', 'model_run_id', 'usage'}:
        raise DiagnosticError('PROPOSAL_SCHEMA')
    for key in ('explanation', 'recommendations', 'evidence_refs', 'uncertainty'):
        if key not in body:
            raise DiagnosticError('PROPOSAL_SCHEMA')
    text = body['explanation']
    if not isinstance(text, str) or not 25 <= len(text) <= 1200:
        raise DiagnosticError('PROPOSAL_EXPLANATION_LENGTH')
    if text.startswith(('{', '[')) or len(_WORD_RE.findall(text)) < 5:
        raise DiagnosticError('PROPOSAL_EXPLANATION_NOT_A_SENTENCE')
    if body['uncertainty'] != LIMIT:
        raise DiagnosticError('PROPOSAL_MUST_KEEP_POLICY_LIMITATION')
    recs = body['recommendations']
    if not isinstance(recs, list) or any(r not in analysis['candidates'] for r in recs):
        raise DiagnosticError('PROPOSAL_RECOMMENDATION_NOT_OFFERED')
    if not isinstance(recs, list) or any(r not in RECOMMENDATIONS for r in recs):
        raise DiagnosticError('PROPOSAL_UNKNOWN_RECOMMENDATION')
    refs = body['evidence_refs']
    if not isinstance(refs, list) or any(r not in analysis['evidence_refs'] for r in refs):
        raise DiagnosticError('PROPOSAL_REFERENCES_UNKNOWN_EVIDENCE')
    if analysis['findings'] and not refs:
        raise DiagnosticError('PROPOSAL_MUST_CITE_EVIDENCE')
    allowed = {Decimal(n) for n in analysis['allowed_numbers']}
    for n in _NUMBER_RE.findall(text):
        if Decimal(n) not in allowed:
            raise DiagnosticError('PROPOSAL_INVENTED_NUMBER:%s' % n)
    return body


def diagnose(question, bundle, proposer, device=None):
    """Full pipeline: deterministic analysis -> proposer -> validation.

    Returns the owner-facing report. Raises DiagnosticError on any
    contract violation, including an ungrounded model proposal.
    """
    analysis = analyze(question, bundle, device)
    body = proposer.propose({'question': analysis['question'], 'target': analysis['target'],
                             'findings': analysis['findings'], 'missing': analysis['missing'],
                             'confidence': analysis['confidence'], 'candidates': analysis['candidates'],
                             'evidence': analysis['evidence']})
    _validate_proposal(body, analysis)
    return {'question': question, 'target': analysis['target'], 'confidence': analysis['confidence'],
            'explanation': body['explanation'],
            'recommendations': [{'id': r, **RECOMMENDATIONS[r]} for r in body['recommendations']],
            'evidence_refs': body['evidence_refs'], 'missing': analysis['missing'],
            'candidates': analysis['candidates'], 'model': body.get('model'),
            'model_run_id': body.get('model_run_id'), 'limitation': LIMIT}




