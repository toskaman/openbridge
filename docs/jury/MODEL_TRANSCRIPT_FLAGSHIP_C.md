# Model transcript annex — flagship C (02-Nov-2026)

One complete, unedited Meta inference → gate → compile trace for the
flagship request. No cherry-picking: the sibling failure case and the
hostile case are recorded alongside in the ablation report.

## Request (exact user text)

> I want volume up and down for the television on my wrist

## Inference

- Model: `llama3.2:3b-instruct-q4_K_M` (Meta, local Ollama).
- Endpoint: `http://127.0.0.1:11437`, temperature 0, think off.
- Latency: 19.3 s. Unloaded after the call (`keep_alive 0`).
- Prompt: `composer.build_prompt` (capability-grounded, labels only —
  device keys never shown to the model).

## Raw model reply (verbatim, 187 chars)

```json
{"steps": [{"skill_id": "tv_volume_step", "target": "android tv", "params": {"direction": "up"}}, {"skill_id": "tv_volume_step", "target": "android tv", "params": {"direction": "down"}}]}
```

Frozen as `tests/integration/flagship_paraphrase_reply.json` and replayed
by `tests/integration/test_flagship_chain.py` (labeled REPLAY there).

## Deterministic verdicts (not model claims)

- Parse: schema-ok, 2 steps.
- Target grounding: `android tv` → verified device key (live link).
- Per-step compose: 2 ALLOWED, 0 refused (registered skill, valid params,
  permitted READY route each).
- Install compile: 2 controls, preview shown, NO consent inside the body —
  the owner adds `consent:true` after review.
- Execution (doubles): exactly-one press EXECUTED, re-press deduped,
  revoke → press denied. See the chain test.

## What the model did NOT do

- It did not choose the install surface (the owner picks the watch relay).
- It did not grant consent, waive approval, or touch leases.
- Its sibling phrasing ("Put TV volume controls on my watch") was REFUSED
  openly (install-surface confusion), and the hostile override held —
  see `flagship-breakthrough/MODEL_ABLATION_RESULTS.md` (kept outside git
  with the run ledger; E2E verdicts above are in-tree tests).
