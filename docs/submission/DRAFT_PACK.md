# OpenBridge — submission pack DRAFT (owner submits; do not file from this doc alone)

Track: Indie Developer. Theme: Push the Frontier (secondary: Build for Your World).
Deadline: 4 Nov 2026, 9:00 PM ET (verify on the official portal before filing).
Pack state: 29 Oct 2026 midday, main `0cf39ec` (PR74 merged, 0 open PRs).

## One line
OpenBridge is a local-first device fabric: ask in plain language from PC or
phone, Meta models draft the understanding, deterministic gates verify, and the
owner approves every action.

## What is demonstrated (all evidenced in-repo)
- Ask OpenBridge P0: EN/FR natural language → registered skill → fingerprint-bound
  preview → approve → exactly-once execute. Live-verified with real local Llama
  (`docs/jury/screens/ask-openbridge-*.png`).
- Phone→PC→phone signed loop over the relay channel: typed on a real phone,
  parsed on the PC, outcome reported on screen
  (`docs/jury/screens/companion-ask-phone.png`). The phone never executes.
- Voice: companion push-to-talk (AudioRecord PCM16) → paired PC only → local
  MMS-1B STT (no cloud); STT→parse 16/16 no wrong-skill on the frozen corpus;
  owner human voice 2/2 (`docs/evidence/v4/overnight/N2_N3_RESULTS.md`).
- Real fabric run: 24 devices, Freebox-authenticated, 2 paired relays, redacted
  capture (`docs/jury/screens/fabric-tv-relay-redacted-1440.png`).
- Capability Forge agent layer (V4): Meta models propose new device
  capabilities as strict JSON manifests; evidence binding, primitive allowlists,
  model-identity checks, UI-schema patches, frozen exclusions and proof receipts
  are enforced in code (`src/forge/v4_*.py`, 40+ focused tests).
- **G3 integration smoke: SUCCESS (29 Oct, attempt 4).** 1 Muse Spark 1.3 call
  (v4-synth-3) → kernel compiled → owner grant → physical TV mute
  (false/20→true/0) → restore → revoke → post-revoke 403. Full transcript:
  `docs/evidence/v4/g3-smoke/attempt4_SUCCESS.json`. Labeled smoke (public
  target), not held-out novelty.
- Spark-vs-local safety finding (N4, 4 broker-guarded calls): Spark abstains on
  unregistered capabilities (lamp, TV pause) where llama 3B confabulates or
  over-resolves — high tier is a registry-safety gain
  (`docs/evidence/v4/overnight/N4_RESULTS.md`).
- Frozen evaluations with honest negatives: routing 32/32; explanations v1 0/8
  content (reasoning exhaustion at 800 tokens), v2 3/8 content, 26 SUPPORTED / 0
  UNSUPPORTED sentences (`docs/evaluation/routing-v1/`).

## Meta AI use (substantive, exclusive in production inference)
- Llama 3.2 3B (local, Ollama): NL parsing + candidate drafting; every live
  parse cites the model id in machine-readable provenance.
- Muse Glimmer 30B (local): medium tier; honestly reported UNUSABLE on this box
  (30b-q4 needs 12.8 GB CUDA, 10.8 GB free; OOM → honest `escalation_required`)
  — never simulated.
- Muse Spark 1.3 (hosted, explicit consent + broker-guarded spend): high tier,
  frozen explanation evals, G3 synthesis. Ledger: $1.30 reserved / $2.00 global
  cap (G3 $0.80 + N4 $0.40 + G3 retry $0.10); actual estimated provider cost
  ≈ $0.11. Every cent receipted in `LOCALAPPDATA/OpenBridge/budget.sqlite3`.
- Muse Wonder: listed available, inference not yet exercised (stated, not claimed).
- Non-Meta assistants were used for development only, never for production inference.

## Honest limits (state on the form)
- G3 held-out novelty run NOT yet performed: sealed commit-reveal machinery is
  merged (`dev/g3_task.py`, `docs/forge/G3_SEALED_TASK_PROTOCOL.md`) but Sol has
  not sealed a target at pack time. The attempt-4 smoke proves the
  generation→grant→invoke→read-back machinery on a public target only.
- Companion 0.7.0 (UI rewrite): reviewed, builds, launches clean on phone + TV;
  full voice regression on the new build is pending.
- Small eval samples; no victory claims.

## Demo script (live-first, ~5 min)
1. Ask panel: "How many devices are online" → preview → approve → READ (3 devices).
2. Phone: type "Send my vacuum to the dock" → PC parses → report on phone.
3. Voice: push-to-talk on phone → local STT → parse → report (needs ≥6 GB free RAM).
4. G3 replay: show the attempt-4 transcript + TV mute/restore on demand (supervised).
5. Screenshots + receipts as fallback if any hardware sleeps. No video
   substitution without an explicit owner request.

## Portal checklist (owner)
- [ ] Title, one-liner, track/theme above.
- [ ] Repo URL + commit hash of the filed tree (fill at filing time).
- [ ] Screenshots: `docs/jury/screens/` PNGs (ask-openbridge-*, companion-ask-phone,
      fabric-tv-relay-redacted-1440).
- [ ] Video: only if owner requests it (live demo is primary).
- [ ] Confirm deadline/timezone on the official page day-of.
