# Exact Undo and slow-device read-back on a real Home Assistant (23 November 2026)

Same setup as [the 22 November soak](device-learning-soak-22nov.md): a real Home Assistant 2026.11 container with its
demo integration, driven through the OpenBridge CLI. Demo devices only; physical devices through Home Assistant are
not tested yet (procedure: [Test with your real devices](../HOME_ASSISTANT.md#test-with-your-real-devices)).

## What changed in the bridge

1. **Exact Undo restores what a person sees.** Lights: on/off, brightness and colour (temperature or hue and
   saturation), not just "on". Media players: playing or paused, not just "on". An Undo that brings a light back
   at the wrong brightness or colour is reported as *not exact*.
2. **Read-back windows per action.** 20 s to start a robot vacuum, 30 s to send it home, 20 s for a lock, 60 s for
   blinds, 10 to 15 s for media players, 6 s otherwise; stretched to 2 x the learned 95th-percentile latency + 1 s
   for devices OpenBridge has learned are slower (cap 90 s).
3. **Second read-back** (`confirm`) before the soak gives up on an action; reported as `verified_late`.
4. **`ha soak --entity ...`** limits the soak to listed devices, for real homes.

## `openbridge ha soak --cycles 3 --seed 11 --consent ALLOW`

| Metric | 22 Nov (20 cycles) | 23 Nov (3 cycles) |
|---|---|---|
| Actions | 1 480 | 222 |
| Verified by read-back | 92.8 % | **95.9 %** |
| Undo restored the exact previous state | 84.3 % | **100 %** (153 / 153) |
| Duration | 45 min | 5 min |

Not verified (9), all genuine: 6 `vacuum pause` (the demo vacuum ignores pause while docked) and 3 `lock`
(the demo includes a lock that jams on purpose). They are reported as failed, never as done. `verified_late`: 0.

Caveat: 3 cycles against 20; the Undo change is structural (what is restored and what is compared), so the rate
should hold on longer runs, but a 20-cycle run is the like-for-like comparison.

## Tests

`tests/fabric/test_home_assistant.py`: 18 tests (7 new: light colour-temperature and hue Undo, an Undo that loses
the colour is not exact, media player resumes playback, read-back windows, slow device verified inside its window,
second read-back). `tests/fabric`: 673 passed.
