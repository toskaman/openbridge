# OpenBridge Companion 0.15 on a real phone — 27 November 2026

Phone: **Blackview BV9300 Pro** (MediaTek Helio G99 / MT6789, 12 GB RAM, Android 13), paired relay `relay-f46b…`,
USB debugging. PC: Windows, RTX 4060 Ti 16 GB. Screenshots taken over adb (`screencap`) after each step.

## What was run and seen

| Check | Result |
|---|---|
| Install 0.15.0 over 0.14.0 (same signing key) | Installed; pairing kept |
| Main screen: new Glasses / Devices / Sensors / Settings buttons, French | Shown |
| Glasses page: live-screen area, Next / Open / Back / Home, volume keys, brightness, reconnect | Shown, French; no glasses connected at test time, so the live picture stayed empty |
| Devices page | Glasses and phone-sensor cards; PC cards not tested (PC hub not running) |
| Settings page: six modules, profiles, messages filter, quiet hours, standalone mode, diagnostics, AI | Shown, French; toggles work |
| Diagnostics page | Link, relay answer times, log; export button |
| Quick settings tiles and widget | Registered by Android (`dumpsys package`, `dumpsys appwidget`) |
| AI engine (`libobai.so`, llama.cpp + whisper.cpp, arm64) | Loads; CPU features dot product and fp16 |
| General model Qwen3.5-2B (4-bit, 1.28 GB) on the phone, no network | "Quelle est la capitale de la France ?" → "La capitale de la France est Paris." (3.1 s incl. load); a recipe in 7.9 s; "Combien de pattes a une araignée ?" → "six" (**wrong**: small models get facts wrong) |
| Command model v1 (Qwen3.5-0.8B fine-tuned on the PC, q8_0, 774 MB) | "passe en mode vélo" → profile Bike (1.5 s); "baisse la luminosité" → brightness 12 (1.6 s); "turn the tv down" → not a phone order, handed to the general model ("I can't change the TV settings…") |
| Command model v3 (shipped) | "éteins la télé" → not a phone order, handed to the general model ("I can't turn a TV off…", 4.9 s; the PC does it when it is there) |
| PC → phone, new modules (`openbridge glasses module tv on`, `vacuum on`, `sensors off`) | Each switch confirmed by the Companion over the signed, encrypted relay |
| `openbridge companion ai push` | Copied the three models (2.1 GB) in about 1 min; found and fixed: adb followed `ANDROID_SERIAL` to another device and the command still said ok (now picks the only phone, or asks for `--serial`, and fails when a copy fails) |
| Standalone-mode drawing (Java panel) rendered by the PC emulator | Upright, red-green palette, inside the visible window, same rules as the PC panel |

## Training the phone's command model (PC)

`dev/ai_training/make_phone_dataset.py` → `train_lora.py --no-think --system <phone line>` (LoRA rank 16 on
Qwen/Qwen3.5-0.8B) → `eval_phone.py` on held-out templates → `export_gguf.py` (merge, convert, q8_0).

| Run | Train examples | Time | Peak VRAM | Held-out accuracy (exact JSON) |
|---|---|---|---|---|
| phone_v1 (2 epochs) | 2242 | 40 min | 1.7 GB | 95.6 % (159): every order family 100 %, questions 84.8 % (one unseen template, "turn the tv down", taken as "standalone off") |
| phone_v2 | stopped: the data gave two labels to "allume la télé" (glasses module vs the TV itself) | | | |
| phone_v3 (1 epoch; glasses menus named with "module" / "menu"; + 377 orders for other devices), **shipped** | 2566 | 32 min | 1.7 GB | 93.5 % exact JSON on 184 held-out (questions, modules, profiles, standalone 100 %); **96.2 % in effect** after the phone's checks; orders for other devices 100 % left to the PC; 6 benign slips ("begin the ride" → profile Bike, "go home" → profile Home) |

Defence in depth on the phone: standalone mode, the sport session, brightness and module switches only run when the
sentence says so (`PhoneActions.mentions`), invalid values are refused, and no profile or voice order can switch the
phone sensors (position sharing) on. The PC's voice module switch follows the same rule: "éteins la télé" stays an
order for the TV.

Visual Oracle on the PC (no phone): a photo of a STOP sign with "Qu'est-ce que c'est ?" → "Un panneau STOP. Il est
rouge. Il est octogonal." from the smallest local vision model (31 s cold, while the GPU was training).

## Not tested on hardware yet

The live mirror and standalone mode with the glasses on; the notification remote and the volume keys with the screen
off; phone GPS and a real Bluetooth sport sensor outdoors; the "OK Bridge" wake word and local dictation (need a
voice); the visual Oracle end to end (needs the camera, a vision model on the PC and the glasses).
