# UI layout v2 on the owned Android TV — 29 Oct 2026 (owner-authorized automation)

Code: branch `claude/ui-renderer-v2` (server + Companion 0.8.0 built from the same head). Isolated server on :18780
(stopped after the run); the managed live server was not touched. Presses were injected with adb (long-press on the
widget, then a tap on the dialog's RUN), on the owner's standing instruction to proceed without asking; they are
labeled as automation, not as a human press.

Manifest: the Meta-generated G3 manifest (Muse Spark 1.3 run `mr_2679619b7ab09920`: `input.key {key: mute}` →
`state.audio`), host-rebound to the current fingerprint, required fact and expiry. Meta steps unchanged.
UI plan: a fixture v2 plan (label + confirm + status), **not** Meta-authored; it exercises the renderer and binding.

| step | run 2 (PASS) |
|---|---|
| pairing + `ui_install` | PAIRED relay-dabd2a796665; HTTP 200, 1 action control + 2 display widgets |
| device ACK | layout revision 7 sent, `applied_revision` 7 reported by the TV |
| screen | `Living room TV`, `Mute toggle`, `Last result · no result yet` |
| hold + confirm dialog → RUN | EXECUTED tx-602e8eda…; oracle `muted` false/20 → **true/0**; status `done 14:54` |
| second confirmed press | EXECUTED tx-d18eab55…; oracle back to **false/20** |
| Companion force-stop + relaunch | same three widgets restored from device storage, status `done 14:55` kept, ACK 7 |
| grant revoked, confirmed press | **BLOCKED**, no transaction; oracle stays false/20; status `blocked 14:55` |
| cleanup (empty controls) | the TV no longer shows the control |

Run 1 (retained) found a real reconnect defect: after the Companion restart, one failed poll left the relay offline
forever and the post-revoke press (device log `seq=3`) was never fetched. Fixed in `cb20adb` (bounded re-probe), with a
failing-first test; run 2 confirms the fix on hardware. Earlier the same day the 0.8.0 build also exposed a TV crash
from the #92 rewrite (`VoiceOrbView` RadialGradient radius ≤ 0), fixed in `37a89fc`.

Files: `run2_PASS.json`, `run1_reconnect_bug_found.json`, `hw_ui_v2_driver.py` (exact driver).
Not covered here: the watch (offline today), a Meta-authored UI plan, human (non-adb) presses.
