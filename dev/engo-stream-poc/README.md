# ENGO Stream POC - video to ActiveLook HUD via imgStream

POC: convert a video stream into a low-resolution 1-bit bitmap and push it
to ENGO/ActiveLook glasses over BLE (the `imgStream 0x44` command).

Scope: **animations only** (sparse content, HUD, subtitles).
Dense fullscreen video stays out of BLE reach (see benchmarks below).

## Demo videos

Recorded emulator output, at the pace the real hardware would sustain (304x256):

- `hybrid_demo.mp4`: pixel graphics + native 0x37 text subtitles (~5.9 fps simulated).
- `stream_sparse304.mp4`: sparse all-pixel content (~4.4 fps simulated).
- `stream_dense304.mp4`: dense all-pixel content (~2.3 fps simulated).

## Run the emulated demo (no glasses needed)

```powershell
pip install -r requirements.txt
python demo_gen.py
python stream.py
```

A window shows in real time what the glasses would display (304x256 canvas),
with simulated fps, latency and tiles sent. Press `q` to quit.

## Useful variants

```powershell
python stream.py --width 152 --height 128 --mode full   # big but slow
python stream.py --width 96 --height 64                 # small but smooth
python stream.py --src 0                                # live webcam
python stream.py --dither fs                            # Floyd-Steinberg (prettier, slower)
python stream.py --headless --record emu_out.mp4 --max-frames 150 --time-scale 0
# Fullscreen + sparse content (OLED):
python sparse_gen.py
python stream.py --src sparse_dark.mp4 --width 288 --height 256 --skip-black --black-cut 0.15
# Light content (auto-invert background to black):
python stream.py --src sparse_light.mp4 --width 288 --height 256 --skip-black --black-cut 0.15 --invert auto
# Max native resolution (304x256):
python stream.py --width 304 --height 256 --dither thresh --skip-black --black-cut 0.15
# Detail/speed tradeoff: --thresh-level 0.5 (silhouettes, fast) vs 0.2 (mid-grays kept, slow)
```

## Phase 2: real glasses

1. `python stream.py --transport ble --ble-discover` lists nearby devices.
2. `python stream.py --transport ble --ble-dump <MAC>` dumps GATT services.
3. Validate the imgStream format (see `protocol.py`, source: patent EP4090057).
4. Stream: `--transport ble --ble-address <MAC> --ble-write-uuid <UUID>`.
5. Or run the guided procedure: `python ble_validate.py` (see VALIDATION.md).

## Benchmarks (simulated time predicts real hardware, 304x256)

| Config | Rate | Latency |
|---|---|---|
| Dense, thresh 0.5 (silhouettes) | 2.3 fps | ~430 ms |
| Dense, thresh 0.2 (detail kept) | 0.6 fps | ~1.6 s |
| Sparse on black (subtitles, HUD) | 4.4 fps | ~230 ms |
| Hybrid pixels + native text | 5.9 fps | ~170 ms |
| Dense + tuned BLE link | 6.1 fps | ~165 ms |

## Files

- `stream.py`: pixel streaming entry point.
- `hybrid_demo.py`: hybrid demo (pixels + native 0x37 text).
- `ble_validate.py`: interactive hardware validation (see VALIDATION.md).
- `convert.py`: downscale + dithering + tiles + skip-black + crop.
- `protocol.py`: GATT UUIDs + clear/text/imgStream frames.
- `transport_emu.py`: glasses emulator + BLE throughput simulation.
- `transport_ble.py`: real BLE transport (bleak).
- `demo_gen.py` / `sparse_gen.py`: test video generators.

## Version francaise

Meme projet, resume en francais : ce POC convertit un flux video en bitmap
1-bit basse resolution et le pousse vers des lunettes ENGO/ActiveLook en BLE
(commande `imgStream 0x44`). Perimetre : **animations uniquement**
(contenus epars, HUD, sous-titres).

Lancement rapide :

```powershell
pip install -r requirements.txt
python demo_gen.py
python stream.py
```

Une fenetre montre en temps reel ce que verraient les lunettes (canvas
304x256). Mesures a 304x256 : contenu epars ~4,4 img/s, hybride pixels +
texte natif ~5,9 img/s, contenu dense ~2,3 img/s. La validation sur
lunettes reelles passe par `python ble_validate.py` (voir la partie
francaise de VALIDATION.md).
