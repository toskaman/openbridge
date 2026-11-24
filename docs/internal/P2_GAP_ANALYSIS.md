# §13 P2 — Capability/gap analysis (2026-10-30)

Delivered by other sections: TV->watch and watch->TV screenshots, automatic
multi-screen collage, TV remote-style controls, battery recommendations,
device relay recovery, dynamic dashboard generation, remote app launching,
sleep/shutdown workflows (see §7/§8/§9 evidence rows).

## RetroArch control — DELIVERED (server-side)
Loopback UDP adapter + `retro_command` primitive/skill, live-proven against
RetroArch 1.21.0 (VERSION/GET_STATUS verified; actions delivery-only — the
emulator sends no reply). No ROM/BIOS used. Watch dashboard area follows the
§8 merge. Evidence: `docs/evidence/retroarch-loopback-30oct.md`.

## Honest gaps (researched, not claimed)
- **Wallpaper distribution**: file delivery works (`file_push`); SETTING the
  wallpaper has no stock adb setter and needs companion-side WallpaperManager
  code. Companion-gated; not built server-side.
- **WhatsApp messaging**: no legitimate server-side API for personal
  messaging. UI-automation hacks are fragile and ToS-gray: refused. A
  companion share-intent is the legitimate future route. Not built.
- **Cross-device audio routing**: no audio capture/route primitives exist;
  Android telephony and assistant audio paths are platform-guarded.
  Research-only; nothing claimed.
- **TV-microphone phone call** ("call my wife ... use my TV mic/speakers"):
  a TV mic permission covers voice search, not continuous third-party call
  audio; Android exposes no legitimate route for this. The legitimate path is
  the phone (or a VoIP app on it). No call was placed or claimed.
- **Wake (WoL)**: device MACs are never stored (privacy design: strong
  identifiers are opaque hashes) and the Freebox integration is reads-only by
  policy, so no legitimate wake path exists today. Waking needs an explicit
  owner opt-in (per-invocation MAC or a policy lift). Sleep/shutdown work via
  `pc_run` + approval. Not built.
