# Frozen request budget (routing-v1 explanations) — DRAFT until owner-approved freeze

- Model: `muse-spark-1.3` only, via `https://api.meta.ai/v1/chat/completions`.
  Any other returned model string invalidates that call (counted INVALID, kept).
- Calls: at most 8 (one per sampled case, SAMPLE.json order). No retries: a
  failed call is recorded as FAILED with the error, never silently repeated.
- Cost: at most $0.10 reserved per call through the existing broker guard
  (`broker._reserve`), at most $0.80 total. Spend stops at the first guard refusal.
- Credits: a FRESH eligible promotional-credit observation is required; the old
  balance must not be reused and no paid provider may be substituted.
- Abort: stop all calls if any reply contains device identifiers beyond the
  synthetic fixture labels, or if spend would exceed the reservation.
- Receipts: per-call request id, token usage, estimated cost and failures are
  published alongside the replies. No explanation score or model-benefit claim.
