# OpenBridge — Video capture checklist (recording day)

Checklist form of [DEMO_STORYBOARD_FINAL.md](DEMO_STORYBOARD_FINAL.md) +
[DEMO_PHYSICAL_RUNBOOK.md](DEMO_PHYSICAL_RUNBOOK.md). Nothing here authorizes
recording by itself — owner media authorization first, always.

## Before cameras roll

- [ ] Owner present, awake, consenting; media authorization explicit (granted/declined logged).
- [ ] Vacuum safe area agreed; nothing fragile in range; pets/children away.
- [ ] Devices awake: TV on, vacuum undocked (S5 full) or docked (S5b fallback), Watch7 awake (not dozing).
- [ ] Companion 0.12.0+ on TV + watch; PC server on the recorded branch/revision.
- [ ] Preflight GO: `python scripts/verify/demo_preflight.py --timeout 30` (exit 0 = GO, 2 = partial, 3 = NO-GO).
- [ ] Phone/watch notifications silenced; personal apps closed; screen lock off during takes.

## Per-scene specs

| Scene | Capture | Spec |
|---|---|---|
| Problem stills | existing redacted PNGs | 1440px min, no private pixels |
| Live discovery | screen capture | 1080p, UI readable at 50% scale |
| S5 request → inference | screen capture | show request text, model id + digest, VALID verdict |
| S5 TV panel + press | camera + adb screenshot | hands visible, no ADB overlay; timestamped |
| S5 vacuum effect | camera | timestamped; motion OR honest DISPATCH ONLY label |
| S6 watch press → effect | camera + screen capture | press visible, single receipt, read-back shown |
| Refusal timeline | live UI (preferred) or `docs/jury/screens/refusal_channel.png` (committed; seeded-UI shot) | red refusal row legible |
| Scorecard still | eval report export | numbers match committed evidence |
| Close | screen capture | finished app + repo URL, 5 s hold |

## Provenance + manifest (every take)

- [ ] Lower-third overlay on beats 2–6: model id + digest, commit SHA, receipt id.
- [ ] Log each file: `shots/demo-s5-…` / `demo-s6-…` (staging folder; author PC uses `E:/shots/`) + take time + revision in the §22 report table.

## Privacy / redaction (before anything leaves the PC)

- [ ] No LAN IPs, MACs, serials, pairing codes (live), API keys, account names.
- [ ] Household device names redacted (`?redact`); no notification content.
- [ ] Expired single-use codes only, if any code is shown at all.

## Backup footage (in order)

1. S5 full (manual press + observed motion) — best.
2. S5b dispatch-only (T2 FIND + receipt + 15-poll oracle + revoke) — ready-made.
3. Refusal/safety beat + live discovery — always available.
4. Scorecard + close — narration-covered stills.

## Cut rules

- Any beat without its listed proof is DROPPED; neighbors keep timing.
- Never a mock-up, never simulated motion presented as physical.
- Final pass: duration 175–180 s, codec/dimensions, redaction sweep, frame inspection.
