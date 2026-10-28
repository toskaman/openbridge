# Explanation v2 run record (routing-v1, 28 Oct 2026)

## Run
- Freeze: attestation PR #75 (bytes PR #73); cap 4000, unseen -02 cases, same run bytes.
- Commands:
  - `python -m dev.run_explain_eval --observation-id owner-20261028-135usd-v2 --free-balance-usd 135 --out docs/evaluation/routing-v1/explain-v2-results --eval-dir docs/evaluation/routing-v1/explain-v2 --max-completion-tokens 4000`
  - resume: same with `--observation-id owner-20261028-135usd-v2b --resume`
- Key: vault `meta-api-key`. Observation: owner-supplied free balance $135, 28 Oct 2026.
- Permits: 4 x $0.20 per observation id (broker per-session cap); calls 1-3 on `-v2`, 4-8 on `-v2b` (fresh 300 s window). No call was ever re-run: `--resume` skips recorded case_ids.

## Mid-run incident (tooling, disclosed)
- Call 3 aborted the run via the leak guard: the v1 detector regex `[A-Z0-9]{6,}` matched the FROZEN OUTPUT VOCABULARY (DECISION/EVIDENCE/LIMITS/UNSUPPORTED) — a false positive, not a device-identifier leak.
- Fix (tooling only, frozen bytes untouched): detector reduced to MAC / IPv4 / long-hex, frozen vocabulary allowlisted. Re-check of call 3's reply: zero identifiers.
- Call 3 keeps status LEAK_ABORT with a `review_note`; its 503-char reply is retained verbatim and scored. Calls 4-8 ran after the fix; calls 1-3 were never repeated.

## Outcome
- 8 records: 7 RECORDED + 1 LEAK_ABORT(false positive). Model `muse-spark-1.3` on all. Spend $0.1477 / $0.80 reserved.
- 3 replies with real cited content (finish=stop): grant_insufficient-02 (503 chars), lease_stale-02 (716), link_down-02 (475).
- 5 replies EMPTY (finish=length, 4000/4000): reasoning still exhausts the budget on most cases even at 4000.
- Finding: raising the cap 800 -> 4000 moved 0/8 to 3/8 content-bearing, but exhaustion remains the dominant mode. Further cap raises have diminishing expected value; a non-reasoning model or shorter evidence context would be the next experiment (new freeze if pursued).

## Scoring (frozen RUBRIC.md)
- Non-empty x3: 26 sentences SUPPORTED, 0 UNSUPPORTED, structure valid (human pass: every cited claim entailed by its row; checked events candidates, rules, documentrule/route presence and alias-map absence).
- Empty x5: INVALID (no sections), 0 sentences.
- No DISPUTED items. No quality score for the router, per the rubric.
