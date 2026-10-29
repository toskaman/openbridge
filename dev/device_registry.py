"""Machine-readable device evidence registry: validate + render the public matrix.

Adapted from OpenBridge_V7/07_TOOLS prototypes (update_hardware_registry.py,
render_device_matrix.py) to repo conventions. Documented adaptations:

1. No D:/E:-only write enforcement: the registry and matrix are small versioned
   text files that the CI gate reads from the repo. The V7 storage policy
   targets large controlled workloads (VMs, ISOs, models, caches), which stay
   on E: (see docs/evidence/vm-fleet-29oct.md). OS-level C: writes are
   unavoidable and declared, per the policy itself.
2. FULL_GUEST_OS + PROTOCOL_ENDPOINT + VERIFIED is accepted when every
   operation names the agent wire protocol (never the Android Companion).
   The prototype's NATIVE_COMPANION requirement is retained for any record
   claiming Companion behavior on a VM. Our VM proofs test agent_reference.py
   handshakes, honestly labeled as protocol proofs.

Usage:
    python -m dev.device_registry --check     # validate registry + matrix sync
    python -m dev.device_registry --render    # rewrite the matrix from registry
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / 'docs' / 'DEVICE_EVIDENCE.json'
MATRIX = ROOT / 'docs' / 'HARDWARE_TEST_MATRIX.md'

ENV = {'REAL_HARDWARE', 'FULL_GUEST_OS', 'OFFICIAL_PLATFORM_EMULATOR',
       'PROTOCOL_SIMULATOR', 'EMULATOR_HOST_BRIDGE', 'MOCK_ONLY'}
STATUS = {'VERIFIED', 'FAILED', 'UNVERIFIED', 'BLOCKED', 'STALE'}
INTEGRATION = {'NATIVE_COMPANION', 'PROTOCOL_ENDPOINT', 'HOST_APP_ADAPTER', 'MODEL_ONLY', 'NONE'}
PRIVATE = [re.compile(r'\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))(?:\.\d{1,3}){2,3}\b'),
           re.compile(r'\b[\w.+-]+@[\w.-]+\.\w+\b'),
           re.compile(r'\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b')]
REQUIRED = ['public_device_id', 'device_alias', 'environment', 'integration', 'platform',
            'status', 'test_id', 'test_utc', 'commit_sha', 'operations', 'evidence']


def check(rec):
    for key in REQUIRED:
        if key not in rec:
            raise ValueError('Missing %s' % key)
    if rec['environment'] not in ENV or rec['status'] not in STATUS or rec['integration'] not in INTEGRATION:
        raise ValueError('Invalid status/environment/integration')
    if not re.fullmatch('[0-9a-f]{40}', rec['commit_sha']):
        raise ValueError('Commit SHA must be 40 lowercase hexadecimal chars')
    if not isinstance(rec['operations'], list) or not rec['operations'] or not all(isinstance(x, str) and x for x in rec['operations']):
        raise ValueError('operations must be a non-empty string list')
    if not isinstance(rec['evidence'], list) or not all(isinstance(x, str) for x in rec['evidence']):
        raise ValueError('evidence must be list of strings')
    try:
        timestamp = dt.datetime.fromisoformat(rec['test_utc'].replace('Z', '+00:00'))
    except Exception as exc:
        raise ValueError('Invalid RFC3339 timestamp') from exc
    if timestamp.tzinfo is None:
        raise ValueError('UTC or timezone-aware timestamp required')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,48}', str(rec['public_device_id'])):
        raise ValueError('Invalid pseudonymous public_device_id')
    if not all(isinstance(rec[k], str) and len(rec[k].strip()) >= 2 for k in ('device_alias', 'platform', 'test_id')):
        raise ValueError('Invalid identifiers')
    if rec['status'] == 'VERIFIED':
        if not rec['evidence'] or not rec.get('independent_oracle'):
            raise ValueError('VERIFIED requires evidence and independent_oracle')
        if rec['commit_sha'] == '0' * 40:
            raise ValueError('VERIFIED requires actual source commit SHA')
        if rec['integration'] == 'NONE':
            raise ValueError('VERIFIED requires a proven integration')
    if rec['environment'] == 'FULL_GUEST_OS' and rec['status'] == 'VERIFIED':
        if rec['integration'] == 'NATIVE_COMPANION':
            pass  # genuine Companion-on-VM proof (none recorded yet)
        elif rec['integration'] == 'PROTOCOL_ENDPOINT':
            if not all('agent' in op.lower() or 'handshake' in op.lower() or 'provision' in op.lower() for op in rec['operations']):
                raise ValueError('VM PROTOCOL_ENDPOINT VERIFIED is only for agent-protocol operations')
        else:
            raise ValueError('FULL_GUEST_OS VERIFIED needs NATIVE_COMPANION or agent-protocol PROTOCOL_ENDPOINT')
    combined = '\n'.join([str(rec.get(x, '')) for x in ('device_alias', 'platform', 'test_id', 'independent_oracle')] + rec['operations'] + rec['evidence'])
    if any(p.search(combined) for p in PRIVATE):
        raise ValueError('Potential private network/email/MAC data in public record')
    if '<script' in combined.lower() or '<!--' in combined:
        raise ValueError('Markup injection in record')
    return rec


def safe(s):
    return str(s).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ').replace('<', '&lt;').replace('>', '&gt;')[:200]


def render(records):
    most_recent = {}
    for rec in records:
        for op in rec['operations']:
            key = (rec['public_device_id'], rec['environment'], op)
            if key not in most_recent or rec['test_utc'] > most_recent[key]:
                most_recent[key] = rec['test_utc']
    hist = HISTORY.read_text(encoding='utf8') if HISTORY.exists() else ''
    lines = ['# OpenBridge — Hardware Compatibility and Evidence', '',
             '> Generated from `docs/DEVICE_EVIDENCE.json` by `python -m dev.device_registry --render`.',
             '> No entry implies support for all functions. Physical and virtual environments are distinct.', '',
             '| Device | Environment | Integration | Platform | Result | Validity | Tested operations | Date (UTC) | Evidence |',
             '|---|---|---|---|---|---|---|---|---|']
    for r in sorted(records, key=lambda x: (x['device_alias'].lower(), x['test_id'])):
        ops = ', '.join(safe(o) for o in r['operations'])
        def link(x):
            rel = x[5:] if x.startswith('docs/') else x  # matrix lives in docs/
            return '[%s](%s)' % (safe(x.rsplit('/', 1)[-1]), safe(rel)) if '/' in x else safe(x)
        proof = ', '.join(link(x) for x in r.get('evidence', [])[:3]) or 'None published'
        current = all(most_recent[(r['public_device_id'], r['environment'], op)] == r['test_utc'] for op in r['operations'])
        validity = 'CURRENT' if current else 'SUPERSEDED / historical'
        lines.append('| ' + ' | '.join([safe(r['device_alias']), safe(r['environment']), safe(r['integration']), safe(r['platform']), safe(r['status']), validity, ops, safe(r['test_utc']), proof]) + ' |')
    lines += ['', '## Interpretation', '',
              '- **VERIFIED**: a specific operation passed a recorded, independent postcondition check; see the cited evidence.',
              '- **FAILED / BLOCKED / UNVERIFIED / STALE**: not a verified working operation; investigate or retest.',
              '- **FULL_GUEST_OS + PROTOCOL_ENDPOINT**: the agent wire protocol was proven in a VM guest — not the Android Companion, not physical hardware.',
              '- **EMULATOR_HOST_BRIDGE**: host controls an emulator, not an original physical console.', '']
    if hist:
        lines += ['---', '', hist]
    return '\n'.join(lines)


HISTORY = ROOT / 'docs' / 'HARDWARE_TEST_HISTORY.md'


def main(argv):
    if '--render' in argv:
        records = json.loads(REGISTRY.read_text(encoding='utf8'))
        for r in records:
            check(r)
        MATRIX.write_text(render(records), encoding='utf8')
        print('Wrote %s with %d evidence rows' % (MATRIX, len(records)))
        return 0
    if '--check' in argv:
        records = json.loads(REGISTRY.read_text(encoding='utf8'))
        for r in records:
            check(r)
        if MATRIX.read_text(encoding='utf8') != render(records):
            print('MATRIX OUT OF SYNC: run python -m dev.device_registry --render')
            return 1
        print('registry OK (%d rows), matrix in sync' % len(records))
        return 0
    print('usage: python -m dev.device_registry --check|--render')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
