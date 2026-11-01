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
  shows the matching `ADJUST_RAISE` pair at 00:10:29 local. The only such
  events since 20:32 are the R1 pair (00:01:45) and the R4 pair (00:10:29),
  both experiment presses; no stray RAISE/LOWER between ready and after
  snapshots. (Correction: an earlier revision said "the only such event in
  hours", which is false for R4 as written — R1's own pair sits 9 min
  earlier. The "hours" phrasing holds for R1, whose prior RAISE was ~3.5 h
  before.)
- Revoke via `set_controls([])`: the controls vanished from the watch
  (owner-confirmed, nothing left to press), so the scripted post-revoke
  re-press was replaced by denial-by-absence. Machine receipt:
  `demo-s6b-verdict.json` step `revoked` ok:true (0 controls for the
  relay). The same verdict file carries overall status FAIL because the
  `re-press denied` step found an empty history (`new2=[]`, nothing left
  to press) — disclosed here; the "Passing run" header refers to the
  press/dispatch/read-back chain, and the denial-by-absence was
  human-accepted (see Limitations). Note: the vehicle re-press check
  reads `h.get('outcome')` (`.xbuild/s6b_watch_tv_direct.py`) while the
  history schema carries `state` — an apparent outcome-vs-state mismatch
  that would make that step unpassable even for a recorded BLOCKED press.
  Verify before reusing the vehicle.

## Independent repeat (R1, 23:01:45 UTC)

The same chain ran end to end one round earlier with a different pairing code:
22 → 23 on `STREAM_MUSIC`, exactly one `EXECUTED` (`tx-6ca2ae98472c77f5`),
matching `ADJUST_RAISE` at 00:01:45 local. R1 only "failed" on a harness bug
(see below); the physical effect was complete and archived
(`E:\shots\demo-s6b-r1-audio-*.txt`, `E:\shots\demo-s6b-r1-history.json`;
R4 counterparts `E:\shots\demo-s6b-r4-audio-*.txt`,
`E:\shots\demo-s6b-r4-history.json`, `E:\shots\demo-s6b-verdict.json`;
failed-harness rounds `E:\shots\demo-s6b-r2-history.json`,
`E:\shots\demo-s6b-r2-verdict.json`, `E:\shots\demo-s6b-r3-history.json`,
`E:\shots\demo-s6b-r3-verdict.json`).

## Two harness bugs found and fixed during the run

1. **Baseline eaten by fast dispatch.** The first vehicle re-read the volume
   baseline when the press was *detected*. The in-process dispatch lands
   inside the 2 s poll granularity, so the "baseline" already contained +1
   and the check waited for a second +1 that never came. Fix: baseline from
   the pre-window snapshot; the press-time snapshot is kept as auxiliary.
2. **Rediscovery without reinstall voids the grant.** A periodic
   `ensure_discovery` inside the press wait (meant to refresh the ~60 s route
   lease) made the next press `BLOCKED: no route` (R3); a press past the lease
   without any refresh is `BLOCKED: lease stale` (R2). Fix: 55 s press
   windows per install; rediscovery and reinstall move together, only
   between empty windows, never while a press may be in flight. (A reinstall
   wipes a just-queued press on the watch, so it must not run mid-window.)

## Limitations

- No watch screenshots: the watch exposes no adb in this setup (Wi-Fi relay
  only), so on-watch rendering is owner-confirmed, not screenshotted.
- Post-revoke re-press not exercised as a denied event: after revoke no
  controls remain on the watch, which satisfies the intent (no control after
  revoke) by absence. Vehicle verdict status FAIL on `re-press denied`
  (`new2=[]`); human-accepted as denial-by-absence. The vehicle check also
  reads history `outcome` where the schema carries `state` (see above) —
  verify before reuse.
- Single-passing-round claim (n=1) plus one independent physical repeat (R1);
  R2/R3 transcripts archived as failed-harness rounds, not product failures
  (`E:\shots\demo-s6b-r2-history.json`: `BLOCKED` "Volume +: Unavailable:
  lease stale"; `E:\shots\demo-s6b-r3-history.json`: `BLOCKED` "Volume +:
  Unavailable: no route"; both verdicts status FAIL on `exactly one
  dispatch`, "1 events (['BLOCKED'])", as narrated).

## Redacted oracle excerpts (short quotes from `E:\shots`; values only, no private bytes)

`adb dumpsys audio` MUSIC `streamVolume` (line 106 of each snapshot):

```text
r1 ready: streamVolume:22   r1 press: streamVolume:23   r1 after: streamVolume:23
r4 ready: streamVolume:23   r4 press: streamVolume:24   r4 after: streamVolume:24
```

TV volume-event log tail (`demo-s6b-r4-audio-after.txt`, full post-20:00 list —
no confounds; attribution by timestamp is clean):

```text
10-31 20:16:39 ADJUST_RAISE x2 (pre-experiment)
10-31 20:32:07 ADJUST_RAISE x2 (pre-experiment)
10-31 21:21:59 ADJUST_MUTE / 21:22:08 ADJUST_UNMUTE (index-neutral)
11-01 00:01:45 ADJUST_RAISE x2 (R1 experiment press)
11-01 00:10:29 ADJUST_RAISE x2 (R4 experiment press)
```

`demo-s6b-verdict.json` steps: discover tv ok, watch paired direct-lan ok
(relay-39f86439fbae), tv controls on watch ok, exactly one dispatch ok ("1
events (['EXECUTED'])"), tv volume +1 read-back ok (MUSIC 23 -> 24),
revoked ok, re-press denied FAIL ("[]"); overall status FAIL (see above).
