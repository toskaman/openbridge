# MQTT gateway

Connect OpenBridge to a local MQTT broker (Mosquitto and friends), and Tasmota plugs and dimmers,
Shelly Gen1 relays and Zigbee2MQTT lights and plugs join at once — with OpenBridge's own layer on
top: allowlisted actions, read-back before saying "done", exact Undo, receipts, and refusals.

> **Validation status:** emulator-validated against a loopback fake broker
> (`tests/fabric/test_mqtt.py`, 14 tests: codec vectors, connect/subscribe/publish, the three
> families, discovery, ingest). No real broker run yet.

## Connect

Point OpenBridge at the broker (LAN only, optional username/password):

```python
from src.adapters import mqtt as M
from src.fabric import mqtt_ingest as MI
from src.fabric.registry import Registry

client = M.Client('192.168.1.10', username='openbridge', password='...')
client.connect()
reg = Registry()
MI.ingest_mqtt(reg, client, salt, seconds=5.0)
```

The same through the command line (passwords only via environment, never on the command line):

```sh
openbridge mqtt discover --host 192.168.1.10 --user openbridge --password-env MQTT_PASSWORD
openbridge mqtt do --host 192.168.1.10 --family tasmota --id tasmota_plug --action power --value on --consent ALLOW
openbridge mqtt do --host 192.168.1.10 --family z2m --id bulb --action brightness --value 50 --consent ALLOW
```

## What OpenBridge can do

| Device | Reads | Actions | Undo |
|---|---|---|---|
| Tasmota plug/dimmer | power, brightness | on, off, brightness, toggle | exact (power, brightness) |
| Shelly Gen1 relay | power, watts | on, off, toggle | exact (power) |
| Zigbee2MQTT light/plug | power, brightness | on, off, brightness, toggle | exact (power, brightness) |

Every write is published QoS 1 and read back from the state topics (6 s window by default); an
action still unconfirmed is reported as *unverified*, never as done. A silent device is never
reported done either (`test_silent_device_never_reported_done`).

## Refused by policy

No firmware, OTA, reset or configuration path exists in the transport (`Update`, `Reset` and
friends have no sender); `POLICY` refuses them before anything is sent, like everywhere else.

## Topics (fixed conventions)

- Tasmota: reads `tele/<t>/STATE`, `stat/<t>/POWER`, `stat/<t>/RESULT`; writes `cmnd/<t>/Power|Dimmer`.
- Shelly Gen1: reads `shellies/<id>/relay/<n>` (+ `/power` watts); writes `.../command`.
- Zigbee2MQTT: reads `zigbee2mqtt/<name>`; writes `zigbee2mqtt/<name>/set` (brightness 0–254).

Discovery subscribes to `tele/+/STATE`, `shellies/+/relay/+` and `zigbee2mqtt/+` for a bounded
time; bridge, availability and `/set` topics are ignored. Raw topics stay off the graph snapshot
(only opaque identifiers and labels); see the ingest test.

## Limits

- MQTT 3.1.1 subset: QoS 0–1, no TLS (LAN-only, documented), no retained-store serving, no MQTT 5.
- No Shelly Gen2+ (different RPC-over-MQTT dialect), no Tasmota covers/blinds yet (same pattern).
- The client is poll-based with no background threads: callers poll regularly.
