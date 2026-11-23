# Native Matter controller: phased plan

Matter, Thread and Zigbee devices paired in Home Assistant already work today through the
[Home Assistant bridge](HOME_ASSISTANT.md). A *native* OpenBridge controller (no Home Assistant
needed) is a large, hardware-gated project; this page is the plan, phase by phase, with honest
gates. Nothing here is claimed before it runs against real devices or the official certification
harness.

## Phase 0 — Vocabulary (done)

- `src/fabric/matter_tlv.py`: Tag-Length-Value encode/decode with bounds and fail-closed errors.
- `tests/fabric/test_matter_tlv.py`: hand-derived vectors (both directions), malformed-input battery,
  seed-fixed round-trip fuzz, and an optional loader for official vectors
  (`tests/fabric/matter_tlv_vectors.json`, git-ignored; extract from the Matter specification
  examples or connectedhomeip's TestTLV).

## Phase 1 — Session security (next, no hardware needed)

- PASE (passcode commissioning): SPAKE2+ over P-256 with the official test vectors. Needs a P-256
  implementation (new; `cpace.py` only has X25519) or a vetted dependency decision.
- CASE (operational sessions): Sigma-like handshake, NOC chain validation against the Rene root.
- Message layer: encrypted packets with session IDs, counters and retransmission, against
  loopback first, then a real device.
- Gate: handshake interop with one real Matter device (any bulb/plug) on the bench.

## Phase 2 — Commissioning (needs hardware + radio)

- BLE commissioning channel (this PC has no Bluetooth adapter today; a dongle or a relayed
  phone channel is required), or commissioning over already-onboarded Wi-Fi/Thread networks.
- QR / manual-code parsing, network provisioning, NOC issuance, ACL bootstrap.
- mDNS discovery of commissionable nodes (`_matterc._udp`) extending `src/fabric/mdns.py`.
- Gate: commission a factory-reset device from OpenBridge alone, twice in a row.

## Phase 3 — Clusters that matter (needs hardware)

- OnOff, LevelControl, ColorControl, Thermostat, DoorLock (lock only, never unlock — same policy
  as Home Assistant), WindowCovering, MediaPlayback basics.
- Each cluster: typed adapter tables (READ/WRITABLE/COMMANDS/POLICY), read-back verification,
  exact Undo where reversible, soak-tested like the HA bridge.
- Gate: the `ha soak` equivalent against native Matter devices, same honesty bar.

## Phase 4 — Certification posture (much later)

- Official test harness runs, certification paperwork, Thread border-router story.
- Not started, not scheduled; the Home Assistant bridge remains the supported Matter path.

## Non-goals

- Replacing the Home Assistant bridge (it stays: more device types, community integrations).
- Touching alarms, cameras, garage doors or gates (same policy everywhere in OpenBridge).
