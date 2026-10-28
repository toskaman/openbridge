# Freeze guide (routing-v1 explanations) — follow exactly, in order

1. Owner reviews PROMPT.md, SAMPLE.json, RUBRIC.md, BUDGET.md on the freeze PR.
   Spark authored them and cannot approve them (author/approver separation).
2. Owner approves explicitly (PR approval or "freeze" instruction). Requested
   changes restart at step 1 with new bytes; never edit after step 3.
3. Single freeze commit containing these four files plus SHA256SUMS over their
   exact bytes, with the message attesting: no explanation calls, spend or
   results exist at freeze time.
4. Only then may the 8 calls run (SAMPLE.json order), spend capped by BUDGET.md.
5. Replies + receipts publish in a follow-up; scoring follows RUBRIC.md.

This directory is DRAFT until step 3 lands on main. Any `.json` results file
here before the freeze commit is a protocol violation: delete it and restart.
