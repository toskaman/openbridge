# Device scope

| Adapter | Discovery | Inspection | Write | Undo |
|---|---|---|---|---|
| SIMULATED Android fixture | Available | Synthetic facts | Blocked | Unavailable |
| Physical Android / ADB | Opt-in USB inventory | Read-only, one phone verified | Blocked | Unavailable |
| Second physical protocol | Not implemented | NOT TESTED | Unavailable | NOT TESTED |

The fixture is synthetic; its facts are not measurements. Inspection is deterministic, not model-generated. Physical Android inspection requires existing Android USB debugging authorization. The app never accepts the permission on the phone for you. No network scan is performed.

Freebox gateway identity was read locally through its unauthenticated API version endpoint. No authenticated router adapter or router changes are implemented.
