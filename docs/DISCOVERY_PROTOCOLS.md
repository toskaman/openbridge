# Discovery protocols

| Protocol | Status | Implementation | Limits |
|---|---|---|---|
| mDNS / DNS-SD | REAL_HARDWARE_VERIFIED (7 services on participant LAN) | stdlib, one query burst per run, legacy unicast replies, default-route LAN interface | 6 s max, 400 packets, 4000 records, TTL 1, private scope only, malformed packets dropped |
| ADB USB | REAL_HARDWARE_VERIFIED | `adb devices -l`, fixed read-only shell allowlist | 8 s per command |
| ADB Wi-Fi (`ip:port`, `_adb-tls-connect`) | REAL_HARDWARE_VERIFIED for `ip:5555` (Android TV); `_adb-tls-connect` pairing NOT TESTED | listed when connected; one owner-triggered `adb connect` to a TV found on the LAN (private IPv4 only, no scanning); never pairs wireless debugging | same |
| Freebox public API | REAL_HARDWARE_VERIFIED | GET /api_version | 4 s |
| Freebox authenticated LAN | REAL_HARDWARE_VERIFIED | official app authorization, GET lan/browser/pub/ | GET allowlist, 2 MB response cap |
| BLE (PC) | NOT_SUPPORTED on this PC (no adapter); code INTEGRATION_VERIFIED | bleak passive scan | 10 s, 300 devices, never connects |
| BLE via relay | REAL_HARDWARE_VERIFIED (Android phone) | relay protocol v1 + Android Companion | 15 s, 200 observations, owner-enabled only |
| SSDP/UPnP | REAL_HARDWARE_VERIFIED (Freebox IGD with 10 service types grouped as one device; Android TV DIAL seen in 1 of 3 runs, likely standby) | stdlib M-SEARCH ×2, description XML GET only (no DTD, 64 KB, private scope) | 6 s, 200 replies; SOAP/port mapping never used (IGD control BLOCKED) |
| ARP table | NOT_SUPPORTED | — | Freebox inventory provides the same view with names |
| Port scanning | NOT_SUPPORTED by design | — | never performed |

Concurrency: `/api/fabric-discover` is single-flight (409 when busy); providers run sequentially with their own timeouts; sockets are closed in `finally`.
