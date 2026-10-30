# Prompt30 gates G01–G22 + final report (30 Oct 2026)

Revision: `feat/p30-cli-release` (merge SHA recorded at PR merge).
Scale: PASS / PARTIAL / BLOCKED / OPEN. BLOCKED/OPEN are stated, never hidden.

## Gates

| Gate | Requirement | Verdict | Evidence |
|---|---|---|---|
| G01 | Source and running release match | PASS | All live runs from this tree (`python -m src.cli`); live :18765 is an older commit, disclosed, never used as proof |
| G02 | Automated tests pass | PASS | 1145 passed 0 failed locally; CI on the PR |
| G03 | Dynamic capability generation on hardware | PASS | 2 Glimmer candidates from the live phone bundle, forge-validated |
| G04 | Native target UI publication, visually proven | BLOCKED | obv4.1 manifests staged (pending-kernel); no on-device rendered UI proof |
| G05 | Physical outcome independently verified | PASS | Montage sha256 recomputed match; capture receipts with bytes + dims |
| G06 | Multiple cross-device tests + evidence | PASS | phone+AVD montage, fabric.status via ask, fault injection |
| G07 | One multi-device orchestration passes | PASS | wf-p30-phone-avd2: 2 captures + montage, all EXECUTED |
| G08 | Duplicate + crash acceptance | PASS | ALREADY_RECORDED, atomic pending claim, crash drill 5/5 (prior) |
| G09 | Local Meta end-to-end proven | PASS | Llama chat + Glimmer synthesis → validated → published → revoked |
| G10 | Paid Meta end-to-end proven | BLOCKED | No key, no spend order; preflight + budget guard proven instead |
| G11 | Cost/consent controls validated | PASS | Unit-tested caps + CLOUD_* codes; live spend untested by design |
| G12 | CLI without GUI dependencies | PASS | No tkinter/Qt; stdlib + src only (tested) |
| G13 | Headless install + operation | PASS | serve smoke on :18799 + systemd/task docs; clean-machine run untested |
| G14 | GUI/CLI parity | PASS | HTTP ≡ in-process parity test + concurrent no-double test |
| G15 | Missing model/API/dependency diagnostics | PASS | doctor statuses + cloud preflight with setup guidance |
| G16 | Clean installation passes | BLOCKED | No independent machine; dev-machine reinstall path only |
| G17 | Independent judge workflow | PARTIAL | Modes A/B/D reproducible; C needs owner hardware |
| G18 | Revocation + cleanup verified | PASS | Capability revoke, deny, no-replay, sessions undo path |
| G19 | Evidence manifest + hashes validate | PASS | Pack VERIFY OK, 24/24 extraction hashes |
| G20 | ZIP complete + reproducible | PASS | Builder + verifier committed; rebuild deterministic modulo timestamps |
| G21 | Docs describe all limitations | PASS | KNOWN_LIMITATIONS + matrix + this file |
| G22 | Submission materials comply | OPEN | Owner-gated: video, portal fields, receipt |

## Final report (§21)

1. Source revision: P30 branch (merge SHA at PR); runtime: same tree.
2. Tests: 1145 passed, 0 failed; CLI adds 40 (router/budget/readiness/cli/parity).
3. Physical devices tested: 1 phone USB + 1 AVD (labeled emulator).
4. Verified device-to-device ops: capture×2 + montage (sha-verified).
5. Meta-generated capabilities: 2 (Glimmer 30B, validated, then revoked).
6. Local Meta: Llama 3.2 3B + Glimmer 30B, digests verified, generations proven.
7. Paid Meta: BLOCKED (no key); $0 spent; guard tested.
8. Comparative benchmark: local rows measured (n=3, tiny); cloud SKIPPED.
9. CLI coverage: all §7.1 commands implemented and live-exercised (except agent start long-run).
10. Headless: Windows proven; Linux via same stdlib path + unit docs.
11. Clean install: dev-machine only (BLOCKED beyond).
12. Orchestration: wf-p30-phone-avd2 + fault run wf-p30-fault, receipts on file.
13. Screenshots/logs: montage PNG + manifest in E:/shots; attempt logs local-only.
14. Security/concurrency: consent-bound approvals, atomic claims, no-replay, revocation.
15. Unresolved: G04 native UI, G10 paid, G16 clean machine, watch/TV/ESP32/Wii/vacuum offline.
16. ZIP: E:/OpenBridge-Jury-Release.zip, sha256 0f1d1836bfc2051c… (see sha256sums.txt).
17. Install: QUICKSTART.md in the pack (Python + pip + CLI).
18. Jury verify: tools/verify-package + `openbridge test jury`.
19. Submission checklist: code/evidence done; video + portal + receipt owner-owned.
20. Verdict: CONDITIONAL GO — EXPLICIT LIMITATIONS (G04, G10, G16, G22).
