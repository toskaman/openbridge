# Overnight run, 23-24 November 2026: long tests, benchmarks, hardening

Goal: finish the evening batch, then run long tests and benchmarks and make
improvements until 10:00. All commands ran from `OpenBridge/` on the owner's PC
(CPython 3.14.4, Windows). Raw logs stayed in TEMP (network share paths below
are the workspace, not evidence).

## Full suites (unittest discover, the CI canon)

| Run | Tests | Result |
|---|---|---|
| Evening batch baseline | 2710 | OK (2 skips: CPace-draft + Matter-TLV vector loaders) |
| Night repeat 1 | 2713 | OK (journal bound + 2 fuzz regressions added) |
| Night repeat 2 | 2714 | OK (+ BLE cap-tolerance test) |
| Night final | 2721 | OK (+ 7 MQTT CLI tests) |

Zero flakes across 4 full runs (~28 min of suite time).

## Extended fuzz (TEMP/night_fuzz.py, not committed)

- 40 seeds × 384 cases × 2 backends (libsodium C + forced pure-Python): skill/pack/voice
  parsers, TLV + MQTT codec round-trips — then 40 000 sealed frames per backend.
- 100-seed run: 38 400 cases + 40 000 frames, clean.
- Found and fixed (each with a committed regression test):
  1. `partner_voice.validate` raised bare `TypeError` on non-list `phrases` (would escape
     `load_dir`, which only catches `OSError`/`ValueError`) → now `ProfileError`.
  2. `skill_library.import_bundle` raised `TypeError` on non-ASCII/non-string signatures
     (hmac.compare_digest) → now `trusted: False`, import proceeds unapproved.

## Endurance (dev/f90_endurance.py)

| Run | Ops | Errors | Latency p50/p95 | Memory | Journal | Notes |
|---|---|---|---|---|---|---|
| 2h seed 41 | 83 765 | 7.6% (515 RelayError injected + 5872 OverflowError) | 148/503 ms | +73 MB | 5.6 MB | OverflowError = registry cap (2000) aborting ingest batches |
| 1h seed 123 | 44 823 | 0.57% (257 RelayError injected, 0 OverflowError) | 32/56 ms | +20 MB | 79 KB | After fixes: ingest cap-tolerance + bounded journal |
| 2h seed 777 | 89 637 | 0.57% (515 RelayError injected, 0 OverflowError), capped=5872 | 32/61 ms | +25 MB | 79 KB | Confirms: same 5872 now counted skips, latencies /5 |

All three: 0 shed, graceful shutdown, no hung workers, threads and sockets back to start.

## MQTT soak (TEMP/night_mqtt_soak.py, loopback FakeBroker)

30 min: 1511 cycles, 2195 verified actions (+undos), 0 unverified, 0 blocked, across
Tasmota on/off/brightness, Shelly on/off/watts and Zigbee2MQTT on/off/brightness.

## Benchmarks (scripts/verify/bench.py, ceilings + baseline compare)

9 measures (3 added overnight: TLV, MQTT codec, sealed frames), all within ceiling,
`--compare` clean against the saved baseline. Sealed 1 MiB: ~instant (C backend),
1.8 s pure Python.

## Browser smokes (Playwright, loopback Chromium)

All 9 smokes re-run overnight and green (ui_v2, command_center, route_inspector,
control_consent, agent_portal, offline, guided, fabric, integrate_page).

## Code changes made overnight (uncommitted, for owner review)

1. `src/ai/partner_voice.py`: typed refusal for non-list `phrases` (+ test).
2. `src/runtime/skill_library.py`: foreign signatures untrusted instead of crashing (+ test).
3. `src/fabric/session.py`: journal keeps every OPEN change + newest 200 closed
   (`MAX_KEPT_CLOSED`), under the existing cross-process lock (+ test).
4. `src/fabric/discovery.py`: `ingest_mdns/ble/ssdp` return `{ingested, capped}` and skip
   capped devices instead of aborting the batch (+ test).
5. `src/fabric/home_assistant_ingest.py`, `freebox_ingest.py`, `mqtt_ingest.py`: same
   per-device cap tolerance, `capped` added to their reports.
6. `dev/f90_endurance.py`: standalone runs note the legacy opt-out; report gains `capped`.
7. `openbridge mqtt discover|do` CLI (+ 7 tests, `docs/MQTT.md` updated).
8. `scripts/verify/bench.py`: TLV, MQTT codec and sealed-frame measures.
9. `docs/`: CHANGELOG night entry, KNOWN_LIMITATIONS (MQTT status), this file.

## Open threads for the owner

- OverflowError taxonomy: with cap-tolerance, no builtin escapes observed anymore; the
  `except OverflowError` handlers document the two registry caps explicitly.
- Journal rewrite cost: the journal file is still fully rewritten per op (small now
  that it is bounded); append-only would be the next step if CPU matters.
- Hardware still pending everywhere it was: real HA soak, ENGO glasses, ESPHome/OpenWrt/
  FRITZ!Box bench runs, real-broker MQTT, model retrain + voice battery.
