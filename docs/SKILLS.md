# Skills the AI creates, and that keep working without it

OpenBridge's AI is needed **once**: to turn a sentence into a new feature. After the owner approves it, the feature
is a saved **recipe** that runs with no AI model at all: from the PC, from a button on a paired device, on a schedule,
or when another device changes state. It can be exported to a file and imported on another install.

> **Status (23 Nov 2026):** the library is implemented and tested (`src/runtime/skill_library.py`), with its command line
> (`openbridge skills ...`) and [skill packs](SKILL_PACKS.md). Wiring it
> into the app and the paired devices is the next step (see [Next steps](#next-steps)).

## From a sentence to a skill

```text
"When the TV starts playing, dim the living room to 20 % and switch off the desk lamp"
        │  AI (once): sentence → recipe proposal, checked against the typed catalog
        ▼
{ trigger: TV becomes "playing",
  steps:   [ living room light → set_brightness 20, desk lamp plug → turn_off ] }
        │  owner approves (exactly this recipe; any later edit voids the approval)
        ▼
runs forever without a model: Executor → consent → read-back → receipt
```

Where proposals come from:

| Origin | How |
|---|---|
| `ai` | the command model maps a request to a recipe (the dedicated model is being trained; see [the model](#the-dedicated-model)) |
| `suggestion` | `openbridge create suggest` combines capabilities each device has **proven** (device learning) into cross-device ideas, then `Library.from_suggestion()` |
| `owner` | written or edited by hand |
| `import` | a skills file from another install, always unapproved on arrival |

## What a recipe can do

- **Triggers:** manual (a button or a command), a device state change (edge only, e.g. the TV becoming `playing`),
  or a time (`07:15` on chosen days).
- **Steps:** 1 to 8 typed actions on known devices, from a fixed list: device facts, Home Assistant actions and their
  Undo, robot vacuum commands, TV wake and sleep, Android device actions, opening a URL or setting the wallpaper on a
  PC, retro consoles. **Never** a free-form command, a PC job, or a file transfer.
- **Guards:** a run stops at the first step that is not verified; automatic triggers have a 30 s cooldown, a cap of
  20 runs per hour, and a chain guard (a device a skill just changed cannot trigger another skill for 10 s, so two
  skills cannot ping-pong).

## Running skills elsewhere than the PC

| Where | Today | How |
|---|---|---|
| **This PC** | ✅ | `Library.run()`, `tick()` for state triggers, `run_due()` once a minute for schedules |
| **A button on the watch, phone or TV** | ✅ building block | `Library.buttons()` lists approved manual skills as `{control_id, label}`; the signed remote-controls channel already carries buttons to paired Companions and their presses back. Binding a press to a skill is the next step. |
| **Another OpenBridge install** | ✅ | `export()` → signed `openbridge-skills/1` file → `import_bundle()` with a device map; imported skills are unapproved |
| **From outside the home** | ✅ with a private mesh | see below |
| **Without any PC** (a phone runs the skills) | concept | [OpenBridge without a PC](concepts/PC_LESS_OPENBRIDGE.md): a recipe is plain data with typed steps, which is what makes it portable to a phone client |

## Using OpenBridge over the internet

The OpenBridge server stays on the owner's PC, with its model. To reach it from outside:

1. **Recommended: a WireGuard mesh such as Tailscale.** Install it on the PC and on the phone, watch or laptop.
   The devices see each other on private `100.x.y.z` addresses, end-to-end encrypted, with **no port opened** on the
   router. OpenBridge treats the mesh like the local network (`100.64.0.0/10` and `*.ts.net` names are accepted,
   e.g. for a Home Assistant reached through the mesh).
2. **Never** forward a router port to the OpenBridge server or to BridgeWindows: the BridgeWindows v4 link is
   authenticated but not encrypted, and the local API is built for loopback.
3. A public relay (the "OpenBridge Server" of the PC-less concept) is a later step: identity, rendezvous and an
   end-to-end encrypted relay for devices that cannot join a mesh.

## The dedicated model

Today OpenBridge uses general-purpose local models (Llama 3.2 3B, Qwen 2.5) behind a strict typed gate. A dedicated
model, trained on OpenBridge's own commands (French and English, spoken style, typos), is in training
(`dev/ai_training/`). The test that matters is a set of hand-written requests the model never sees in training
(`dev/ai_training/novel_test.py`). Its job will grow from "pick one skill" to "propose a recipe".

## Next steps

1. Done: `openbridge skills list | show | approve | run | remove | export | import`, and ready-made
   [skill packs](SKILL_PACKS.md) (`skills packs | install-pack`). Still to do: `create suggest --save`.
2. App: a Skills page (proposals to approve, runs and receipts, enable / disable).
3. Bind remote-control buttons to skills (`skill-…` control ids → `Library.run(actor='relay:<id>')`).
4. Feed `tick()` from the Home Assistant / device watchers and call `run_due()` every minute.
5. The model proposes recipes, not only single skills (`links.create` and multi-step requests).
