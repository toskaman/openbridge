"""Verified by OpenBridge: decide, from the public evidence registry only, whether a device earns the label.

    python scripts/verify/verified_label.py                      # every device: earned or not, and why
    python scripts/verify/verified_label.py --device tv-companion-01 --badge badge.svg

The label is never sold and never granted by hand. A device earns it when docs/DEVICE_EVIDENCE.json shows:
  1. at least MIN_RUNS runs with status VERIFIED on REAL_HARDWARE,
  2. on at least MIN_DAYS different days,
  3. covering at least MIN_OPERATIONS distinct operations,
  4. each naming an independent oracle (how the result was checked without trusting OpenBridge) and evidence,
  5. the latest one less than VALID_DAYS days old (the label lapses; a new run renews it).
Evidence paths in the repository must exist. The criteria a reviewer checks by hand (refusals, exact Undo, recovery)
are in docs/partners/VERIFIED.md. Standard library only.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
MIN_RUNS = 3
MIN_DAYS = 2
MIN_OPERATIONS = 5
VALID_DAYS = 180


def _when(r):
    try:
        return datetime.fromisoformat(r['test_utc'].replace('Z', '+00:00'))
    except (KeyError, ValueError, AttributeError):
        return None


def _evidence_ok(ref, root):
    ref = str(ref).strip()
    if ref.startswith(('http://', 'https://')):
        return True
    if ' ' in ref:          # a description (e.g. held on the author's PC) is not public evidence
        return False
    return (root / ref.rstrip('/')).exists()


def assess(records, device, now=None, root=ROOT):
    now = now or datetime.now(timezone.utc)
    runs = [r for r in records if r.get('public_device_id') == device]
    real = [r for r in runs if r.get('status') == 'VERIFIED' and r.get('environment') == 'REAL_HARDWARE']
    good = [r for r in real if str(r.get('independent_oracle', '')).strip() and r.get('evidence')
            and all(_evidence_ok(e, root) for e in r['evidence']) and _when(r)]
    days = sorted({_when(r).date().isoformat() for r in good})
    ops = sorted({str(o) for r in good for o in r.get('operations', [])})
    latest = max((_when(r) for r in good), default=None)
    reasons = []
    if len(good) < MIN_RUNS:
        reasons.append('%d qualifying real-hardware runs, %d needed' % (len(good), MIN_RUNS))
    if len(days) < MIN_DAYS:
        reasons.append('runs on %d day(s), %d needed' % (len(days), MIN_DAYS))
    if len(ops) < MIN_OPERATIONS:
        reasons.append('%d distinct operations, %d needed' % (len(ops), MIN_OPERATIONS))
    if latest and now - latest > timedelta(days=VALID_DAYS):
        reasons.append('latest run older than %d days' % VALID_DAYS)
    if len(real) > len(good):
        reasons.append('%d real-hardware run(s) without an oracle or with missing evidence were not counted' % (len(real) - len(good)))
    earned = len(good) >= MIN_RUNS and len(days) >= MIN_DAYS and len(ops) >= MIN_OPERATIONS and latest is not None \
        and now - latest <= timedelta(days=VALID_DAYS)
    return {'device': device, 'earned': earned, 'runs': len(good), 'days': len(days), 'operations': len(ops),
            'latest': latest.date().isoformat() if latest else None,
            'valid_until': (latest + timedelta(days=VALID_DAYS)).date().isoformat() if earned else None,
            'reasons': [] if earned else reasons, 'evidence': [e for r in good for e in r['evidence']]}


def assess_all(records, now=None, root=ROOT):
    return [assess(records, d, now, root) for d in sorted({r.get('public_device_id') for r in records if r.get('public_device_id')})]


def badge(result):
    """A small SVG badge: green and dated when earned, grey ("evidence pending") otherwise."""
    left = 'Verified by OpenBridge'
    right = ('until %s' % result['valid_until']) if result['earned'] else 'evidence pending'
    color = '#0f9f8a' if result['earned'] else '#6f80aa'
    lw, rw = 8 + 7 * len(left), 8 + 7 * len(right)
    w = lw + rw
    title = '%s: %s (%d real-hardware runs, %d operations)' % (result['device'], right, result['runs'], result['operations'])
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" aria-label="{t}">'
            '<title>{t}</title><rect width="{lw}" height="20" rx="3" fill="#111a3d"/>'
            '<rect x="{lw}" width="{rw}" height="20" rx="3" fill="{c}"/><rect x="{lw}" width="4" height="20" fill="{c}"/>'
            '<g fill="#fff" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">'
            '<text x="6" y="14">{l}</text><text x="{rx}" y="14">{r}</text></g></svg>\n').format(
        w=w, lw=lw, rw=rw, c=color, rx=lw + 5, l=escape(left), r=escape(right), t=escape(title, {'"': '&quot;'}))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--registry', default=str(ROOT / 'docs' / 'DEVICE_EVIDENCE.json'))
    ap.add_argument('--device', default=None)
    ap.add_argument('--badge', default=None, help='write the SVG badge for --device here')
    a = ap.parse_args(argv)
    records = json.loads(Path(a.registry).read_text(encoding='utf-8'))
    if a.device:
        result = assess(records, a.device)
        if a.badge:
            Path(a.badge).write_text(badge(result), encoding='utf-8')
        print(json.dumps(result, indent=1))
    else:
        for r in assess_all(records):
            print('%-32s %s' % (r['device'], 'EARNED until %s' % r['valid_until'] if r['earned'] else 'not yet: ' + '; '.join(r['reasons'])))


if __name__ == '__main__':
    main()
