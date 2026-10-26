# Bluetooth local and remote

Local (PC): bleak 3.0.2 optional, passive advertisement scan ≤10 s, never connects; static-random addresses only are strong identity. This PC has no Bluetooth adapter -> BLE_UNAVAILABLE. Bluetooth Classic: not implemented (no reliable cross-OS API here).
Remote: relay protocol v1 + Android Companion (RELAY_SECURITY.md, ANDROID_COMPANION.md). Relayed devices are linked `relay device -> BLE device` with observe-only grants. Energy: scans only on request, bounded, app must be open, no polling.
