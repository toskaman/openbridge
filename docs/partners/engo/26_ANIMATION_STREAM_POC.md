# 26 - Animation stream POC (BLE pixels + native text)

> Status: emulator only. Not validated on physical glasses.
> Companion code: `dev/engo-stream-poc/` (branch `feat/engo-stream-poc`).
> Standalone mirror: https://github.com/toskaman/engo-stream-poc

## What it is

A proof of concept that pushes low-resolution 1-bit animations to ENGO /
ActiveLook glasses over BLE, using the `imgStream (0x44)` command for pixels
and the native `0x37` command for text. Scope is **animations only**
(sparse content, HUD elements, subtitles): dense fullscreen video stays out
of BLE reach (see measurements).

## How it works

- Downscale + dithering (Bayer / threshold / Floyd-Steinberg) to 1-bit.
- 32px tiles with delta updates, OLED skip-black, dark-background inversion,
  optional content-bbox crop.
- Hybrid mode: graphics as pixels, subtitles as native text (about 50 bytes
  per line instead of 10 tiles).
- 304x256 emulator with BLE throughput simulation (bytes/s budget, MTU
  chunking, per-command firmware overhead) and recording of the glasses view.

## Measured results (simulated time, 304x256)

| Config | Rate | Latency |
|---|---|---|
| Dense, thresh 0.5 (silhouettes) | 2.3 fps | ~430 ms |
| Dense, thresh 0.2 (detail kept) | 0.6 fps | ~1.6 s |
| Sparse on black (subtitles, HUD) | 4.4 fps | ~230 ms |
| Hybrid pixels + native text | 5.9 fps | ~170 ms |
| Dense + tuned BLE link (80 KB/s) | 6.1 fps | ~165 ms |

Evidence videos (emulator output at simulated pace) are committed next to
the code: `hybrid_demo.mp4`, `stream_sparse304.mp4`, `stream_dense304.mp4`.

## Protocol notes (to confirm on hardware)

GATT service `0783B03E-...-CB7`, write on `...CBA`, notify on `...CB8`,
`0xFF...0xAA` framing, known-good `CLEAR` and `0x37` demo frames replayed
from the official API. The `imgStream` wire format used here (patent body +
`FF..AA` framing) is candidate A and needs hardware confirmation, as do the
5 text parameter bytes. See `protocol.py` and `VALIDATION.md` in the folder.

## Run it

```powershell
cd dev/engo-stream-poc
pip install -r requirements.txt
python demo_gen.py
python stream.py            # pixel streaming, emulated glasses window
python hybrid_demo.py       # hybrid pixels + native text demo
python ble_validate.py      # guided hardware validation (needs glasses)
```

## Open points for ENGO

1. Confirm the `imgStream` wire format (candidate A) or provide the exact one.
2. Confirm the 5 text parameter bytes (rotation / font / size / color?).
3. Confirm the per-command processing budget (the model assumes ~30 ms).
4. Confirm whether a native filled-rectangle / zone-clear command exists
   (tile erase is currently modeled as one cheap command).
