"""G3 integration smoke (owner-supervised): Meta-generated manifest -> trusted kernel -> owner grant ->
physical invoke on the Android TV -> state.audio read-back -> restore -> revoke.

Labeled an INTEGRATION SMOKE (docs/forge/G3_RUN_PLAN.md rev 2): the TV-mute target is public, so this
proves the generation->grant->invoke->read-back machinery, not held-out novelty.

Spend: Muse Spark 1.3 via broker._reserve on the canonical ledger, explicit owner allowance + authz file,
at most 3 calls x $0.10 reservation. No retry after a transport failure. Model output is validated by the
unchanged Forge code (v4_synthesize.synthesize) and then compiled by the kernel; nothing the model says
is executed without the kernel and an owner grant.

Usage: python -m dev.run_g3_smoke --base http://127.0.0.1:18780 --observation-id ID --observed-at ISO
       --free-balance-usd N --authz-file PATH --out DIR
"""
import argparse
import hashlib
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTENT = 'Mute the TV audio, then confirm by reading the media stream state that it reports muted.'
MAX_CALLS = 3
MAX_COMPLETION_TOKENS = 4000
OFFER = ('input.key', 'state.audio', 'state.screen', 'state.read_setting', 'app.list', 'device.read_descriptor')


class Http:
    def __init__(self, base):
        self.base = base.rstrip('/')
        self.csrf = json.loads(urllib.request.urlopen(self.base + '/api/session').read())['csrf_token']

    def __call__(self, path, body=None):
        h = {'Content-Type': 'application/json'}
        if body is not None:
            h.update({'X-CSRF-Token': self.csrf, 'Origin': self.base})
        r = urllib.request.Request(self.base + path, json.dumps(body).encode() if body is not None else None, h)
        try:
            with urllib.request.urlopen(r, timeout=120) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')


def strip_fences(text):
    m = re.fullmatch(r'\s*```(?:json)?\s*(.*?)\s*```\s*', text or '', re.S)
    return m[1] if m else text


def resolve_scope(links, tv_key):
    """Live grant scope from the SAME discover response (snapshot-level links,
    filtered by child key). (None, reason) when unverifiable: the runner must
    KILL, never invent a default scope (Sol HOLD). Device keys rotate between
    discovers, so links and key must come from one response."""
    grants = sorted({g for l in (links or []) if isinstance(l, dict) and l.get('child') == tv_key
                     for g in (l.get('grants') or [])})
    if not grants or not all(isinstance(g, str) and g for g in grants):
        return None, 'grant scope unverifiable from live links (refusing invented scope)'
    return grants, None


def success_predicate(pre, mid, post, st1, r1, st2, after_revoke_http):
    """SUCCESS requires a muted=false->true TRANSITION plus full restore: an
    already-muted oracle scores no success (Sol HOLD: no-op false-success)."""
    reasons = []
    if not isinstance(pre, dict) or pre.get('muted') is not False:
        reasons.append('pre must show muted=false (already-muted scores no success)')
    if not isinstance(mid, dict) or mid.get('muted') is not True:
        reasons.append('post-act oracle must show muted=true')
    if post != pre:
        reasons.append('post-restore oracle must equal the pre-run oracle')
    if not (st1 == 200 and (r1 or {}).get('status') in ('VERIFIED', 'EXECUTED')):
        reasons.append('act invoke must be VERIFIED/EXECUTED')
    if st2 != 200:
        reasons.append('restore invoke must succeed')
    if after_revoke_http == 200:
        reasons.append('invoke after revoke must be refused')
    return (not reasons), reasons


def effect_binding(steps, catalog):
    """Owner consent covers ONE effect: a single input.key{key: mute}. Every other step must be a
    READ-class primitive. Anything else is KILLed before a grant (generic compiler validity is not
    consent for an arbitrary key chain)."""
    effects = [s for s in steps if (catalog.get(s.get('primitive_id')) or {}).get('side_effect_class') != 'READ']
    if len(effects) != 1:
        return 'plan must contain exactly one effect step (got %d)' % len(effects)
    e = effects[0]
    if e.get('primitive_id') != 'input.key' or e.get('args') != {'key': 'mute'}:
        return 'the only allowed effect is input.key {"key": "mute"}'
    return None


def act_restore_sequence(invoke, oracle, revoke, sleep=time.sleep, observed=None, restore=None):
    """Act -> oracle -> conditional restore -> oracle, revoke always attempted.

    Restore runs ONLY if act executed (no blind restore after an unknown act);
    revoke runs in a finally and its own crash is recorded, never raised
    (Sol HOLD). Returns (st1, r1, mid, st2, r2, post, revoke_record).
    """
    st1 = r1 = mid = st2 = r2 = post = None
    try:
        st1, r1 = invoke('act')
        sleep(1.5)
        mid = oracle()
        # Restore only after an OBSERVED transition: an executed act whose effect was not seen
        # is reconciled by the owner, never by a second blind toggle.
        seen = observed(mid) if observed else (mid or {}).get('muted') is True
        if st1 == 200 and (r1 or {}).get('status') in ('VERIFIED', 'EXECUTED') and seen:
            st2, r2 = restore() if restore else invoke('restore')
            sleep(1.5)
            post = oracle()
    finally:
        try:
            st, rv = revoke()
        except Exception as e:
            st, rv = -1, {'error': '%s: %s' % (type(e).__name__, str(e)[:200])}
        record = {'http': st, **(rv if isinstance(rv, dict) else {})}
    return st1, r1, mid, st2, r2, post, record


def main():
    """The hosted (paid Meta Muse Spark) G3 run was removed: OpenBridge ships no paid model.

    The same live G3 pipeline runs on the pinned local models: python -m dev.run_g3_local
    (see its --help). The helpers above stay shared with that runner."""
    print('run_g3_smoke: the paid hosted run was removed; use: python -m dev.run_g3_local --help')
    return 2


if __name__ == '__main__':
    sys.exit(main())
