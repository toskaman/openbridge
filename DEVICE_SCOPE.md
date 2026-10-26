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
