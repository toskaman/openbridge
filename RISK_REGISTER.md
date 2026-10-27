# Current risks

1. Hardware diversity: evidence comes from one phone (Xiaomi, Android 14) and one Android TV (Android 11). Other vendors may differ; adapters fail closed and the UI shows vendor-aware guidance.
2. Physical cable unplug during a write is covered by mocked tests and the durable journal, not by a physical run (a real process crash is covered).
3. Muse Glimmer needs ~18 GB; on a 16 GB GPU shared with other models it may need other local models unloaded. The product never substitutes another model silently.
4. Relay security relies on on-screen pairing and the Companion being in the foreground; a compromised paired device could report false observations (they are observe-only and never trigger actions).
5. Loopback isolation does not protect against malicious software running as the same local user.
6. Event-start confirmation is participant-reported; organizer answers to office-hours questions are pending.

| Start-date eligibility (repo created 26 Oct) | Participant reports organizer confirmation that building could start at first push; keep CONTRIBUTIONS.md disclosure | 27 Oct |
