# TV sleep/wake + Companion reveal — live verification (02-Nov-2026)

Branch `feat/tv-power`. TV: label `android tv`, 192.168.1.15:5555 (owner set).
Script: `dev/tv_sleep_verify.py`. Transcript: `E:/shots/tv-sleep-02nov/tv-sleep-transcript.json`
(final run below; earlier attempts in §Findings).

## Verified results (REAL_HARDWARE)

| # | Skill | Receipt | Oracle | Owner eyes |
|---|-------|---------|--------|------------|
| 1 | `tv_sleep` | key accepted (see §Findings for receipt evolution) | link dropped before read-back | **screen went dark — confirmed by owner** |
| 2 | `tv_wake` | `EXECUTED verified=True` | `mWakefulness=Awake` via dumpsys power | screen on |
| 3 | `companion_foreground` | `EXECUTED verified=True` | `mFocusedApp=…fr.openbridge.companion/.MainActivity` | **Companion visible on screen — confirmed by owner** |

Run-3 output (final): `tv_wake -> EXECUTED verified=True`,
`companion_foreground -> EXECUTED verified=True`, `LIVE RUN PASS`.

Owner note on run 3: the TV had idled back to sleep before he looked; on
waking it with the remote, the Companion was displayed. Consistent with the
oracle (Companion was the focused activity; it survives sleep/wake).
Demo consequence: disable the sleep timeout (or wake just before) when filming.

## Findings (adverse + fixes, all preserved)

1. **Sleep drops Wi-Fi ADB on this TV.** After the SLEEP keyevent, the link went
   `offline` and `adb connect` was refused (10060) while asleep. On wake with
   the remote, the link returns (`device`) by itself. Consequence: `tv_wake`
   cannot power-on this TV over a dead link — the remote wakes it; the skill
   then verifies. Runbook §TV-PWR records this; do not present `tv_wake` as a
   remote power-on for this set.
2. **Honesty fix (commit `f036ea8`).** First run returned BLOCKED for all three
   skills although the sleep key had been sent — BLOCKED ("refusal before
   anything was attempted") was false. Post-send oracle-read failures now
   return `EXECUTED_UNVERIFIED` ("sent; link dropped before read-back"),
   following the `_retro_command` precedent. 3 unit tests added.
3. **Oracle cap fix (commit `20f2c8e`).** `dumpsys power` measures **435 KB**
   on this TV (wake-lock history) and `dumpsys activity activities` 69 KB —
   both exceeded the 64 KB `shell()` default, failing every oracle read while
   the link was up. Oracle reads now pass explicit bounded caps (1 MB / 4 MB,
   measured + headroom). Live regex formats confirmed:
   `mWakefulness=Awake`, `mFocusedApp=ActivityRecord{a7ee65e u0 …/.MainActivity …}`.
   Fakes assert the minimum caps (regression lock).

## What was NOT claimed

- No footage recorded this run (owner will film the finale with Claude).
- `tv_sleep` verified-by-oracle was not achieved on this TV (link drops too
  fast); the effect is proven by owner eyes, the receipt stays UNVERIFIED.
- `tv_wake` as ADB remote power-on: disproven for this TV, documented as such.
