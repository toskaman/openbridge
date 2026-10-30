# Companion direct-Wi-Fi discovery, no adb address (REAL_HARDWARE, 30 Oct 2026)

Owner request: with the Companion installed, connecting a device must not
require re-typing the rotating wireless-debugging address — the Companion
should be found directly over Wi-Fi.

## What was built

- Android (`RelayServer.java`): NSD advertisement of `_openbridge-relay._tcp`
  on port 47800 with TXT relay/proto/ver/form/label; MulticastLock while the
  relay runs; feed line on success or failure. Manifest 0.12.0 (code 12) adds
  `CHANGE_WIFI_MULTICAST_STATE` (normal, auto-granted).
- PC (`src/fabric/mdns.py`): browse now sets the QU bit (RFC 6762 §5.4).
  Without it, Android's NsdService answers multicast-only and the PC (ephemeral
  port, no group membership) never hears it — targeted browse returned 0
  packets before the fix, 1 instance after.
- PC (`src/fabric/discovery.py`): ingest refines category from TXT `form`
  (phone/watch/tv, fallback phone), stores the relay endpoint off-snapshot,
  adds the `companion_relay` capability and a `companion_relay` identifier.
- PC (`src/fabric/onboarding.py`): new `companion_lan` method (READY,
  `relay_address`), listed first, with no-cable/no-adb steps. Unit-tested:
  no `:47800` or `relay_address` leaks into the snapshot.

## Debug trail (honest)

1. First install advertised nothing: registration ran on the relay thread
   without a Looper — moved to the main looper.
2. Still nothing: app held no MulticastLock — added (needs the manifest
   permission above).
3. Still nothing on the PC, yet system logcat showed
   `[MdnsAdvertiser] Adding service ... _openbridge-relay._tcp ... port: 47800`
   and `Probing finished` — so the bug was PC-side receive, fixed by the QU bit.
4. A visible feed line (`mDNS: this relay is advertised on the LAN`) was added
   during debugging and kept as a permanent on-device diagnostic.

## Proof transcript (adb DISCONNECTED for the whole run)

```
REPORT: {"mdns": {"status": "OK", "instances": 8, "packets": 7}}
FOUND: SM-L310 | kind watch | state READY | relay 192.168.1.14:47800
       | evidence ['OpenBridge Companion on the LAN (mDNS, no adb needed)']
```

- Full browse instances: Freebox api/smb/http, TV remote + cast, 2× adb-tls
  (system daemon, unrelated), and `_openbridge-relay._tcp 192.168.1.14:47800`.
  The 7 pre-existing instances still resolve with the QU bit (no regression).
- TXT decoded live: ver=12 form=watch label=SM-L310 proto=openbridge-relay/1
  relay=relay-39f86439fbae.
- Watch feed: `docs/jury/screens/watch-0-12-mdns-feed.png`
  (`22:44:05 mDNS: this relay is advertised on the LAN`).
- Driver: `E:\shots\prove_landisc.py` (real `discovery.run` providers=mdns +
  real `onboarding.candidates`, no adb anywhere in the chain).

Commit under test: main `994cdc9` + this change (sources) / APK 0.12.0
sha256 `3cf7ff91…866c98` on the watch.

## Limitations

- The relay (and its NSD record lifetime) still needs the app open; a sleeping
  device stops advertising — pairing then fails honestly with "open the app"
  guidance (not exercised this run).
- mDNS stays link-local: no discovery across subnets/VPN (by design).

## 3/3 roll-out (same evening)

0.12.0 was installed on the phone and the TV as well (both Success, pairings
kept). With all three apps awake in the foreground, one targeted browse
returned all three relays: SM-L310/watch/192.168.1.14, BV9300 Pro/phone/
192.168.1.40, Android TV/tv/192.168.1.15 — all ver 12. The TV activity feed
shows `mDNS: this relay is advertised on the LAN`
(`docs/jury/screens/tv-0-12-mdns-feed.png`).
