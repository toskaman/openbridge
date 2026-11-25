# Hardware validation - ENGO / ActiveLook glasses

This guide validates the wire protocol on real glasses, step by step.
Without this validation everything stays simulated: it is THE required
step before going live.

## Prerequisites

- Glasses charged and powered on (near the PC, < 3 m).
- **Official ENGO / ActiveLook app closed or disconnected**: a single
  BLE connection at a time, otherwise the script cannot connect.
- PC Bluetooth on. `pip install -r requirements.txt` done.

## Procedure (5 minutes)

```powershell
python ble_validate.py
```

The script scans, connects to the `A.LooK*` glasses, then runs 7 steps:
CLEAR, replay of the official text demo, texts at various positions
(X/Y mapping), then a 32x32 checkerboard via imgStream. At each step,
wear the glasses and answer the question (y/n + what you see).

Everything is logged to `validation_log.txt` (frames + observations +
glasses notifications): send back that file plus your answers.

## Reading the results

| Observation | Conclusion |
|---|---|
| Steps 1-2 OK | Connection + FF..AA framing valid |
| Steps 3-6 placed correctly | Text command 0x37 valid, X/Y confirmed |
| Step 7 checkerboard visible | imgStream valid, pixel streaming is open |
| Step 7 blank, but 1-6 OK | Native text OK, image format needs work (candidate B) |
| Nothing from step 1 | Connection refused / other protocol revision -> GATT dump |

## Fallback: GATT dump

```powershell
python stream.py --transport ble --ble-discover
python stream.py --transport ble --ble-dump <MAC>
```

Compare the UUIDs with `protocol.py`. If they differ (ENGO 3 =
a newer revision?), send the dump so it can be adapted.

## After validation

- Text OK -> wire the live translation chain (Whisper -> native text).
- Image OK -> calibrate `--throughput` / `--cmd-ms` on real measurements,
  then live hybrid streaming.

## Version francaise

Meme procedure en francais : charge et allume les lunettes, ferme l'app
officielle (une seule connexion BLE a la fois), puis lance
`python ble_validate.py`. Le script enchaine 7 etapes (effacement, demo
texte officielle, textes positionnes, damier imgStream) : mets les
lunettes et reponds a chaque question (o/n + ce que tu vois). Tout est
journalise dans `validation_log.txt`. Si rien ne s'affiche des l'etape
1, fais un dump GATT (`--ble-discover` / `--ble-dump`) et compare les
UUIDs avec `protocol.py`.
