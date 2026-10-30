# Companion 0.12.0 — LAN self-advertisement, no adb address needed (30 Oct 2026)

APK: `artifacts/companion/openbridge-companion.apk`, 119187 bytes,
sha256 `e9f6d7b9a8a0ee4375c79eb3d18d311f4c89fddbaac5b9c4f1265eea214cd4ff`,
versionCode 12 / versionName 0.12.0. Installed on phone (BV9300) and TV
(Android TV 11) via `adb install -r` — Success, same participant signature,
pairings preserved. The watch currently runs intermediate build
`3cf7ff91…866c98` (same NSD feature, proven); the final build only adds the
watch UI rescale, and its watch install + screenshot check are pending the
watch waking up (wireless adb down at doc time).

## What changed

- The relay advertises `_openbridge-relay._tcp` (port 47800) via Android NSD
  while it runs, with TXT `relay`, `proto`, `ver`, `form` (phone/watch/tv),
  `label` (Build.MODEL). Registration lives and dies with the relay socket.
- New manifest permission `CHANGE_WIFI_MULTICAST_STATE` (normal level,
  auto-granted): the app holds a MulticastLock so it hears mDNS queries.
- The activity feed reports `mDNS: this relay is advertised on the LAN`, or
  `mDNS: advertisement failed (err N)` / `(err -1)` (exception) / `(err -2)`
  (no NSD service) — failures stay silent on the wire, visible on screen.
- No new dangerous permission; the broadcast relay id is useless without the
  on-screen 6-digit pairing code.
- PC side (same change): the browse sets the unicast-response bit (RFC 6762
  §5.4) so strictly-compliant responders (Android NsdService) answer back over
  unicast; discovery ingests the new service and onboarding offers
  `companion_lan` (READY, `relay_address`) ahead of the adb methods.
- Watch UI rescale (same release): stacked centered header, single-column LIVE
  tiles, roomier input bar (smaller glyph buttons, shorter hint), vertical flow
  legend, "Watch" device line, tighter pill buttons — all gated on
  `android.hardware.type.watch`; phone/TV layouts are untouched code paths
  (verified by screenshot on both; watch screenshots pending).

## Live proof (watch, 30 Oct ~22:45, adb DISCONNECTED)

- Targeted browse `services=('_openbridge-relay._tcp',)` → 1 instance:
  `openbridge-39f86439fbae`, port 47800, 192.168.1.14,
  TXT ver=12 form=watch label=SM-L310.
- Full browse → 8 instances (previous 7 + the new one, no regression).
- `onboarding.candidates` → `SM-L310 | kind watch | state READY |
  relay 192.168.1.14:47800 | OpenBridge Companion on the LAN (mDNS, no adb needed)`.
- Watch feed screenshot: [mDNS advertised](../jury/screens/watch-0-12-mdns-feed.png).
- System logcat confirms: `acquireMulticastLock lockTag=openbridge-nsd`,
  `[MdnsAdvertiser] Adding service name: OpenBridge-39f86439fbae,
  type: _openbridge-relay._tcp, port: 47800`, `Probing finished`.

Full transcript: [companion-lan-discovery-30oct](../evidence/companion-lan-discovery-30oct.md).
