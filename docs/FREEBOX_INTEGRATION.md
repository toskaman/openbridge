# Freebox integration

- Public identity: GET http://mafreebox.freebox.fr/api_version (REAL_HARDWARE_VERIFIED).
- mDNS `_fbx-api._tcp` provides api_version, api_domain, box model (REAL_HARDWARE_VERIFIED).
- App authorization (official Freebox OS flow): POST /api/vN/login/authorize/ -> owner presses ✓ on the Freebox Server display -> poll /login/authorize/<track_id> -> token stored with Windows DPAPI (src/fabric/credential_vault.py) -> challenge/HMAC-SHA1 session. REAL_HARDWARE_VERIFIED on a Freebox v7 (r1), API 16.1; granted permissions did not include `settings`.
- Read-only allowlist: lan/browser/interfaces/, lan/browser/pub/, system/, connection/. Only GET after login. Expired session renewed once; revoked token deleted and re-authorization required.
- Graph: active LAN hosts become `freebox -> host` INVENTORY links with observe-only grants; inactive history is counted not drawn (real: 127 known, 12 active, 37 randomized MACs).
- Policy: router_settings, wifi_settings, dhcp, firewall are BLOCKED (no independent recovery path). No credential guessing; no factory-password attempts.
- Revocation: Freebox OS -> Paramètres -> Gestion des accès -> Applications.
Files: src/adapters/freebox.py, freebox_auth.py, src/fabric/freebox_ingest.py, dev/freebox_authorize.py, tests/fabric/test_freebox_auth.py.
