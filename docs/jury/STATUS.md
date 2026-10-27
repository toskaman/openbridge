# Demonstration status (27 Oct 2026)

Real hardware (author's home): Windows PC without Bluetooth, Freebox v7, Xiaomi Android 14 phone (USB), Android 11 TV (ADB Wi-Fi), LG webOS TV and other LAN devices (observed only).

Verified: mDNS discovery; Freebox app authorization and read-only LAN inventory; phone and TV inspection; strong identity merge of the TV (mDNS + ADB via Bluetooth address); BLE relay through the phone (USB) and through the TV (LAN); Meta planning and explanation with Llama 3.2 3B and Muse Glimmer 30B; consent-gated reversible change with exact Undo; crash recovery; session restore of pre-session settings; Meta-only runtime registry.

Simulated and labelled: the demo fixture and its persistent change/Undo sandbox; hermetic UI suites in CI.

Not verified: cable unplug during a write; Bluetooth on the PC itself (no adapter); OpenWrt/FRITZ!Box/Home Assistant/ESPHome/Matter/Zigbee (not implemented); more than one phone and one Android TV model. No bonus eligibility or organizer acceptance is claimed. Final video: pending (recorded only once the project is complete).

## Update 27 Oct
New since the last status: `/api/v2` contract and safe primitives; Windows PC (read-only agent); Galaxy Watch7 pairing and reads; crash drill 5/5 on the phone; live Meta Model API advisory; Capability Forge publication on real phone and TV relays. Final video: still pending until the project is complete.

## Update 27 Oct (evening) — V4 code complete, hardware runs pending
Merged as a stack of PRs: cross-transport timeline and hypotheses (V4-01), privacy-preserving cloud escalation (V4-05), registered ablation with rules arm measured (V4-04), read-only UPnP-IGD, BLE zones (V4-11), visual read-back (V4-07), voice (V4-10), Wear OS manifest (V4-08), inference scheduler (V4-12). All are SIMULATED_VERIFIED in CI except voice (IMPLEMENTED_UNVERIFIED). Hardware runs pending: TV+router timeline, IGD read, BLE zone calibration, TV visual read-back, Watch7 manifest, LAN worker benchmark, model arms of the ablation, one live cloud escalation, one live STT. See CLAIM_EVIDENCE_MATRIX.md and DEMO_STORYBOARD_150S.md.
