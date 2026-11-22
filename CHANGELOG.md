# What's new in OpenBridge

The newest changes first. Planned work is in the [roadmap](ROADMAP.md).

## Unreleased

- 🧠 **Devices that learn:** every action updates a per-device profile (success rate, latency, states seen).
  `openbridge learn report`. [Guide](docs/DEVICE_LEARNING.md)
- ✨ **New features from what works:** `openbridge create suggest` combines proven capabilities into
  cross-device features such as Cinema mode or Leaving home.
- 🔗 **Devices that talk to each other:** `openbridge links add / approve / watch`. Edge-triggered, approved by
  you, cooldowns and a loop guard, every firing read back.
- 🧪 **Long soak test:** `openbridge ha soak`. 1 480 actions on a real Home Assistant: 92.8 % verified.
  Four bugs found and fixed. [Evidence](docs/evidence/device-learning-soak-22nov.md)

## v0.4.0: 22 November 2026

### New in this release
- 🏠 **Home Assistant bridge:** everything your Home Assistant knows joins OpenBridge, Matter, Zigbee and Thread
  devices included. Allowlisted actions per device, consent per action, read-back before “done”, exact Undo. OpenBridge
  never unlocks a door, never moves a garage door or a gate, never touches an alarm, and never lists cameras or people.
  Verified on a real Home Assistant instance with its demo devices (13/13). [Guide](docs/HOME_ASSISTANT.md)
- 🧰 **Partner integration kit:** `openbridge partner new "Your Device"` writes an adapter, an emulator, a graph entry,
  tests that pass on day one and a checklist. [Guide](docs/INTEGRATE_YOUR_DEVICE.md)
- 🪟 **Windows download:** a 15 MB zip with Python included; unzip and double-click. Built in CI, smoke-tested and
  published with Sigstore build provenance.
- 🔐 **Security signals:** CodeQL analysis on every change, OpenSSF Scorecard, signed commits and tags.
- 🎮 **Website:** in-browser simulation, Compatibility and Benchmarks pages, French and English.
- ⌨️ **`openbridge demo`:** the offline demo under a plain name (`judge demo` still works).

### Earlier in November

### Partners
- 🤝 **Partner program launched:** [what a hardware partner gains](docs/partners/README.md), how a
  partnership works, and the ENGO case study. Partners keep their hardware: donated units or a permanent loan,
  never a time-limited one.
- 🕶️ **ENGO joins as the first hardware partner** (ActiveLook heads-up display smart glasses).
- 🖥️ **HUD Studio:** a professional emulator of the ENGO glasses, with Pixels / OLED / Lens views, a frame
  inspector, metrics, session recording, PNG / GIF export and a control API. The official ActiveLook Android app
  drives it over the real binary protocol.
- ✨ **38 HUD features** and **82 dedicated tests**, all emulator-validated while the glasses are on their way.
- 📘 **The ENGO technical dossier is now fully in English** (19 documents).

### Product
- 🔓 **No paid AI models any more.** The built-in AI runs locally, for free.
- 🔌 **Connect your own AI or API by hand:** any OpenAI-compatible server or Ollama (LM Studio, llama.cpp,
  OpenRouter presets), from the Settings screen or with `openbridge ai`. Keys stay in the Windows vault or an
  environment variable, and requests to any AI outside this PC need your consent.
- 🧭 **New onboarding** on the home screen, and clearer empty states.

### Project
- 🧪 **CI:** the HUD renderer tests run in a dedicated job; the main suite stays dependency-free on Linux,
  Windows and macOS.
- 🔐 [Security policy](SECURITY.md), [privacy note](docs/PRIVACY.md), commercial and partner
  [licensing](docs/LICENSING.md), [roadmap](ROADMAP.md) and this changelog.
- 🌐 New project website and a one-page partner brief (PDF).
- 💡 Concept published: [OpenBridge without a PC](docs/concepts/PC_LESS_OPENBRIDGE.md) (description only, not
  integrated).
- ⚖️ Licensing clarified: [PolyForm Strict 1.0.0](LICENSE) only.

## v0.3.2: 4 November 2026
- 🎬 Official 3-minute demo video, re-voiced, linked from the project page.

## v0.3.0 and v0.3.1: 3 November 2026
- ✅ Release freeze: every claim in the README is backed by the
  [evidence registry](docs/DEVICE_EVIDENCE.json) and the [hardware test matrix](docs/HARDWARE_TEST_MATRIX.md).
- 📺 TV power controls (sleep and wake, read back on the device).

## v0.2.0: 1 November 2026
- 📺 **AI-made control panels on the TV:** vacuum buttons generated on demand, pressed on a real Android TV,
  with the robot's state read back.
- ⌚ **The watch becomes a TV remote:** volume controls created on a Galaxy Watch7, drive the TV, then removed.
- 🗣️ Voice requests from the phone, TV and watch, transcribed locally on the PC.
- 📶 Direct Wi-Fi pairing for the companions, no USB debugging needed.
- 🧩 Capability transplant, control migration, workflow composer, adaptive routing, device diagnostics and
  portable dashboards.
- 🛡️ Permission center, hardware intelligence (measurements and benchmarks), stress and failure-matrix tests.

## Late October 2026
- 🤖 Robot vacuum (Tuya, local network): start, pause, dock, locate, with state read back.
- 🌐 Freebox Delta router: network inventory, read-only by policy.
- 💻 Remote agents on Windows PCs, plus Windows XP, Windows 7 and Linux guests; native ESP32 agent.
- 📱 Android / Android TV / Wear OS companion with signed, sealed, replay-protected pairing.
- 🧠 Local AI tiers on the PC, with strict validation of every AI proposal.

## v0.1.0 previews: 26–27 October 2026
- 🚀 First public previews: local device workspace, physical action verification, capability forge.
