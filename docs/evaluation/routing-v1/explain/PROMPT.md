# Frozen explanation prompt (routing-v1) — DRAFT until owner-approved freeze

The exact bytes below (between the fences, with `{CASE_JSON}` substituted) are
the sole user message for every explanation call. No system/developer preamble
beyond the API default, temperature 0, max_completion_tokens 800.

```
You explain ONE recorded routing decision. Use ONLY the JSON record below.
Every factual sentence must end with a citation [field] naming the record field
it comes from (e.g. [predictions.router], [expected], [family]).
Rules:
- Never state a fact without a citation. Never cite a field that is absent.
- Never claim why the router is better than a baseline; describe only this record.
- If the record is ambiguous or a field is missing, say UNSUPPORTED for that point.
- Reply with exactly three sections: DECISION, EVIDENCE, LIMITS. No other text.

Record:
{CASE_JSON}
```

Substitution: `{CASE_JSON}` = the sampled row object verbatim from
`docs/evaluation/routing-v1/results/run-f8873d9.json`
(sha256 `94aa4e74222c7321960abd55b0c03fad12be2f888dd4e7d2ad535e3bb7c7017d`),
keys `case_id, family, predictions, reasons, expected, document, events`.
No other context, no retrieval, no tools.
