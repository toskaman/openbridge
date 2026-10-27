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
