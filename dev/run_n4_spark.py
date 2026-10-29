"""N4 morning runner: 4-case Spark-vs-local comparison, ledger-bound.

Frozen pack dev/n4_pack.json (P7/P4/P1/P2 with local llama outcomes recorded).
Spends at most 4 x $0.10 under a NEW owner-minted observation; stops at the
ledger cap ($1.00 global, ~$0.40 headroom left). Never retries a call.

The owner mints the observation (balance + time + authz ref); the runner never
invents them. No --ledger override (Sol audit: canonical shared ledger only).

Usage:
  python -m dev.run_n4_spark --observation-id <id> --free-balance-usd <n> \\
      --observed-at <ISO-tz> --authz <ref> --out <dir>
  python -m dev.run_n4_spark --dry-run   # no reserve, no network
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / 'dev' / 'n4_pack.json'


def parse_observed_at(value):
    text = str(value).strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError('observed-at must carry a timezone')
    return dt.astimezone(timezone.utc)


def read_authz_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        ref = f.read().strip()
    if not ref:
        raise ValueError('authz file is empty')
    return ref


def load_pack(path=PACK):
    pack = json.loads(Path(path).read_text(encoding='utf-8'))
    cases = pack.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('pack has no cases')
    for c in cases:
        if not isinstance(c.get('text'), str) or not c['text'].strip():
            raise ValueError('pack case missing text')
        if c.get('lang') not in ('en', 'fr'):
            raise ValueError('pack case lang must be en|fr')
    budget = pack.get('budget_calls_max', len(cases))
    if not isinstance(budget, int) or not 1 <= budget <= len(cases):
        raise ValueError('pack budget_calls_max invalid')
    return pack


def ledger_totals(budget_path):
    import sqlite3
    from contextlib import closing
    from pathlib import Path as _P
    if not _P(budget_path).exists():
        return 0, 0
    with closing(sqlite3.connect(budget_path, timeout=5)) as db:
        try:
            row = db.execute('SELECT COUNT(*), COALESCE(SUM(reserved),0) FROM reservations').fetchone()
        except Exception:
            return 0, 0
    return int(row[0]), int(row[1])


def run_pack(broker_factory, cases, out_dir):
    """Run cases through the PRODUCTION high path. broker_factory() -> broker.

    One broker._reserve per case happens inside the production gate; a
    ModelBlocked (cap/authz/expiry) stops the run honestly with no retry.
    Returns (records, stopped_reason_or_None).
    """
    sys.path.insert(0, str(ROOT))
    from src.ai.broker import ModelBlocked
    from src.runtime import command as cmd

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = []
    stopped = None
    for c in cases:
        started = time.monotonic()
        srv = type('Srv', (), {})()
        srv.model_broker = broker_factory()
        try:
            res = cmd.parse_request(srv, {'text': c['text'], 'lang': c['lang'],
                                          'quality': 'high', 'cloud_consent': True})
        except ModelBlocked as e:
            stopped = 'CAP_OR_AUTHZ: %s' % e
            break
        except cmd.CommandError as e:
            stopped = 'COMMAND: %s' % e
            break
        intent = res['intent']
        cloud = getattr(getattr(srv, 'command_cloud', None), 'last_usage', None)
        records.append({'prompt_id': c.get('prompt_id'), 'text': c['text'], 'lang': c['lang'],
                        'status': intent.get('status'), 'skill_id': intent.get('skill_id'),
                        'clarifying_question': intent.get('clarifying_question'),
                        'ambiguities': intent.get('ambiguities'),
                        'usage': cloud, 'reserved_usd': 0.10,
                        'elapsed_ms': round((time.monotonic() - started) * 1000)})
        (out / 'replies.json').write_text(json.dumps(records, indent=1), encoding='utf-8')
        # The production gate turns a blocked reserve into an escalation doc (no
        # raise, no spend). A blocked gate stops the run: later cases would fail
        # the same way, and the rule is never-retry.
        if intent.get('status') == 'escalation_required' and _gate_blocked(intent):
            stopped = 'GATE: %s' % (intent.get('ambiguities') or ['blocked'])
            break
    return records, stopped


_GATE_WORDS = ('exhaust', 'expired', 'allowance', 'observation', 'authz',
               'verification', 'credit', 'configured', 'consent')


def _gate_blocked(intent):
    hay = ' '.join(intent.get('ambiguities') or []).lower()
    return any(w in hay for w in _GATE_WORDS)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--observation-id', default=None)
    ap.add_argument('--free-balance-usd', default=None, type=float)
    ap.add_argument('--observed-at', default=None)
    ap.add_argument('--out', default=None)
    ap.add_argument('--pack', default=str(PACK))
    ap.add_argument('--allowance-usd', type=float, default=0.40,
                    help='owner-authorized allowance for this observation (<= broker max)')
    ap.add_argument('--authz', default=None)
    ap.add_argument('--authz-file', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)
    try:
        pack = load_pack(args.pack)
    except (OSError, ValueError) as e:
        print('PACK: %s' % e)
        return 2
    cases = pack['cases'][:pack.get('budget_calls_max', len(pack['cases']))]
    sys.path.insert(0, str(ROOT))
    from src.ai.broker import resolve_ledger
    n, used = ledger_totals(resolve_ledger(None))
    headroom = (1_000_000 - used) / 1_000_000
    print('pack=%s cases=%d ledger_rows=%d ledger_used_usd=%.2f headroom_usd=%.2f'
          % (pack.get('pack'), len(cases), n, used / 1_000_000, headroom))
    if args.dry_run:
        print('DRY_OK no-reserve no-network')
        return 0
    if not args.observation_id or args.free_balance_usd is None or not args.observed_at or not args.out:
        print('MISSING_INPUTS need --observation-id --free-balance-usd --observed-at --out')
        return 2
    if args.authz_file:
        if args.authz:
            print('AUTHZ_EXCLUSIVE')
            return 2
        try:
            authz = read_authz_file(args.authz_file)
        except (OSError, ValueError) as e:
            print('AUTHZ_FILE: %s' % e)
            return 2
    else:
        authz = args.authz
    if not authz:
        print('MISSING_AUTHZ')
        return 2
    try:
        observed_at = parse_observed_at(args.observed_at)
    except ValueError as e:
        print('OBSERVED_AT: %s' % e)
        return 2
    from src.ai.broker import (CreditPermit, MetaTransport, RuntimeModelBroker, ModelBlocked,
                               MODEL_ID, ENDPOINT)
    from src.fabric.credential_vault import Vault
    assert ENDPOINT == 'https://api.meta.ai/v1/chat/completions' and MODEL_ID == 'muse-spark-1.3'
    key = Vault().get('meta-api-key')
    if not key:
        print('NO_KEY')
        return 2
    permit = CreditPermit(observation_id=args.observation_id, verified_at=observed_at,
                          free_balance_usd=args.free_balance_usd, session_budget_usd=0.20)

    def factory():
        return RuntimeModelBroker(resolve_ledger(None), permit, MetaTransport(key),
                                  evaluation_allowance_usd=args.allowance_usd,
                                  evaluation_authz=authz)
    try:
        records, stopped = run_pack(factory, cases, args.out)
    except ModelBlocked as e:
        print('BLOCKED_FIRST_RESERVE: %s' % e)
        return 3
    print('spark_calls=%d stopped=%s' % (len(records), stopped or 'no'))
    (Path(args.out) / 'summary.json').write_text(json.dumps(
        {'pack': pack.get('pack'), 'calls': len(records), 'stopped': stopped,
         'observation': args.observation_id}, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
