# OpenBridge offline demo (no hardware needed)

The offline demo proves the install works end to end without any device,
model, or network access. It is the same check the clean-room lab runs on
every platform.

## Run it

```sh
python -m src.cli judge demo
```

Expected output ends with `DEMO_COMPLETE` plus readiness counts
(`Ready for the offline demo: n/n required checks passed`). If any required
check fails you get `DEMO_BLOCKED` with the failing checks named — fix those
and re-run. Nothing is skipped silently.

## What it exercises

- CLI readiness split (required vs optional checks)
- Fixture-backed device flows (no live hardware touched)
- Diagnostics that report missing pieces explicitly instead of failing silently
- Clean shutdown with no orphan processes

## Companion checks

```sh
python -m src.cli test smoke   # fast offline smoke
python -m src.cli test jury    # jury test path (from the app distribution root)
python -m unittest discover -s tests  # full controlled suite, no hardware needed
```

## Notes for jurors

- The demo is labeled as a demo everywhere it appears; it reproduces the safe
  subset only. Real-device behavior is covered separately by the 37 verified
  evidence rows ([DEVICE_EVIDENCE.json](DEVICE_EVIDENCE.json),
  [HARDWARE_TEST_MATRIX.md](HARDWARE_TEST_MATRIX.md)).
- Scripted UI tours (`tour-*.webm` in the media package) show the same flows
  in a browser; they are labeled EMULATOR and are not hardware claims.
