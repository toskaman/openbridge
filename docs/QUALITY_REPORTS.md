# Quality reports (opt-in)

A device maker wants to know, before customers complain, that firmware 1.5.0 made the lamp miss one command in four.
OpenBridge already checks every action by reading the device back, so it knows. With the owner's consent, it can
count this, and the owner can choose to share the counts.

## For owners

```
openbridge quality enable --consent ALLOW     # off until you do this
openbridge quality report --markdown nov.md   # what your devices did this month
openbridge quality export --month 2026-11 --out openbridge-quality-2026-11.json
openbridge quality disable --forget           # stop and erase everything counted
```

What is counted, per month and per (manufacturer, model, firmware, category, action): runs, verified, unverified,
failed, blocked by policy, and a latency histogram (0.25 s to 32 s buckets). Manufacturer, model and firmware come
from Home Assistant's device registry.

What is never kept: device names, rooms, entity ids, values, exact times, IP addresses, an install id. The export file
is plain JSON: read it before sending it. **Nothing is ever sent by OpenBridge**: sharing the file is your choice,
by email or any other channel.

## For device makers

Merge the files owners send you:

```
openbridge quality merge exports/*.json --markdown acme-2026-11.md
```

The report gives, per model, firmware and action: runs, success rate (verified / (runs - blocked)), p95 latency and the
number of homes. It flags **firmware regressions**: comparing each firmware with the previous one of the same model,

- the success rate dropped by 10 points or more (each version with at least 20 runs), or
- the p95 latency is 1.5 times higher and at least 0.5 s slower.

Rows seen in fewer than 5 homes are marked "few", so a single unusual home is not over-read. On a partner plan,
OpenBridge prepares this report every month from the files partners' testers and volunteer owners send (see
[Plans](partners/PLANS.md)).

## How it is built

`src/runtime/quality_reports.py` (tests in `tests/runtime/test_quality_reports.py`). The counter listens to the same
receipts as the device learner, only once the owner has enabled it; a failure in the counter never affects the action.
