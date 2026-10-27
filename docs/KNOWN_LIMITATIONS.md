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
