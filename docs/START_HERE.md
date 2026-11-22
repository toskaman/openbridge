# Start here

OpenBridge has a lot of documentation. You don't need most of it. Pick the path that matches why you are here.

> 🇫🇷 **En français :** commencez par le [site du projet](https://toskaman.github.io/openbridge/?lang=fr) (bouton FR/EN en
> haut), puis suivez le parcours qui vous correspond ci-dessous. La documentation technique est en anglais.

| You are… | You want to know… | Time |
|---|---|---|
| 🧭 [**A decision-maker**](#decision-makers) | What OpenBridge does, why it matters for your products, what a partnership involves | 10 min |
| 🛠️ [**An engineer**](#engineers) | How it works inside, how a device gets integrated, how safe it is | 1 hour |
| 🧪 [**In QA or testing**](#qa) | What was tested, how it was verified, how to re-run it yourself | 30 min |

---

<a id="decision-makers"></a>

## 🧭 Decision-makers

1. **See it work.** [Download it for Windows](https://github.com/toskaman/openbridge/releases/latest) (nothing to install), [try it in your browser](https://toskaman.github.io/openbridge/try.html) (a labelled simulation, 2 minutes),
   then watch the [3-minute demo on real devices](https://youtu.be/TZaxCcRmrLQ).
2. **Understand what a partner gains.** [Partner program](partners/README.md): new features without new firmware,
   interoperability, tests and benchmarks, an emulator of your device, a verified compatibility report.
3. **Look at the proof.** [ENGO case study](partners/ENGO.md): what was delivered before the hardware even arrived.
   [Compatibility](https://toskaman.github.io/openbridge/compatibility.html) and
   [benchmarks](https://toskaman.github.io/openbridge/benchmarks.html), unfavourable results included.
4. **Check the terms.** [Commercial & partner licensing](LICENSING.md#commercial--partner-licensing): your code and
   data stay yours, NDA on request. [Privacy](PRIVACY.md): nothing leaves the machine by default.
   [Security policy](../SECURITY.md).
5. **See where it is going.** [Roadmap](../ROADMAP.md) and [what's new](../CHANGELOG.md). What does not work yet is
   written down too: [known limitations](KNOWN_LIMITATIONS.md).

Something to forward internally: the [one-page partner brief (PDF)](../site/OpenBridge-Partner-Brief.pdf).
Contact: **[info@lepcpro.fr](mailto:info@lepcpro.fr?subject=OpenBridge)**.

---

<a id="engineers"></a>

## 🛠️ Engineers

**Run it first** (Windows, Linux or macOS, Python 3.14, no third-party packages):

```sh
git clone https://github.com/toskaman/openbridge.git
cd openbridge
python -m src.cli demo        # offline demo, no devices required
python -m src.server          # local interface on http://127.0.0.1:18765
```

Then read, in this order:

| Topic | Document |
|---|---|
| The big picture | [Universal device architecture](UNIVERSAL_DEVICE_ARCHITECTURE.md) |
| How devices are found | [Discovery protocols](DISCOVERY_PROTOCOLS.md) · [Bluetooth, local and remote](BLUETOOTH_LOCAL_AND_REMOTE.md) · [Device identity](DEVICE_IDENTITY_AND_DEDUPLICATION.md) |
| What a device can do | [Device capabilities](DEVICE_CAPABILITIES.md) · [Capability schema](DEVICE_CAPABILITY_SCHEMA.md) |
| Add a device | [Integrate your device](INTEGRATE_YOUR_DEVICE.md): `python -m src.cli partner new "Your Device"` · [Home Assistant bridge](HOME_ASSISTANT.md) |
| Integration examples | [Android TV adapter](ANDROID_TV_ADAPTER.md) · [Freebox](FREEBOX_INTEGRATION.md) · [Routers](ROUTER_ADAPTERS.md) · [Android companion](ANDROID_COMPANION.md) |
| A full partner integration | [ENGO technical hub](partners/engo/README.md): protocol, opcodes, layouts, emulator |
| Safety | [Relay security](RELAY_SECURITY.md) (pairing, signing, replay protection) · [Transactions and undo](TRANSACTION_AND_UNDO.md) |
| AI | [Connect your own AI or API](AI_PROVIDERS.md) · [Model usage and evaluation](MODEL_USAGE_AND_EVALUATION.md) |
| Day-to-day use | [Quickstart](QUICKSTART.md) · [CLI reference](CLI_REFERENCE.md) · [Headless deployment](HEADLESS_DEPLOYMENT.md) · [Platforms](PLATFORMS.md) · [Troubleshooting](TROUBLESHOOTING.md) |

---

<a id="qa"></a>

## 🧪 QA and test engineers

| Question | Where to look |
|---|---|
| Which devices were verified, and how? | [Hardware test matrix](HARDWARE_TEST_MATRIX.md), generated from the [evidence registry](DEVICE_EVIDENCE.json), or the filterable [Compatibility page](https://toskaman.github.io/openbridge/compatibility.html) |
| What counts as proof? | Real hardware, virtual machines and emulators are labelled apart; each run names its independent check. Emulated results never count as hardware proof. |
| Benchmarks and their method | [Benchmark status](benchmark/STATUS.md) · [Endurance baseline](benchmark/F90_ENDURANCE_BASELINE.md) · [1,000-turn evaluation](benchmark/EVAL_1000_RULES_BASELINE.md) · [Re-run manifest](benchmark/RERUN_MANIFEST.md) · [Charts](https://toskaman.github.io/openbridge/benchmarks.html) |
| Release evidence | [Release evidence](RELEASE_EVIDENCE.md) · [Stress report](STRESS_14_REPORT.md) |
| What does not work yet | [Known limitations](KNOWN_LIMITATIONS.md) |

Re-run everything yourself, no hardware needed:

```sh
python -m unittest discover -s tests   # 2,400+ tests
python -m src.cli demo                 # offline end-to-end check
python -m src.cli test smoke           # fast smoke test
```

The same suite runs in CI on Linux, Windows and macOS on every change.
