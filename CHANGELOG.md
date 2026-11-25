# What's new in OpenBridge

The newest changes first. Planned work is in the [roadmap](ROADMAP.md).

## Unreleased

- **VoiceAI Oracle for ENGO 3 & multi-device microphones:** added [`src/ai/oracle.py`](src/ai/oracle.py) (local `<1 ms` math evaluator, `ddgs` `lite` web search with 120s cache & speculative partial-transcript prefetch, `127.0.0.1` HTTP/1.1 keep-alive for warm Ollama/Groq/Gemini Flash, 60s TTL answer cache) and [`src/ai/mic_oracle.py`](src/ai/mic_oracle.py) (pure-Python energy VAD + universal mic client for PC/USB/Bluetooth mics). Integrated `OracleScreen` and `Hub.oracle()` in `src/glasses/` + `push_oracle_answer()` in `src/adapters/activelook.py`, `POST /api/v2/voice/oracle` & `GET /api/v2/voice/oracle/status` in `api_v2.py`, long-polling wakeup (`wait_ms=3000`) in `RelayServer.java` & `command_drain.py`, and the continuous `OracleVoiceActivity` screen (`Oracle ENGO` button) in the Android/Wear OS Companion.
- **New hardware partner: [AirGradient](https://www.airgradient.com).** AirGradient is sending an [AirGradient ONE Indoor Monitor I-9PSL (Kit)](https://www.airgradient.com/shop/#!/AirGradient-ONE-Indoor-Monitor-I-9PSL-Kit/p/594725501): PM2.5, CO₂, TVOC, NOx, temperature and humidity on an ESP32-C3, read over its local API, for air-aware alerts and automations. Credited in the README, the installation guide, the compatibility report and the website; checked in CI. [Partner page](docs/partners/AIRGRADIENT.md)
- **Custom controls:** a new Controls page lets you build your own buttons for each paired screen (TV, watch, phone): pick a device, pick what the button does, name it. Buttons are saved as profiles ("Movie night", "Cleaning"), several per screen, and sent to the screen in one click after a confirmation. You can copy what an AI proposal installed into a profile and edit it, reorder by drag and drop, and the active profile comes back by itself after a Companion or PC restart. Same safety path as the Studio: every button is checked again by the server when sent. [Guide](docs/CUSTOM_CONTROLS.md)
- **What's new on the front page:** a dated, timed log of every update just above the demo, older entries folded away; kept up to date on every change (rule in AGENTS.md, checked by `tests/unit/test_whats_new.py`).
- **New hardware partner: [Elecrow](https://www.elecrow.com).** The [CrowPanel Advance 4.3-inch](https://www.elecrow.com/crowpanel-advance-4-3-hmi-esp32-800x480-ai-display-ips-touch-artificial-intelligent-screen.html)
  (ESP32-S3) and an ESP32-H2 module join the bench, for an OpenBridge control panel and Matter / Thread testing.
  [Partner page](docs/partners/ELECROW.md)
- **Partner commitments are now enforced in CI:** [partners.json](docs/partners/partners.json) lists what each
  partner was promised; a test fails if a credit or a promised report goes missing.
- **Cleaner repository:** light and dark illustrations, lighter demo clips, and working notes moved to `docs/internal/`.
- 🧭 **A shorter, more professional README:** one headline, two buttons, a row of proof figures and the partner logos up top; the French version moves to [README.fr.md](README.fr.md), and the longer sections move to [Why OpenBridge](docs/WHY_OPENBRIDGE.md) and [Hardware partners](docs/partners/HARDWARE_PARTNERS.md). The website gains Heltec and the same two sections.
- 🗣️ **Partner voice adapter, measured:** trained on the fictional Acme brand from the official v4 model, it gets 98.6 %
  of held-out Acme requests right (official model: 45.1 %) with no loss on the base test sets.
  [Results](docs/PARTNER_VOICE_MODEL.md#example-results-the-fictional-acme-brand-24-november-2026)
- 📡 **New hardware partner: [Heltec Automation](https://heltec.cn/).** Heltec is sending a WiFi LoRa 32 V4 board
  (ESP32-S3 + SX1262 LoRa): the first physical ESP32 for the agent, so far verified on QEMU only. [README](README.md#-heltec-automation)
- 🥽 **Tested on the PICO headset emulator:** the Companion pairs with PICO OS 6 (official PICO Emulator 6.2.1), runs
  a signed relay round trip and is refused once revoked. The emulator image crashes hardware-accelerated apps, so
  `python -m dev.build_companion --software-rendering` makes a test-only build; `cloud_e2e.py` now handles multi-display
  focus, system dialogs and offline emulators. [Guide](docs/PICO_EMULATOR.md)
- 🧠 **OpenBridge's own model v4 is now the official one:** trained on household chores, it gets 88 % of
  hand-written chore requests right (v3: 47 %) and never runs one as a command; home requests held out: 93.2 %
  (v3: 90.2 %). Two hand-written requests regressed and are listed. `train_lora.py --vram-fraction` keeps training
  fast on Windows. [Details](docs/AI_TRAINING.md#v4-24-november-2026-household-chores-now-the-official-model)

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
- 🔌 **FRITZ!Box adapter from the kit:** local TR-064 SOAP (digest auth), uptime, WAN, hosts, Wi-Fi clients,
  model and firmware; read-only by policy. Emulator-validated with loopback round-trip tests (8 tests).
  [Guide](docs/partners/fritzbox_router/README.md)
- 🔐 **BridgeWindows v5 sealed-transport core:** pure-Python XChaCha20-Poly1305 + HKDF + PSK-confirmed X25519
  handshake and record layer (`src/fabric/sealed.py`, 19 tests), verified byte-for-byte against libsodium,
  `cryptography` and PyCryptodome; C backend auto-used when installed (same wire bytes). C agent, negotiation
  and live proofs remain; v4 stays the shipping transport.
- 🧱 **Matter phase 0:** TLV codec with hand-derived vectors, fuzz and an official-vector loader
  (`src/fabric/matter_tlv.py`), plus the phased controller plan (PASE/CASE → commissioning → clusters).
  [Plan](docs/MATTER_PLAN.md)
- 🗺️ **Companion platforms surveyed:** what a port needs (protocol checklist) and verdicts for 10 OS families —
  Linux tray first, one web kit for Tizen + webOS TVs, Swift core for iOS + macOS, AAOS variant, Playdate
  prototype; HarmonyOS phones blocked, KaiOS thin-client only. [Plan](docs/COMPANION_PLATFORMS.md)
- 📡 **MQTT gateway:** Tasmota, Shelly Gen1 and Zigbee2MQTT devices over a local broker (stdlib MQTT 3.1.1
  subset, typed on/off/brightness/toggle with read-back and exact Undo, discovery, graph ingest). 14 loopback
  tests. [Guide](docs/MQTT.md)
- 🏠 **7 new Home Assistant actions:** light colour temperature + colour, fan speed, media next/previous/mute,
  thermostat mode — each gated by device capabilities, read back, exactly undone, voiced in FR/EN (`ha say`
  domains, training families, battery) and soaked.
- 🔒 **Legacy pairing cut:** PBKDF2 pairing refused by default (offline-guessable); CPace required unless the
  owner sets `OPENBRIDGE_PAIRING_ALLOW_LEGACY=1` for the transition. Already-paired relays unaffected.
- 🧰 **One LAN guard** (`src/fabric/netguard.py`) replaces 5 copies; partner kit ships a loopback HTTP fake
  (`tests/partners/httpfake.py`, 3 adapter suites refactored onto it); ESPHome covers switches, sensors,
  covers and climate reads.
- 📜 **OpenAPI 3.0 for `/api/v2`** (102 paths, `docs/api/openapi.json`, coverage-enforced by tests) for
  third-party companions and clients.
- 🌙 **Overnight hardening:** `openbridge mqtt discover|do` CLI (passwords via env only); discovery and gateway
  ingests stay alive at the registry caps (new devices counted as capped, merges still apply); the session
  journal keeps every OPEN change plus the newest 200 closed ones instead of growing forever; voice-profile
  and skills-bundle parsers fail typed on hostile shapes (found by extended fuzz); endurance report counts
  capped devices. [Night evidence](docs/evidence/overnight-24nov.md)

- 🏃 **Sport on the glasses:** running and cycling dashboards, interval workouts (`--workout 6x400@4:15`), a Ghost
  of a previous session and GPX navigation (next turn, distance left, off-route, arrival). Standard Bluetooth sensors
  are decoded: heart rate, running and cycling speed and cadence, power, smart trainers. Tested on simulated data
  and in HUD Studio; real outings come with the glasses. [Guide](docs/GLASSES.md#sport)
- 🇫🇷 🇬🇧 **Français / English:** Settings → Language on the glasses, `openbridge glasses set --lang fr|en|auto`,
  an optional separate glasses language (`--hud-lang`) and units (`--units`); the Companion app has the same switch.
  The PC web interface is still English-only.
- 📶 **Steadier Bluetooth to the glasses:** writes sized to the link, no writing while the glasses ask to pause,
  stale screens dropped instead of queued, bounded reconnection, and one OpenBridge process at a time
  (`--takeover` to switch). Unit-tested; to measure on the real pair.
- 📋 **ENGO dossier 20–25:** master product spec, a 334-feature traceability matrix generated from a registry (0
  validated on real hardware yet, by design), the real-hardware validation procedure, the manufacturer package,
  the data contracts and the compatibility matrix. [ENGO folder](docs/partners/engo/README.md)

- 🕶️ **ENGO glasses hub:** `openbridge glasses run` puts messages (Discord, Telegram, SMS, Messages), a TV remote
  (volume, apps, arrows, play/pause, sleep/wake), the robot vacuum and voice commands from the phone's mic on ENGO
  glasses, in a new line-icon design. One wave: next; two: open; three: back. Nothing acts before a one-time grant
  on the PC; every action is a typed primitive through the gate. Companion: notification access and
  `get_notifications`. Verified end to end in HUD Studio; real glasses next. [Guide](docs/GLASSES.md)

- 🧠 **OpenBridge's own model is now the official one, everywhere:** `openbridge ask`, the app's command box and
  the Companions' voice understand requests with `openbridge-intent` (v3) first, and fall back to the general
  Llama 3.2 3B only when it is not installed. Each answer says which model understood it; `openbridge models list`
  checks the install against the pinned digest. [Details](docs/AI_TRAINING.md#the-official-model-everywhere-a-request-is-understood)
- 🗑️ **« Sors les poubelles » no longer empties the robot vacuum:** a robot-vacuum or TV command whose request never
  names the device is now asked back instead of run, whatever the model. New training data for chores (French, US
  and UK English) for the next model version. [Details](docs/AI_TRAINING.md#honest-limits)

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
