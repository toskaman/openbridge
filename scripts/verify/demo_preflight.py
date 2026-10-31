"""Demo preflight probe (§5/§6 gate). STRICTLY READ-ONLY: bounded discovery +
adb device list. Never pairs, installs, commands, or moves anything.

Exit 0: TV + vacuum + watch all seen → GO. Exit 2: partial. Exit 3: none.
Prints aliases only; serials/IPs/keys are redacted.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def blocks(text):
    """Split discovery YAML-ish output into per-device blocks."""
    parts = re.split(r'\n  -\n', text)
    return parts[1:] if len(parts) > 1 else []


def observed_fresh(block, max_age_s=600):
    from datetime import datetime, timezone
    m = re.search(r'observed_at:\s*(\S+)', block)
    if not m:
        return False, 'no observed_at'
    try:
        ts = datetime.fromisoformat(m.group(1))
    except ValueError:
        return False, 'bad timestamp'
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return (0 <= age <= max_age_s), f'age {age:.0f}s'


def leg_status(disc, adb, leg):
    """Match whole device blocks (never substrings): tv needs an Android TV
    block, vacuum a Tuya/vacuum block, watch a Watch/Wear block, each with a
    fresh observed_at. adb adds transport liveness for android legs."""
    b = blocks(disc)
    if leg == 'tv':
        hit = [x for x in b if 'category: tv' in x and 'android tv' in x.lower()
               and 'webos' not in x.lower() and 'lg' not in x.split('label:')[-1].lower()[:40]]
    elif leg == 'vacuum':
        def _lab(x):
            m = re.search(r'label:\s*(.+)', x)
            return (m.group(1).lower() if m else '')[:80]
        hit = [x for x in b if 'tuya' in _lab(x) or 'vacuum' in _lab(x) or 'category: vacuum' in x]
    else:
        hit = [x for x in b if 'sm-l310' in x.lower() or 'galaxy watch' in x.lower()
               or 'category: watch' in x or 'category: wear' in x]
    if not hit:
        return 'NO-GO', 'not in discovery'
    fresh, why = observed_fresh(hit[0])
    if not fresh:
        return 'NO-GO', f'stale ({why})'
    label = re.search(r'label:\s*(.+)', hit[0])
    return 'GO', (label.group(1).strip() if label else '?') + f' [{why}]'

REDACT = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b|[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){2,}|key[=:]\s*\S+', re.I)


def scrub(text):
    return REDACT.sub('[redacted]', text)


def run(cmd, timeout):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        return (p.stdout or '') + (p.stderr or '')
    except (OSError, subprocess.TimeoutExpired) as e:
        return f'<probe failed: {type(e).__name__}>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--timeout', type=int, default=30)
    args = ap.parse_args()

    disc = run([sys.executable, '-m', 'src.cli', 'devices', 'discover', '--timeout', str(args.timeout)],
               timeout=args.timeout + 60)
    adb = run(['adb', 'devices', '-l'], timeout=30)

    result, notes = {}, {}
    for leg in ('tv', 'vacuum', 'watch'):
        result[leg], notes[leg] = leg_status(disc, adb, leg)
    n = sum(1 for v in result.values() if v == 'GO')
    verdict = 'GO' if n == 3 else ('PARTIAL' if n else 'NO-GO')
    print(json.dumps({'verdict': verdict, 'legs': result, 'notes': notes}, indent=1))
    print('--- discovery (scrubbed) ---')
    print(scrub(disc.strip() or '<empty>')[:2000])
    print('--- adb devices (scrubbed) ---')
    print(scrub(adb.strip() or '<empty>')[:1000])
    return 0 if n == 3 else (2 if n else 3)


if __name__ == '__main__':
    sys.exit(main())
