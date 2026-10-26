# Device scope

| Adapter | Discovery | Inspection | Write | Undo |
|---|---|---|---|---|
| SIMULATED Android fixture | Available | Synthetic facts | Blocked | Unavailable |
| Physical Android / ADB | Not implemented | NOT TESTED | Unavailable | NOT TESTED |
| Second physical protocol | Not implemented | NOT TESTED | Unavailable | NOT TESTED |

The fixture is synthetic; its facts are not measurements. Inspection is deterministic, not model-generated. This release requests no USB permissions and performs no network scan.
