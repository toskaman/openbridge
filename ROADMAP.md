# OpenBridge roadmap

Where OpenBridge is going next, and where partners can steer it. Priorities move with the hardware that
partners provide: **a device on the bench moves to the top of the list.**

Status legend: 🟢 shipped · 🟡 in progress · 🔵 next · ⚪ later / concept

## Now

| | Item | Status |
|---|---|---|
| 🕶️ | **ENGO smart glasses (ActiveLook):** move from emulator-validated to real-hardware-validated. Run the 38 HUD features, the 82 tests and the latency / battery benchmarks on the physical pair. | 🟡 glasses on their way |
| 📊 | **Public benchmark reports per device:** latency, success rate, refusal correctness, linked to CI runs. | 🟡 |
| 🏠 | **Home Assistant bridge:** lights, plugs, thermostats, media players, blinds, locks and robots known to Home Assistant (Matter, Zigbee and Thread included), with consent, read-back and exact Undo. [Guide](docs/HOME_ASSISTANT.md) | 🟢 shipped, verified on a real Home Assistant (demo devices) |
| 🧰 | **Partner integration kit:** `openbridge partner new` scaffolds an adapter, an emulator and passing tests. [Guide](docs/INTEGRATE_YOUR_DEVICE.md) | 🟢 shipped |
| 🤝 | **Partner program:** one adapter, one emulator and one test suite per partner device, with a verified compatibility report. | 🟡 open |

## Next

| | Device family | Planned integrations | Status |
|---|---|---|---|
| 🏠 | Smart home standards | Native Matter controller, ESPHome (Matter, Thread and Zigbee devices already work through the Home Assistant bridge) | 🔵 |
| 🌐 | Networking | OpenWrt, FRITZ!Box, more ISP boxes (read-only by policy first) | 🔵 |
| 📺 | Screens | More Android TV / Google TV models, set-top boxes, projectors, soundbars | 🔵 |
| ⌚ | Wearables | More smart glasses and HUDs, rings, fitness sensors, more Wear OS watches | 🔵 |
| 🤖 | Robots | More robot vacuum and mop brands, lawn mowers, pool robots | 🔵 |

Already built and tested, waiting for more real hardware: capability transplant, control migration, workflow
composer, adaptive routing, device diagnostics, portable dashboards (see the [README](README.md)).

## Later

| | Item | Status |
|---|---|---|
| 📡 | **OpenBridge without a PC:** devices use each other directly through a made-to-measure, self-updating client and an OpenBridge server over the internet. [Concept](docs/concepts/PC_LESS_OPENBRIDGE.md) | ⚪ concept |
| 🚗 | Mobility: EV chargers, automotive and e-bike interfaces | ⚪ |
| 🏭 | Industry: gateways and test benches | ⚪ |

## What partners can influence

- **Priority:** your device category moves up as soon as hardware is on the bench.
- **Feature focus:** which cross-device features are built first for your product.
- **Test and benchmark scenarios:** the cases that matter to your QA and your customers.
- **Publication:** what is published, and when. Material shared under NDA stays private.
- **Emulator depth:** how faithfully your device is modelled for your developers, QA and sales demos.

Have a device that should be on this list? → [Partner program](docs/partners/README.md) ·
**[info@lepcpro.fr](mailto:info@lepcpro.fr?subject=OpenBridge%3A%20Roadmap)** ·
[Partner requests on Discussions](https://github.com/toskaman/openbridge/discussions)

<sub>This roadmap states intentions, not commitments or dates. See the [changelog](CHANGELOG.md) for what has shipped.</sub>
