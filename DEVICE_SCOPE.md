# Device scope

| Adapter | Discovery | Inspection | Write | Undo |
|---|---|---|---|---|
| SIMULATED Android fixture | Available | Synthetic facts | Blocked | Unavailable |
| Physical Android / ADB | Opt-in USB inventory | Read-only, one phone verified | Blocked | Unavailable |
| Freebox public discovery | Opt-in local endpoint | Identity inspection verified | Blocked | Unavailable |

The fixture is synthetic; its facts are not measurements. Inspection is deterministic, not model-generated. Physical Android inspection requires existing Android USB debugging authorization. The app never accepts the permission on the phone for you. No network scan is performed.

Freebox gateway identity was read locally through its unauthenticated API version endpoint. The application now exposes this public identity through an opt-in adapter. No authenticated router adapter or router changes are implemented.

## Recovery sandbox

An isolated persistent SIMULATED setting supports a bounded change and exact Undo. This is a separate synthetic sandbox, not a physical adapter capability. Its journal persists before changes, detects conflicting state and supports restart recovery. Android and Freebox remain read-only.

## Isolated physical verifier

A separate opt-in CLI adapter is restricted to the screen_off_timeout setting on exactly one authorized USB phone. The tested phone refused this write; its original timeout was independently confirmed unchanged. No physical change or physical Undo success is supported by the evidence. The browser exposes no physical writer. Protected Android authorization is never bypassed.

## Local Meta review

With `--local-meta`, an inspected Android phone's allowlisted numeric facts may be reviewed by a pinned local Llama 3.2 3B model on this PC. Advice is inspect-only; no write path exists. Freebox data is never sent to a model.
