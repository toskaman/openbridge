"""Run the 8 frozen explanation calls (routing-v1 explanations).

Frozen inputs: docs/evaluation/routing-v1/explain/{PROMPT.md,SAMPLE.json,RUBRIC.md,BUDGET.md,SHA256SUMS}
plus docs/evaluation/routing-v1/results/run-f8873d9.json (bound by SAMPLE.run_sha256).

Budget: at most 8 calls x $0.10 through broker._reserve under ONE canonical
observation identity/time and one shared ledger, with an explicit
owner-authorized evaluation allowance (--allowance-usd + --authz).

Usage:
  python -m dev.run_explain_eval --observation-id <id> --free-balance-usd <n> --out <dir> --authz <ref>
"""
import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPLAIN = ROOT / 'docs/evaluation/routing-v1/explain'
MAX_COMPLETION_TOKENS = 800
ROW_KEYS = ('case_id', 'family', 'predictions', 'reasons', 'expected', 'document', 'events')
ID_RES = (re.compile(r'(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}'),
          re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b'),
          re.compile(r'\b[0-9a-f]{16,}\b'))
FROZEN_VOCABULARY = {'DECISION', 'EVIDENCE', 'LIMITS', 'UNSUPPORTED', 'SUPPORTED', 'INVALID'}


def frozen_template():
    text = (EXPLAIN / 'PROMPT.md').read_text(encoding='utf-8')
    start = text.index('```\n') + 4
    end = text.index('\n```', start)
    return text[start:end]


def identifiers(s):
    out = set()
    for rx in ID_RES:
        out.update(x for x in rx.findall(s) if x not in FROZEN_VOCABULARY)
    return out


def parse_observed_at(value):
    from datetime import datetime, timezone
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--observation-id', required=True)
    ap.add_argument('--free-balance-usd', required=True, type=float)
    ap.add_argument('--out', required=True)
    ap.add_argument('--eval-dir', default='docs/evaluation/routing-v1/explain')
    ap.add_argument('--max-completion-tokens', type=int, default=800)
    ap.add_argument('--resume', action='store_true',
                    help='skip case_ids already in <out>/replies.json; never re-runs a call')
    ap.add_argument('--allowance-usd', type=float, default=0.80,
                    help='explicit owner-authorized evaluation allowance (canonical observation, shared ledger)')
    ap.add_argument('--authz', default=None,
                    help='explicit owner authorization reference for the allowance')
    ap.add_argument('--authz-file', default=None,
                    help='owner-written file containing the authorization ref (read-only, never created)')
    ap.add_argument('--observed-at', required=True,
                    help='owner observation time, ISO with timezone (immutable, never minted)')
    ap.add_argument('--ledger', default=None,
                    help='explicit ledger path (tests/one-offs only; default is the canonical shared ledger)')
    args = ap.parse_args()
    authz = args.authz
    if args.authz_file:
        if args.authz:
            print('AUTHZ_EXCLUSIVE')
            return 2
        try:
            authz = read_authz_file(args.authz_file)
        except (OSError, ValueError) as e:
            print('AUTHZ_FILE: %s' % e)
            return 2
    if not authz:
        print('MISSING_AUTHZ')
        return 2
    try:
        observed_at = parse_observed_at(args.observed_at)
    except ValueError as e:
        print('OBSERVED_AT: %s' % e)
        return 2
    global EXPLAIN, MAX_COMPLETION_TOKENS
    EXPLAIN = ROOT / args.eval_dir
    MAX_COMPLETION_TOKENS = args.max_completion_tokens

    sys.path.insert(0, str(ROOT))
    from src.ai.broker import CreditPermit, MetaTransport, RuntimeModelBroker, ModelBlocked, MODEL_ID, ENDPOINT, resolve_ledger
    from src.fabric.credential_vault import Vault

    assert ENDPOINT == 'https://api.meta.ai/v1/chat/completions' and MODEL_ID == 'muse-spark-1.3'
    sample = json.loads((EXPLAIN / 'SAMPLE.json').read_text(encoding='utf-8'))
    run_path = ROOT / 'docs/evaluation/routing-v1/results/run-f8873d9.json'
    digest = hashlib.sha256(run_path.read_bytes()).hexdigest()
    if digest != sample['run_sha256']:
        print('RUN_SHA_MISMATCH exp=%s got=%s' % (sample['run_sha256'], digest))
        return 2
    rows = {r['case_id']: r for r in json.loads(run_path.read_text(encoding='utf-8'))['rows']}
    template = frozen_template()
    assert template.count('{CASE_JSON}') == 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    key = Vault().get('meta-api-key')
    if not key:
        print('NO_KEY')
        return 2
    transport = MetaTransport(key)
    budget_path = resolve_ledger(args.ledger)
    print('ledger: %s' % budget_path)
    records = []
    done = set()
    if args.resume:
        prev = out / 'replies.json'
        if prev.exists():
            records = json.loads(prev.read_text(encoding='utf-8'))
            done = {r['case_id'] for r in records}
            print('resume: keeping %d recorded calls' % len(records))
    permit = CreditPermit(observation_id=args.observation_id, verified_at=observed_at,
                          free_balance_usd=args.free_balance_usd, session_budget_usd=0.20)
    broker = RuntimeModelBroker(budget_path, permit, transport,
                                evaluation_allowance_usd=args.allowance_usd,
                                evaluation_authz=authz)

    pending = [c for c in sample['sampled_case_ids'][:sample['budget_calls_max']] if c not in done]
    for i, case_id in enumerate(pending):
        row = {k: rows[case_id][k] for k in ROW_KEYS}
        case_json = json.dumps(row, indent=2, ensure_ascii=False)
        prompt = template.replace('{CASE_JSON}', case_json)
        rec = {'case_id': case_id,
               'input_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
               'status': None}
        try:
            broker._reserve()
        except ModelBlocked as e:
            rec['status'] = 'BLOCKED'
            rec['error'] = str(e)
            records.append(rec)
            break  # spend stops at the first guard refusal
        started = time.monotonic()
        try:
            response = transport({'model': MODEL_ID, 'temperature': 0,
                                  'max_completion_tokens': MAX_COMPLETION_TOKENS,
                                  'messages': [{'role': 'user', 'content': prompt}]})
        except Exception as e:  # noqa: BLE001 - failed call recorded, never retried
            rec['status'] = 'FAILED'
            rec['error'] = '%s: %s' % (type(e).__name__, str(e)[:200])
            records.append(rec)
            continue
        rec['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        rec['request_id'] = response.get('id')
        rec['model'] = response.get('model')
        rec['finish_reason'] = ((response.get('choices') or [{}])[0].get('finish_reason'))
        rec['max_completion_tokens'] = MAX_COMPLETION_TOKENS
        usage = (response.get('usage') or {})
        rec['usage'] = {k: usage.get(k) for k in ('prompt_tokens', 'completion_tokens')}
        if (rec['model'] != MODEL_ID or any(type(usage.get(k)) is not int or not 0 <= usage.get(k) <= 100_000
                                            for k in ('prompt_tokens', 'completion_tokens'))):
            rec['status'] = 'INVALID'
            rec['reply'] = str(response)[:2000]
            records.append(rec)
            continue
        content = (((response.get('choices') or [{}])[0].get('message') or {}).get('content')) or ''
        rec['reply'] = content
        rec['estimated_cost_usd'] = (usage['prompt_tokens'] * 1.25 + usage['completion_tokens'] * 4.25) / 1_000_000
        rec['reserved_usd'] = 0.10
        leaked = identifiers(content) - identifiers(case_json)
        if leaked:
            rec['status'] = 'LEAK_ABORT'
            rec['leaked'] = sorted(leaked)[:10]
            records.append(rec)
            break
        rec['status'] = 'RECORDED'
        records.append(rec)

    (out / 'replies.json').write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding='utf-8')
    print('calls=%d status=%s' % (len(records), [r['status'] for r in records]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
