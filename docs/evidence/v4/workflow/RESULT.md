# Multi-device workflow on owned hardware — 29 Oct 2026 15:02 CET (owner-authorized automation)

Isolated server :18780 at `claude/workflow-runtime` (stopped after). Devices: Android TV (Wi-Fi ADB) + BV9300 phone (USB).

| step | result |
|---|---|
| node manifests | TV: the Meta G3 manifest (Muse Spark run `mr_2679619b7ab09920`, `input.key mute` → `state.audio`), host-rebound; phone: a **fixture** read-only `state.screen` manifest written by Claude for this infrastructure test |
| independent oracle before | TV `muted` false, 20/100 |
| WF1 `tv_mute` ∥ `phone_read` (max_parallel 2, owner workflow grant) | **COMPLETED**: both nodes EXECUTED, 2.0 s |
| oracle after WF1 | **muted true, 0/100** |
| replay of WF1 (same operation id) | **409 OPERATION_REPLAY** |
| WF2 `tv_unmute` (same Meta manifest, second use of its grant) | COMPLETED |
| oracle after WF2 | false, 20/100 (restored) |

Signed workflow receipts and the last manifest receipts are in `run1_PASS.json`; exact driver in `hw_workflow_driver.py`.
Not shown on hardware (covered by unit tests only): failure propagation, cancellation, tampered/forged/revoked grants.
The workflow DAG here is a fixture, not Meta-authored; Muse's planner emitting `obv4.1-wf` is the next integration step.
