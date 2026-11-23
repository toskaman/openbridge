# A neutral interoperability benchmark

Device makers are measured by the same method, in public, and the results are published as measured. Nobody pays for
a result, and nobody can veto one: a maker can answer it next to the figures, and ask for a re-run after a fix.

## What is measured

Per device, per action, on real hardware (an emulator run is reported separately and never ranked):

| Metric | How |
|---|---|
| **Read-back success** | share of actions the device really did, read back independently (verified / attempted) |
| **Latency** | p50 and p95, from the command to the read-back that confirms it |
| **Exact Undo** | share of reversible changes restored to the exact previous state |
| **Honest failure** | a device that acknowledges but does not act must be reported as not done (never "done") |
| **Refusals** | forbidden actions (unlock, firmware, alarms...) refused before anything is sent: must be 100 % |
| **Recovery** | behaviour after the device, the network or OpenBridge restarts mid-action |
| **Soak** | the same over a long run (hundreds of cycles), to catch drift, leaks and rate limits |

## How it runs

- Home Assistant devices: `openbridge ha soak --cycles N --consent ALLOW --entity ...` changes each listed device and
  undoes every change, recording receipts; `openbridge learn report` gives the latencies.
- Devices integrated with the kit: the generated tests run against the real transport, then the soak.
- Firmware over time, across homes: [quality reports](../QUALITY_REPORTS.md), opt-in.

Each run records the commit, the device, the firmware, the environment and the raw receipts. The method and every
result live in this repository, so anyone can re-run them. Existing results: [benchmark/](../benchmark/STATUS.md)
for the planning models, [DEVICE_EVIDENCE.json](../DEVICE_EVIDENCE.json) for devices.

## What a maker gets

The run on its device, the raw data, a short report, and a slot to reply. On a partner plan, a run every release;
as a service on its own, a one-off run (see [Plans](PLANS.md)).
