# Known limitations

- Physical phone evidence covers Xiaomi Android 14 and Blackview BV9300 Pro; action support differs by vendor. Xiaomi input/settings writes remain denied in the recorded sweep, while the Blackview action sweep passed. See [device results](DEVICE_CAPABILITIES.md).
- BLE is verified through the phone and TV relays only; this PC has no Bluetooth adapter. Android TV evidence comes from one TV (Android 11).
- OpenWrt, FRITZ!Box, Home Assistant, ESPHome, Matter, Thread and Zigbee adapters are not implemented.
- Router/box configuration is read-only by policy.
- A physical USB cable pull was verified during revert on the owned Xiaomi phone, followed by quarantine and exact recovery after reconnect. This does not prove cable loss during every write phase or on other devices; see the [evidence ledger](../EVIDENCE_LEDGER.md).
- Identity merging is conservative: the same device may appear twice with a "possible duplicate" hint rather than be merged.
- The local 3B model is weak at planning (53% correct); Muse Glimmer 87%; a simple rule reaches 90% on the narrow benchmark. Safety never depends on the model.

## BridgeWindows adapter (Windows PCs)
BridgeWindows diagnostics use read-only allowlisted methods. A separate consent-gated `pc_job` primitive now permits arbitrary owner-typed commands; these jobs cannot be undone. This exception must not be described as read-only.

The current v4 adapter uses mutual HMAC challenge-response and session-MAC envelopes; it does not transmit the pre-shared key. Payloads are authenticated, not encrypted. Keep the link on a trusted LAN. OpenBridge still accepts one agent at a time; the separate bridge's multi-PC support is not yet ported. The adapter is off unless the server is started with `--windows-bridge`.

## Corrected 30 Oct (supersedes stale rows above, history preserved)

- Companion is 0.11.0 (live flow overlay + pill-icon buttons), installed and PAIRED/READY-verified on phone, Android TV and Galaxy Watch7.
- Watch: signed relay pair PAIRED (relay-39f86439fbae) plus 0.10.0/0.11.0 installs verified; wireless adb still drops when the watch dozes.
- XP SP3 + Win7 SP1: legacy C agent VERIFIED on real QEMU guests (mutual-auth HIT + RPC exec exit 0 + screenshots); VMs deleted after proofs.
- Registry holds realized tests only (15 rows, all VERIFIED): the merely-planned i386 guest moved to the catalog below.

## Planned test targets (catalog, 30 Oct)

Targets below are NOT tested and MUST NOT appear in [the evidence registry](DEVICE_EVIDENCE.json) (realized tests only, rendered to [the matrix](HARDWARE_TEST_MATRIX.md)). No new separate compatibility document: this section is the catalog.

Promotion to the registry requires the SAME validation pipeline for every target — this is what turns an emulator catalog into a credible technical demonstration:

1. A program actually executes inside the emulated environment (agent or real Companion, not a host-side stub).
2. Bidirectional communication with the PC is proven (handshake + round-trip, both directions observed).
3. A command flows from the emulated environment toward another device (or vice versa through it).
4. The result is independently verified (oracle outside the channel under test: read-back, screenshot, hash, second observer).
5. The physical deployment procedure is documented (how the same program reaches real hardware).

Only after all five steps does the entry earn a registry row, a matrix render, and a claim link in [the claim matrix](jury/CLAIM_EVIDENCE_MATRIX.md).

| Target | Environment class | Step-1 program |
|---|---|---|
| 32-bit Linux guest (i386) | Full guest OS, protocol endpoint | Reference agent handshake + RPC |
| Android phone/tablet official emulator + real Companion | Official platform emulator | Companion APK, pair, relay op |
| Android TV official emulator + real Companion | Official platform emulator | Companion APK, pair, relay op |
| Wear OS official emulator + real Companion | Official platform emulator | Companion APK, pair, small-screen UI check |
| MQTT broker + Matter test fabric | Protocol simulator | Adapter against simulator, facts verified |
| Home Assistant test instance | Protocol simulator | Inventory via official API, read-only first |
| ESPHome / Thread / Zigbee adapters | Not implemented | Adapter + lab hardware or simulator first |
| RetroArch emulator-host integration | Emulator controlled through host adapter | Host-process control proof (no ROM claims) |
| Console emulators (Game Boy / PlayStation class) | Emulator controlled through host adapter | Host-process control only; no ROM/BIOS without rights |
| IoT protocol simulators (generic) | Protocol simulator | Per-simulator facts verified, labeled as simulated |

## Corrected 29 Oct (supersedes stale rows above, history preserved)

- Multi-PC: the OpenBridge server now accepts up to 8 agents (rewritten accept loop); second PC verified with binary swap + hash match. The "one agent at a time" row above is stale.
- Tuya vacuum: owner-linked AND commanded (facts + seek beep verified on hardware 29 Oct; full 12-command surface model-composable, mode/water/resets unit-tested only). The "DISCOVERED only" matrix row is stale.
- Companion is 0.10.0 (was 0.4.0/0.9.0 in older rows): encrypted relay channel (aead1), durable pairings, Allow-full-control toggle with warning popup. Relay runs only while the app is open.
- Watch: Companion 0.9.0 installed, PAIRED/READY verified; the signed wire probe is UNVERIFIED (adb transport died, needs physical wake). Watch-to-TV control is not claimed.
- Sealed G3 (29 Oct): held-out skill synthesis proven on live TV with 2 honestly reported KILLs; the seal was same-party (Spark), disclosed as weakened held-out in the REVEAL docs.
- VM fleet: agent wire protocol proven on Debian 13 x2, Debian 12, Ubuntu 22.04, Debian 13 ARM64. The Android Companion was NOT tested in any VM. XP blocked (no product key), Win7 blocked (no media), x86 guest unstaged. See the [device registry](DEVICE_EVIDENCE.json).
- Freebox: reads only by policy (leases + inventory verified); no writes exist.

## Added 27 Oct
- Tuya vacuum: owner-linked through the owner's own Tuya IoT Cloud project (`python -m dev.tuya_link`); reads plus suction/volume with exact Undo; robot commands (start, moves, dock, resets…) are irreversible and need consent per command; manual moves auto-stop after at most 3 s. OpenBridge never extracts keys from apps, caches or traffic.
- BridgeWindows agent: v4 uses mutual authentication and session MACs without payload encryption; OpenBridge diagnostics are read-only, with the separate owner-consented `pc_job` exception. OpenBridge `--windows-bridge` and the BridgeWindows daemon both need port 9876; run one at a time.
- Watch7: the owner recorded direct ADB remote keys/touch/app launch and exact volume restore while awake. This is PC-to-watch control, not a Watch-to-TV Companion control surface; dozing can time out. See [device results](DEVICE_CAPABILITIES.md).
- Hosted Meta advisory: synthetic facts only; $0.10 reserved per explicit request, $0.20 per fresh observation and $1 persistent local lifetime ceiling; Meta's spending alerts are not a provider hard cap.

## Added 27 Oct (V4)
- Hypotheses are rule-based correlations in time, not causes; the rules miss WAN outages when two devices drop together (registered ablation, 20/24).
- Cloud escalation is data minimisation, not anonymity: device categories and relative timing are sent after review.
- UPnP-IGD gives WAN status only (no clients, channels or DHCP); many gateways disable IGD.
- BLE zones need per-home calibration and fail to "unknown"; furniture changes invalidate them; no positions.
- Visual read-back depends on local Glimmer (~minutes on CPU offload); without it the result is STRUCTURED_ONLY.
- Voice: the evidence ledger records a live synthetic speech/transcription run. Audio leaves the PC when this optional service is used; a transcript is a proposal, never authorization. No new transcription was made for this documentation update.
- LAN inference worker must be declared by the owner; it is not in the default runtime manifest.
- PC jobs (`pc_job`) run arbitrary owner-typed commands and cannot be undone. The BridgeWindows v4 link authenticates messages but does not encrypt payloads; use it only on a trusted LAN.

## Physical routing and remote-control follow-up

- The earlier partial two-relay run remains preserved. A later [complete contributor-recorded handover](release/COMPLETE_HANDOVER.md) verifies a fresh phone scan after TV loss. This is a demonstration, not an unseen evaluation; cleanup and permission-revocation coverage remain separately qualified.
- Revised Watch controls and integration fixes merged in PR57. The [reported owner-attended hold](release/WATCH_CONTROL_ACCEPTANCE.md) produced one request and one TV volume increment. The original two-tap/sixteen-action cause remains unproven; duplicate/expiry cases are unit-tested only. Revocation stops new admissions, not an already-admitted physical operation.
- Both devices still reported location mode3 after the rerun. This run made no location writes; the earlier requested restoration needs confirmation.

- Corrected persistence in [PR59](https://github.com/toskaman/openbridge/pull/59) supersedes original PR56 behavior. [Persistence scope](runtime/PERSISTENCE.md) covers saved completed unresolved outcomes only, not a pre-dispatch crash journal or global cross-process operation admission. Retained acknowledgement tombstones grow until the explicit storage bound; storage failure blocks visibly. Live deployment is a separate gate.
