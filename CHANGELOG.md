# What's new in OpenBridge

The newest changes first. Planned work is in the [roadmap](ROADMAP.md).

## Unreleased

- ✨ **Skills wired end to end:** saved skills now run in the server (`SkillService`: state ticks from Home Assistant
  every 15 s, schedules every minute), from the app (Workflows → Saved skills: approve, run, enable / disable,
  remove) and from buttons on a paired watch, phone or TV (at-most-once per press).
  `GET /api/v2/library`, `POST /api/v2/library/*`, `POST /api/v2/remote_controls/skills`. [Guide](docs/SKILLS.md)
- 🔌 **Two new adapters from the kit:** ESPHome lights over the local `web_server` REST API (on/off, brightness,
  toggle; OTA/restart/config refused) and OpenWrt routers over local LuCI JSON-RPC (uptime, WAN, load, DHCP leases;
  read-only by policy like the Freebox). Both are emulator-validated with loopback round-trip tests (18 tests);
  hardware runs are the next step. [ESPHome](docs/partners/esphome_light/README.md) ·
  [OpenWrt](docs/partners/openwrt_router/README.md)
- 🧪 **Advanced tests:** chaos-network suite for the Home Assistant client (refused/timeout/truncated/reset links,
  hostile shapes — all fail closed as `HAError`), adversarial fuzz for every file-driven parser (640 mutated cases;
  found and fixed 3 untyped-error bugs in skills/packs import), deterministic CPace properties plus a loader for the
  draft's own vectors, and micro-benchmarks with ceilings in CI (`scripts/verify/bench.py`).
- 🩹 **Fixes:** the emulator-harness timeout test now passes on Windows (POSIX script path + launch guard), and the
  local API accepts dict queries without a Python 3.14 deprecation warning.
- 🗣️ **3 new home skills:** `home.cover_stop` (stop blinds mid-travel), `home.vacuum_start` and `home.vacuum_dock`
  (robot vacuums through Home Assistant; "robot" in the request picks them, plain "vacuum" keeps the native Tuya
  skills). Wired into `ha say` domains, FR/EN voice training families and the end-to-end battery.
- 📦 **New `energy-saver` skill pack:** "Eco evening" (light to 30 %, standby plug off), nightly standby cull at 1:00,
  "Back to full light". Installs by role, unapproved as always. [Guide](docs/SKILL_PACKS.md)
- 💡 **`create suggest --save [N]`:** save suggested automations as unapproved skill proposals (all, or one by number).
  Fixed `from_suggestion` to consume the real `suggest_recipes` shape (it expected a format nothing produced).
- 🤖 **Vacuum paths unified in docs:** native `vacuum.*` (+ ENGO glasses grant) vs `home.vacuum_start/pause/dock`
  through Home Assistant — "vacuum" picks native, "robot …" picks HA. New `home.vacuum_pause` completes the HA trio
  (registry, `ha say`, voice families, battery).

## v0.5.0: 23 November 2026

> **A demo release**, like the previous ones: it is not yet the final version with OpenBridge's dedicated model wired
> into every part of the app. Supported until three months after 0.6.0 ([support policy](docs/SUPPORT.md)).

### For companies
- 🆓 **Free 90-day evaluation licence** for any company: install it, test it with your products, in your lab and CI,
  no signature needed. [Evaluation licence](LICENSES/OpenBridge-Evaluation-1.0.md) · [Plans](docs/partners/PLANS.md)
  (Community, Evaluation, Partner, OEM) · a [source-available option](docs/LICENSING_FSL_OPTION.md) under study.
- 🧰 **Bring your device, leave with an integration:** `openbridge partner new NAME --from-openapi FILE`, or the
  [Integrate page](https://toskaman.github.io/openbridge/integrate.html) in the browser, turns an OpenAPI description
  into an adapter, an emulator and passing tests. The page and the command line write byte-identical files (tested).
- 📦 **Skill packs:** ready-made cross-brand features (Cinema, Leaving home, Quiet cleaning, Good morning, Good night)
  installed by role on your own devices, in French and English, always waiting for your approval. Partner packs
  follow the same format. `openbridge skills packs / install-pack`. [Guide](docs/SKILL_PACKS.md)
- 🗣️ **A voice model per partner:** a voice profile teaches OpenBridge a brand's product names, phrasings and
  mishearings, offline; a generator writes the training lines for a partner adapter. [Guide](docs/PARTNER_VOICE_MODEL.md)
- 📈 **Quality reports, opt-in:** success rate and latency per device model and firmware, firmware regressions flagged
  across homes. Off by default, nothing identifying, never sent by OpenBridge. [Guide](docs/QUALITY_REPORTS.md)
- ✅ **Verified by OpenBridge:** a label earned from public real-hardware evidence only, never sold, renewed by new runs.
  [Rules](docs/partners/VERIFIED.md) · [neutral benchmark](docs/partners/BENCHMARK.md) ·
  [API audits](docs/partners/AUDIT.md) · [co-marketing](docs/partners/CO_MARKETING.md)
- 🧩 **`openbridge skills ...`** to list, approve, run, export and import saved skills from the command line.

### Release quality
- 📜 [Support policy](docs/SUPPORT.md), [GDPR page](docs/GDPR.md), and a **CycloneDX SBOM** attached to every
  Windows download, attested with Sigstore like the download itself.

### Also in this release
- ⚖️ **Licensing made explicit for partners:** the OpenBridge core stays under PolyForm Strict 1.0.0; the integration
  kit (`openbridge partner new` and every file it generates, plus the integration guide) is now **Apache 2.0**, and a
  partner's own code stays under the partner's licence. A [partner licence term sheet](docs/partners/PARTNER_LICENSE.md)
  (English and French) describes the written licence for using the core commercially. [Licensing](docs/LICENSING.md)

- 🧠 **Devices that learn:** every action updates a per-device profile (success rate, latency, states seen).
  `openbridge learn report`. [Guide](docs/DEVICE_LEARNING.md)
- ✨ **New features from what works:** `openbridge create suggest` combines proven capabilities into
  cross-device features such as Cinema mode or Leaving home.
- 🔗 **Devices that talk to each other:** `openbridge links add / approve / watch`. Edge-triggered, approved by
  you, cooldowns and a loop guard, every firing read back.
- 🧪 **Long soak test:** `openbridge ha soak`. 1 480 actions on a real Home Assistant: 92.8 % verified.
  Four bugs found and fixed. [Evidence](docs/evidence/device-learning-soak-22nov.md)
- 🧩 **Skill library:** features created by the AI (or suggested, or written by hand) are saved as recipes that run
  with **no AI model**: manual, on a device state change, or on a schedule; exportable to a signed file, importable
  elsewhere (always re-approved). [Guide](docs/SKILLS.md)
- ↩️ **Exact Undo, really exact:** lights come back with their brightness and colour, media players playing or paused.
  Slow devices (vacuums, locks, blinds, media players) get longer read-back windows, stretched by the latency
  OpenBridge has learned. On the real Home Assistant (demo devices): Undo exact 84.3 % → **100 %**, verified
  92.8 % → **95.9 %**. [Evidence](docs/evidence/home-assistant-undo-readback-23nov.md)
- 🏠 **`ha soak --entity`** to test only the devices you choose on a real home, plus a
  [procedure](docs/HOME_ASSISTANT.md#test-with-your-real-devices) for Zigbee and Matter bulbs and plugs.
- 🔐 **CPace pairing:** a recorded pairing no longer lets anyone guess the 6-digit code offline (Companion 0.13.0;
  older Companions still pair, with a warning). Voice recognition checks free GPU memory and falls back to the CPU.
- 🌐 **Tailscale-friendly:** devices and Home Assistant reached through a WireGuard mesh count as local.
  [How to use OpenBridge from outside](docs/SKILLS.md#using-openbridge-over-the-internet)
- 🧠 **Dedicated model, v2 data:** 2 433 training examples and an independent test set written by hand, never trained on.
- 🗣️ **Talk to your home: `openbridge ha say "..."`** in French, US English or UK English. OpenBridge's own model
  (Llama 3.2 3B, trained on 30 kinds of home devices) understands, the gate checks, Home Assistant acts, the
  result is read back. 13 new skills: on/off, brightness, temperature, play/pause/volume, blinds, lock, undo, plus
  **creating a new device link by voice**, suggesting features and reporting what was learned. Hand-written home
  requests: **100 %** (Llama 3.1 8B: 16.7 %); 47 / 47 spoken requests understood on a real Home Assistant, 30 / 30
  actions verified, a link created by voice fired for real; about 1 s per request through Ollama. [Details and limits](docs/AI_TRAINING.md)

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
