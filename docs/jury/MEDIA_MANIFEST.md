# OpenBridge — Media manifest (presentation assets)

Human-readable index. Machine labels live in
[MEDIA_MANIFEST_V2.json](MEDIA_MANIFEST_V2.json). All files below ship in
`docs/jury/screens/`; every frame is a real capture, nothing staged, nothing
AI-generated. Corrupt/missing items are listed at the bottom — never silently
dropped.

## Hero + tour

| File | Size | Depicts | Date | PII |
|---|---|---|---|---|
| openbridge-tour.gif | 320 KB, 960×540, 6×1.8 s | Fabric → Ask → phone → TV → watch → S5b panel | rebuilt 31 Oct (`dev/rebuild_tour_gif.py`) | none beyond source frames |
| fabric-tv-relay-redacted-1440.png | 210 KB, 1440×900 | My Devices: 24 dev / 31 links, names redacted | 28 Oct | none (redacted) |
| ask-openbridge-1440.png | 319 KB, 1440×1000 | Ask panel: tiers + consent, fresh session | 28 Oct | none |

## Real Companions (REAL_HARDWARE)

| File | Size | Depicts | Date | PII |
|---|---|---|---|---|
| phone-companion-0-12-paired.png | 416 KB, 1080×2388 | Phone orb PAIRED READY | 31 Oct | status-bar icons/time only |
| tv-companion-0-11-paired.png | 179 KB, 1920×1080 | TV orb PAIRED, LIVE tiles, feed | 30 Oct | relay id + port (test ids) |
| tv-0-12-mdns-feed.png | 184 KB, 1920×1080 | TV + mDNS-advertised row | 30 Oct | same test relay id |
| g04-watch-quick-controls.png | 30 KB, 480×480 | Watch7 native Scan-room / Watch-facts | 30 Oct | none |
| g04-watch-press-ack.png | 38 KB, 480×480 | Watch "Press recorded (evidence run)" | 30 Oct | none |
| watch-0-12-mdns-feed.png | 29 KB, 480×480 | Watch activity feed, mDNS row | 30 Oct | none |

## Meta-generated controls + safety (REAL_HARDWARE)

| File | Size | Depicts | Date | PII |
|---|---|---|---|---|
| s5b_installed.png | 219 KB, 1920×1080 | Meta T2 panel on TV (Find + Volume) | 31 Oct | test relay id |
| s5b_pressed.png | 232 KB, 1920×1080 | After hold-press FIND (tx-4a96f8f6) | 31 Oct | test relay id |
| s5b_revoked.png | 253 KB, 1920×1080 | After revoke (controls gone) | 31 Oct | test relay id |
| refusal_channel.png | 256 KB, 1440×1000 | Refused press in Activity timeline | 31 Oct | none |
| agent-glimmer-1440-undone.png | 41 KB, 1080×421 | Agent loop plan→act→verify→UNDO | 26 Oct | battery/storage facts |
| companion-0-10-full-control-popup.png | 214 KB, 1080×2388 | "Allow full control" warning | 29 Oct | status bar only |

## Emulator + legacy (labeled, never as physical)

| File | Size | Depicts | Date | PII |
|---|---|---|---|---|
| tv-launch.png / tv-focus.png | 325 / 319 KB, 1920×1080 | TV emulator first launch + focus | 31 Oct | none |
| wear-launch.png | 32 KB, 454×454 | Wear emulator first launch | 31 Oct | none |
| esp32-idf-qemu-proof.png | 30 KB | Terminal: AUTH + CROSS_OK | 30 Oct | local paths/ports |
| legacy-xp-agent-connected.png | 126 KB, 640×480 | XP agent CONNECTED + exec exit 0 | 30 Oct | VM NAT ip only |
| legacy-win7-agent-connected.png | 114 KB, 800×600 | Win7 agent LINKED | 30 Oct | VM NAT ip only |
| legacy-win7-uac-consent.png | 147 KB, 800×600 | UAC consent (unsigned, honest) | 30 Oct | none |

## Known-bad / missing (re-capture required)

- `phone-pairing-code.png`, `phone-companion-fixed.png`,
  `phone-companion-launch.png`, `on-avd-companion-home.png` (E:-only):
  UTF-16-mangled, PIL-unreadable. Manifest REAL items with no valid file.
- `phone-scan-live.mp4` (10 MB, E:-only): metadata verified, ships in the
  jury ZIP only — not committed to git.
- Clean-room per-OS `tour-*.webm` × 6 + `phone-demo.mp4`: cited by the
  manifest, not found on disk (CI artifacts, unrecovered).
- Forge `capability-forge-170s.mp4` + live-glimmer mp4s: specs only, unproduced.
- Final 180 s video: BLOCKED until new explicit owner authorization.
