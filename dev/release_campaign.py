"""§16 release test orchestrator: ordered stages, exact denominators, honest skips.

Stages: unit -> integration -> e2e-smoke -> security -> chaos/races ->
model-live (needs Ollama :11437) -> hardware-live (needs adb TV).
A stage with unmet gating is reported SKIPPED (never passed).
Writes TEST_RESULTS/s16_campaign.json (override with OPENBRIDGE_CAMPAIGN_OUT).
Usage: python dev/release_campaign.py [--fast]  (--fast skips live stages)
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

if os.path.isdir('E:/ms-playwright'):
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', 'E:/ms-playwright')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get('OPENBRIDGE_CAMPAIGN_OUT',
                     os.path.join(ROOT, 'TEST_RESULTS', 's16_campaign.json'))
FAST = '--fast' in sys.argv


def run(cmd):
    t0 = time.monotonic()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
    lines = (p.stderr + '\n' + p.stdout).strip().splitlines()
    ok, ran = False, 0
    for line in lines:
        s = line.strip()
        if s.startswith('Ran ') or '\nRan ' in line or 'Ran ' in s:
            for tok_i, tok in enumerate(s.split()):
                if tok == 'Ran' and tok_i + 1 < len(s.split()):
                    try:
                        ran = int(s.split()[tok_i + 1])
                    except ValueError:
                        pass
        if s == 'OK' or s.endswith('\nOK'):
            ok = True
    return {'ok': ok, 'ran': ran, 'seconds': round(time.monotonic() - t0, 1),
            'tail': lines[-2:] if lines else []}


def ollama_up():
    try:
        urllib.request.urlopen('http://127.0.0.1:11437/', timeout=3)
        return True
    except Exception:
        return False


def adb_tv():
    try:
        p = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=15)
        return '192.168.1.15:5555' in p.stdout and 'device' in p.stdout
    except Exception:
        return False


STAGES = [
    ('unit', ['python', '-m', 'unittest', 'discover', '-s', 'tests/unit'], None),
    ('integration', ['python', '-m', 'unittest', 'discover', '-s', 'tests/runtime'], None),
    ('contracts-forge', ['python', '-m', 'unittest', 'discover', '-s', 'tests/contracts'], None),
    ('fabric', ['python', '-m', 'unittest', 'discover', '-s', 'tests/fabric'], None),
    ('forge', ['python', '-m', 'unittest', 'discover', '-s', 'tests/forge'], None),
    ('security', ['python', '-m', 'unittest',
                  'tests.runtime.test_remote_controls', 'tests.runtime.test_remote_grant_ordering',
                  'tests.contracts.test_inflight_ledger', 'tests.fabric.test_f90_adversarial',
                  'tests.fabric.test_aead'], None),
    ('chaos-races', ['python', '-m', 'unittest',
                     'tests.runtime.test_command_concurrency', 'tests.runtime.test_release_faults',
                     'tests.fabric.test_endurance', 'tests.runtime.test_overnight_stress'], None),
]
E2E_SMOKES = ['tests.e2e.forge_workspace_smoke', 'tests.e2e.forge_smoke',
              'tests.e2e.forge_publication_failure_smoke', 'tests.e2e.forge_runtime_smoke',
              'tests.e2e.forge_expiry_smoke']

report = {'stages': [], 'live': {}}
failed = False
for name, cmd, _ in STAGES:
    r = run(cmd)
    r['stage'] = name
    r['verdict'] = 'PASS' if (r['ok'] and r['ran'] > 0) else 'FAIL'
    if r['verdict'] == 'FAIL':
        failed = True
    report['stages'].append(r)
    print(name, r['verdict'], 'n=%d %.1fs' % (r['ran'], r['seconds']), flush=True)
    if failed:
        break

if not failed:
    t0 = time.monotonic()
    smoke_ok, smoke_log = True, []
    for mod in E2E_SMOKES:
        p = subprocess.run(['python', '-m', mod], cwd=ROOT, capture_output=True,
                           text=True, timeout=300)
        smoke_ok = smoke_ok and p.returncode == 0
        smoke_log.append('%s rc=%d' % (mod.split('.')[-1], p.returncode))
    r = {'stage': 'e2e-smoke', 'ok': smoke_ok, 'ran': len(E2E_SMOKES),
         'seconds': round(time.monotonic() - t0, 1), 'tail': smoke_log,
         'verdict': 'PASS' if smoke_ok else 'FAIL'}
    report['stages'].append(r)
    print('e2e-smoke', r['verdict'], 'n=%d %.1fs' % (len(E2E_SMOKES), r['seconds']), flush=True)
    failed = not smoke_ok

if not FAST and not failed:
    report['live']['model_s8'] = 'RUN: python MISSION_CONTROL/tools/s8_eval_p0.py (needs :11437)' \
        if ollama_up() else 'SKIPPED: Ollama :11437 unreachable'
    report['live']['hardware_flagship'] = \
        'RUN: python MISSION_CONTROL/tools/flagship_e2e.py (needs adb TV)' \
        if adb_tv() else 'SKIPPED: TV 192.168.1.15:5555 not on adb'
    print('model-live:', report['live']['model_s8'], flush=True)
    print('hardware-live:', report['live']['hardware_flagship'], flush=True)
else:
    report['live']['note'] = 'fast mode or earlier FAIL: live stages not attempted'

report['verdict'] = 'FAIL' if failed else 'PASS (live stages see above)'
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(report, open(OUT, 'w', encoding='utf-8'), indent=1)
print('verdict:', report['verdict'], flush=True)
sys.exit(1 if failed else 0)
