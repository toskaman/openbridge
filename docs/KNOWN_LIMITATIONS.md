# Known limitations

- One owned phone (Xiaomi, Android 14) for all physical evidence; other vendors may behave differently and adapters fail closed.
- BLE is verified through the phone and TV relays only; this PC has no Bluetooth adapter. Android TV evidence comes from one TV (Android 11).
- SSDP/UPnP, OpenWrt, FRITZ!Box, Home Assistant, ESPHome, Matter, Thread and Zigbee adapters are not implemented.
- Router/box configuration is read-only by policy.
- Cable unplug during a write is covered by mocked tests only.
- Identity merging is conservative: the same device may appear twice with a "possible duplicate" hint rather than be merged.
- The local 3B model is weak at planning (53% correct); Muse Glimmer 87%; a simple rule reaches 90% on the narrow benchmark. Safety never depends on the model.

## BridgeWindows adapter (Windows PCs)
OpenBridge only reads from the owner's BridgeWindows agent: system diagnostics, process count and an exact allowlist of registry values. The agent's command, file, registry-write, input and update methods are refused before anything is sent.

The agent's current authentication is a static pre-shared key sent in clear over plain TCP. Until it uses per-request signing (like the relay protocol), keep the agent on a trusted LAN. The adapter is off unless the server is started with `--windows-bridge`.

## Added 27 Oct
- Tuya devices: discovered only. Local reads need the owner's device ID and local key from a free Tuya IoT project; OpenBridge never extracts keys from apps, cloud or traffic.
- BridgeWindows agent: its own static key travels in clear over plain TCP; OpenBridge uses it read-only. OpenBridge `--windows-bridge` and the BridgeWindows daemon both need port 9876; run one at a time.
- Smartwatch: read-only facts; no controls published on the watch yet.
- Hosted Meta advisory: synthetic facts only; $0.10 per session, $1 local ceiling; Meta's spending alerts are not a provider hard cap.
