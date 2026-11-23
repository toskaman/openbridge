"""Quality reports: how well each device model and firmware version answers, with the owner's consent.

Off by default. When the owner turns it on, OpenBridge counts, per month and per (manufacturer, model, firmware,
category, action): runs, verified, unverified, failed, blocked, and a latency histogram. Nothing else is kept: no
device names, no rooms, no entity ids, no times finer than the month, no values. Nothing is ever sent: the owner can
export a month to a file and choose to share it (for example with the device maker). A maker merges the files it
receives into a monthly report that flags firmware regressions.

Regression rule (per manufacturer, model, category and action, comparing each firmware with the previous one):
  - success rate down by at least REGRESSION_POINTS points, both versions with at least MIN_RUNS runs, or
  - p95 latency at least LATENCY_RATIO times higher and at least LATENCY_MIN_S seconds slower.
In a merged report, a row seen in fewer than MIN_HOMES homes is marked `few_homes` so it is not over-read.
"""
import json
import os
import re
import threading
import time
from pathlib import Path

FORMAT = 'openbridge-quality/1'
BUCKETS = (0.25, 0.5, 1, 2, 4, 8, 16, 32)          # seconds; one more bucket for anything slower
MIN_RUNS = 20
REGRESSION_POINTS = 10.0
LATENCY_RATIO = 1.5
LATENCY_MIN_S = 0.5
MIN_HOMES = 5
FIELDS = ('manufacturer', 'model', 'firmware', 'category', 'action')
MONTH = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


class QualityError(ValueError):
    pass


def default_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge' / 'quality.json'


def _clean(v, n=40):
    v = str(v or '').strip()
    return re.sub(r'[\x00-\x1f]', '', v)[:n] or 'unknown'


def _bucket(seconds):
    for i, b in enumerate(BUCKETS):
        if seconds <= b:
            return i
    return len(BUCKETS)


def p95(hist):
    total = sum(hist)
    if not total:
        return None
    need, acc = 0.95 * total, 0
    for i, n in enumerate(hist):
        acc += n
        if acc >= need:
            return BUCKETS[i] if i < len(BUCKETS) else BUCKETS[-1] * 2
    return None


def _seconds(a, b):
    from datetime import datetime
    try:
        return (datetime.fromisoformat(str(b).replace('Z', '+00:00')) -
                datetime.fromisoformat(str(a).replace('Z', '+00:00'))).total_seconds()
    except (TypeError, ValueError):
        return None


def _new_row(key):
    return dict(zip(FIELDS, key), runs=0, verified=0, unverified=0, failed=0, blocked=0, latency=[0] * (len(BUCKETS) + 1))


class Quality:
    def __init__(self, path=None, persist=True, clock=time.time):
        self.path = Path(path) if path else default_path()
        self.persist, self.clock = persist, clock
        self._lock = threading.Lock()
        self.consent, self.months = None, {}
        if persist:
            try:
                doc = json.loads(self.path.read_text(encoding='utf-8'))
                if doc.get('format') == FORMAT:
                    self.consent, self.months = doc.get('consent'), doc.get('months', {})
            except (OSError, ValueError):
                pass

    def _save(self):
        if self.persist:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'format': FORMAT, 'consent': self.consent, 'months': self.months}, indent=1),
                           encoding='utf-8')
            os.replace(tmp, self.path)

    # ---------- consent ----------
    @property
    def enabled(self):
        return bool(self.consent and self.consent.get('enabled'))

    def enable(self):
        with self._lock:
            self.consent = {'enabled': True, 'at': int(self.clock()), 'scope': 'aggregated counts, kept on this PC'}
            self._save()
        return self.consent

    def disable(self, forget=False):
        with self._lock:
            self.consent = {'enabled': False, 'at': int(self.clock())}
            if forget:
                self.months = {}
            self._save()
        return self.consent

    # ---------- record ----------
    def month(self, t=None):
        return time.strftime('%Y-%m', time.gmtime(self.clock() if t is None else t))

    def observe(self, device_info, category, action, receipt):
        """Count one receipt. Does nothing without consent. device_info: {manufacturer, model, firmware} or None."""
        if not self.enabled:
            return False
        info = device_info if isinstance(device_info, dict) else {}
        key = (_clean(info.get('manufacturer')), _clean(info.get('model')), _clean(info.get('firmware'), 32),
               _clean(category, 20), _clean(action, 40))
        state = receipt.get('state')
        with self._lock:
            rows = self.months.setdefault(self.month(), {})
            row = rows.setdefault('|'.join(key), _new_row(key))
            row['runs'] += 1
            if receipt.get('verified'):
                row['verified'] += 1
            elif state == 'BLOCKED':
                row['blocked'] += 1
            elif state == 'EXECUTED_UNVERIFIED':
                row['unverified'] += 1
            else:
                row['failed'] += 1
            lat = _seconds(receipt.get('started_at'), receipt.get('finished_at'))
            if lat is not None and lat >= 0 and state != 'BLOCKED':
                row['latency'][_bucket(lat)] += 1
            self._save()
        return True

    # ---------- reports ----------
    def export(self, month=None):
        """The file an owner may choose to share: the month's counts, nothing that identifies the home."""
        month = month or self.month()
        if not MONTH.match(month):
            raise QualityError('month is YYYY-MM')
        rows = sorted(self.months.get(month, {}).values(), key=lambda r: tuple(r[f] for f in FIELDS))
        return {'format': FORMAT, 'kind': 'export', 'month': month, 'rows': json.loads(json.dumps(rows)),
                'contains': 'counts per manufacturer, model, firmware, category and action; no names, rooms, ids or times'}

    def report(self, month=None):
        return build_report([self.export(month)])


def validate_export(doc):
    if not isinstance(doc, dict) or doc.get('format') != FORMAT or doc.get('kind') != 'export' \
            or not MONTH.match(str(doc.get('month', ''))) or not isinstance(doc.get('rows'), list):
        raise QualityError('not an OpenBridge quality export')
    for r in doc['rows']:
        if not isinstance(r, dict) or not all(isinstance(r.get(f), str) for f in FIELDS) \
                or not all(isinstance(r.get(k), int) and r[k] >= 0 for k in ('runs', 'verified', 'unverified', 'failed', 'blocked')) \
                or not isinstance(r.get('latency'), list) or len(r['latency']) != len(BUCKETS) + 1:
            raise QualityError('malformed row in a quality export')
    return doc


def _version_key(v):
    return [(0, int(t), '') if t.isdigit() else (1, 0, t) for t in re.findall(r'\d+|[a-zA-Z]+', v)] or [(2, 0, v)]


def regressions(rows):
    groups = {}
    for r in rows:
        groups.setdefault((r['manufacturer'], r['model'], r['category'], r['action']), []).append(r)
    out = []
    for (man, model, cat, action), rs in groups.items():
        rs = sorted((r for r in rs if r['firmware'] != 'unknown'), key=lambda r: _version_key(r['firmware']))
        for prev, cur in zip(rs, rs[1:]):
            if prev['runs'] < MIN_RUNS or cur['runs'] < MIN_RUNS:
                continue
            base = {'manufacturer': man, 'model': model, 'category': cat, 'action': action,
                    'from_firmware': prev['firmware'], 'to_firmware': cur['firmware']}
            a, b = rate(prev), rate(cur)
            if a - b >= REGRESSION_POINTS:
                out.append(dict(base, kind='success_rate', before=a, after=b))
            pa, pb = p95(prev['latency']), p95(cur['latency'])
            if pa and pb and pb >= pa * LATENCY_RATIO and pb - pa >= LATENCY_MIN_S:
                out.append(dict(base, kind='latency_p95', before=pa, after=pb))
    return sorted(out, key=lambda x: (x['manufacturer'], x['model'], x['action'], x['to_firmware']))


def rate(r):
    attempted = r['runs'] - r['blocked']
    return round(100.0 * r['verified'] / attempted, 1) if attempted else 0.0


def build_report(exports):
    """Merge exports (one or many homes, one month or several) into a report with firmware regressions."""
    months, merged = set(), {}
    for doc in exports:
        validate_export(doc)
        months.add(doc['month'])
        for r in doc['rows']:
            key = tuple(r[f] for f in FIELDS)
            m = merged.setdefault(key, dict(_new_row(key), homes=0))
            for k in ('runs', 'verified', 'unverified', 'failed', 'blocked'):
                m[k] += r[k]
            m['latency'] = [x + y for x, y in zip(m['latency'], r['latency'])]
            m['homes'] += 1
    rows = sorted(merged.values(), key=lambda r: tuple(r[f] for f in FIELDS))
    for r in rows:
        r['success_rate'] = rate(r)
        r['latency_p95_s'] = p95(r['latency'])
        if len(exports) > 1 and r['homes'] < MIN_HOMES:
            r['few_homes'] = True
    return {'format': FORMAT, 'kind': 'report', 'months': sorted(months), 'files': len(exports), 'rows': rows,
            'regressions': regressions(rows)}


def markdown(report, title='OpenBridge quality report'):
    lines = ['# %s: %s' % (title, ', '.join(report['months']) or 'no data'), '',
             '%d file(s), %d row(s). Success rate = verified / (runs - blocked by policy).' % (report['files'], len(report['rows'])), '']
    if report['regressions']:
        lines += ['## Firmware regressions', '', '| Device | Action | Firmware | Change |', '|---|---|---|---|']
        for g in report['regressions']:
            unit = ' %' if g['kind'] == 'success_rate' else ' s (p95)'
            lines.append('| %s %s | %s | %s → %s | %s%s → %s%s |' % (g['manufacturer'], g['model'], g['action'], g['from_firmware'],
                                                                      g['to_firmware'], g['before'], unit, g['after'], unit))
        lines.append('')
    else:
        lines += ['No firmware regression detected.', '']
    lines += ['## All rows', '', '| Manufacturer | Model | Firmware | Action | Runs | Success | p95 latency | Homes |',
              '|---|---|---|---|---|---|---|---|']
    for r in report['rows']:
        lines.append('| %s | %s | %s | %s | %d | %.1f %% | %s | %s%s |' % (
            r['manufacturer'], r['model'], r['firmware'], r['action'], r['runs'], r['success_rate'],
            '%s s' % r['latency_p95_s'] if r['latency_p95_s'] is not None else '-', r['homes'],
            ' (few)' if r.get('few_homes') else ''))
    return '\n'.join(lines) + '\n'
