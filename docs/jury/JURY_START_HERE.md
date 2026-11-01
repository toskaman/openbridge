# OpenBridge — Jury start here

**One AI. Many devices. New possibilities.** Meta AI helps different devices
understand, connect, and control one another — through verified capabilities,
explicit authorization, and observable results.

## In 30 seconds

OpenBridge turns disconnected hardware into one permission-aware system. Ask in
plain language; local Meta models (Llama 3.2, Muse Glimmer) propose controls;
deterministic gates validate them; you approve; the devices act; independent
read-back proves it. The centerpiece: **Meta AI composed a vacuum control
panel that runs on a real Android TV and drives a real robot vacuum**
([S5](../evidence/s5-tv-panel-31oct.md), [S5b](../evidence/s5b-safe-seek-31oct.md)).
Without Meta inference there is no plain-language control, no generated
panels, and no usable device explanations — only static device plumbing.
35 verified evidence rows, honest limits stated inline.

## In 2 minutes: demonstrated on real devices

| # | Demonstration | Proof |
|---|---|---|
| 1 | Glimmer-generated TV panel → vacuum dispatch → revoke → verified deny | [S5](../evidence/s5-tv-panel-31oct.md) · [S5b](../evidence/s5b-safe-seek-31oct.md) |
| 2 | Llama-planned quiet mode: TV vol 22→21 + vacuum dock, read back | [S4](../evidence/s4-quiet-mode-31oct.md) |
| 3 | Phone/TV BLE relays + proven TV-to-phone handover | [handover](../release/COMPLETE_HANDOVER.md) · [row 29](../DEVICE_EVIDENCE.json) |
| 4 | Phone, TV, Watch7 Companions paired; native watch controls | [G04](../evidence/g04-watch-30oct.md) · [matrix](../HARDWARE_TEST_MATRIX.md) |
| 5 | Refusals as first-class outcomes (timeline + receipts) | [report](OVERNIGHT_REPORT_31OCT.md) §B |
| 6 | 2nd PC jobs, Freebox inventory, vacuum reads, legacy VMs, AVD, ESP32-QEMU | [matrix](../HARDWARE_TEST_MATRIX.md) |

Limits up front: S5/S5b presses were ADB-injected (labeled), vacuum motion
never observed; watch→TV volume is verified via an owner press on the
watch (S6) — see [runbook](DEMO_PHYSICAL_RUNBOOK.md) and
[limits](../KNOWN_LIMITATIONS.md).

## In 5 minutes: run it yourself

```sh
git clone https://github.com/toskaman/openbridge.git
cd openbridge
python -m unittest discover -s tests   # 2016 tests, no hardware needed
python -m src.cli judge demo           # offline demo → DEMO_COMPLETE
python -m src.server                   # → http://127.0.0.1:18765
```

No hardware? The offline demo, fixtures, and browser smokes reproduce the safe
subset. With hardware: [QUICKSTART](../QUICKSTART.md). With models:
`dev.start_local_meta` (Llama 3B, CPU) and `dev.start_glimmer` (Glimmer 30B).

## In 10 minutes: technical evidence

- [Claim ↔ evidence matrix](CLAIM_EVIDENCE_MATRIX.md) — every claim, one status, one source
- [Verified capabilities](VERIFIED_CAPABILITIES.md) — scenario-by-scenario verdicts
- [Hardware matrix](../HARDWARE_TEST_MATRIX.md) + [registry](../DEVICE_EVIDENCE.json) — 35 rows
- [Benchmark status](../benchmark/STATUS.md) + [model usage](../MODEL_USAGE_AND_EVALUATION.md)
- [Release evidence](../RELEASE_EVIDENCE.md) · [release status](../RELEASE_STATUS.md)
- [Compliance checklist](COMPLIANCE_CHECKLIST.md) — portal items marked OPEN stay OPEN
- [Final storyboard](DEMO_STORYBOARD_FINAL.md) · [narration](DEMO_NARRATION.md) · [capture checklist](VIDEO_CAPTURE_CHECKLIST.md)

## Evidence table (featured claims)

| Feature | Demo | Hardware / emulator | Meta contribution | Result | Oracle | Limits | Proof | Source |
|---|---|---|---|---|---|---|---|---|
| TV vacuum panel (S5) | Ask → panel → press → revoke | TV 11 + vacuum, REAL | Glimmer 30B panel synthesis | tx-ab731d7b885b5e1a, revoke→deny | OCR render, Tuya re-read | adb press, docked, n=1 | [S5](../evidence/s5-tv-panel-31oct.md) | row 28 |
| Safe seek (S5b) | T2 FIND → beep → poll → revoke | TV 11 + vacuum, REAL | Glimmer T2 panel | tx-4a96f8f626a1adc5 EXECUTED_UNVERIFIED | 15×2 s polls, fault 0 | adb press, beep unproven | [S5b](../evidence/s5b-safe-seek-31oct.md) | row 30 |
| Quiet pair (S4) | Llama plan → TV + vacuum | TV 11 + vacuum, REAL | Llama 3B 2-step plan | vol 22→21, dock acked | adb dumpsys, Tuya read | docked, n=1 | [S4](../evidence/s4-quiet-mode-31oct.md) | row 27 |
| BLE relay + handover | Phone/TV scans, failover | Phone + TV, REAL | Rules + signed channel | dedup + consent-void | second relay scan | one TV, PC has no BT | [handover](../release/COMPLETE_HANDOVER.md) | rows 25, 29 |
| Watch controls | QUICK CONTROLS + long-press | Watch7, REAL | Sealed install, ack loop | ack on screen | on-watch display | press adb-injected | [G04](../evidence/g04-watch-30oct.md) | row 22 |
| Refusal channel | Denied press in timeline | Server + UI | Structured verdicts | TDD 3/3, red render | API + events | shot staged from live UI | [report](OVERNIGHT_REPORT_31OCT.md) | §B |
| Legacy + VMs | Agent exec exit 0 | 7 QEMU guests | None (protocol) | mutual-auth + exec | screenshots, hashes | labeled VMs, deleted after | [legacy](../evidence/vm-legacy-xp-win7-30oct.md) | rows 14–15 |
| ESP32 agent | Boot + CROSS_OK | QEMU-ESP32, EMU | None (protocol) | serial handshake + execs | host agent fwd | no WiFi/TFT/physical | [esp32](../evidence/esp32-idf-qemu-30oct.md) | row 16 |
| Cloud e2e flow | Pair → scan → revoke | Phone 13, REAL | None (signed protocol) | 9/9 PASS, 3 BLE advertisers, revoke→409 | dumpsys + forward list + HMAC | phone ended unpaired, screen kept awake | [cloud_e2e.py](../../scripts/verify/cloud_e2e.py) | row 31 |
| Voice loop | Speak/type → STT → report + TTS | Phone 13, REAL | Llama 3B parse + MMS STT | 6 clips transcribed + spoken, FR order parsed | dumpsys MIC, caption dumps, sha256 | MMS hallucinates on silence, watch mic unproven | [command_drain.py](../../src/runtime/command_drain.py) | row 32 |
| WD7 direct drain | Pair → adb down → drain → caption | TV 11, REAL | None (direct-LAN protocol) | drain with adb down, report captioned | adb devices assert + TV screencap | stray leading char in typed order, n=1 | [caption shot](screens/tv-wd7-direct-drain-caption.png) | row 33 |
| S6 watch→TV volume | Owner press → TV vol step → revoke | Watch7 + TV 11, REAL | None (companion dispatch) | tx-5b326915aef0f777, MUSIC 23→24 | dumpsys audio + TV volume-event log | no watch shots, denial-by-absence, n=1+R1 | [S6](../evidence/s6-watch-tv-volume-01nov.md) | row 34 |
| Watch voice loop | 3 FR orders → STT → signed reports | Watch7, REAL | Local STT + parse | 3/3 transcribed + reported, sleep-timeout tolerant | drain log transcripts + HMAC replies | STT mishears, no watch shots, n=3 | [voice-watch](../evidence/voice-watch-direct-01nov.md) | row 35 |
