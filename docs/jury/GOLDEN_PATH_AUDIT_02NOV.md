# Golden-path audit (02-Nov-2026, main `2351308` + `feat/overnight-docs-a`)

NL request → Meta inference → grounded selection → proposal → validation →
consent → dispatch → read-back → receipt → revocation → refusal.
All paths below verified by reading the code, not by assertion.

## Path map (production)

| Leg | Code | Notes |
|---|---|---|
| Ask parse | `command.parse_request` → `nl_router.parse` | tiers low/medium local, high gated by consent+broker+allowance (`command.py:113-176`) |
| Single-intent approval | `command.approve` | skill registry resolve, target resolve (404/409 on miss/ambiguity), route check, fingerprint (`command.py:187-228`) |
| Single-intent execute | `command.execute` → `_execute_claimed` | fresh consent, preview match, idempotent (intent,fingerprint) claim, re-approve (revocations block), arm+invoke or direct executor (`command.py:252-362`) |
| Multi-step plan (CLI) | `cmd_workflows_plan --text` → `nl_plan.plan` | pinned local Meta only; S8 gate ON (`cli.py:1227-1244`, `nl_plan.py:247-264`) |
| Proposal validate | `composer.proposal_from_doc/compose` | shape + per-step allow/refuse, never raises per-step (`composer.py:143-180,237+`) |
| Studio proposals | `studio_view.js` TEMPLATES | deterministic client regexes, `origin:'template'`; same consent/revoke machinery; rehearsal SIMULATED |
| Migrate proposals | `migrate.propose/apply` | deterministic parse/resolve/match; discriminated proposal/clarification/refusal (`migrate.py:308+`) |

## Finding C-1: S8 gate scope (verified, not a defect)

The S8 intent/effect gate (`intent_effect.check`) runs ONLY inside
`nl_plan.plan_from_reply(..., request_text=...)` (`nl_plan.py:182-212`).
Production callers of that bridge: `nl_plan.plan`, called only by CLI
`workflows plan --text` (`cli.py:1240`) — plus the eval harness.
The UI Ask path (`nl_router.parse`) and the compose API
(`proposal_from_reply`, shape-only) do NOT apply the semantic gate.
This is coherent, not a hole: Ask shows the exact skill+params+target in a
fingerprinted preview and requires fresh consent (the human IS the semantic
check); Studio proposals are deterministic templates; the gate guards the
model→spec bridge where per-step preview is weakest. Do not rewire Ask
through the gate without evidence of a bypass — false refusals would tax the
golden path. Claim wording kept: "S8 gate over proposals" (workflow
proposals), never "S8 gate over Ask".

## Decision C-2: Studio stays template-driven (blocker published)

Investigated wiring Meta planning/synthesis into Studio publish.
Against the six safety conditions: (1) registered capabilities ✓ possible via
compose, (2) no bypass ✓ possible, (3) owner inspects ✓ possible,
(4) revocable ✓ possible, (5) comprehensive tests ✓ possible,
(6) existing demos functional ✗ FAILS in practice — the pinned small model
resolves novel intents at ~22% (ModelStudy48) and never clarifies, so a
model-driven Studio would propose wrong controls on the demo path and train
owners to click through previews. A gate-covered bridge exists only for CLI
workflows, not for the Studio publish shape. VERDICT: preserve the safe
template path. Revisit when: a pinned model scores ≥80% intent on a frozen
held-out Studio set AND a server-side Studio bridge reuses `compose` +
consent + revoke with red→green tests. This note is the published blocker.
