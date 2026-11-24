# Current risks

Updated 23 Nov 2026. The 27 Oct snapshot is kept below for history.

| # | Risk | Mitigation today | Next step |
|---|---|---|---|
| 1 | **Hardware diversity.** Real-hardware evidence covers a few devices (Xiaomi and Blackview phones, one Android TV, a Galaxy Watch7, a Tuya vacuum, a Freebox, Windows PCs). Other vendors may behave differently. | Adapters fail closed; every action is read back and reported as unverified when it cannot be confirmed. | Partner hardware; real Zigbee / Matter devices through Home Assistant ([procedure](HOME_ASSISTANT.md#test-with-your-real-devices)). |
| 2 | **Old Companions pair with the legacy code derivation**, which a recorded pairing exposes to offline guessing. | CPace pairing in Companion 0.13.0; legacy pairings are labelled `legacy-v1` with a warning; `OPENBRIDGE_PAIRING_REQUIRE_PAKE=1` refuses them. | Reinstall Companion 0.13.0 on every device, re-pair, then make CPace mandatory by default. |
| 3 | **BridgeWindows v4 is authenticated but not encrypted** on the LAN. | PSK of 16+ characters, mutual HMAC, specific LAN bind address, read-only allowlist. | v5 sealed transport (X25519 + AEAD), agent and master. |
| 4 | **Local models are weak at planning**; the dedicated model is not shipped yet. | Safety never depends on the model: typed skills, consent per action, read-back, refusals by policy. | Dedicated model (v2 training in progress), then quantized serving through Ollama. |
| 5 | **Large local models compete for one GPU.** | Pinned model registry, STT VRAM admission with CPU fallback, worker isolation. | Idle TTL for the STT worker. |
| 6 | **Loopback isolation does not stop malicious software running as the same local user.** | Out of scope by design; secrets in the OS vault, never logged. | — |
| 7 | **A compromised paired device can report false observations.** | Observations are observe-only and never trigger actions by themselves. | Cross-device corroboration for safety-relevant observations. |

## Snapshot of 27 Oct 2026 (history)

1. Hardware diversity: evidence comes from one phone (Xiaomi, Android 14) and one Android TV (Android 11). Other vendors may differ; adapters fail closed and the UI shows vendor-aware guidance.
2. Physical cable pull during revert is verified on one phone, including quarantine and exact recovery after reconnect. Cable loss during other write phases/devices remains unproven. Five process-kill recovery points are separately recorded in EVIDENCE_LEDGER.md.
3. Muse Glimmer needs ~18 GB; on a 16 GB GPU shared with other models it may need other local models unloaded. The product never substitutes another model silently.
4. Relay security relies on on-screen pairing and the Companion being in the foreground; a compromised paired device could report false observations (they are observe-only and never trigger actions).
5. Loopback isolation does not protect against malicious software running as the same local user.
6. Event-start confirmation was participant-reported; organizer answers to office-hours questions were pending.
