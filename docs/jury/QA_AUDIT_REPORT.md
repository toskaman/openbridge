# OpenBridge — QA / audit report (presentation redesign, 31 Oct 2026)

Branch: `feat/jury-presentation-redesign`. Scope: presentation, docs, media,
pack tooling only — no business-logic change except the matrix link renderer
(`dev/device_registry.py`, covered by the registry gate test).

## Hostile review (10 lenses)

| # | Lens | Finding → Action → Verification |
|---|---|---|
| 1 | Impatient nontechnical judge | Old README was 36 KB of tables → rebuilt to ~11 KB with 10-second hero + 30-second explainer → byte count + read-through |
| 2 | Senior Meta AI engineer | Meta role was buried → dedicated "Meta AI" sections with receipts; vision (Meta-driven discovery) labeled future-only → code paths cited (`src/ai/*`, `config/runtime_models.json`) |
| 3 | Robotics/interop engineer | ESP32 "real control points" overclaim → downgraded to VERIFIED EMULATOR everywhere → registry row 16 + matrix |
| 4 | Security reviewer | Plaintext v4, pairing brute-force, foreground-scan scope now stated in README + limits → `KNOWN_LIMITATIONS.md` |
| 5 | Open-source maintainer | 7 broken relative links (6 matrix + 1 report) → fixed at the generator + re-rendered → `--check` green + pack validator |
| 6 | Product designer | Misleading GIF frame + stale shots → GIF rebuilt from 6 real stills (320 KB), PII shots excluded, manifest written → visual inspection of frame 1 |
| 7 | Technical journalist | Count conflicts (30/28/26 rows, 1245/1203/1150/864 tests) → single truth: 30 rows, 1245 tests; history preserved in git + snapshot → grep audit |
| 8 | Reproducibility tester | QUICKSTART said Windows/Linux only, no tool links → macOS qualified + adb/Ollama URLs → doc diff |
| 9 | Compliance reviewer | Scoring % and bonus table stated as fact → removed; portal items stay OPEN → `COMPLIANCE_CHECKLIST.md` unchanged, README links it |
| 10 | Skeptic | "Every frame real, nothing staged" + V4 REAL-vs-SIMULATED conflicts → claims qualified, matrix reconciled with notes → claim matrix diff |

## Mandatory verification

- README renders (GitHub markdown, no HTML): yes; 6 images + 2 badges, all targets present.
- Internal links: repo sweep clean (7 fixed); jury ZIP validator: 290 files, 0 missing, 0 broken.
- Badges truthful: MIT (LICENSE exists) + live verify.yml badge (reflects CI, whatever it is).
- No staged-as-real media: GIF frames are committed stills; emulator shots labeled; PII shots excluded.
- No universal-Undo / exactly-once-physical / encrypted-transport claims: scoped to journaled settings; v4 plaintext disclosed.
- No invented benchmarks: unfavorable arms published (ablation, Forge 0%, EVAL 1.4%).
- No hidden contributions: CONTRIBUTIONS/THIRD_PARTY untouched and linked.
- No secrets: pack is docs + code proof + public shots; vault/keys never included.
- App behavior unchanged: full suite green (see below); only renderer + docs + new dev tools.
- Assets reasonable: README images ~1.7 MB total; ZIP 16.4 MB (incl. 10 MB mp4, E:-only source).

## Test outcomes (this branch, 31 Oct)

- `python -m unittest discover -s tests`: **1245 tests OK** (110 s).
- `python -m dev.device_registry --check`: registry OK (30 rows), matrix in sync.
- `compileall` on new/changed dev scripts: clean.
- `python dev/build_jury_presentation.py`: 290 files, ZIP sha256
  `fbd6bd8ae10563778dbc6f116d7dfdb217411c3ce4ac9bb8759eb592fefd7cfd`.
- Not executed: browser smokes locally (CI covers), clean-room rebuild,
  Android e2e (CI failing, disclosed), macOS hand-run.

## Outstanding limitations (owner-gated or external)

1. Final 180 s video BLOCKED without new explicit owner authorization.
2. S5 manual-press + vacuum-motion and S6 watch-chain runs need owner + awake hardware.
3. Portal verification pending: deadline, video max, public-repo rule, bonus criteria, scoring.
4. 4 E: PNGs corrupt (re-capture required); per-OS tour webms + forge mp4s missing/unproduced.
5. Android `e2e` CI job failing (builds green); live :18765 revision unreconciled (reload owner-gated).
6. 2-tap→16-exec root cause, full-control re-pair review, Doze soak still open.

## Backups

- `D:\DevBackups\OpenBridge\OpenBridge_2026-10-31_16-46-22.zip` (12 files)
- `D:\DevBackups\OpenBridge\OpenBridge_2026-10-31_16-48-28.zip` (history + GIF)
- Pack: `E:\jury-pack\OpenBridge-Jury-Presentation.zip` + `SHA256SUMS.txt` in-stage.
