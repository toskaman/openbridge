# OpenBridge — QA / audit report (presentation redesign, 31 Oct 2026)

Branch: `feat/jury-presentation-redesign`. Scope of my commits (`8c00a1d`
+ follow-ups): presentation, docs, media, pack tooling only — no app
behavior change except the matrix link renderer (`dev/device_registry.py`,
covered by the registry gate test). The branch concurrently carries
another author's companion commits (`ffba663`, `9664eca`, `ec46fe5`,
`bfe3dd2`: consent-gate UX, relay unpair/singleton, launcher icons), which
DO change app behavior and ship without Android `e2e` cover (job failing,
disclosed) — out of my scope, listed here for the merger.

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
- No staged-as-real media: GIF frames are committed stills; emulator shots labeled; PII shots excluded; the one seeded-UI shot (`refusal_channel.png`, demo server, real refusal payload) is labeled at every display point.
- No universal-Undo / exactly-once-physical / encrypted-transport claims: scoped to journaled settings; v4 plaintext disclosed.
- No invented benchmarks: unfavorable arms published (ablation, Forge 0%, EVAL 1.4%).
- No hidden contributions: CONTRIBUTIONS/THIRD_PARTY untouched and linked.
- No secrets: pack is docs + code proof + public shots; vault/keys never included.
- App behavior unchanged by my commits: full suite green (see below); only renderer + docs + new dev tools. Companion behavior changes on this branch belong to the concurrent commits listed above.
- Assets reasonable: README images ~1.7 MB total; ZIP 16.4 MB (incl. 10 MB mp4, E:-only source).

## Test outcomes (this branch, 31 Oct)

- `python -m unittest discover -s tests`: **1245 tests OK** (110 s).
- `python -m dev.device_registry --check`: registry OK (30 rows), matrix in sync.
- `compileall` on new/changed dev scripts: clean.
- `python dev/build_jury_presentation.py`: 292 files, ZIP sha256
  `bce5686cc565dde4e31ceb603fab90729e6a8b0857ac7ce4e431f09cd69e5f69`
  (`--without-extras` portable mode also verified: 290 files, exit 0).
- Showcase page (`docs/showcase/index.html`): Playwright smoke on file:// —
  10/10 images loaded, 0 console/page/network errors, desktop 1440 + mobile
  390 verified by screenshot; in-pack HTML links validated by the builder.
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
