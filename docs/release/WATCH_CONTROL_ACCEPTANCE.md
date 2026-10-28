# Watch control acceptance evidence

Contributor-reported hardware result from [PR #54](https://github.com/toskaman/openbridge/pull/54), source `ffd778f`. Codex reviewed this report without repeating the physical actions. Subsequent upstream changes through `e44e144` only change security documentation. The integration additionally fixes concurrent controller initialization and delayed grant-response ordering, with controlled regression tests.

Claude: **owner-attended hardware acceptance** (Galaxy Watch7 worn by the owner → PC 18780 → Android TV), head **ffd778f**.

| Check | Result |
|---|---|
| Watch paired as relay; owner granted 1 control (TV volume +) | `ctl-c7ef44f141-g1` |
| A tap (not a hold) | Nothing sent ("Hold the button to send") |
| **One deliberate hold** | **1 request (device seq 5, long_press, finger, 411 ms) → 1 invocation (inv-1919…) → 1 receipt tx-a0155cd8702e5e60 EXECUTED** |
| Second hold while "Sending…" | Refused on the device: no seq 6 exists |
| Independent TV read-back (`dumpsys audio`, active output) | 24 → **25** (+1) |
| Revocation from the PC | 200; the control card **disappeared** from the watch (owner confirmed) |

**Earlier run on the same day, previous build:** the owner held 4 times because the outcome was off-screen. That gave 4 requests (seq 1-4, each its own long_press and finger touch) → 4 executions → TV 20 → 24. That is 1:1 as well, and no request appeared without a touch. This is why the button now shows "Sending…" and is disabled while one press is in flight.

**On the original 2 taps → 16 executions:** the defect has not reappeared under the evidence chain, and with the current build a tap cannot send. The 28 Oct morning run had no seq/gesture data, so its exact cause stays **unproven**. My best supported reading is touch input on an unworn watch, because every later request carries a real touch DOWN. That is a hypothesis, not a proof.

**Unit-tested only, not shown on hardware:** duplicate delivery (same request_id → no second action) and expiry (±30 s).

Ready for Codex re-review.


Acceptance is limited to the revised hold-only interaction and reported run. The original repeated-action cause remains unproven; no claim of root-cause closure is made. Revocation prevents new dispatch admissions; an already-admitted operation may finish. No controls are granted automatically.
