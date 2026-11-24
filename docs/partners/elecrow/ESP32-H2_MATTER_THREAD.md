# ESP32-H2 on the Elecrow CrowPanel: Matter and Thread notes

> **Status: planned. No test has been run yet, so this page contains no results.**
> It will be filled in as the tests run on the real module. Promised to [Elecrow](https://www.elecrow.com)
> (see [ELECROW.md](../ELECROW.md)); tracked in [partners.json](../partners.json).

Hardware: [Elecrow CrowPanel Advance 4.3-inch HMI (ESP32-S3)](https://www.elecrow.com/crowpanel-advance-4-3-hmi-esp32-800x480-ai-display-ips-touch-artificial-intelligent-screen.html)
with the ESP32-H2 wireless module (IEEE 802.15.4: Thread, Zigbee).

## What will be tested

| # | Test | Pass condition |
|---|---|---|
| 1 | Module detected by the CrowPanel firmware | H2 answers over the module interface; firmware version read back |
| 2 | Thread network | H2 joins or forms a Thread network; role and partition ID read back |
| 3 | Thread Border Router path | An IPv6 device on Thread is reachable from the OpenBridge PC |
| 4 | Matter commissioning over Thread | A Matter-over-Thread device is commissioned; its descriptor clusters are read |
| 5 | Matter control with read-back | On/Off (and Level where available) changed by OpenBridge, then read back from the device |
| 6 | Refusal path | A command on a stale or unreachable device is refused with a reason, never reported as done |
| 7 | Zigbee (if supported by the module firmware) | A Zigbee light joins; on/off with read-back |
| 8 | Stability | Repeated on/off cycles with success rate and latency recorded (p50, p95) |

## Report format (once run)

For each test: date, firmware versions (CrowPanel, H2, ESP-IDF / Matter SDK), setup, result
(VERIFIED / FAILED / NOT SUPPORTED), raw evidence file, and what Elecrow could improve (documentation,
firmware, examples). Every passed run is also recorded in
[DEVICE_EVIDENCE.json](../../DEVICE_EVIDENCE.json) and appears in the
[hardware compatibility report](../../HARDWARE_TEST_MATRIX.md).

## Results

None yet.
