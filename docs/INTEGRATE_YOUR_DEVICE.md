# Integrate your device

How a device joins OpenBridge, from the first command to recorded proof on real hardware. Written for the engineers of
a hardware partner; no prior knowledge of the codebase needed.

> **Licence.** This guide, the kit (`src/partner_kit.py`) and every file it generates are **Apache 2.0**
> ([text](../LICENSES/Apache-2.0.txt)): you may modify, keep and ship them, and the code you add is yours. The OpenBridge
> core they import stays under PolyForm Strict 1.0.0; using it commercially needs a [partner licence](partners/PARTNER_LICENSE.md).
> [Licensing overview](LICENSING.md)

> **Already in Home Assistant?** If your device has a Home Assistant integration (including Matter, Zigbee or Thread),
> it can be reached today through the [Home Assistant bridge](HOME_ASSISTANT.md). A native integration, below, adds
> what a generic bridge cannot: your full feature set, an emulator, dedicated tests and benchmarks.

## The rules every integration follows

These are what make OpenBridge safe to put between an AI and real hardware. The generated code already applies them.

1. **Typed and allowlisted.** No free-form command ever reaches your device: only named settings and commands, each
   with its allowed values.
2. **Owner consent.** Every change needs the owner's approval, once, for that action.
3. **Read back, then report.** After a change, the device is read again. “Done” is only said when the read-back agrees;
   otherwise the result is *failed* or *unverified*, never a fake success.
4. **Exact Undo when it exists.** Reversible settings record the previous value and can restore it exactly.
   Momentary commands (start, identify…) are marked irreversible.
5. **Policy beats consent.** Some actions are refused whatever the owner says (for example: firmware changes, unlocking
   a door). You decide them with us.
6. **Private by default.** Raw serials and addresses never reach the shared graph: they are salted pseudonyms.
7. **Honest status.** Emulated, simulated and real-hardware results are labelled apart. Only real-hardware runs count as
   proof.

## 1. Scaffold

```sh
python -m src.cli partner new "Acme Lamp" --category lamp
python -m unittest tests.partners.test_acme_lamp -v      # 6 tests, passing against the emulator
```

This writes five files and never overwrites anything (add `--dry-run` to only list them):

| File | What it is |
|---|---|
| `src/adapters/acme_lamp.py` | The typed adapter: `READ`, `WRITABLE`, `COMMANDS`, `POLICY`, and the transport to fill |
| `src/adapters/acme_lamp_emulator.py` | An emulator speaking the same transport, so everything runs before the hardware arrives |
| `src/fabric/acme_lamp_ingest.py` | Puts the device in the OpenBridge graph, pseudonymized, with an honest status |
| `tests/partners/test_acme_lamp.py` | Tests that pass on the emulator and must keep passing on the real unit |
| `docs/partners/acme_lamp/README.md` | Your integration checklist and validation status |

### From an API description

If your device has an HTTP API described in OpenAPI 3 (JSON), start from it instead: the settings, commands,
refusals, emulator state and tests are generated from the description.

```sh
python -m src.cli partner new "Acme Glow" --category lamp --from-openapi acme-glow-openapi.json
python -m unittest tests.partners.test_acme_glow -v      # 7 tests: every setting, command and refusal
```

No install needed: the [Integrate page](https://toskaman.github.io/openbridge/integrate.html) does the same in your
browser and gives you a zip; the description never leaves the page. Both apply the same published rules
(`src/partner_kit_api.py`), and a test checks that they write identical files:

| In the description | Becomes |
|---|---|
| A GET returning a JSON object (a "state" or "status" path first) | `READ`: the facts shown to the owner |
| A bounded field (enum, boolean, or minimum and maximum) in a PUT/PATCH/POST body that `READ` also reports | `WRITABLE`: a setting, read back, with exact Undo |
| A POST with no body, or a bounded field that `READ` does not report | `COMMANDS`: momentary, consent per command |
| A name or path about firmware, OTA, update, reset, reboot, unlock, password, Wi-Fi, delete… | `POLICY`: always refused |
| A field that looks like a secret (password, token, key) | not even read |
| Anything else (unbounded strings, path parameters, nested objects) | listed in the README with the reason |

The example used by the page and the tests is
[partners/examples/openapi.acme-glow.json](partners/examples/openapi.acme-glow.json). Review the result like any
generated code: tighten the ranges to what the device really accepts and add refusals; then continue at step 3.

## 2. Describe the device

In the adapter, fill the four tables:

```python
READ = {'power': '', 'level': '%', 'firmware': ''}                 # what the device reports
WRITABLE = {'power': ('on', 'off'), 'level': tuple(range(0, 101))}  # reversible settings
COMMANDS = {'identify': None}                                      # momentary, irreversible
POLICY = {('firmware', '*'): 'Firmware is never changed by OpenBridge.'}
```

Keep `WRITABLE` to settings you can read back exactly. Anything you cannot read back belongs in `COMMANDS`.

## 3. Connect the real transport

`AcmeLampTransport` has three methods: `read()`, `write(name, value)` and `command(name, value)`. Implement them with
your protocol (HTTP, BLE, serial, your SDK). Keep calls bounded: timeouts, response size limits, no redirects. For
examples, see the [Home Assistant bridge](../src/adapters/home_assistant.py) (HTTP) and the
[Tuya adapter](../src/adapters/tuya_local.py) (local protocol).

## 4. Make the emulator faithful

Copy the real device's ranges, delays and quirks into the emulator as you learn them. The emulator is what your QA,
your sales demos and our CI use; the [ENGO HUD Studio](partners/engo/19_HUD_STUDIO_EMULATOR.md) shows how far it can go.

## 5. Test

The generated tests cover read-back, exact Undo, refusals before anything is sent, a device that ignores a write, and
pseudonymization. Add tests for every quirk you find. Then run the same tests with the real transport.

## 6. Expose it in the app

To make the device controllable from the app and the AI, add primitives in
[`src/runtime/primitives.py`](../src/runtime/primitives.py) (a schema, consent, verification text and inverse), runners
that call your adapter, and the ingest call in [`src/fabric/discovery.py`](../src/fabric/discovery.py). The Home
Assistant bridge (`ha_set`, `ha_command`, `ha_undo`) is a complete, recent example to copy.

## 7. Record the proof

When a run passes on the real unit, record it in [`docs/DEVICE_EVIDENCE.json`](DEVICE_EVIDENCE.json): the operations,
the independent check, the limitations and the evidence files. It then appears in the
[hardware test matrix](HARDWARE_TEST_MATRIX.md) and on the public
[Compatibility page](https://toskaman.github.io/openbridge/compatibility.html).

## What you get, and what we ask

See the [partner program](partners/README.md). Questions: **[info@lepcpro.fr](mailto:info@lepcpro.fr?subject=OpenBridge%3A%20Integration)**.
