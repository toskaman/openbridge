# OpenBridge × ENGO: API and data contracts

The contracts the glasses code is built on, as they are in the code today (`src/glasses/`). Master spec references
(§) point to [20_OPENBRIDGE_MASTER_PRODUCT_SPEC.md](20_OPENBRIDGE_MASTER_PRODUCT_SPEC.md). Byte values for the
ActiveLook protocol follow the public ActiveLook documentation as we read it and are **to be confirmed on a real
ENGO 3**; nothing here claims firmware behaviour ENGO has not confirmed.

## 1. Observation (§6.1), `src/glasses/metrics.py`

One measured value from one source. Values outside the plausible range are rejected (`Rejected`), never shown.

| Field | Type | Meaning |
|---|---|---|
| `schema_version`, `event_id`, `kind` | string | `kind` is `metric` |
| `metric` | string | one of the metric names below |
| `value` | number | in the metric's unit |
| `unit` | string | fixed per metric |
| `source_type` | string | `ble_heart_rate`, `ble_rsc`, `ble_csc`, `ble_power`, `ble_ftms`, `phone_gps`, `simulated`… |
| `source_id` | string | stable id of the sensor (never a raw Bluetooth address in shared logs) |
| `measured_at` / `received_at` | number | seconds, when measured / when received |
| `quality` | string | `valid`, `estimated` or `degraded` |
| `confidence` | number 0–1 | source's own confidence when known |
| `ttl_ms` | integer | how long the value stays fresh (fixed per metric) |
| `profile` | string | wearing / activity profile, when known |

| Metric | Unit | Fresh for (s) | Plausible range |
|---|---|---:|---|
| `heart_rate_bpm` | bpm | 5 | 25–240 |
| `speed_mps` | m/s | 5 | 0–40 |
| `cadence_rpm` | rpm | 3 | 0–250 |
| `cadence_spm` | spm | 3 | 0–260 |
| `power_w` | W | 3 | 0–2500 |
| `distance_m` | m | 10 | 0–1 000 000 |
| `altitude_m` | m | 10 | −500–9000 |
| `latitude_deg` / `longitude_deg` | deg | 5 | ±90 / ±180 |
| `gps_accuracy_m` | m | 5 | 0–5000 |
| `battery_pct` | % | 120 | 0–100 |
| `stride_length_m` | m | 5 | 0–4 |
| `temperature_c` | °C | 900 | −60–70 |

The `Store` keeps the newest observation per metric and source. When two sources are fresh, a dedicated sensor
(`ble_*`) wins over the phone (`phone_*`), then the most recent wins. A metric is `READY` (fresh), `STALE` (known but
older than its TTL) or `UNAVAILABLE` (never seen). Only fresh values are returned for display: a stale value is never
presented as current.

## 2. HUD event (§6.2) and priorities (§6.3), `src/glasses/events.py`

| Field | Meaning |
|---|---|
| `schema_version`, `event_id` | `1.0`, unique id |
| `event_type` | today: `nav.turn`, `nav.route`, `sport.lap`, `training.step`, `ghost.cross` (messages and action receipts use their own screens) |
| `message_key` | i18n key of the text (never a translated string) |
| `priority` | `CRITICAL` > `ACTION_RECEIPT` > `INTERACTION` > `SPORT` > `AMBIENT` |
| `params` | values for the text, already formatted in the HUD language and units |
| `created_at` / `expires_at` | an expired event is never shown (default lifetime 8 s) |
| `source_id` | who published it |
| `dismissible` / `requires_ack` | can be closed / stays until acknowledged (gesture or voice) |
| `locale` | HUD language the params were formatted for |

Scheduler rules: a higher priority pre-empts the event on screen (which goes back in the queue); an event with the
same `(event_type, source_id)` replaces the one on screen or queued (coalescing, no backlog of stale turns); the
queue is bounded at 32 and drops the lowest priority, oldest first.

## 3. BLE sensors (§5.8), `src/glasses/sensors.py`

Standard Bluetooth SIG GATT characteristics, decoded from their specification layouts (tested on specification
byte sequences, not yet on real sensors):

| Characteristic | UUID | Gives |
|---|---|---|
| Heart Rate Measurement | `0x2A37` | `heart_rate_bpm` (8 or 16 bit), RR intervals |
| RSC Measurement | `0x2A53` | `speed_mps`, `cadence_spm`, `stride_length_m`, `distance_m` |
| CSC Measurement | `0x2A5B` | wheel speed and crank `cadence_rpm`, rollover-safe |
| Cycling Power Measurement | `0x2A63` | `power_w` |
| Indoor Bike Data (FTMS) | `0x2AD2` | `speed_mps`, `cadence_rpm`, `power_w`, `heart_rate_bpm` |
| Battery Level | `0x2A19` | `battery_pct` |

## 4. Transport to the glasses (§3.4), `src/glasses/transport.py`

- Frames are ActiveLook commands `0xFF … 0xAA` (built by `src/adapters/activelook.py`).
- Writes are cut to the negotiated MTU minus 3 bytes (minimum 20).
- Queue kinds, highest first: `critical`, `screen`, `update`, `ambient`; at most 64 frames. A new full-screen
  redraw replaces one not yet sent; a frame past its deadline (default 2 s) is dropped and counted.
- Flow control: nothing is written after PAUSE (`0x02`) until RESUME (`0x01`); other values are counted as errors.
- Reconnection back-off: 1, 2, 4, 8, 16, 30 s, then 30 s, 12 attempts.
- One controller at a time: a lock file refreshed by heartbeat; stale after 15 s; taking a live lock over needs
  `openbridge glasses run --takeover`.
- Counters (`frames`, `chunks`, `bytes`, `dropped_late`, `dropped_full`, `superseded`, `flow_errors`, `pauses`),
  the chunk size and the pause state are reported under `transport` by `openbridge glasses status` on a BLE link.

## 5. Phone ↔ PC (Companion relay)

The PC polls the paired, encrypted Companion relay:

| Op | Returns |
|---|---|
| `get_notifications` | new notifications of the allowed apps since the last call: app, sender, text (subject to the privacy setting), time. Kept in memory only (last 50). |
| `get_commands` | voice clips and button presses queued on the phone |
| `status` | includes `language` (`fr` or `en`, the Companion's resolved language) |

## 6. Hub control port

`openbridge glasses run` listens on `127.0.0.1:7791` (`--control-port`), local only. `openbridge glasses press`,
`notify`, `say` and `status` talk to it. HUD Studio uses `127.0.0.1:7789` for glasses frames and gestures
(gesture frame `FF 0A 01 <code> AA`) and `127.0.0.1:7790` for its own control API.

## 7. Settings, `%LOCALAPPDATA%\OpenBridge\glasses.json`

| Key | Values | Default |
|---|---|---|
| `language` | `auto`, `fr`, `en` | `auto` (system language, English if neither) |
| `hud_language` | `follow`, `fr`, `en` | `follow` (same as `language`) |
| `units` | `metric`, `imperial` | `metric` |
| `privacy` | `full`, `sender`, `off` | `full` |
| `apps` | apps whose messages are shown (`set --apps discord,telegram,sms,messages`) | Discord, Telegram, Google Messages, Samsung Messages, SMS |
| `rotate180` | boolean (`set --rotate on\|off`) | false |
| `grant` | what the glasses may run (`tv_remote`, `tv_apps`, `tv_power`, `vacuum`) | none |

Set with `openbridge glasses set …` and `openbridge glasses grant …`, or from the glasses (Settings → Language).

## 8. Languages (§4), `src/glasses/i18n.py`

- Text is addressed by stable keys (`hud.navigation.next_turn`, `menu.settings`…), in `src/glasses/locales/en.json`
  and `fr.json`; both files carry the same keys (a test fails otherwise).
- Missing key → English → the key itself; a screen never crashes on a translation.
- Numbers, distances, durations, pace and speed are formatted per language and per unit system
  (`fmt_distance`, `fmt_duration`, `fmt_pace`, `fmt_speed`): `1,2 km` in French, `1.2 km` in English.
- The Companion uses the same choice (`L.java`: Auto → Français → English) and reports it in `status`.
