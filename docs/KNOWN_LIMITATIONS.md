# Known limitations

- One owned phone (Xiaomi, Android 14) for all physical evidence; other vendors may behave differently and adapters fail closed.
- BLE is verified through the phone and TV relays only; this PC has no Bluetooth adapter. Android TV evidence comes from one TV (Android 11).
- OpenWrt, FRITZ!Box, Home Assistant, ESPHome, Matter, Thread and Zigbee adapters are not implemented.
- SSDP/UPnP read-only discovery is implemented and physically observed (Freebox service advertisements; intermittent Android TV DIAL). No UPnP control or port mapping is enabled; see [evidence ledger](../EVIDENCE_LEDGER.md#ssdpupnp-and-endurance).
- Router/box configuration is read-only by policy.
- Physical USB cable pull was verified specifically during revert on the owned phone: quarantine followed by exact recovery after reconnect. This does not prove loss during every write phase or on other devices; see [evidence ledger](../EVIDENCE_LEDGER.md).
- Identity merging is conservative: the same device may appear twice with a "possible duplicate" hint rather than be merged.
- The local 3B model is weak at planning (53% correct); Muse Glimmer 87%; a simple rule reaches 90% on the narrow benchmark. Safety never depends on the model.

## BridgeWindows adapter (Windows PCs)
OpenBridge only reads from the owner's BridgeWindows agent: system diagnostics, process count and an exact allowlist of registry values. The agent's command, file, registry-write, input and update methods are refused before anything is sent.

The agent's current authentication is a static pre-shared key sent in clear over plain TCP. Until it uses per-request signing (like the relay protocol), keep the agent on a trusted LAN. The adapter is off unless the server is started with `--windows-bridge`.

## Added 27 Oct
- Tuya devices: discovered only. Local reads need the owner's device ID and local key from a free Tuya IoT project; OpenBridge never extracts keys from apps, cloud or traffic.
- BridgeWindows agent: its own static key travels in clear over plain TCP; OpenBridge uses it read-only. OpenBridge `--windows-bridge` and the BridgeWindows daemon both need port 9876; run one at a time.
- Smartwatch: read-only facts; no controls published on the watch yet.
- Hosted Meta advisory: synthetic facts only; $0.10 reserved per request, $0.20 allowance per fresh observation, $1 persistent local lifetime ceiling; Meta's spending alerts are not a provider hard cap.
