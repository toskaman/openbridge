# S5 TV panel — 01-Nov-2026 fully-manual proof (REAL_HARDWARE, owner presses)

Supersedes the ADB-injected 31-Oct press for the *press* leg. Panel widgets are
the 31-Oct Glimmer-validated set, reused verbatim (fresh proposal blocked
tonight: Glimmer :11438 OOM, Llama-3B PATCH_REJECTED); only the opaque target
pointer was re-resolved to the current discovery epoch. Recorded in-transcript,
never silent.

## Attempt 1 (~18:3x) — START verified, DOCK blocked
- Pairing: unassisted OCR path, code 718199 auto-read + confirmed, PAIRED.
- START: owner manual tap, tx-8abdd1eb, VERIFIED. Oracle: standby, 95→86 %.
  No motion (unit already docked — expected).
- DOCK: owner manual tap BLOCKED by the device: "Unavailable: lease stale"
  (Tuya WIFI route lease 60 s expired after a ~3.5 min press gap). Honest
  negative result, preserved in `attempt1/chain-manual-transcript.json`.
- End: controls revoked (0 grants), invoke-after-revoke denied, relay revoked.

## Attempt 2 (~18:48–18:51) — DOCK verified, oracle motion delta
- Pairing: assisted. Two blind retries failed first (OCR misreads the huge
  pairing digits + 120 s TV code expiry → TV refused "not paired", then
  "pairing locked; reopen the app"). Cold-restarted the Companion via adb,
  fresh pair-start, operator read code 146976 from one screenshot, confirmed
  in-process within TTL → PAIRED. Recorded as `operator-assist` in transcript.
  Owner still performed every physical button press.
- DOCK: owner manual press (`gesture: key`, TV remote), tx-63ee07451c4099ce,
  VERIFIED — "Dock vacuum: done, verified" on the TV panel screenshot.
- Oracle delta (independent Tuya read-back): `vacuum_status` standby →
  **goto_charge**, battery 83 %. The unit is returning to its dock: motion
  behavior proven by oracle, not by video.
- End: controls revoked (0 grants), `deny_after_revoke` =
  `RemoteControlError: This control is no longer authorized`, relay_revoke
  VERIFIED.

## Artifacts (E:/shots/demo-s5-01nov/, local, not in git)
- `chain-manual-transcript.json` (attempt 2, fail_stage null, progress DONE)
- `demo-s5-tv-installed.png` (18:49:38), `demo-s5-tv-press-dock.png`
  (18:50:34), `demo-s5-tv-revoked.png` (18:50:45)
- `attempt1/` — full attempt-1 transcript + shots + reused patch
  (`patch-reuse.json`), incl. the lease-stale adverse finding
- `pair-assist.png` (code 146976 as shown), `tv-pairing-now.png` (code 116805,
  dead challenge from a blind retry — superseded, kept for honesty)

## Instrument
`dev/s5_tv_panel_chain_manual.py` (this branch): manual-press chain with
PRESS_ORDER argv (`start,dock` default, `dock`-only supported), IME dismiss
via KEYCODE_BACK (navigation only, never the press), 600 s press budget,
OB_PAIR_ASSIST operator code path (fallback: OCR loop), OB_REUSE_PAIRED
get_status fast path. No product-code change: dev-only.

Note: `docs/jury/FINAL_RELEASE_AUDIT_2026-11-01.md` §13 predates this run;
fold these tx ids into the audit on the next revision.
