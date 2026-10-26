# Router adapters

Implemented: Freebox OS (public identity, mDNS, official app authorization, read-only LAN inventory) — REAL_HARDWARE_VERIFIED. Not implemented: OpenWrt ubus/rpcd, FRITZ!Box TR-064, generic UPnP IGD; no assumption that admin web UIs share a structure. Credentials: official authorization only; no password guessing or factory-default attempts were implemented. Write capabilities (settings, Wi-Fi, DHCP, firewall) are BLOCKED by policy until an independent recovery path exists.
