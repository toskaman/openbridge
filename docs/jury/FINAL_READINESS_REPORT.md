# FINAL READINESS REPORT — OpenBridge Absolute Final Jury Release

Date: 03-Nov-2026. This report records the release candidate, not the portal act.

## 1. Executive summary

- Status: READY_FOR_SUBMISSION (all artifacts delivered; portal filing remains).
- Version: v0.3.1 (video-link commit on v0.3.0 `a413829`; content freeze `7d74757`,
  merge #188; start of campaign: origin/main `a5e8208`, PR #182).
- Tests: 2378/2378 (`python -m unittest discover -s tests`), N03 cross-process
  dispatch-once verified, incl. new restart-duplicate regression test.
- CI: main run 41681182589 SUCCESS 5/5 on `ec03baa` (merge #187); fix-head push
  run 41674354259 SUCCESS 5/5 on `333d14d`; docs PR #188 7/7 executed SUCCESS
  (3 macOS jobs infra-cancelled in queue, zero steps ran, code covered by main).
- Systems: Windows + Ubuntu + macOS + Chromium + WebKit CI; clean-room +
  Android labs are manual-dispatch and run on the freeze SHA (see §8).
- Video: DELIVERED 03-Nov — https://youtu.be/Q4slAW3NjuQ ("OpenBridge Jury";
  link live + oEmbed verified).
- Submission: prepared (docs/submission/FINAL_SUBMISSION.md), NOT submitted.

## 2. Rules (labels: OFFICIAL_CONFIRMED / ORGANIZER_CLARIFICATION /
PARTICIPANT_PROVIDED_OFFICIAL_GUIDE / THIRD_PARTY_UNVERIFIED / PORTAL_ONLY)

- Deadline 4 Nov 2026 9 PM ET, Indie track, Push the Frontier + Build for Your
  World: OFFICIAL_CONFIRMED (dev.meta.ai + Cerebral Valley event pages).
- 18+, ≤20000 rolling, territory/sanctions exclusions: OFFICIAL_CONFIRMED.
- Meta-only runtime (every model called must be Meta): ORGANIZER_CLARIFICATION +
  PARTICIPANT_PROVIDED (satisfied — registry-enforced, §6).
- Video ≤180 s, working product, English-intelligible: ORGANIZER_CLARIFICATION.
- Submission = public GitHub repo + video link + teammates, editable until
  deadline, one representative: ORGANIZER_CLARIFICATION (portal PORTAL_ONLY).
- Weights 30/25/25/20 vs equal 4×0-10: CONFLICT (third-party vs guide) —
  owner confirms. Bonus names/dates: PARTIALLY CONFLICTING (Nov 10 vs Nov 16).
- Waiver/IP (ownership retained + broad organizer license): THIRD_PARTY quoting
  a PORTAL_ONLY waiver — owner reads before accepting. No open-source mandate
  found; repo license split declared (PolyForm main + judge grant, MIT v0.2.0).
- Start-ref/provenance: zero files predate 2026-10-26T16:24:00Z; v4-rewrite and
  build-time assistants disclosed (CONTRIBUTIONS.md).

## 3. Fixes (campaign 03-Nov)

- P0 N03 `test_same_intent_dispatches_once_across_processes` (Windows, 2/2 PR
  runs): root cause — arm-time and claim-time UNCERTAIN_OUTCOME refusals used
  different wordings for one contract outcome; Windows scheduling hits the
  arm-time path the test never pinned. Fix (commit `333d14d`, PR #187): single
  `_UNCERTAIN_MSG` on all four uncertain paths; DONE stays a distinct
  DUPLICATE_REQUEST. No dispatch-twice (ledger + atomic journal claim + file
  locks verified), 409s preserved, no blind replay after crash.
- P0-2 latent (found by the same trace): direct invoke of a restart-restored
  DONE id fell through to dispatch with route=None (TypeError-FAILED receipt).
  Fix: DUPLICATE_REQUEST refusal in both probes + regression test
  `test_direct_invoke_of_restarted_done_id_is_duplicate` (failed pre-fix).
- Ubuntu #186 failures (4): fresh-boot monotonic 0-sentinel throttling first
  reconnect (fixed by None sentinel, commit dd2e5d3) + POSIX relay-path test
  spelling (test-only). macOS relay_store: same fix.
- Contract: B2 §6 restart-refusal rule added. Full local suite 2378 OK;
  Windows/macOS/Ubuntu/browser CI green on the merged main.
- PRs: #187 merged (ec03baa, 69 commits incl. #183–#186 ancestry + N03 fix);
  #183–#186 auto-MERGED as reachable; #188 docs merged (7d74757).

## 4. Documentation

- 165 active Markdown files inventoried; 0 broken relative links; all cited
  short SHAs resolve. 38 files synced in #188 (D1–D7): SHA re-pins, 2378 counts
  + era notes, V4/V5 HISTORICAL matrix rows + canonical owner-video slot,
  MIT stales annotated, v0.2.0 framing retired, DRAFT_PACK archived with
  SUPERSEDED pointer, 35-vs-37 contradiction fixed, staleness headers,
  ModelStudy48/S8 rows added.
- Old jury cuts V2–V5 kept as labeled history (builders, manifests, docs);
  removed from every active submission surface. Exactly one canonical video
  reference: https://youtu.be/Q4slAW3NjuQ ("OpenBridge Jury", owner-filmed,
  delivered 03-Nov; canonical slot `submission/final-video.mp4`).
- v0.2.0 release assets left untouched as immutable history (documented choice).
- Jury ladder: docs/jury/JURY_START_HERE.md (30 s → 10 min), README, QUICKSTART,
  claim/evidence matrix, verified capabilities, limitations, submission pack.

## 5. Security

- Verified by inspection + tests: pairing/challenge + replay resistance,
  dispatch-time consent/lease/actor checks, revocation (relay + substrate +
  fail-closed restart), double-submit/multi-process admission (journal claim +
  ledger), strict input allowlists (relay ops, IDs, paths, URLs, model parses).
- Residuals (documented, not hidden): BridgeWindows v4 is HMAC-authenticated
  PLAINTEXT (trusted LAN only; v5 sealed design unshipped); 6-digit pairing
  falls to offline transcript brute force (online controls strong);
  RecursionError/envelope-replay findings rest on code inspection (no live
  exploitation per scope); Companion Keystore upgrade path open; Windows
  journal dir-fsync skipped (file fsync kept).
- No secrets in repo, packs, or logs (pack script refuses secret patterns).

## 6. Meta models

- Runtime Meta-only, enforced: registry allowlist + ALLOWED_HOSTS, per-call
  require(), digest-pinned Ollama models, no silent fallback (explicit raises),
  outbound scan clean, R12 drift tests.
- Llama 3.2 3B: quiet-mode plan (TV vol + dock, wf-a44e6e7a62b7).
  Glimmer 30B: TV vacuum panel synthesis + install/dispatch/revoke chain
  (tx-ab731d7b885b5e1a, 31 Oct). Spark 1.3: consent-gated cloud tier.
- Losses published, not hidden: ModelStudy48 rules .361 vs Llama .222
  (Glimmer OOM); Forge Llama 0%; S8 gate 2→0/4→0 unsafe with zero correct
  blocked. Dev-time non-Meta assistants disclosed as build-time only.

## 7. Reproducibility (judge path, verified by CI + clean-room design)

```sh
git clone https://github.com/toskaman/openbridge.git
cd openbridge   # checkout tag v0.3.0
python -m unittest discover -s tests   # 2378 controlled tests, no hardware
python -m src.cli judge demo           # offline demo, verdict DEMO_COMPLETE
python -m src.server                   # loopback → http://127.0.0.1:18765
```

Zero secrets, zero personal devices, zero home-network access needed for the
base path. Hardware features declare prerequisites; offline REPLAY fallback
stays honest (SIMULATED-labeled). Extract-and-run from the app pack is part of
release validation (§8).

## 8. Release v0.3.0

- Freeze: v0.3.1 (this commit: video-link on v0.3.0 `a413829`; content
  `7d74757`, merge #188); tag v0.3.1 after its CI is green. v0.3.0 packs
  superseded (identical code, pre-video docs).
- Packs (built from the freeze commit via scripts/release_pack.py, secret-scan
  enforced): OpenBridge-App-v0.3.1.zip, OpenBridge-Evidence-v0.3.1.zip,
  OpenBridge-Media-v0.3.1.zip — each with BUILD.json, RELEASE_MANIFEST.json,
  sha256sums.txt. Hashes recorded on the GitHub release page (packs postdate
  this report by construction).
- Validation: clean-room manual dispatch + Android manual dispatch on the freeze
  SHA; archive extraction test; run-from-archive smoke; no-secret rescan.
- Release page: https://github.com/toskaman/openbridge/releases/tag/v0.3.1
  (video is the YouTube link in §9; no mp4 redistributed).

## 9. Video

- Status: DELIVERED 03-Nov — https://youtu.be/Q4slAW3NjuQ ("OpenBridge Jury",
  channel MS; verified live + oEmbed title/author/embeddable; canonical slot
  `submission/final-video.mp4`, see submission/README.md). No agent-generated,
  reused, or fallback jury video is published or linked as the submission.
- V2 (3d3e228e) / V3 (eee76671, 159.33 s) / V4 (12f49234) / V5 (b3cb41e7,
  170.70 s): HISTORICAL DRAFTs with builders + manifests preserved.
- Vacuum caveat preserved: dispatch/UI-state + Tuya oracle proven; locomotion
  unfilmed — the owner finale is the chance to film it.
- Reception checks on delivery: ≤180 s, A/V tracks, codec/resolution,
  subtitles, SHA-256, no misleading presentation, match to submitted commit.

## 10. Evaluation (adversarial sample; full objections in jury docs)

Strengths: real Meta-composed features on real hardware with receipts;
defense-in-depth consent/revocation/idempotency; honest negative results;
reproducible offline judge path; measured benchmarks with kept losses.
Weaknesses: macOS GUI hand-test missing; 2-tap root cause open; pairing
offline-brute-force residual; plaintext v4 LAN transport; some F90 modules
software-tested, hardware-pending; Portal-only rules unverified.
Sample objections answered in-repo: rules-vs-AI (measured ablations),
Home Assistant (capability composition vs static integrations),
wrong-command safety (S8 gate + fingerprint-bound consent),
offline behavior (graceful DEMO_BLOCKED/REPLAY), Mac support (CI matrix),
no-hardware testing (offline demo), data theft (local-first + budgets +
consent), commercial path (docs/jury investor section).

## 11. Owner-only remaining

- [x] Film + upload the finale video — DELIVERED: https://youtu.be/Q4slAW3NjuQ
  (owner keeps raw + subtitles).
- Portal: confirm track/members/bonus/license/editability; enter the v0.3.0
  commit SHA; attach packs; submit before 4 Nov 9 PM ET; keep receipt.
- Read (do not auto-accept) any new portal terms/waiver.
- Optional post-submission: vacuum-motion filming, macOS hand-test, live
  duplicate/expiry retest, Companion Keystore upgrade.

## 12. Verdict

READY_FOR_SUBMISSION — supported by: merged main (release v0.3.1), 2378-test
suite green locally + 5/5 CI, docs synced with zero broken links, Meta-only
runtime enforced, official owner video delivered + verified live, packs +
checksums published, submission fields copy-ready. NOT SUBMITTED_VERIFIED
(portal filing is the remaining owner act; no receipt yet).
