# OpenBridge — submission pack DRAFT (owner submits; do not file from this doc alone)

Track: Indie Developer. Theme: Push the Frontier (secondary: Build for Your World).
Deadline: 4 Nov 2026, 9:00 PM ET (verify on the official portal before filing).

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
- Real fabric run: 24 devices, Freebox-authenticated, 2 paired relays, redacted
  capture (`docs/jury/screens/fabric-tv-relay-redacted-1440.png`).
- Capability Forge agent layer (V4): Meta models propose new device
  capabilities as strict JSON manifests; evidence binding, primitive allowlists,
  model-identity checks, UI-schema patches, frozen exclusions and proof receipts
  are enforced in code (`src/forge/v4_*.py`, 40+ focused tests).
- Frozen evaluations with honest negatives: routing 32/32; explanations v1 0/8
  content (reasoning exhaustion at 800 tokens), v2 3/8 content, 26 SUPPORTED / 0
  UNSUPPORTED sentences (`docs/evaluation/routing-v1/`).

## Meta AI use (substantive, exclusive in production inference)
- Llama 3.2 3B (local, Ollama): NL parsing + candidate drafting; every live
  parse cites the model id in machine-readable provenance.
- Muse Glimmer 30B (local): medium tier; honestly reported UNAVAILABLE while
  its endpoint 500s (tiers API + UI badge) — never simulated.
- Muse Spark 1.3 (hosted, explicit consent + broker-guarded spend): high tier
  and frozen explanation evals; all spend receipted ($0.05 + $0.15).
- Muse Wonder: listed available, inference not yet exercised (stated, not claimed).
- Non-Meta assistants were used for development only, never for production inference.

## Honest limits (state on the form)
- G3 flagship (novel runtime hardware adapter generated live) is NOT yet
  demonstrated; the Forge layer, substrate contract (PR72, unmerged at pack
  time) and audit trail exist, the supervised physical run does not.
- Relay BLE scans work from the phone; TV on-screen report display is
  unverifiable with available tooling (identical code path as phone).
- Small eval samples; no victory claims.

## Demo script (live-first, ~5 min)
1. Ask panel: "How many devices are online" → preview → approve → READ (3 devices).
2. Phone: type "Send my vacuum to the dock" → PC parses → report on phone.
3. Relay scan from phone → advertisers merged (observe-only).
4. Screenshots + receipts as fallback if any hardware sleeps. No video
   substitution without an explicit owner request.

## Portal checklist (owner)
- [ ] Title, one-liner, track/theme above.
- [ ] Repo URL + commit hash of the filed tree (fill at filing time).
- [ ] Screenshots: the three `docs/jury/screens/` PNGs.
- [ ] Video: only if owner requests it (live demo is primary).
- [ ] Confirm deadline/timezone on the official page day-of.
