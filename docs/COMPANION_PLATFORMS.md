# Companion platforms: where OpenBridge can run next

What the Android Companion does today (`companion/android`, Java, no third-party libraries), and what it
would take to bring the same cooperation — plus the AI — to other operating systems. Status of the
outside world checked November 2026; store and sideloading rules move fast, re-check before committing.

## What a companion must do

Full companions (phone, TV, watch) implement all of this; thin clients implement a subset:

| Need | Android today | Everywhere else |
|---|---|---|
| LAN server | TCP 47800, `POST /ob`, 16 KB cap | Listening TCP sockets on the LAN |
| Canonical JSON | `sort_keys`, no spaces | Same byte rules (tests pin them) |
| Crypto | AEAD channel, CPace/X25519 pairing, HMAC | X25519 + ChaCha20-Poly1305 + HKDF (or a port of the pure-Java code) |
| Discovery | NSD/mDNS advertise | mDNS advertise (or rely on the PC scan) |
| BLE relay | Foreground scans on signed request | BLE central role + background allowance |
| Buttons | Remote-control UI, presses back | Any UI + HTTPS POSTs to the PC |
| Voice | Mic drain to the PC (`ha say` path) | Mic + streaming or file upload |
| Notifications | Listener (ENGO hub pattern) | OS notification API |
| Persistence | Foreground service | Whatever keeps a socket alive |

Three tiers: **full relay** (server + BLE + background), **thin client** (polls the PC, shows buttons,
sends voice; no server, no BLE), **display-only** (shows state/frames). A thin client is always
possible where HTTPS and a timer exist.

## Platform verdicts

Ordered by recommended build order, not alphabetically.

### 1. Linux desktop — cheapest (mostly packaging)

The whole stack already runs on Linux. A "companion" is a small tray client reusing `src/` itself:
buttons via the local API, mic via the existing STT path, mDNS via `src/fabric/mdns.py`. Ship as a
native package plus Flatpak. Effort: days. Also covers ChromeOS (runs the Android APK directly)
and Windows-on-ARM/Linux VMs trivially.

### 2. Web TV kit: Tizen (Samsung) + webOS (LG) — one codebase, two stores

Both run HTML5/JS TV apps with LAN access, both need the same thing the Android TV companion does:
show AI-made buttons, send presses back, D-pad navigation. Write it once as a hosted web app with a
thin per-store shell (Tizen Studio / webOS TV SDK), speaking the same signed channel (WebCrypto has
everything except X25519 — ship the small JS port or start these TVs in thin-client mode). Publish
in both TV stores; both allow developer sideloading for testing. Effort: weeks. Skip Tizen
*watches* (legacy since Galaxy Watch 4 moved to Wear OS).

### 3. iOS + iPadOS, with macOS free — biggest user base, real constraints

Feasible, foreground-first. Swift + Network framework (TCP listener works while the app runs),
CryptoKit (X25519, ChaCha20-Poly1305, HKDF all present), BLE central allowed with limits, mic
drain fine. What iOS forbids: a persistent background TCP server and silent background work — so
the iOS companion pairs and relays while open (exactly the Android contract: "runs only while the
app is open") and degrades to thin client in background. Distribution: App Store / TestFlight
worldwide; alternative marketplaces and web distribution in the EU, Japan and Brazil (AltStore PAL
et al, per Apple support docs October 2026); self-signing elsewhere. The same Swift core builds a
macOS menu-bar companion (full sockets, notarized) nearly free. Effort: 1–2 months for both.

### 4. Android Automotive (AAOS) — cheap variant, big stage

AAOS runs Android apps: the existing APK is ~90% reusable (car UI templates for parked use, media
template while driving, Play-for-cars review). The car becomes a control point: "start the vacuum
when I leave" from the dashboard. Effort: weeks after the phone app. Tesla and closed IVIs: no
third-party path, skip.

### 5. Playdate — the fun build

Official Lua/C SDK, Wi-Fi, and blessed sideloading (no store fight). A Lua companion that polls the
PC, shows two buttons and a status line, and sends the crank position as a dimmer/knob is a weekend
prototype and a great demo. Already a P1 catalog target in [the limitations](KNOWN_LIMITATIONS.md).
Effort: days for thin client; the full native-agent proof stays the catalog's bar.

### 6. Pebble (reborn) + Garmin — via the Android phone

Both are phone-dependent watches (no direct LAN). The ENGO glasses-hub pattern already solves this:
the Android Companion relays frames/notifications/voice to the peripheral. PebbleOS is open source
with new hardware (Core 2 Duo / Core Time 2 announced 2025); a Pebble watchapp (C SDK) plus a relay
endpoint in our Android app is cheap. Garmin Connect IQ (Monkey C) follows the same shape with more
friction (Connect Mobile dependency, tiny UI budget). Verdict: Pebble after the phone app is solid;
Garmin only on demand.

### 7. KaiOS — thin client only, low priority

Alive (4.0 in May 2025, maintenance into 2027–2029, huge historical base) but shrinking: few new
apps, harder developer mode on 3.x+, HMD gone. Apps are HTML5/JS through KaiStore (partner process);
raw TCP server sockets need privileged APIs ordinary apps don't get. A KaiOS companion can only be
a polling thin client (buttons + status, no BLE relay, no server). Build only if a partner brings
devices and a KaiStore slot.

### 8. HarmonyOS NEXT — blocked for phones, watches are the exception

No sideloading (AppGallery only) and, per Huawei's own developer docs (May 2026), native phone/tablet
apps available only in mainland China — global NEXT phone apps are watches-only. A DevEco/ArkTS
rewrite (HAP packaging, no Android reuse) for a China-only phone companion is not worth it now.
Revisit if: a partner needs it, or the reported 2026 sideloading opening (PCs first) reaches phones.
The global NEXT *watch* stays a theoretical thin client via AppGallery.

### 9. watchOS, tvOS, visionOS — after iOS, if ever

watchOS forbids listening sockets (WatchConnectivity + URLSession only): it can only be a thin
client through the paired iPhone, so it waits for §3. tvOS is technically easy (same Swift core,
focus UI) with a tiny user base. visionOS likewise. Verdict: tvOS as a stretch goal of the Swift
core; the rest on demand.

### 10. Windows companion UX — the agent exists, the face is missing

BridgeWindows is an RPC agent (no user interface). A companion *face* (tray icon, buttons, mic,
pairing QR) on Windows is a separate small app; only build it once §1–§3 define the shared design
language, so all companions look like one product.

## What porters implement (checklist)

1. Canonical JSON byte rules + the 16 KB cap (copy the vector tests, don't re-derive them).
2. X25519 + CPace pairing + AEAD channel + HKDF, verified against the Python vectors in
   `tests/fabric/` (generate the same pinned vectors in the new language first).
3. `POST /ob` verbs the tier needs (full: everything; thin: poll + press + voice).
4. Consent surfaces: owner enables scans/voice explicitly; "Remove pairing" revokes.
5. mDNS advertise where the OS allows; otherwise document PC-scan-only discovery.
6. No new network permissions beyond the LAN; nothing leaves the home without the owner's action.

## Suggested order

1. Linux tray companion (§1) — days, proves the thin-client API shape.
2. Web TV kit (§2) — weeks, doubles the TV footprint.
3. Swift core: iOS + macOS (§3), tvOS stretch (§9).
4. AAOS variant (§4) + Playdate prototype (§5).
5. Phone-relayed watches (§6) once the Android relay endpoint exists.
6. KaiOS / HarmonyOS / watchOS only on partner demand (§7–§9).
