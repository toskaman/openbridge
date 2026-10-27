# Router adapters

UI and README label for the gateway row: **ISP Router API (e.g., Freebox OS / UPnP-IGD)**. This is a vendor-neutral facade; it does not mean UPnP-IGD exposes what Freebox OS exposes.

| Adapter | What it reads | Status |
|---|---|---|
| Freebox OS (official app authorization) | public identity, mDNS, read-only LAN inventory, connection/FTTH/system/Wi-Fi radio status | REAL_HARDWARE_VERIFIED |
| Generic UPnP-IGD (`src/adapters/upnp_igd.py`) | WAN connection status, uptime, last error, connection type, access type, link status, max bit rates; external IPv4 reported only as *public / private (double NAT) / none* | SIMULATED_VERIFIED with a fake IGD in CI; real-gateway read pending (see EVIDENCE_LEDGER) |
| SSDP / mDNS discovery | service announcements only; not authentication and not IGD interrogation | REAL_HARDWARE_VERIFIED |
| OpenWrt ubus/rpcd, FRITZ!Box TR-064 | — | NOT_IMPLEMENTED |

## UPnP-IGD boundaries
- Used only for a gateway found by the owner's bounded SSDP discovery whose description advertises `WANIPConnection` or `WANPPPConnection`. The description/control URLs must be `http`, private-scope and on the same host as the SSDP `LOCATION`; no proxy, no redirects, 64 KiB / 16 KiB caps, DTD and entity declarations refused.
- Allowlisted SOAP queries: `GetStatusInfo`, `GetExternalIPAddress` (masked), `GetConnectionTypeInfo`, `GetCommonLinkProperties`, `GetTotalBytesReceived`, `GetTotalBytesSent`. Everything else — `AddPortMapping`, `DeletePortMapping`, `ForceTermination`, `RequestConnection`, port-mapping listing, any setter — is refused before a byte is sent (tests in `tests/fabric/test_upnp_igd.py`).
- IGD is not a Wi-Fi diagnostic API: no client list, channel, DHCP lease or SSID is read or inferred. Unsupported fields are returned as `UNSUPPORTED`.
- When Freebox OS authorization exists for the same gateway, the Freebox adapter is used and IGD is not queried.

Credentials: official authorization only; no password guessing or factory-default attempts. Write capabilities (settings, Wi-Fi, DHCP, firewall, port mappings) are BLOCKED by policy until an independent recovery path exists.
