# Overnight N4 — Spark-vs-local: local side done, Spark side morning-gated (2026-10-29)

Branch: `spark/night-batch`. Live 18765 queried read-only (no reload/restart).

## Ledger truth (VERIFIED, canonical ledger `LOCALAPPDATA/OpenBridge/budget.sqlite3`)

- 6 rows x $0.10 = **$0.60 reserved**, all under observation
  `meta-dashboard-20261029T0010` (G3 authz, allowance $0.80).
- `src/ai/broker.py:140`: **global cap $1.00 TOTAL across the whole ledger, ever**.
- Remaining headroom: **$0.40 = 4 Spark calls max**, regardless of any larger
  authorization. The owner's $3 overnight auth CANNOT be fully spent without an
  owner+trust code change to the cap — I will not touch that safety rail myself.

## Why $0.00 was spent overnight (by design, not by omission)

A new spend needs a NEW owner-minted observation (balance + observed-at):
- G3's observation is bound to G3's allowance/authz (`broker.py:136` rejects reuse
  with different authz); reusing it for N4 would misattribute spend. Refused.
- Minting my own observation timestamp = fabrication (`run_explain_eval --observed-at`:
  "immutable, never minted"). Refused.
- Morning unlock: owner states ONE fresh balance observation -> runner below spends
  at most 4 x $0.10 under the remaining $0.40 headroom, then stops at the cap.

## Local side: 8 hard prompts on low tier (llama3.2:3b, live 18765, 2026-10-29 ~01:00)

| id | lang | prompt | status | skill | question | ms |
|---|---|---|---|---|---|---|
| P1 | fr | allume la lampe du salon et lance l aspirateur | needs_clarification | — | Allume la lampe du salon, ou allume et lance l'aspirateur? | 15444 |
| P2 | en | turn it off | needs_clarification | — | Set an exact volume, or step up once? | 4692 |
| P3 | fr | commande une pizza | needs_clarification | — | Quelle pizza voulez-vous commander? | 4507 |
| P4 | en | mets la TV en pause s il te plait | **resolved** | tv_volume_step | — | 4293 |
| P5 | fr | fais quelque chose pour la tele | needs_clarification | — | Set un volume exact, ou faire un pas vers le haut? | 5232 |
| P6 | en | turn off everything in the bedroom | needs_clarification | — | Set an exact volume, or step up once? | 5217 |
| P7 | fr | allume la lampe du salon | needs_clarification | — | Quelle lampe du salon voulez-vous allumer? | 4519 |
| P8 | en | start my vacuum | **resolved** | vacuum.start | — | 4055 |

Read (honest, no over-claim):
- Controls: P8 resolves (vacuum keyword-strong). P7 SHOULD resolve but asks which
  lamp — weak recall on the exact demo phrase; best Spark comparison candidate.
- P4 is suspicious: FR text with lang=en resolved to tv_volume_step (pause != volume
  step). Possible over-resolve; Spark's answer will arbitrate, and the deterministic
  approve/preview gate still stands in front of any execution.
- P2/P5/P6: clarification questions are volume-template-biased ("set vs step") even
  when the request is not about volume — cosmetic weakness, honest status.
- P3: safe (clarifies instead of inventing); stricter would be `unsupported`.
- No wrong-skill execution risk observed: all non-resolved statuses block approve.

## Frozen Spark comparison set (4 calls = $0.40, see `dev/n4_pack.json`)

P7 (control that failed), P4 (suspected over-resolve), P1 (multi-intent), P2 (no-target).
Morning command (owner mints observation):
`python -m dev.run_n4_spark --observation-id <id> --free-balance-usd <n> --observed-at <ISO-tz> --authz <ref> --out docs/evidence/v4/overnight/n4_spark`
Stops at ledger cap; never retries; records usage + cost per call.

## Pre-existing findings on the high path (VERIFIED hermetic, NOT fixed in night PR)

1. Double-reserve on non-terminal first reply: `nl_router.py:295-318` — if the
   first cloud reply doesn't reach a terminal status (or the transport raises),
   the `quality == 'high'` tail calls `before_cloud()` (reserve) + transport a
   SECOND time. Reproduced hermetic: invalid reply (targets []) -> 2 sends.
   Impact on N4: worst case 2 reserves/case; the runner stops earlier via
   gate-stop, so the run stays ledger-honest. Fix needs trust review (V4 lane).
2. No `format` JSON-schema on the cloud payload (`nl_router.py:238-241`): only a
   developer-prompt instruction, unlike the strict INTENT_SCHEMA on Ollama.
   Spark replies are validated AFTER the spend. Same disposition: document, don't
   touch (trust-adjacent).
