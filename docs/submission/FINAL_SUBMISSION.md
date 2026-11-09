# FINAL SUBMISSION — OpenBridge (copy-ready portal fields)

Status: prepared 03-Nov-2026, owner submits before 4 Nov 9 PM ET. Video + portal-only
confirmations remain owner actions (see bottom).

## Project

- Name: OpenBridge
- Tagline: One AI. Many devices. New possibilities.
- Track: Indie Developer
- Primary theme: Push the Frontier
- Secondary theme: Build for Your World
- Repository: https://github.com/toskaman/openbridge
- Submitted revision: release tag v0.3.1 (video-link commit on v0.3.0
  `a4138298b5f45c80e8ce9432470246e1c4d4aa1c`; content freeze
  `7d7475781bc4548ff20ca2339123708de7454ef9`, merge #188; the v0.3.1 tag points
  at the video-link commit — read its exact SHA from the tag/release page and
  enter that SHA in the portal).
- Release: https://github.com/toskaman/openbridge/releases/tag/v0.3.1
  (app/evidence/media packs + SHA-256 checksums).
- Jury entry: https://github.com/toskaman/openbridge/blob/v0.3.1/docs/jury/JURY_START_HERE.md
- License at the submitted revision: PolyForm Strict 1.0.0
  (see docs/LICENSING.md) + HACKATHON_EVALUATION_PERMISSION.md,
  the scoped judge-run grant.
- Members: owner-declared in the portal (OWNER_PENDING — confirm exact list).

## Short pitch (copy)

OpenBridge uses Meta AI to help different devices understand, connect, and control
one another through verified capabilities, explicit authorization, and observable
results.

## Full description (copy)

Every home and workshop is full of capable devices that cannot talk to each other:
a TV, phones, a watch, PCs, a robot vacuum, a router — each locked behind its own
app and vendor protocol. OpenBridge is a local-first device fabric: it discovers
what your devices can really do, and Meta AI turns that verified capability graph
into new cross-device features — a TV panel that controls the vacuum, watch
controls for the TV, phone-as-relay routes for a PC without Bluetooth — composed
from registered capabilities, never hardcoded one by one.

Without Meta inference, OpenBridge would be static device plumbing: it could
transport commands but not interpret free-form intentions, propose intelligent
compositions, or generate new interfaces from discovered capabilities. Every Meta
proposal passes through deterministic gates: typed validation, fingerprint-bound
previews, explicit owner consent, exactly-once dispatch with a pre-dispatch
journal, read-back verification, receipts, and revocation. Simulated results are
never counted as physical proof, and limits are stated upfront in
docs/KNOWN_LIMITATIONS.md.

## Problem solved (copy)

Device fragmentation: N devices × M vendor apps with no shared intelligence, no
common authorization, and no verifiable execution. OpenBridge replaces per-vendor
remote apps with one permission-aware fabric where new controls are composed from
proven capabilities and every action is authorized, verified, and revocable.

## Why OpenBridge is new (copy)

AI-generated capabilities, not predefined integrations: Meta models compose new
controls from a live, verified capability graph. Permission-aware cross-device
orchestration with verified actions instead of untrusted AI execution, local-first
intelligence, explicit consent, and one interface for heterogeneous hardware.

## Meta models role (copy)

- Llama 3.2 3B (local, Ollama :11437, digest-pinned): NL→plan routing and
  capability selection; live-verified (quiet-mode plan → TV vol 22→21 + vacuum
  dock, wf-a44e6e7a62b7).
- Muse Glimmer 30B (local, :11438, digest-pinned): structured TV control-panel
  synthesis; verified install/dispatch/receipt/revoke chain 31 Oct
  (tx-ab731d7b885b5e1a).
- Muse Spark 1.3 (hosted, consent-gated, budgeted): design-time assistance and
  optional cloud tier; runtime calls need per-call consent + spend approval.
- Runtime is Meta-only (enforced by src/ai/registry.py + drift tests); no silent
  non-Meta substitution. Published losses kept: ModelStudy48 rules 36.1% vs Llama
  22.2%; S8 gate eval2 unsafe 2→0, eval3 unsafe 4→0, zero fully-correct proposals
  blocked.

## Demo video

https://youtu.be/TZaxCcRmrLQ — "OpenBridge Jury v5 MetaMMS 175s", partly owner-filmed, Meta MMS-TTS narration, re-delivered
04-Nov-2026 (link verified live + oEmbed title/author/embeddable; canonical slot:
`submission/final-video.mp4`). Agent-built cuts V2–V5 are HISTORICAL DRAFTs,
never the submission. Owner pastes this video link in the portal.

## Selected screenshots

- docs/jury/screens/s5b_pressed.png — Meta-generated TV panel mid-run on the real
  TV (hold-press FIND dispatched, receipt, oracle stable, revoke+deny after).
- docs/ui/screens/after-home-1440.webp — Ask OpenBridge home workspace.
- docs/jury/screens/ask-openbridge-*.png — live local-tier Ask flows.
- docs/evidence/frames-02nov/ — filmed START/DOCK dispatch + lease-stale refusal.

## Technologies

Python 3.14 (stdlib-only runtime), Meta Llama 3.2 / Glimmer / Muse Spark (Ollama +
Meta Model API), Android + Wear OS + Android TV companions (0.12.0), ADB, mDNS/SSDP,
Freebox/UPnP-IGD router reads, Tuya local 3.4, Bluetooth relays, Chromium/WebKit UI.

## Hackathon contribution

Built 26 Oct – 4 Nov 2026 (start ref 2026-10-26T16:24:00Z, zero files predate;
CONTRIBUTIONS.md). Pre-existing private agent.exe prototype rewritten as Bridge
Agent v4 (separate repo, disclosed); dev-time coding assistants (Codex/Muse)
disclosed as build-time only — runtime inference is Meta-only.

## Bonus eligibility (rule labels from the 03-Nov audit)

- Best Agentic Use-Case: POSSIBLY_ELIGIBLE (Meta reasoning → synthesis →
  authorization → execution → verification chain).
- Best Build on Meta Open Weight Models: POSSIBLY_ELIGIBLE (local Glimmer + Llama;
  confirm whether Llama-alone counts — guide says Glimmer or Spark Open).
- Best Creative Build: UNVERIFIED (needs Muse Image or Wonder per guide).
- Most Viral / Community Vote: UNVERIFIED (dates conflict: Nov 10 vs Nov 16).
Owner confirms names/conditions in the portal before claiming any bonus.

## Known limitations (copy)

Honest limits: vacuum dispatch verified, locomotion oracle-proven but unfilmed;
BridgeWindows v4 transport is HMAC-authenticated plaintext (trusted LAN only);
6-digit pairing resists online guessing but not offline transcript brute force;
macOS GUI CI-covered, not hand-tested; 2-taps→16-executions root cause still open.
Full list: docs/KNOWN_LIMITATIONS.md.

## Judge test procedure (copy, no secrets or hardware needed)

```sh
git clone https://github.com/toskaman/openbridge.git
cd openbridge   # checkout tag v0.3.0
python -m unittest discover -s tests   # 2378 controlled tests
python -m src.cli judge demo           # offline demo, verdict DEMO_COMPLETE
python -m src.server                   # loopback → http://127.0.0.1:18765
```

Full path: docs/jury/JURY_START_HERE.md (30 s → 10 min ladder).

## Owner-only remaining

- [x] Film + upload the finale video — RE-DELIVERED 04-Nov:
      https://youtu.be/TZaxCcRmrLQ ("OpenBridge Jury v5 MetaMMS 175s"); paste link in portal.
- [ ] Confirm track/theme/members, bonus names, license scope, editability
      (portal-only items).
- [ ] Enter submitted-revision SHA from the v0.3.1 tag page.
- [ ] Submit before 4 Nov 9 PM ET; keep the receipt; report back for the
      SUBMITTED flag. Do not accept new legal terms without reading them.
