# Known limitations

- One owned phone (Xiaomi, Android 14) for all physical evidence; other vendors may behave differently and adapters fail closed.
- Wi-Fi ADB, Android TV over ADB, and BLE (PC or relay) are not hardware-verified yet. This PC has no Bluetooth adapter.
- SSDP/UPnP, OpenWrt, FRITZ!Box, Home Assistant, ESPHome, Matter, Thread and Zigbee adapters are not implemented.
- Router/box configuration is read-only by policy.
- Cable unplug during a write is covered by mocked tests only.
- Identity merging is conservative: the same device may appear twice with a "possible duplicate" hint rather than be merged.
- The local 3B model is weak at planning (53% correct); Muse Glimmer 87%; a simple rule reaches 90% on the narrow benchmark. Safety never depends on the model.
