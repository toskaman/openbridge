# RetroArch loopback proof — 2026-10-30

RetroArch 1.21.0 Win64 (portable, E:), launched with `network_cmd_enable=true`
on 127.0.0.1:55355. Driven through the REAL stack: Router skill_routes ->
arm -> invoke -> Executor -> RetroArch adapter -> loopback UDP. No ROM, BIOS
or game content was used, loaded or distributed (menu state only).

Observed protocol truth (raw socket, then adapter):
- `VERSION` -> `1.21.0` (reply).
- `GET_STATUS` -> `GET_STATUS CONTENTLESS` (reply; no content loaded).
- `PAUSE_TOGGLE`, `VOLUME_UP`, `VOLUME_DOWN`, `MUTE` -> NO REPLY
  (fire-and-forget in menu state; delivery accepted, effect unverifiable
  without loaded content).

Receipts through the stack:
- VERSION -> EXECUTED, verified=true, reply `1.21.0`.
- GET_STATUS -> EXECUTED, verified=true, reply `GET_STATUS CONTENTLESS`.
- VOLUME_UP -> EXECUTED_UNVERIFIED, verified=false, `SENT` (honest
  delivery-only; workflows cap such steps at UNVERIFIED -> partial).

Policy: QUIT is excluded from the allowlist (killing the user's emulator
session is not a dashboard action). MUTE is excluded (unverifiable, unneeded).
Only 127.0.0.1 is ever contacted. Process quit after the proof.
