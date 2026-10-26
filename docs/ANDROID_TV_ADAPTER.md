# Android TV / Google TV

Detection: mDNS `_androidtvremote2._tcp` and `_googlecast._tcp` (REAL_HARDWARE_VERIFIED on the participant LAN), Freebox inventory host_type `television`, and ADB (`android.software.leanback` feature -> category tv, battery absent handled). States surfaced: detected-not-associated (mDNS only, capability tv_remote_protocol NOT_SUPPORTED), ADB authorized (inspect REAL path shared with phones), companion installed (relay panel). Wireless ADB pairing is guided (wifi_adb_pairing) but OpenBridge never pairs or connects on its own. The Android TV remote protocol itself is not implemented.
Hardware status: the participant's Android TV has only been observed via mDNS; ADB and companion on TV are NOT TESTED.
