# S5b safe-seek proof: T2 panel on real TV → hold-press FIND → vacuum beep → poll oracle → revoke → deny (REAL_HARDWARE, 31 Oct 2026)

Companion run to [S5](s5-tv-panel-31oct.md) (dock, no motion observed). S5b presses the
`vacuum_command seek` button of the Meta-generated T2 panel instead: an audible beep
with zero motion, so the physical chain can run without moving the robot.

## Chain

Pair (TV relay `relay-dabd2a796665`, on-screen code via screencap + Windows OCR,
accepted on the FIRST candidate) → install T2 patch (Find vacuum + Volume up/down,
`set_controls` round-trip) → OCR-located hold-press on "Find vacuum" (1290, 595,
adb swipe 1500 ms, honestly labeled NOT a manual tap) → press queue → PC poll →
arm/invoke → Tuya dispatch → receipt `tx-4a96f8f626a1adc5` (`EXECUTED_UNVERIFIED`)
→ 15 × 2 s Tuya polls → `set_controls([])` revoke (0 grants left) → post-revoke
press denied (`RemoteControlError: This control is no longer authorized`) →
`relay_revoke` VERIFIED.

Vehicle: `dev/s5b_safe_seek_chain.py` (same product paths as `dev/s5_tv_panel_chain.py`).

## Context: the robot was already cleaning

Between the pre-read (standby, 100%) and the run, the vacuum went to `smart_clean`
(73%) on its own — not started by this test (no start/pause/dock/move was ever sent;
only reads plus the single seek). All 15 post-press polls read `smart_clean`,
fault 0: no state transit, as expected for a beep. The audible effect itself is not
machine-proven (covered by the cleaning noise); the owner was home.

## Vehicle fix learned live

The first attempt failed pairing with three refused OCR candidates: the script read
all OCR rounds BEFORE trying any candidate, and Windows OCR is slow enough that the
120 s code TTL expired while the stale digits stayed on screen ("not paired" for the
displayed code). S5b confirms round by round; the rerun paired on its first candidate
(`frag-join/r1`). The stale-code display after TTL expiry is flagged for product review.

## Artifacts

- Transcript: `C:/tmp/on_s5b2.log` (this host; sanitized JSON, no keys/codes).
- Screenshots: `E:/shots/s5b/` (`s5b_installed.png`, `s5b_pressed.png`, `s5b_revoked.png`, `s5b_code_*.png`).
- Panel: `artifacts/s5-tv-panel-31oct/t2-propose-medium.json` (Meta-generated 31 Oct AM, bindings exact).

## Honest limits

- Press is adb-injected long-press, not an owner manual tap.
- Receipt is `EXECUTED_UNVERIFIED` (no read-backable effect for a beep).
- No suction/move/dock command was sent; nothing to undo.
- The vacuum was NOT touched beyond reads + one seek; it kept cleaning throughout.
