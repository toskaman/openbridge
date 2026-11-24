# Elecrow × OpenBridge

**[Elecrow](https://www.elecrow.com)** is an OpenBridge hardware partner. Elecrow designs and manufactures
open hardware for makers and product teams, including the CrowPanel range of ESP32 touch displays.

| Hardware | Role in OpenBridge |
|---|---|
| **[CrowPanel Advance 4.3-inch HMI (ESP32-S3)](https://www.elecrow.com/crowpanel-advance-4-3-hmi-esp32-800x480-ai-display-ips-touch-artificial-intelligent-screen.html)** | 800×480 IPS touch screen with an ESP32-S3, Wi-Fi and Bluetooth LE. Target: a wall-mounted or desk OpenBridge control panel that shows the controls OpenBridge creates, and runs the native ESP32 agent. |
| **ESP32-H2 wireless module** | Thread and Zigbee radio (IEEE 802.15.4) for the CrowPanel. Target: Matter over Thread and Zigbee testing, without going through a third-party hub. |

## Status

| Step | Status |
|---|---|
| Partnership agreed | Done, 24 Nov 2026 |
| CrowPanel Advance 4.3 integration | In progress |
| ESP32-H2 Matter / Thread testing | Planned. Results will be published in [ESP32-H2 Matter and Thread notes](elecrow/ESP32-H2_MATTER_THREAD.md) |
| Entry in the [hardware compatibility report](../HARDWARE_TEST_MATRIX.md) | Listed as a partner; test rows are added only once a run on the real board passes |

As for every device, nothing is claimed before it is verified on the real hardware. Emulator results, if
any, are labelled as emulator results.

## What OpenBridge committed to

These commitments are tracked in [partners.json](partners.json) and checked in CI
([COMMITMENTS.md](COMMITMENTS.md)), so they cannot silently disappear.

1. **Partner credit.** Elecrow is listed as a hardware partner in the README partner section, with a direct
   link to the CrowPanel Advance 4.3-inch product page.
2. **Credit in the repository and reports.** Elecrow is credited, with a link to elecrow.com, in the
   [README](../../README.md), the [installation guide](../QUICKSTART.md) and the
   [hardware compatibility report](../HARDWARE_TEST_MATRIX.md), and on the project website.
3. **ESP32-H2 report.** A short technical report on the ESP32-H2 Matter and Thread testing, published in
   [elecrow/ESP32-H2_MATTER_THREAD.md](elecrow/ESP32-H2_MATTER_THREAD.md) once the tests are run.
4. **Media authorization.** See below.

## Media authorization

Granted on 24 November 2026 by the OpenBridge author: **Elecrow may reuse screenshots and videos from
OpenBridge integration demos on its official channels.**

A mention of "OpenBridge" with a link to https://github.com/toskaman/openbridge is appreciated. Demo footage
may show other brands' devices (TVs, watches, phones) in the background; those remain their owners'
trademarks.

## Contact

info@lepcpro.fr (English or French).
