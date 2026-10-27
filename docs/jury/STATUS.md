# Demonstration status (27 Oct 2026)

Real hardware (author's home): Windows PC without Bluetooth, Freebox v7, Xiaomi Android 14 phone (USB), Android 11 TV (ADB Wi-Fi), LG webOS TV and other LAN devices (observed only).

Verified: mDNS discovery; Freebox app authorization and read-only LAN inventory; phone and TV inspection; strong identity merge of the TV (mDNS + ADB via Bluetooth address); BLE relay through the phone (USB) and through the TV (LAN); Meta planning and explanation with Llama 3.2 3B and Muse Glimmer 30B; consent-gated reversible change with exact Undo; crash recovery; session restore of pre-session settings; Meta-only runtime registry.

Simulated and labelled: the demo fixture and its persistent change/Undo sandbox; hermetic UI suites in CI.

Verified cable-loss scope: physical USB pull during revert, quarantine and exact recovery after reconnect. Other write phases remain unverified. Not verified: Bluetooth on the PC itself (no adapter); OpenWrt/FRITZ!Box/Home Assistant/ESPHome/Matter/Zigbee (not implemented); more than one phone and one Android TV model. No bonus eligibility or organizer acceptance is claimed. No videos, recordings, video edits or renders until a new explicit owner request, even after project completion.

## Update 27 Oct
New since the last status: `/api/v2` contract and safe primitives; Windows PC (read-only agent); Galaxy Watch7 pairing and reads; crash drill 5/5 on the phone; live Meta Model API advisory; Capability Forge publication on real phone and TV relays. Video remains blocked until a new explicit owner request, even after completion.

Current Forge evidence: [TV → local Glimmer → HTTP lifecycle](../forge/TV_GLIMMER_JOURNEY.md), including local-authority denial and route removal. See [release status](../RELEASE_STATUS.md) for remaining acceptance work.
