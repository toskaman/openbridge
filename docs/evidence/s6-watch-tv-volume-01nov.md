# S6 watch → TV volume over direct LAN (31 Oct 2026 23:10 UTC / 1 Nov 00:10 CET)

Owner press on the Galaxy Watch7 (companion over plain Wi-Fi, no watch adb)
dispatches exactly one `tv_volume_step`, and the TV volume step is read back
over an independent adb channel. Run vehicle: `.xbuild/s6b_watch_tv_direct.py`
(uncommitted session tooling).

## Passing run (R4, 23:10:29 UTC)

- Watch paired over the direct-LAN relay URL (owner-read 6-digit code,
  `relay-39f86439fbae`, aead1 sealed channel). No watch adb exists; the TV
  stays on adb for measurement only.
- `tv` dashboard installed: Volume +, Volume −, YouTube — rendered on the
  watch screen (owner-confirmed).
- Owner pressed Volume + on the watch: exactly one history event,
  `EXECUTED`, `tx-5b326915aef0f777`.
- TV `STREAM_MUSIC` read back 23 → 24 via `adb dumpsys audio` snapshots taken
  before the press window and after the dispatch. The TV-side volume-event log
  shows the matching `ADJUST_RAISE` pair at 00:10:29 local, the only such
  event in hours.
- Revoke via `set_controls([])`: the controls vanished from the watch
  (owner-confirmed, nothing left to press), so the scripted post-revoke
  re-press was replaced by denial-by-absence.

## Independent repeat (R1, 23:01:45 UTC)

The same chain ran end to end one round earlier with a different pairing code:
22 → 23 on `STREAM_MUSIC`, exactly one `EXECUTED` (`tx-6ca2ae98472c77f5`),
matching `ADJUST_RAISE` at 00:01:45 local. R1 only "failed" on a harness bug
(see below); the physical effect was complete and archived
(`demo-s6b-r1-audio-*.txt`, `demo-s6b-r1-history.json`).

## Two harness bugs found and fixed during the run

1. **Baseline eaten by fast dispatch.** The first vehicle re-read the volume
   baseline when the press was *detected*. The in-process dispatch lands
   inside the 2 s poll granularity, so the "baseline" already contained +1
   and the check waited for a second +1 that never came. Fix: baseline from
   the pre-window snapshot; the press-time snapshot is kept as auxiliary.
2. **Rediscovery without reinstall voids the grant.** A periodic
   `ensure_discovery` inside the press wait (meant to refresh the ~60 s route
   lease) made the next press `BLOCKED: no route`; a press past the lease
   without any refresh is `BLOCKED: lease stale` (R2). Fix: 55 s press
   windows per install; rediscovery and reinstall move together, only
   between empty windows, never while a press may be in flight. (A reinstall
   wipes a just-queued press on the watch, so it must not run mid-window.)

## Limitations

- No watch screenshots: the watch exposes no adb in this setup (Wi-Fi relay
  only), so on-watch rendering is owner-confirmed, not screenshotted.
- Post-revoke re-press not exercised as a denied event: after revoke no
  controls remain on the watch, which satisfies the intent (no control after
  revoke) by absence.
- Single-passing-round claim (n=1) plus one independent physical repeat (R1);
  R2/R3 transcripts archived as failed-harness rounds, not product failures.
