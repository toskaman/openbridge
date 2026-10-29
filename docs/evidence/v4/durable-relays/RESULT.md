# Durable relay pairing across a server restart — 29 Oct 2026 15:23 CET

Isolated server :18780 at `claude/durable-relays` with its own LOCALAPPDATA (`.xbuild/la-durable`), so the managed
live server's store was not touched. Android TV with Companion 0.9.0.

| step | result |
|---|---|
| pair (on-screen code read via uiautomator) | PAIRED `relay-dabd2a796665`, transport **aead1** |
| on disk | `relays.json` (321 B: serial, transport, declared capabilities; **no key**, see `relays.json.sample`) + `vault/relay-key-dabd2a796665.bin` (294 B DPAPI blob) |
| server stopped, new server started, android discovery | relay restored automatically: transport **aead1**, no re-pairing |
| owner command over the restored relay (sealed `set_controls`) | **HTTP 200** |

Limitation: the stored identity is the ADB serial. For a Wi-Fi ADB device whose port changes (e.g. the watch's
wireless-debugging port), the serial changes and the pairing is not restored (re-pair needed) — fails safe.
