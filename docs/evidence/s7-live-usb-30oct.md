# §7 live USB proof — 2026-10-30

Real phone (rugged model, Android 13) over owner-authorized USB ADB, driven
through the REAL stack: Router skill_routes -> arm -> invoke -> Executor ->
AndroidAdapter -> adb. Tmp journal only (live server untouched).

## A — screen_capture
- Route READY (USB link, control grant). Receipt EXECUTED, verified=true.
- PNG 1080x2388, 15503 bytes,
  sha256 7b01218438a5f71c1d9ec464a809926eae5e8d8ea1ea2adc78fab4d72c72ea22.
- Stored server-side under cap-b7711ace49cc783c. A copy was saved to the
  owner's local shots folder (private screen content, NOT committed).

## B — capture_send (same capture pushed back, then deleted)
- Receipt EXECUTED, verified=true. Remote /sdcard/OpenBridge/cap-b7711ace49cc783c.png.
- On-device sha256sum EQUALS the server sha256 (hash-identical round trip).
- Cleanup: `rm` the pushed file, then `adb shell ls /sdcard/OpenBridge/` exits 0
  with an EMPTY listing — no trace left on the device.

## C — capture_montage (server-side, stdlib only)
- Second live capture + row montage of the two frames: EXECUTED,
  2160x2388 PNG, sha256 04279038f0832104c89b3cdc104470da5bd35dad3ba511cd3b52281c037ac535.

## Limits (honest)
- Single-device loop: capture and send ran on the same phone (TV and watch
  were offline at proof time). Multi-target routing is unit-tested with fakes.
- No serials, IPs or screen pixels are committed to the repo.
