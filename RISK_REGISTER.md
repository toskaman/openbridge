# Current risks

1. Evidence comes from one owned phone (Xiaomi, Android 14). Other vendors may refuse `pm disable-user` or report state differently; the adapter fails closed on inconsistency.
2. Physical unplug or authorization loss mid-write is covered by mocked tests and the durable journal, not yet by a physical fault-injection run.
3. The local 3B model needed an explicit sentence template to pass grounding checks; plans that fail validation are blocked, which can make the agent unhelpful but not unsafe.
4. Muse Glimmer (Open Weight bonus route) is unverified until a pinned pull, real inference and benchmark exist. The GPU is shared with other workloads, so offload performance must be measured, not assumed.
5. Loopback isolation does not protect against malicious software running as the same local user. This is a single-user local tool, not an authenticated deployment.
6. Event-start confirmation is participant-reported; organizer answers to the office-hours questions are pending.
