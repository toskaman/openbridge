"""Run the 8 frozen explanation calls (routing-v1 explanations).

Frozen inputs: docs/evaluation/routing-v1/explain/{PROMPT.md,SAMPLE.json,RUBRIC.md,BUDGET.md,SHA256SUMS}
plus docs/evaluation/routing-v1/results/run-f8873d9.json (bound by SAMPLE.run_sha256).

Budget: at most 8 calls x $0.10 through broker._reserve. The broker caps one
supervised session at $0.20, so the run mints 4 permits ($0.20 each) from the
single owner-supplied balance observation; each permit is minted lazily just
before its 2 calls so every reserve lands inside the 300 s freshness window.

Usage:
  python -m dev.run_explain_eval --observation-id <id> --free-balance-usd <n> --out <dir>
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
          re.compile(r'\b[A-Z0-9]{6,}\b'))


def frozen_template():
    text = (EXPLAIN / 'PROMPT.md').read_text(encoding='utf-8')
    start = text.index('```\n') + 4
    end = text.index('\n```', start)
    return text[start:end]


def identifiers(s):
    out = set()
    for rx in ID_RES:
        out.update(rx.findall(s))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--observation-id', required=True)
    ap.add_argument('--free-balance-usd', required=True, type=float)
    ap.add_argument('--out', required=True)
    ap.add_argument('--eval-dir', default='docs/evaluation/routing-v1/explain')
    ap.add_argument('--max-completion-tokens', type=int, default=800)
    args = ap.parse_args()
    global EXPLAIN, MAX_COMPLETION_TOKENS
    EXPLAIN = ROOT / args.eval_dir
    MAX_COMPLETION_TOKENS = args.max_completion_tokens

    sys.path.insert(0, str(ROOT))
    from src.ai.broker import CreditPermit, MetaTransport, RuntimeModelBroker, ModelBlocked, MODEL_ID, ENDPOINT
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
    budget_path = out / 'budget.sqlite3'
    permits = {}
    records = []

    def permit_for(i):
        slot = i // 2
        if slot not in permits:
            permits[slot] = CreditPermit(
                observation_id='%s#%d' % (args.observation_id, slot + 1),
                verified_at=datetime.now(timezone.utc),
                free_balance_usd=args.free_balance_usd, session_budget_usd=0.20)
        return permits[slot]

    for i, case_id in enumerate(sample['sampled_case_ids'][:sample['budget_calls_max']]):
        row = {k: rows[case_id][k] for k in ROW_KEYS}
        case_json = json.dumps(row, indent=2, ensure_ascii=False)
        prompt = template.replace('{CASE_JSON}', case_json)
        rec = {'case_id': case_id, 'slot': i // 2 + 1,
               'input_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
               'status': None}
        broker = RuntimeModelBroker(budget_path, permit_for(i), transport)
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
