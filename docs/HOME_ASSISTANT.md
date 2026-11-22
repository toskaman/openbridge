# Home Assistant bridge

Connect OpenBridge to your Home Assistant, and the lights, plugs, thermostats, media players, blinds, locks and robots
it already knows join OpenBridge at once. That includes Matter, Zigbee and Thread devices paired in Home Assistant.
OpenBridge adds its own layer on top: consent per action, read-back before saying “done”, exact Undo, receipts, and
actions that are refused whatever happens.

> **Validation status:** verified on a real Home Assistant instance (official Docker image) with Home Assistant's demo
> devices: 13/13 checks ([evidence](evidence/home-assistant-real-instance-22nov.md)), plus the automated tests against a
> simulated API ([`tests/fabric/test_home_assistant.py`](../tests/fabric/test_home_assistant.py)). Physical devices
> through Home Assistant are not yet tested.

## Connect

1. In Home Assistant, open your profile, then **Security**, and create a **long-lived access token**.
2. On the OpenBridge PC:

```sh
python -m src.cli ha connect --url http://homeassistant.local:8123 --store-token   # token kept in the Windows vault
python -m src.cli ha status
python -m src.cli ha devices
```

On Linux or macOS, put the token in an environment variable instead: `--token-env OPENBRIDGE_HA_TOKEN`.
The token is never written in clear, never logged and never shown by any API.

Plain `http://` is accepted only on your local network; anything else must use `https://`. Redirects are refused.

## Use

Home Assistant devices appear in the app with the rest of your devices, each with its allowed actions. From the
command line:

```sh
python -m src.cli ha do light.living_room set_brightness --value 40 --consent ALLOW
python -m src.cli ha do switch.coffee_machine turn_on --consent ALLOW
```

Without `--consent ALLOW` nothing is sent.

## What OpenBridge can do

| Device | Actions | Undo |
|---|---|---|
| Lights | turn on, turn off, set brightness | exact |
| Plugs and switches, fans | turn on, turn off | exact |
| Thermostats | set the target temperature (7 to 30 °C, within the device's own range) | exact |
| Media players | turn on, turn off, set volume, play, pause | exact for power and volume |
| Blinds and shutters | open, close, stop | no (physical movement) |
| Locks | lock | no |
| Robot vacuums | start, pause, return to base | no |
| Sensors, alarms | read only | n/a |

## What OpenBridge never does

- **Unlock or open a door**, whatever the consent.
- **Move a garage door or a gate.**
- **Touch an alarm system** (arm, disarm or trigger).
- **List cameras, people or device trackers.** Their state is personal data and OpenBridge has no action for them.
- **Call a service that is not in the table above.** There is no free-form service call.

## Disconnect

```sh
python -m src.cli ha disconnect     # removes the URL and the stored token
```

## Matter

Matter devices are reachable today through Home Assistant's Matter integration. A native Matter controller in
OpenBridge is on the [roadmap](../ROADMAP.md).
