# 150-second demo storyboard (V4-06)

Real app captures only, captioned, names redacted (`?redact`). Each beat shows the status label on screen. Record only after the pending hardware runs below are done; otherwise drop the beat rather than simulate it.

| Time | Beat | Screen | Proof shown | Needs before recording |
|---|---|---|---|---|
| 0–12 s | Problem | Device Fabric empty, then "Discover my environment" | — | — |
| 12–32 s | One graph across transports | Topology: ISP Router API (e.g., Freebox OS / UPnP-IGD), phone (USB), TV (ADB Wi-Fi), BLE via TV relay, Watch7, PC 2 | REAL_HARDWARE_VERIFIED chips | — |
| 32–60 s | "Why did the TV disconnect?" | TV → Diagnose across transports → hypotheses with cited entries and counterexamples; Re-measure (read-only) | timeline + hypotheses | real TV+router timeline capture (10 min) |
| 60–80 s | Ask Meta, privately | Prepare Meta cloud review → split view local vs outgoing bytes, diff, consent → Muse Spark ranking | live receipt (model, payload hash) | supervised credit permit |
| 80–100 s | Change only what can be undone | Agent plan → consent → act → read-back → crash drill clip → exact Undo | 5/5 crash receipt | — |
| 100–115 s | See the screen like the owner | Visual read-back on the TV: CONFIRMED / INCONCLUSIVE | Glimmer local | `dev.visual_readback_tv` run |
| 115–130 s | Voice | Push-to-talk "Trouve les appareils Bluetooth via la télé" → transcript → proposal → Run | Muse Voice Transcribe | first live STT receipt |
| 130–145 s | Measured, not claimed | Ablation table (rules 20/24 + model arms), Glimmer vs Llama | registered results | model arms run |
| 145–150 s | Boundaries | "Meta-only runtime · read-only by default · exact Undo" | — | — |

Cut list if a beat is not proven by recording day: drop it, keep the timing of the others, never replace with mock-ups.
