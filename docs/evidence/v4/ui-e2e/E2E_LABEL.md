# E2E UI label publish — evidence (29 Oct 2026, ~15:10 CET, owner-authorized autonomy)

Loop: S2 draft (`v4_uidraft.draft_from_slots`) → C1 emit (`emit_install_plan`)
→ POST `/api/v2/manifests/ui_install` → TV screen → withdraw → gone.
Zero-effect widget (label, no binding): proves the publish path end to end
without any executable surface.

## Transcript (live 18765, TV relay `relay-dabd2a796665`, companion 0.8.0)
- Pair: `CODE_SHOWN_ON_DEVICE` → code read on TV screen (`940 143`) →
  `PAIRED`. Companion declares `remote_controls` + `aead1`.
- Fingerprint: `fp-2248383272a4d550` via `/api/v2/facts/signed` (13 facts).
- Install: HTTP 200, `plan_hash sha256:4d3a78cb…`, layout revision 3,
  display entry `label "Forge E2E label"`.
- Independent read-back: TV UI dump contains `Forge E2E` (exact distinctive
  string, only source = this plan).
- Cleanup: POST controls `[]` → HTTP 200, `layouts {}`, TV UI dump no longer
  contains the string.

## What this proves / does not prove
- Proves: Forge draft → kernel-validated plan → relay delivery → on-screen
  render → acknowledged withdraw, all API-verified + screen-verified.
- Does NOT prove: button/confirm execution (needs approved manifest + grant;
  covered by sibling HW_UI runs on the same kernel path), Meta-authored
  wording (slots were explicit; model drafting measured separately in S1).
