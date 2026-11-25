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
| Lights | turn on, turn off, set brightness, colour temperature (kelvin), colour (hue 0-360) | exact: on/off, brightness and colour (temperature or hue) |
| Plugs and switches | turn on, turn off | exact |
| Fans | turn on, turn off, set speed (0-100 %) | exact |
| Thermostats | set the target temperature (7 to 30 °C, within the device's own range), set mode (off, heat, cool, auto, dry, fan_only) | exact |
| Media players | turn on, turn off, set volume, mute/unmute, play, pause, next/previous track | exact for power (playing / paused come back too), volume and mute; next/previous verify the player is active |
| Blinds and shutters | open, close, stop | no (physical movement) |
| Locks | lock | no |
| Robot vacuums | start, pause, return to base | no |
| Sensors, alarms | read only | n/a |

> **Two paths to a Tuya vacuum.** A Tuya robot exposed both natively and through Home Assistant can be driven two
> ways: the native `vacuum.*` skills (plus the ENGO glasses `vacuum` grant, both over `tuya_command`) and the Home
> Assistant skills `home.vacuum_start`, `home.vacuum_pause`, `home.vacuum_dock` (over `ha_command`). Say "vacuum" for
> the native path, "robot …" for the Home Assistant path. Pick one target per automation or button so two paths never
> drive the same robot.

## Slow devices

A command is “done” only when Home Assistant reads the expected state back. Slow devices get a longer read-back
window: 20 s to start a robot vacuum, 30 s to send it home, 20 s for a lock, 60 s for blinds, 10 to 15 s for media
players, 6 s for everything else. When OpenBridge has learned that a device is slower (its 95th-percentile latency),
the window grows to twice that plus one second, up to 90 s. An action still unconfirmed after its window is reported
as *unverified*, never as done; reading the device again later (`ha.confirm`) can confirm it.

## Test with your real devices

The soak test changes devices and undoes the changes. On a real home, **list the devices it may touch**, and leave
out anything that must stay powered (fridge, freezer, network gear, medical devices):

```sh
python -m src.cli ha devices                          # entity ids
python -m src.cli ha soak --cycles 5 --consent ALLOW --entity light.desk --entity light.kitchen --entity switch.lamp_plug
```

Suggested first run, and what to send back (the JSON output, or `docs/evidence/` if you want it published):

| Device | Why |
|---|---|
| 1 Zigbee bulb with colour temperature | exact Undo of brightness and colour |
| 1 Zigbee or Matter colour bulb | exact Undo of hue / saturation |
| 1 Matter or Wi-Fi plug **with a lamp on it** | on/off and read-back latency |
| 1 media player (TV or speaker) | playing / paused after Undo, slower read-back |
| 1 thermostat, if you have one | target temperature and its Undo |

The output reports, per action: runs, verified, unverified, exact Undo rate, and `verified_late` (actions that were
slower than their window but confirmed by a second read-back; a sign that window should grow).

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
