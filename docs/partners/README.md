<p align="center">
  <img src="../assets/readme/partner-value.svg" width="100%" alt="Partner with OpenBridge: new features, interoperability, tests and benchmarks, wider compatibility. ENGO case study.">
</p>

# Partner with OpenBridge

**You build connected devices. OpenBridge makes them work with everything around them.**

OpenBridge is a local-first layer that discovers the devices in a home or a company, learns what each one can
*really* do, and lets an AI compose new controls between them: vacuum buttons on a TV, a TV remote on a
watch, alerts in smart glasses. Every action needs the owner's approval and is **checked on the real device**
afterwards. It runs on Windows, Linux, macOS, Android, Android TV and Wear OS, with no runtime dependencies.

For a hardware maker, that means your product stops being an island.

---

## What your company gains

| | What you get | Why it matters |
|---|---|---|
| ✨ | **New features, without new firmware** | OpenBridge composes controls, alerts, voice and cross-device flows on top of what your device already exposes. Your customers get abilities you never shipped. |
| 🔌 | **Interoperability with other brands** | Your device works with TVs, watches, phones, routers, robots and PCs from other vendors, through one consent and verification model, not a pile of one-off integrations. |
| 🧪 | **Complete test suites and benchmarks** | Hundreds of automated tests written for your product (protocol, edge cases, failure paths), plus benchmarks on the real hardware. They keep running on every change, on three operating systems in CI. |
| 📈 | **Wider compatibility** | Your device becomes reachable over USB, Wi-Fi, BLE or through a relay device (a PC without Bluetooth can reach BLE devices through a phone), across 6 platforms and even legacy Windows machines. |
| 🖥️ | **An emulator of your device** | A faithful software model of your product, so your own developers, QA and sales can demo and test without a unit on the desk. |
| 🐞 | **Expert feedback on your API / SDK** | Detailed, reproducible reports from a real-world integrator: quirks, firmware workarounds, documentation gaps. |
| 🧾 | **A public, verified compatibility report** | Every claim is backed by an evidence record. Emulated results are labelled as emulated; only real-device runs count as physical proof. |
| ⭐ | **Visibility** | Your brand featured as a hardware partner on the project page, in the demo videos and in the documentation. |

---

## Proof, not promises: the ENGO case study

[ENGO](ENGO.md) (heads-up display smart glasses, built on Microoled's ActiveLook platform) agreed to send a
pair. **Before the glasses even arrived**, OpenBridge delivered:

| Delivered | Details |
|---|---|
| **A pro HUD emulator** | [HUD Studio](engo/19_HUD_STUDIO_EMULATOR.md): pixel-accurate 304×256 MicroOLED with Pixels / OLED / Lens views, frame inspector, metrics, session recording, PNG/GIF export and a JSON control API. |
| **The official app, driving the emulator** | The official ActiveLook Android app (development build) talks to HUD Studio over the same binary protocol, so the real phone-side code path is exercised today. |
| **38 HUD features** | From action receipts and a vacuum radar to a two-phase abort gate and live subtitles, each rendered and measured ([catalogue](engo/18_OPENBRIDGE_NEURAL_SENSORY_EXPANSION.md)). |
| **82 dedicated automated tests** | Protocol encoder, flow control, layouts, gestures, AI bridge and emulator, all green. |
| **19 technical documents** | Hardware specs, BLE protocol manual, full opcode reference, Wireshark dissector, firmware pitfalls, ergonomics benchmark ([hub](engo/README.md)). |

<p align="center">
  <img src="engo/img/hud_studio_overview.png" width="88%" alt="HUD Studio emulating ENGO glasses">
  <br><sub>HUD Studio emulating ENGO glasses. Validated in the emulator; hardware tests start when the pair arrives.</sub>
</p>

---

## How it works

<p align="center">
  <img src="../assets/readme/partner-process.svg" width="100%" alt="How a partnership works: send a device, adapter and emulator, tests and benchmarks, verified report">
</p>

**What we ask:** 📦 **hardware to keep**: donated units or a permanent loan, not a time-limited loan. Integration,
regression tests and benchmarks run on every release for the life of the integration, so the device has to stay on
the bench. Plus access to APIs, SDKs or developer documentation, and
a technical contact for integration questions.

Commercial licensing and deeper co-development are available on request.

---

## Who we are looking for

| Category | Examples |
|---|---|
| 🏠 Smart home | plugs, lights, thermostats, locks, sensors, Matter / Thread / Zigbee bridges |
| 🤖 Robots | robot vacuums and mops, lawn mowers, pool robots |
| 📺 Screens | TVs, set-top boxes, projectors, soundbars |
| ⌚ Wearables | watches, smart glasses and HUDs, rings, fitness sensors |
| 🌐 Networking | routers and ISP boxes, mesh Wi-Fi, NAS |
| 🔧 Makers and industry | ESP32 / IoT boards, industrial gateways, test benches |
| 🚗 Mobility | EV chargers, automotive and e-bike interfaces |

---

## Frequently asked questions

**Does OpenBridge change my device's behaviour or settings on its own?**
No. Nothing privileged runs without the owner's explicit approval, every action is verified by reading the
device back, and some categories are blocked by policy (for example, OpenBridge never changes router
settings).

**Does user data go to a cloud?**
No by default. The AI runs locally on the user's machine; OpenBridge ships no paid model. A hosted AI is used
only if the owner connects one by hand ([details](../AI_PROVIDERS.md)).

**Who owns the integration code?**
OpenBridge is source-available under [PolyForm Strict 1.0.0](../../LICENSE). Partner-specific licensing
(for example, shipping the adapter in your own product) is discussed case by case.

**Can our documentation stay confidential?**
Working under an NDA can be arranged: what you share confidentially stays out of the public repository, and
only what you approve is published.

---

<p align="center">
  <a href="mailto:toskaman5962@gmail.com?subject=OpenBridge%3A%20Hardware%20partnership"><img src="https://img.shields.io/badge/📩_Become_a_partner-toskaman5962@gmail.com-2dd4bf?style=for-the-badge" alt="Become a partner"></a>
  <a href="ENGO.md"><img src="https://img.shields.io/badge/Case_study-ENGO_×_OpenBridge-e7f11f?style=for-the-badge&labelColor=1a1a1a" alt="ENGO case study"></a>
</p>
<p align="center"><sub>Replies in English and French. <a href="../../README.md">Back to the project</a>.</sub></p>
