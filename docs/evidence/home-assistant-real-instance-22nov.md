# Home Assistant bridge on a real Home Assistant instance (22 November 2026)

- **Home Assistant:** Home Assistant 2026.11.2, official Docker image, on the owner's Windows PC; long-lived token from the owner's profile.
- **Devices:** Home Assistant's own **Demo** integration (65 entities). Real Home Assistant software and API,
  virtual devices: this is not a physical-device test.
- **Path:** OpenBridge primitives (`ha_set`, `ha_command`, `ha_undo`, `read_facts`) through the same Executor as the app:
  consent, read-back through the Home Assistant API, receipts.
- **Script:** the run used the public adapter and Executor; every result below is the receipt state.

| Test | Entity | Receipt | State before → after |
|---|---|---|---|
| no consent -> blocked | `light.bed_light` | BLOCKED | None → None |
| light brightness 30 | `light.bed_light` | VERIFIED | off → on |
| light undo | `light.bed_light` | REVERTED | None → off |
| switch toggle | `switch.decorative_lights` | VERIFIED | on → off |
| switch undo | `switch.decorative_lights` | REVERTED | None → on |
| thermostat 21 | `climate.heatpump` | VERIFIED | heat → heat |
| thermostat undo | `climate.heatpump` | REVERTED | None → heat |
| media volume 35 | `media_player.living_room` | VERIFIED | playing → playing |
| media undo | `media_player.living_room` | REVERTED | None → playing |
| cover (non garage) close | `cover.kitchen_window` | VERIFIED | closed → closed |
| garage door open -> refused | `cover.garage_door` | BLOCKED | None → None |
| lock | `lock.front_door` | VERIFIED | locked → locked |
| read facts | `light.bed_light` | VERIFIED | None → None |

Result: 13/13 as expected (2 refusals by design: no consent, garage door).
