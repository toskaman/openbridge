"""BLE zone proximity (V4-11): calibrated *zones*, never coordinates.

Two fixed relays (Companion on the phone, Companion on the TV) report RSSI of ONE advertiser the owner opted in.
Calibration records labelled runs per zone; the model is a per-zone, per-relay robust fingerprint (median + MAD).
Estimation smooths a recent window with the median, picks the nearest fingerprint, and answers "unknown" when the
data is stale, a relay is missing, or the best zone does not beat the runner-up by a clear margin. Hysteresis keeps
a zone only after it has held for `hold_s`. Evaluation is leave-one-run-out, reported as precision/recall per zone,
unknown rate and a single-relay vs two-relay comparison. Nothing here is a person locator or a 2D position.
"""
import json
import math
from statistics import median

STALE_S = 20
MIN_MARGIN_DB = 3.0
WINDOW_S = 10
HOLD_S = 15
UNKNOWN = 'unknown'


def _mad(xs):
    m = median(xs)
    return median(abs(x - m) for x in xs) if xs else 0.0


def fit(samples, relays=None):
    """samples: [{'zone', 'run', 'relay_id', 'rssi'}] -> {zone: {relay: {'median', 'mad', 'n'}}}"""
    model = {}
    for s in samples:
        if relays and s['relay_id'] not in relays:
            continue
        model.setdefault(s['zone'], {}).setdefault(s['relay_id'], []).append(s['rssi'])
    return {z: {r: {'median': median(v), 'mad': max(_mad(v), 1.0), 'n': len(v)} for r, v in rs.items()} for z, rs in model.items()}


def _vector(window, relays):
    by = {}
    for s in window:
        if s['relay_id'] in relays:
            by.setdefault(s['relay_id'], []).append(s['rssi'])
    return {r: median(v) for r, v in by.items()}


def classify(model, window, now=None, relays=None, margin_db=MIN_MARGIN_DB):
    """window: recent [{'t', 'relay_id', 'rssi'}]. -> {'zone', 'confidence', 'margin_db', 'reason'}"""
    relays = sorted(relays or {r for z in model.values() for r in z})
    if now is not None:
        window = [s for s in window if now - s['t'] <= WINDOW_S]
        if not window:
            return {'zone': UNKNOWN, 'confidence': 0.0, 'margin_db': None, 'reason': 'stale: no sample in the last window'}
    v = _vector(window, relays)
    missing = [r for r in relays if r not in v]
    if missing:
        return {'zone': UNKNOWN, 'confidence': 0.0, 'margin_db': None, 'reason': f'{len(missing)} relay(s) without a recent sample'}
    dist = {}
    for z, fp in model.items():
        if any(r not in fp for r in relays):
            continue
        # root-mean-square difference to the zone's median fingerprint, in dB
        dist[z] = math.sqrt(sum((v[r] - fp[r]['median']) ** 2 for r in relays) / len(relays))
    if len(dist) < 2:
        return {'zone': UNKNOWN, 'confidence': 0.0, 'margin_db': None, 'reason': 'fewer than two calibrated zones'}
    ranked = sorted(dist.items(), key=lambda kv: kv[1])
    margin = ranked[1][1] - ranked[0][1]
    if margin < margin_db:
        return {'zone': UNKNOWN, 'confidence': round(margin / margin_db / 2, 2), 'margin_db': round(margin, 1),
                'reason': f'{ranked[0][0]} and {ranked[1][0]} are too close to tell apart'}
    return {'zone': ranked[0][0], 'confidence': round(min(1.0, 0.5 + margin / (4 * margin_db)), 2),
            'margin_db': round(margin, 1), 'reason': 'nearest calibrated fingerprint'}


class Hysteresis:
    def __init__(self, hold_s=HOLD_S):
        self.hold_s, self.zone, self._cand, self._since = hold_s, UNKNOWN, None, None

    def update(self, zone, t):
        if zone == self.zone:
            self._cand = None
            return self.zone
        if zone != self._cand:
            self._cand, self._since = zone, t
        elif t - self._since >= self.hold_s:
            self.zone, self._cand = zone, None
        return self.zone


def windows(samples, step_s=5):
    """Cut one labelled run into evaluation windows of WINDOW_S seconds."""
    if not samples:
        return []
    t0, t1 = min(s['t'] for s in samples), max(s['t'] for s in samples)
    out, t = [], t0 + WINDOW_S
    while t <= t1 + 1e-9:
        out.append((t, [s for s in samples if t - WINDOW_S < s['t'] <= t]))
        t += step_s
    return out


def evaluate(samples, relays=None, margin_db=MIN_MARGIN_DB):
    """Leave-one-run-out. -> per-zone precision/recall, unknown rate, confusion; no fabricated score when data lacks."""
    runs = sorted({(s['zone'], s['run']) for s in samples})
    zones = sorted({z for z, _ in runs})
    confusion = {z: {} for z in zones}
    for zone, run in runs:
        train = [s for s in samples if (s['zone'], s['run']) != (zone, run)]
        test = [s for s in samples if (s['zone'], s['run']) == (zone, run)]
        model = fit(train, relays)
        if zone not in model:
            continue                          # the only run of this zone: cannot be evaluated honestly
        for t, w in windows(test):
            p = classify(model, w, relays=relays, margin_db=margin_db)['zone']
            confusion[zone][p] = confusion[zone].get(p, 0) + 1
    per = {}
    for z in zones:
        tp = confusion[z].get(z, 0)
        total = sum(confusion[z].values())
        predicted = sum(confusion[o].get(z, 0) for o in zones)
        per[z] = {'windows': total, 'precision': round(tp / predicted, 3) if predicted else None,
                  'recall': round(tp / total, 3) if total else None,
                  'unknown_rate': round(confusion[z].get(UNKNOWN, 0) / total, 3) if total else None}
    n = sum(sum(c.values()) for c in confusion.values())
    return {'relays': sorted(relays) if relays else 'all', 'zones': per, 'confusion': confusion, 'windows': n,
            'wrong_zone_rate': round(sum(v for z in zones for p, v in confusion[z].items() if p not in (z, UNKNOWN)) / n, 3) if n else None,
            'claim': 'zone-level proximity from RSSI fingerprints; not a position, not a person locator'}


def report(samples):
    all_relays = sorted({s['relay_id'] for s in samples})
    out = {'two_relays': evaluate(samples, all_relays)}
    for r in all_relays:
        out['single_' + r] = evaluate(samples, [r])
    return out


def load(path):
    return json.loads(open(path, encoding='utf-8').read())
