# Long soak, learning and links on a real Home Assistant (22 November 2026)

Everything below was run through the OpenBridge CLI against a real Home Assistant 2026.11 container with its
demo integration (28 controllable devices: lights, switches, fans, media players, climate, vacuums, locks).

## `openbridge ha soak --cycles 20 --seed 11 --consent ALLOW`

| Metric | Value |
|---|---|
| Actions sent through the gate | 1 480 |
| Verified by independent read-back | 92.8 % |
| Undo restored the exact previous state | 84.3 % |
| Duration | 45 min |
| Proven actions learned | 87 on 28 devices |

Not verified (106, all acknowledged after a read-back): 57 media player, 29 vacuum, 20 lock. These are
demo-integration quirks (state changes slower than the 6 s read-back window, or no state change at all);
they are reported as failed, never as done.

### Bugs found by the soak and fixed

1. **Unsupported actions sent to devices (HTTP 400).** Actions are now filtered by Home Assistant's
   `supported_features` bits for media players, climate and vacuums.
2. **A failed Undo locked the device forever.** Undo is now one-shot: it reports whether the state came back
   exactly, then clears.
3. **Recovery backlog filling during long runs.** After 64 unverified outcomes the executor rightly refuses more
   changes; the soak now reads the device back and acknowledges each one, as an owner would.
4. **Device keys changed on every run**, so learning and links did not survive a restart (155 duplicate profiles).
   Keys are now derived from the pseudonymized strong identifiers: 28 devices, 28 profiles.

First 10-cycle run before the fixes: 18.5 % verified. After: 92.8 % over 20 cycles.

## `openbridge create suggest`

10 suggestions, all high confidence, e.g. *Cinema mode: when `media_player.living_room` is playing, dim
`light.ceiling_lights` to 20 %*.

## Links, end to end

```
openbridge links add --when media_player.living_room --state playing --then light.ceiling_lights \
                     --action set_brightness --value 20 --title "Cinema mode"
openbridge links approve link-21af5655 --consent ALLOW
openbridge links watch --seconds 35      # meanwhile: openbridge ha do media_player.living_room play
```

Result: 17 ticks, the link fired exactly once on the paused → playing edge, `VERIFIED` by read-back.

## Test suite

`pytest tests/fabric tests/runtime tests/unit`: 2 020 passed, 642 subtests.
